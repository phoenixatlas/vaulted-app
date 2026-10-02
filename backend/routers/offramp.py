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
    remits. Executes the full Kotani v3 flow:
      1) create (or reuse) the mobile-money customer for the recipient
      2) request an offramp rate quote (locks in a `rateId`)
      3) create the offramp transaction with `referenceId=remit_tx.id`
      4) persist the Kotani `referenceId` + `escrowAddress` on the tx
    Failures at any step are non-fatal — the Stripe payment already
    succeeded; ops can retry the off-ramp from admin dashboard.
    """
    remit_ctx = (remit_tx.get("remit") or {})
    dest_country = (remit_ctx.get("destination_country_code") or "").upper()
    dest_currency = (remit_ctx.get("destination_currency") or "").upper()
    if dest_country != "KE" and dest_currency != "KES":
        return {"kotani": {"skipped": True, "reason": "destination not KES/M-Pesa"}}

    phone = (remit_tx.get("counterparty") or "").strip()
    recipient_name = (remit_tx.get("recipient_name") or "").strip() or "Vaulted Recipient"
    # Split recipient name best-effort for Kotani KYC fields.
    parts = recipient_name.split(" ", 1)
    first_name = parts[0]
    last_name = parts[1] if len(parts) > 1 else ""

    # Amount handling: Kotani wants the crypto amount we intend to send.
    # Our remits are USD-denominated (USDC ≈ USD), so use fiat_value as the
    # USDC amount. The remit_quote already produced a KES estimate for UX.
    src_amount_usd = float(remit_tx.get("fiat_value") or 0.0)

    # --- Step 1: create / find customer ---------------------------------
    cust_res = await kotani.create_mobile_money_customer(
        phone_number=phone,
        country_code="KE",
        network="MPESA",
        first_name=first_name,
        last_name=last_name,
        account_name=recipient_name,
    )
    customer_key = kotani.extract_customer_key(cust_res)
    if not customer_key:
        logger.warning("[kotani] customer create failed: %s", cust_res)
        return {"kotani": {"skipped": True, "reason": "customer create failed", "raw": cust_res}}

    # --- Step 2: get a rate quote ---------------------------------------
    rate_res = await kotani.offramp_rate(
        from_token="USDC",
        to_currency="KES",
        crypto_amount=src_amount_usd,
    )
    rate_id = kotani.extract_rate_id(rate_res)
    if not rate_id:
        logger.warning("[kotani] rate quote failed: %s", rate_res)
        return {"kotani": {"skipped": True, "reason": "rate quote failed", "raw": rate_res}}

    # --- Step 3: create the offramp -------------------------------------
    kotani_res = await kotani.create_offramp(
        crypto_amount=src_amount_usd,
        currency="KES",
        chain="BASE",   # Vaulted uses Base USDC by default
        token="USDC",
        reference_id=remit_tx["id"],
        customer_key=customer_key,
        rate_id=rate_id,
        callback_url=_offramp_callback_url(),
    )
    data = (kotani_res or {}).get("data") or {}
    ref_id = data.get("referenceId") or remit_tx["id"]
    kotani_status = (data.get("status") or "UNKNOWN").upper()
    escrow_address = data.get("escrowAddress") or data.get("depositAddress")

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
                "customer_key": customer_key,
                "rate_id": rate_id,
                "escrow_address": escrow_address,
                "fiat_currency": data.get("fiatCurrency") or "KES",
                "fiat_amount": data.get("fiatAmount"),
            },
            # Success-status transactions: flip receipt status to "settled"
            # for mock (deterministic) — live mode waits for webhook.
            # Accept both legacy "SUCCESS" (from our mock) and Kotani v3's
            # canonical "SUCCESSFUL" so the UX doesn't regress when we
            # switch to real sandbox responses.
            **({"status": "settled"} if (
                kotani_status in kotani.TERMINAL_SUCCESS and not kotani.live_mode()
            ) else {}),
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
            "customer_key": customer_key,
            "rate_id": rate_id,
        })
    except Exception as e:  # noqa: BLE001
        logger.warning("kotani audit_write failed: %s", e)

    return {"kotani": {
        "reference_id": ref_id,
        "status": kotani_status,
        "mode": "live" if kotani.live_mode() else "mock",
        "escrow_address": escrow_address,
    }}


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
        crypto_amount=body.amount_usd,
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
    """Webhook endpoint — Kotani Pay POSTs transaction + settlement events
    here. Handles both v3 signed envelopes (`{event, data, signature}`)
    and legacy direct-callback mode (raw tx object in body).

    Events we actively handle:
      - transaction.offramp.status.updated   → remit → M-Pesa payouts
      - transaction.onramp.status.updated    → inbound Africa → UK/EU
      - transaction.deposit.status.updated   → integrator fiat wallet credits
      - transaction.withdrawal.status.updated
      - refund.completed / refund.failed     → informational only

    Signature verification is enforced when KOTANI_WEBHOOK_SECRET is set.
    Every delivery is logged to `kotani_webhook_log` (last 100 kept) so the
    admin webhook-echo endpoint can show operators exactly what Kotani is
    sending — invaluable when debugging dashboard config.
    """
    payload = await request.body()
    signature = request.headers.get("X-Kotani-Signature")
    event_type_header = request.headers.get("X-Kotani-Event")
    integrator_header = request.headers.get("X-Kotani-Integrator")

    sig_valid = kotani.verify_webhook_signature(payload, signature)

    # Always persist the raw delivery first so admin can see even
    # malformed / failed-sig attempts. Capped at 100 rows.
    try:
        await db.kotani_webhook_log.insert_one({
            "received_at": iso(now_utc()),
            "signature_present": bool(signature),
            "signature_valid": sig_valid,
            "event_header": event_type_header,
            "integrator_header": integrator_header,
            "raw_body": payload.decode("utf-8", errors="replace")[:4000],
        })
        count = await db.kotani_webhook_log.count_documents({})
        if count > 100:
            oldest = await db.kotani_webhook_log.find({}, {"_id": 1}) \
                .sort("received_at", 1).limit(count - 100).to_list(length=count - 100)
            if oldest:
                await db.kotani_webhook_log.delete_many(
                    {"_id": {"$in": [o["_id"] for o in oldest]}}
                )
    except Exception as e:  # noqa: BLE001
        logger.warning("[kotani-webhook] log insert failed: %s", e)

    if not sig_valid:
        await audit_write(db, EventType.OFFRAMP_WEBHOOK_INVALID_SIGNATURE, user=None, data={
            "event_type": event_type_header or "unknown",
            "sig_present": bool(signature),
        })
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        envelope = json.loads(payload.decode())
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}") from e

    if not isinstance(envelope, dict):
        raise HTTPException(status_code=400, detail="Payload must be a JSON object")

    # Determine the event name + inner data, accepting both shapes:
    #   signed:    {event, data: {...}, signature}
    #   unsigned:  {referenceId, status, ...}  — the whole body IS the data
    if isinstance(envelope.get("data"), dict):
        event_name = envelope.get("event") or event_type_header or ""
        data = envelope["data"]
    else:
        event_name = event_type_header or ""
        data = envelope

    # Fire-and-forget audit of every well-formed delivery so admins can
    # trace what Kotani sent even for events we don't act on.
    try:
        await audit_write(db, EventType.OFFRAMP_WEBHOOK_RECEIVED, user=None, data={
            "event_name": event_name,
            "reference_id": kotani.pick(data, "reference_id"),
            "status": data.get("status"),
        })
    except Exception as e:  # noqa: BLE001
        logger.warning("[kotani-webhook] receive audit failed: %s", e)

    event_lower = (event_name or "").lower()

    # --- Dispatch -------------------------------------------------------
    if event_lower.startswith("transaction.offramp") or event_lower in ("", "callback"):
        return await _handle_offramp_event(data)
    if event_lower.startswith("transaction.onramp"):
        return await _handle_onramp_event(data)
    if event_lower.startswith("transaction.deposit"):
        return await _handle_deposit_event(data)
    if event_lower.startswith("transaction.withdrawal"):
        return await _handle_withdrawal_event(data)
    if event_lower.startswith("refund."):
        return await _handle_refund_event(event_lower, data)
    if event_lower.startswith("kyc.") or event_lower.startswith("settlement."):
        # Informational-only for now; already logged above.
        return {"ok": True, "handled": "logged", "event": event_name}

    # Unknown event — don't 400 (Kotani will retry forever); log + 200.
    logger.info("[kotani-webhook] unknown event %r, body-head=%r", event_name,
                payload[:200])
    return {"ok": True, "handled": "unknown", "event": event_name}


async def _handle_offramp_event(data: dict) -> dict:
    """Terminal state for a crypto → fiat (M-Pesa) disbursement."""
    ref_id = kotani.pick(data, "reference_id")
    kotani_status = (data.get("status") or "").upper()
    if not ref_id or not kotani_status:
        raise HTTPException(status_code=400, detail="Payload missing referenceId or status")

    tx = await db.transactions.find_one({"kotani.reference_id": ref_id}, {"_id": 0})
    if not tx:
        logger.warning("[kotani-webhook] no local tx for referenceId=%s", ref_id)
        return {"ok": True, "matched": False, "reference_id": ref_id}

    bucket = kotani.classify_status(kotani_status)
    updates: dict = {"kotani.status": kotani_status, "kotani.updated_at": iso(now_utc())}
    audit_event = None

    if bucket == "settled":
        updates["status"] = "settled"
        receipt = kotani.extract_mpesa_receipt(data)
        if receipt:
            updates["kotani.mpesa_receipt"] = receipt
        updates["kotani.settled_at"] = data.get("settledAt") or iso(now_utc())
        updates["kotani.fiat_transaction_amount"] = data.get("fiatTransactionAmount")
        updates["kotani.transaction_hash"] = data.get("transactionHash")
        audit_event = EventType.OFFRAMP_MPESA_SUCCESS
    elif bucket == "failed":
        updates["status"] = "failed"
        updates["kotani.failure_reason"] = (
            data.get("transactionError")
            or data.get("errorMessage")
            or (data.get("onchainError") or {}).get("message")
            or data.get("message")
        )
        audit_event = EventType.OFFRAMP_MPESA_FAILED
    elif bucket in ("refunded", "refund_pending"):
        updates["status"] = "refunded" if bucket == "refunded" else "processing"
        audit_event = EventType.OFFRAMP_MPESA_REFUNDED

    await db.transactions.update_one({"id": tx["id"]}, {"$set": updates})

    if audit_event:
        user_doc = await db.users.find_one({"id": tx["user_id"]}, {"_id": 0})
        try:
            await audit_write(db, audit_event, user=user_doc, data={
                "tx_id": tx["id"],
                "kotani_reference_id": ref_id,
                "kotani_status": kotani_status,
                "mpesa_receipt": kotani.extract_mpesa_receipt(data),
            })
        except Exception as e:  # noqa: BLE001
            logger.warning("kotani webhook audit_write failed: %s", e)

    return {"ok": True, "matched": True, "status": kotani_status, "bucket": bucket}


async def _handle_onramp_event(data: dict) -> dict:
    """Terminal state for a fiat → crypto (inbound Africa→UK/EU) ramp."""
    ref_id = kotani.pick(data, "reference_id")
    status = (data.get("status") or "").upper()
    if not ref_id:
        return {"ok": True, "matched": False, "reason": "no referenceId"}

    bucket = kotani.classify_status(status)
    tx = await db.transactions.find_one({"onramp.reference_id": ref_id}, {"_id": 0})

    updates = {
        "onramp.status": status,
        "onramp.deposit_status": data.get("depositStatus"),
        "onramp.onchain_status": data.get("onchainStatus"),
        "onramp.transaction_hash": data.get("transactionHash"),
        "onramp.updated_at": iso(now_utc()),
    }
    audit_event = None
    if bucket == "settled":
        updates["status"] = "settled"
        audit_event = EventType.ONRAMP_SUCCESS
    elif bucket == "failed":
        updates["status"] = "failed"
        updates["onramp.failure_reason"] = (
            (data.get("error") or {}).get("message")
            or data.get("errorMessage")
            or data.get("transactionError")
        )
        audit_event = EventType.ONRAMP_FAILED

    if tx:
        await db.transactions.update_one({"id": tx["id"]}, {"$set": updates})

    if audit_event:
        user_doc = await db.users.find_one({"id": (tx or {}).get("user_id")}, {"_id": 0}) if tx else None
        try:
            await audit_write(db, audit_event, user=user_doc, data={
                "tx_id": (tx or {}).get("id"),
                "kotani_reference_id": ref_id,
                "kotani_status": status,
            })
        except Exception as e:  # noqa: BLE001
            logger.warning("kotani onramp audit_write failed: %s", e)

    return {"ok": True, "matched": bool(tx), "status": status, "bucket": bucket}


async def _handle_deposit_event(data: dict) -> dict:
    """Integrator fiat wallet was credited (settlement-side)."""
    ref_id = kotani.pick(data, "reference_id")
    status = (data.get("status") or "").upper()
    logger.info("[kotani-webhook] deposit event ref=%s status=%s amount=%s",
                ref_id, status, data.get("transaction_amount") or data.get("amount"))
    return {"ok": True, "event": "deposit", "status": status, "reference_id": ref_id}


async def _handle_withdrawal_event(data: dict) -> dict:
    """Integrator fiat wallet was debited (payout-side)."""
    ref_id = kotani.pick(data, "reference_id")
    status = (data.get("status") or "").upper()
    logger.info("[kotani-webhook] withdrawal event ref=%s status=%s", ref_id, status)
    return {"ok": True, "event": "withdrawal", "status": status, "reference_id": ref_id}


async def _handle_refund_event(event_name: str, data: dict) -> dict:
    """Record refund outcomes against the original offramp tx so the
    user-facing timeline shows 'refunded' instead of 'failed'."""
    ref_id = kotani.pick(data, "reference_id")
    if not ref_id:
        return {"ok": True, "matched": False}
    tx = await db.transactions.find_one({"kotani.reference_id": ref_id}, {"_id": 0})
    if not tx:
        return {"ok": True, "matched": False, "reference_id": ref_id}

    if event_name == "refund.completed":
        updates = {
            "status": "refunded",
            "kotani.refund_status": "SUCCESSFUL",
            "kotani.refund_tx_hash": data.get("refundTransactionHash"),
            "kotani.refund_amount": data.get("refundAmount"),
        }
    elif event_name == "refund.failed":
        updates = {
            "kotani.refund_status": "FAILED",
            "kotani.refund_error": data.get("error"),
            "kotani.refund_retries": data.get("totalRetries"),
        }
    else:
        updates = {"kotani.refund_status": event_name}

    await db.transactions.update_one({"id": tx["id"]}, {"$set": updates})

    try:
        user_doc = await db.users.find_one({"id": tx["user_id"]}, {"_id": 0})
        await audit_write(db, EventType.OFFRAMP_MPESA_REFUNDED, user=user_doc, data={
            "tx_id": tx["id"],
            "kotani_reference_id": ref_id,
            "refund_event": event_name,
        })
    except Exception as e:  # noqa: BLE001
        logger.warning("[kotani-webhook] refund audit_write failed: %s", e)

    return {"ok": True, "matched": True, "event": event_name}
