"""Off-ramp routes (Kotani Pay M-Pesa) — USDC → KES payouts to phone numbers.

Automatically kicks in when a fiat-funded remit lands with destination Kenya
(KE). The Stripe payment is booked first (funds land in Vaulted's balance);
then Kotani Pay disburses KES directly to the recipient's M-Pesa wallet.
Runs in MOCK mode until KOTANI_API_KEY is set in .env — flips to LIVE
automatically on backend restart with a real key.

Docs: https://documentation.kotanipay.com/v3/flows/offramp-flow

`trigger_kotani_offramp_for_remit` is also imported by server.py's Stripe
checkout completion handler (_apply_checkout_session).
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request

import kotani
from audit import EventType, write_event as audit_write
from deps import APP_PUBLIC_URL, db, get_current_user, iso, logger, now_utc, require_admin
from models import OfframpQuoteIn

router = APIRouter()


def _offramp_callback_url() -> str:
    base = (APP_PUBLIC_URL or "https://vaulted-app.onrender.com").rstrip("/")
    return f"{base}/api/offramp/callback"


async def trigger_kotani_offramp_for_remit(remit_tx: dict) -> dict:
    """Called from _apply_checkout_session for KE-destined fiat-funded
    remits. Books the Kotani off-ramp, updates the transaction row with
    the Kotani reference id, and audits every terminal state.

    Returns a summary dict for the /stripe/sync response. Failures are
    non-fatal — the user still sees a successful send (money charged);
    ops can retry the off-ramp from admin dashboard.
    """
    remit_ctx = (remit_tx.get("remit") or {})
    if remit_ctx.get("destination_country_code") != "KE" and remit_ctx.get("destination_currency") != "KES":
        return {"kotani": {"skipped": True, "reason": "destination not KES/M-Pesa"}}
    phone = (remit_tx.get("counterparty") or "").strip()
    recipient_name = (remit_tx.get("recipient_name") or "").strip() or "Vaulted Recipient"
    src_amount_usd = float(remit_tx.get("fiat_value") or 0.0)
    # Rough USD conversion from source fiat — we already have the tx's
    # source in USD via the remit_quote earlier so this is a passable
    # approximation for the off-ramp instruction.
    kotani_res = await kotani.create_offramp(
        phone_number=phone,
        recipient_name=recipient_name,
        amount_usdc=src_amount_usd,
        estimated_kes=float(remit_ctx.get("destination_amount") or 0.0),
        callback_url=_offramp_callback_url(),
        country="KE",
        currency="KES",
        mobile_money_network="MPESA",
    )
    data = (kotani_res or {}).get("data") or {}
    ref_id = data.get("referenceId")
    kotani_status = data.get("status", "UNKNOWN")

    # Persist the Kotani ref on the transaction so status polls + webhook
    # correlation both work.
    await db.transactions.update_one(
        {"id": remit_tx["id"]},
        {"$set": {
            "kotani": {
                "reference_id": ref_id,
                "status": kotani_status,
                "mode": "live" if kotani.live_mode() else "mock",
                "initiated_at": iso(now_utc()),
                "callback_url": _offramp_callback_url(),
            },
            # Success-status transactions: flip receipt status to "settled"
            # for mock (deterministic) — live mode waits for webhook.
            **({"status": "settled"} if (kotani_status == "SUCCESS" and not kotani.live_mode()) else {}),
        }},
    )

    audit_event = EventType.OFFRAMP_MPESA_INITIATED
    if not kotani_res.get("success"):
        audit_event = EventType.OFFRAMP_MPESA_FAILED
    try:
        user_doc = await db.users.find_one({"id": remit_tx["user_id"]}, {"_id": 0})
        await audit_write(db, audit_event, user=user_doc, data={
            "tx_id": remit_tx["id"],
            "kotani_reference_id": ref_id,
            "kotani_status": kotani_status,
            "kotani_mode": "live" if kotani.live_mode() else "mock",
            "phone_masked": kotani.mask_phone(phone),
            "amount_kes": remit_ctx.get("destination_amount"),
            "amount_usd": src_amount_usd,
        })
    except Exception as e:  # noqa: BLE001
        logger.warning("kotani audit_write failed: %s", e)

    return {"kotani": {"reference_id": ref_id, "status": kotani_status, "mode": "live" if kotani.live_mode() else "mock"}}


@router.get("/offramp/health")
async def offramp_health(_admin=Depends(require_admin)):
    """Admin-only sanity check — confirms Kotani auth works (or that we're
    intentionally in mock mode). Not for end users."""
    res = await kotani.health()
    return {"kotani": res, "config": kotani.diagnostic_info()}


@router.post("/offramp/mpesa/quote")
async def offramp_mpesa_quote(body: OfframpQuoteIn, user=Depends(get_current_user)):
    """Show the user what KES they'll get for a given USD amount. Used
    by the frontend as a secondary rate check next to our own remit quote —
    if Kotani's rate diverges > 3%, we warn the user."""
    res = await kotani.offramp_rate(
        from_token="USDC",
        to_currency=body.to_currency,
        amount_usd=body.amount_usd,
    )
    return {
        "kotani": res,
        "mode": "live" if kotani.live_mode() else "mock",
    }


@router.get("/offramp/mpesa/status/{reference_id}")
async def offramp_mpesa_status(reference_id: str, user=Depends(get_current_user)):
    """Poll a single off-ramp. Also cross-checks the tx belongs to the
    caller (or is admin) to prevent enumeration."""
    tx = await db.transactions.find_one(
        {"$or": [
            {"id": reference_id},
            {"kotani.reference_id": reference_id},
        ]},
        {"_id": 0},
    )
    if not tx:
        raise HTTPException(status_code=404, detail="No such off-ramp reference")
    if tx.get("user_id") != user["id"]:
        # Allow admins through
        if not user.get("is_admin"):
            raise HTTPException(status_code=403, detail="Not your transaction")
    kotani_ref = (tx.get("kotani") or {}).get("reference_id") or reference_id
    res = await kotani.offramp_status(kotani_ref)
    return {"kotani": res, "tx": tx}


@router.post("/offramp/callback")
async def offramp_callback(request: Request):
    """Webhook endpoint — Kotani Pay POSTs terminal state here after fiat
    disbursement. Signature verification is enforced when
    KOTANI_WEBHOOK_SECRET is configured.

    Terminal states we handle:
    - SUCCESS: mark tx settled, record M-Pesa receipt
    - FAILED: mark tx failed, ops will follow up
    - REFUNDED / REFUND_FAILED: informational only for the tx timeline
    """
    payload = await request.body()
    signature = request.headers.get("X-Kotani-Signature")
    event_type = request.headers.get("X-Kotani-Event", "callback")

    if not kotani.verify_webhook_signature(payload, signature):
        await audit_write(db, EventType.OFFRAMP_WEBHOOK_INVALID_SIGNATURE, user=None, data={
            "event_type": event_type,
            "sig_present": bool(signature),
        })
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        event = json.loads(payload.decode())
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}") from e

    # Kotani sends either the raw tx object (unsigned mode) or a
    # {event, data} envelope (signed mode). Handle both.
    if isinstance(event, dict) and isinstance(event.get("data"), dict):
        data = event["data"]
    elif isinstance(event, dict):
        # Unsigned mode — the whole payload is the tx object
        data = event
    else:
        raise HTTPException(status_code=400, detail="Payload must be a JSON object")

    ref_id = data.get("referenceId") or data.get("reference_id")
    kotani_status = (data.get("status") or "").upper()
    if not ref_id or not kotani_status:
        raise HTTPException(status_code=400, detail="Payload missing referenceId or status")

    tx = await db.transactions.find_one({"kotani.reference_id": ref_id}, {"_id": 0})
    if not tx:
        # Kotani retries webhooks; a stray one is not fatal — log + 200.
        logger.warning("[kotani-webhook] no local tx for referenceId=%s", ref_id)
        return {"ok": True, "matched": False}

    updates: dict = {"kotani.status": kotani_status, "kotani.updated_at": iso(now_utc())}
    audit_event = None
    if kotani_status == "SUCCESS":
        updates["status"] = "settled"
        updates["kotani.mpesa_receipt"] = (data.get("receipt") or {}).get("mpesaReceipt")
        updates["kotani.settled_at"] = data.get("settledAt") or iso(now_utc())
        audit_event = EventType.OFFRAMP_MPESA_SUCCESS
    elif kotani_status == "FAILED":
        updates["status"] = "failed"
        updates["kotani.failure_reason"] = data.get("failureReason") or data.get("message")
        audit_event = EventType.OFFRAMP_MPESA_FAILED
    elif kotani_status in ("REFUNDED", "REFUND_PENDING"):
        updates["status"] = "refunded" if kotani_status == "REFUNDED" else "processing"
        audit_event = EventType.OFFRAMP_MPESA_REFUNDED

    await db.transactions.update_one({"id": tx["id"]}, {"$set": updates})

    if audit_event:
        user_doc = await db.users.find_one({"id": tx["user_id"]}, {"_id": 0})
        try:
            await audit_write(db, audit_event, user=user_doc, data={
                "tx_id": tx["id"],
                "kotani_reference_id": ref_id,
                "kotani_status": kotani_status,
                "mpesa_receipt": (data.get("receipt") or {}).get("mpesaReceipt"),
            })
        except Exception as e:  # noqa: BLE001
            logger.warning("kotani webhook audit_write failed: %s", e)

    return {"ok": True, "matched": True, "status": kotani_status}
