"""Stripe payments router — extracted from server.py during the P2 refactor.

Owns the Stripe integration surface:
  - Checkout Sessions (deposit + subscription flows)
  - Post-checkout state application (_apply_checkout_session)
  - Webhook handler (payments, subscriptions, identity events fan-out)
  - Billing Portal + subscription cancellation

Non-Stripe helpers (identity apply, offramp trigger) are imported from their
respective routers so this file stays focused on payment flows.

Endpoints (all mounted at /api by server.py):
  POST /stripe/checkout/deposit       — one-off USDC top-up checkout session
  POST /stripe/checkout/subscription  — Vault Pro monthly subscription checkout
  POST /stripe/sync                   — client-side settle after redirect
  POST /stripe/webhook                — Stripe event fan-out (payments + subs + identity)
  POST /stripe/portal                 — Stripe Billing Portal deep-link
  POST /stripe/cancel                 — cancel-at-period-end subscription cancel
"""
from __future__ import annotations

import hashlib
import json
import uuid
from typing import Optional

import stripe
from fastapi import APIRouter, Depends, HTTPException, Header, Request

from deps import (
    APP_PUBLIC_URL,
    STRIPE_API_KEY,
    STRIPE_WEBHOOK_SECRET,
    VAULT_PRO_PRICE_USD,
    db,
    get_current_user,
    iso,
    logger,
    now_utc,
    public_user,
)
from audit import EventType, write_event as audit_write
from models import StripeDepositIn, StripeSyncIn
from routers.offramp import trigger_kotani_offramp_for_remit
from routers.kyc import _apply_identity_verified, _apply_identity_requires_input

# Stripe library is configured module-level in server.py — no need to
# re-set stripe.api_key here (the same process share the module).

router = APIRouter()


# --- Helpers -------------------------------------------------------------
async def _get_or_create_vault_pro_price() -> str:
    """Lazy-create a recurring Stripe Price for Vault Pro, cache id in DB."""
    if not STRIPE_API_KEY:
        raise HTTPException(status_code=503, detail="Stripe not configured")
    cfg = await db.config.find_one({"_id": "stripe"})
    if cfg and cfg.get("vault_pro_price_id"):
        return cfg["vault_pro_price_id"]
    try:
        product = stripe.Product.create(name="Vault Pro", description="Premium tier: multi-sig, lower fees, priority support")
        price = stripe.Price.create(
            unit_amount=int(VAULT_PRO_PRICE_USD * 100),  # env var name is legacy; value is now in GBP
            currency="gbp",
            recurring={"interval": "month"},
            product=product.id,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Stripe error: {e}")
    await db.config.update_one(
        {"_id": "stripe"},
        {"$set": {"vault_pro_product_id": product.id, "vault_pro_price_id": price.id}},
        upsert=True,
    )
    return price.id


def _success_cancel_urls(flow: str) -> tuple[str, str]:
    base = APP_PUBLIC_URL.rstrip("/") if APP_PUBLIC_URL else "https://example.com"
    success = f"{base}/stripe-return?flow={flow}&status=success&session_id={{CHECKOUT_SESSION_ID}}"
    cancel = f"{base}/stripe-return?flow={flow}&status=cancel"
    return success, cancel


# --- Checkout ------------------------------------------------------------
@router.post("/stripe/checkout/deposit")
async def stripe_checkout_deposit(body: StripeDepositIn, user=Depends(get_current_user)):
    if not STRIPE_API_KEY:
        raise HTTPException(status_code=503, detail="Stripe not configured")
    amount_cents = int(round(body.amount_usd * 100))
    success, cancel = _success_cancel_urls("deposit")
    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": "USDC Wallet Top-up", "description": "Vaulted fiat deposit"},
                    "unit_amount": amount_cents,
                },
                "quantity": 1,
            }],
            success_url=success,
            cancel_url=cancel,
            metadata={"user_id": user["id"], "flow": "deposit", "amount_usd": str(body.amount_usd)},
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Stripe error: {e}")
    return {"checkout_url": session.url, "session_id": session.id}


@router.post("/stripe/checkout/subscription")
async def stripe_checkout_subscription(user=Depends(get_current_user)):
    if not STRIPE_API_KEY:
        raise HTTPException(status_code=503, detail="Stripe not configured")
    price_id = await _get_or_create_vault_pro_price()
    success, cancel = _success_cancel_urls("subscription")

    customer_id = (user.get("stripe") or {}).get("customer_id")
    if not customer_id:
        try:
            cust = stripe.Customer.create(email=user["email"], metadata={"user_id": user["id"]})
            customer_id = cust.id
            await db.users.update_one(
                {"id": user["id"]},
                {"$set": {"stripe.customer_id": customer_id}},
            )
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Stripe error: {e}")
    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            customer=customer_id,
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=success,
            cancel_url=cancel,
            metadata={"user_id": user["id"], "flow": "subscription", "tier": "vault_pro"},
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Stripe error: {e}")
    return {"checkout_url": session.url, "session_id": session.id, "price_id": price_id}


# --- Session application (shared between /sync and /webhook) -------------
async def _apply_checkout_session(session_obj: dict) -> dict:
    """Idempotently apply a completed Stripe session to user state. Returns summary."""
    mode = session_obj.get("mode")
    metadata = session_obj.get("metadata") or {}
    user_id = metadata.get("user_id")
    if not user_id:
        return {"applied": False, "reason": "no user_id"}
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user:
        return {"applied": False, "reason": "user not found"}

    # Idempotency: check if already processed
    existing = await db.stripe_events.find_one({"session_id": session_obj.get("id")})
    if existing:
        return {"applied": False, "already": True}

    if mode == "payment" and metadata.get("flow") == "deposit":
        if session_obj.get("payment_status") != "paid":
            return {"applied": False, "reason": "not paid"}
        amount_usd = (session_obj.get("amount_total") or 0) / 100.0
        await db.balances.update_one(
            {"user_id": user_id, "symbol": "USDC"},
            {"$inc": {"amount": amount_usd}, "$set": {"updated_at": iso(now_utc())}},
        )
        tx = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "type": "deposit",
            "category": "fiat",
            "asset": (session_obj.get("currency") or "usd").upper(),
            "amount": amount_usd,
            "fiat_value": amount_usd,
            "counterparty": "Stripe Card Top-up",
            "method": "card",
            "status": "completed",
            "receipt_id": "VLT-" + (session_obj.get("id") or "")[-8:].upper(),
            "stripe_session_id": session_obj.get("id"),
            "created_at": iso(now_utc()),
        }
        await db.transactions.insert_one(tx)
        await db.stripe_events.insert_one({"session_id": session_obj.get("id"), "kind": "deposit", "at": iso(now_utc())})
        return {"applied": True, "kind": "deposit", "amount_usd": amount_usd}

    if mode == "payment" and metadata.get("flow") == "remit_fund":
        # Fiat-funded cross-border send. We already charged the user — now
        # book the send as processing. Actual settlement to the recipient
        # happens via our off-ramp partners (Kotani Pay for KE, ops-executed
        # for others until direct integrations land). The tx is created with
        # `funding_method: stripe` so the receipt/UX can hide crypto rails.
        if session_obj.get("payment_status") != "paid":
            return {"applied": False, "reason": "not paid"}
        try:
            src_amount = float(metadata.get("source_amount") or 0)
            dst_amount = float(metadata.get("destination_amount") or 0)
            fx_rate = float(metadata.get("fx_rate") or 0)
            svc_fee_usd = float(metadata.get("vaulted_service_usd") or 0)
        except ValueError:
            return {"applied": False, "reason": "bad metadata"}

        # What the user paid (already charged by Stripe, all-in)
        total_paid_src = (session_obj.get("amount_total") or 0) / 100.0

        tx_id = str(uuid.uuid4())
        record = {
            "id": tx_id,
            "user_id": user_id,
            "type": "send",
            "category": f"Remit · {metadata.get('destination_country')}",
            "asset": (metadata.get("source_fiat") or "GBP").upper(),  # user-facing fiat asset
            "amount": src_amount,
            "fiat_value": total_paid_src,
            "counterparty": metadata.get("recipient_address") or "",
            "recipient_name": metadata.get("recipient_name") or None,
            "memo": metadata.get("memo") or None,
            "network": "Stripe",
            "tx_hash": f"stripe:{session_obj.get('id')}",  # placeholder ref
            "explorer_url": None,
            "status": "processing",  # fiat rails: settled by ops / off-ramp partners
            "service_fee_usd": svc_fee_usd,
            "gross_service_fee_usd": svc_fee_usd,
            "credit_applied_gbp": 0.0,
            "credit_balance_after_gbp": 0.0,
            "funding_method": "stripe",
            "payment_method": metadata.get("payment_method") or "card",
            "stripe_session_id": session_obj.get("id"),
            "receipt_id": "VLT-" + (session_obj.get("id") or "")[-8:].upper(),
            "created_at": iso(now_utc()),
            "remit": {
                "source_currency": (metadata.get("source_fiat") or "GBP").upper(),
                "source_amount": src_amount,
                "destination_currency": metadata.get("destination_currency"),
                "destination_amount": dst_amount,
                "destination_country": metadata.get("destination_country"),
                "destination_country_code": (metadata.get("destination_code") or "").upper(),
                "destination_flag": metadata.get("destination_flag"),
                "chain": None,  # hidden from user — fiat rails
                "fx_rate": fx_rate,
                "receive_via": metadata.get("receive_via"),
            },
        }
        await db.transactions.insert_one(record)
        record.pop("_id", None)
        await db.stripe_events.insert_one({
            "session_id": session_obj.get("id"), "kind": "remit_fund", "at": iso(now_utc()),
        })

        # Audit as a remit success — same event type as crypto path so
        # analytics + compliance reports treat both funding methods uniformly.
        user_doc = await db.users.find_one({"id": user_id}, {"_id": 0})
        user_kyc = (user_doc or {}).get("kyc") or {}
        user_sanctions = user_kyc.get("sanctions") or {}
        try:
            await audit_write(db, EventType.REMIT_SEND_SUCCESS, user=user_doc, data={
                "tx_id": tx_id,
                "tx_hash": record["tx_hash"],
                "chain": None,
                "funding_method": "stripe",
                "payment_method": record["payment_method"],
                "source_currency": record["remit"]["source_currency"],
                "source_amount": record["remit"]["source_amount"],
                "destination_country": record["remit"]["destination_country"],
                "destination_currency": record["remit"]["destination_currency"],
                "destination_amount": record["remit"]["destination_amount"],
                "recipient_address_hash": hashlib.sha256((record["counterparty"] or "").lower().encode()).hexdigest()[:12],
                "recipient_name_hash": hashlib.sha256((record.get("recipient_name") or "").strip().lower().encode()).hexdigest()[:12] if record.get("recipient_name") else None,
                "service_fee_usd": record["service_fee_usd"],
                "fiat_value_src": total_paid_src,
                "tier_at_send": user_kyc.get("tier"),
                "sanctions_state_at_send": {
                    "matched": user_sanctions.get("matched", False),
                    "degraded": user_sanctions.get("degraded", True),
                    "degraded_reason": user_sanctions.get("degraded_reason"),
                },
            })
        except Exception as e:  # noqa: BLE001
            logger.warning("remit_fund audit_write failed: %s", e)

        # === Auto-trigger Kotani Pay M-Pesa off-ramp for Kenya sends ===
        # Non-fatal: any Kotani failure leaves the Stripe charge in place
        # and the tx in "processing" so ops can retry. Mock mode returns
        # SUCCESS immediately, so mock-mode receipts render "settled".
        kotani_result: dict = {}
        try:
            if (metadata.get("destination_code") or "").upper() == "KE":
                kotani_result = await trigger_kotani_offramp_for_remit(record)
                # Reload the record so the returned tx has the fresh kotani state
                fresh = await db.transactions.find_one({"id": record["id"]}, {"_id": 0})
                if fresh:
                    record = fresh
        except Exception as e:  # noqa: BLE001
            logger.warning("kotani offramp trigger failed for tx %s: %s", tx_id, e)
            kotani_result = {"error": str(e)[:200]}

        return {"applied": True, "kind": "remit_fund", "tx": record, **kotani_result}

    if mode == "subscription":
        sub_id = session_obj.get("subscription")
        cust_id = session_obj.get("customer")
        # Fetch subscription for accurate status
        status_val = "active"
        period_end = None
        if sub_id and STRIPE_API_KEY:
            try:
                sub = stripe.Subscription.retrieve(sub_id)
                status_val = sub.get("status", "active")
                period_end = sub.get("current_period_end")
            except Exception:
                pass
        await db.users.update_one(
            {"id": user_id},
            {"$set": {
                "stripe.customer_id": cust_id,
                "subscription": {
                    "tier": "vault_pro",
                    "stripe_subscription_id": sub_id,
                    "status": status_val,
                    "current_period_end": period_end,
                },
            }},
        )
        await db.stripe_events.insert_one({"session_id": session_obj.get("id"), "kind": "subscription", "at": iso(now_utc())})
        return {"applied": True, "kind": "subscription", "status": status_val}

    return {"applied": False, "reason": "unhandled mode"}


@router.post("/stripe/sync")
async def stripe_sync(body: StripeSyncIn, user=Depends(get_current_user)):
    """Client polls this after returning from Stripe Checkout to settle state."""
    if not STRIPE_API_KEY:
        raise HTTPException(status_code=503, detail="Stripe not configured")
    try:
        session = stripe.checkout.Session.retrieve(body.session_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Session not found: {e}")
    if (session.get("metadata") or {}).get("user_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Session not for this user")
    result = await _apply_checkout_session(dict(session))
    u = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    return {"session_status": session.get("status"), "payment_status": session.get("payment_status"), "applied": result, "user": public_user(u)}


@router.post("/stripe/webhook")
async def stripe_webhook(request: Request, stripe_signature: Optional[str] = Header(None, alias="Stripe-Signature")):
    payload = await request.body()
    if STRIPE_WEBHOOK_SECRET and stripe_signature:
        try:
            event = stripe.Webhook.construct_event(payload, stripe_signature, STRIPE_WEBHOOK_SECRET)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid webhook: {e}")
    else:
        try:
            event = json.loads(payload.decode())
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid payload")
    if event["type"] == "checkout.session.completed":
        await _apply_checkout_session(event["data"]["object"])
    elif event["type"] in ("customer.subscription.updated", "customer.subscription.deleted"):
        sub = event["data"]["object"]
        await db.users.update_one(
            {"subscription.stripe_subscription_id": sub.get("id")},
            {"$set": {"subscription.status": sub.get("status"), "subscription.current_period_end": sub.get("current_period_end")}},
        )
    elif event["type"] == "identity.verification_session.verified":
        await _apply_identity_verified(event["data"]["object"])
    elif event["type"] == "identity.verification_session.requires_input":
        await _apply_identity_requires_input(event["data"]["object"])
    elif event["type"] == "identity.verification_session.canceled":
        # User canceled mid-flow — leave the tier alone, just clear the pending state
        user_id = ((event["data"]["object"].get("metadata") or {}).get("user_id"))
        if user_id:
            await db.users.update_one(
                {"id": user_id},
                {"$set": {"kyc.identity_verification_status": "canceled"}},
            )
            await audit_write(
                db,
                EventType.KYC_CANCELED,
                user_id=user_id,
                data={"session_id": event["data"]["object"].get("id")},
            )
    return {"status": "ok"}


@router.post("/stripe/portal")
async def stripe_portal(user=Depends(get_current_user)):
    """Returns a Stripe Billing Portal URL so the user can manage their subscription."""
    if not STRIPE_API_KEY:
        raise HTTPException(status_code=503, detail="Stripe not configured")
    customer_id = (user.get("stripe") or {}).get("customer_id")
    if not customer_id:
        raise HTTPException(status_code=400, detail="No billing customer; subscribe first.")
    base = APP_PUBLIC_URL.rstrip("/") if APP_PUBLIC_URL else "https://example.com"
    try:
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=f"{base}/vault-pro",
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Stripe portal error: {e}")
    return {"url": session.url}


@router.post("/stripe/cancel")
async def stripe_cancel_subscription(user=Depends(get_current_user)):
    if not STRIPE_API_KEY:
        raise HTTPException(status_code=503, detail="Stripe not configured")
    sub_id = (user.get("subscription") or {}).get("stripe_subscription_id")
    if not sub_id:
        raise HTTPException(status_code=400, detail="No active subscription")
    try:
        stripe.Subscription.modify(sub_id, cancel_at_period_end=True)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Stripe error: {e}")
    await db.users.update_one({"id": user["id"]}, {"$set": {"subscription.status": "canceled"}})
    return {"status": "canceled"}
