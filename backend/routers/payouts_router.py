"""Payout partner routes — app config, admin provider switch/health, and the
Yellow Card webhook."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

import kotani
import payouts
import yellowcard
from deps import db, get_current_user, iso, logger, now_utc, require_admin

router = APIRouter()


class PayoutSettingsIn(BaseModel):
    provider: Optional[str] = None
    beta_test_mode: Optional[bool] = None


class ResolveAccountIn(BaseModel):
    account_number: str = Field(min_length=10, max_length=10, pattern=r"^\d{10}$")
    bank_id: str = Field(min_length=1, max_length=120)


@router.get("/payouts/banks")
async def payout_banks(country: str = "NG", _user=Depends(get_current_user)):
    """Banks a recipient can be paid into (Nigeria). Yellow Card networks
    when keys are set, a built-in list of major Nigerian banks otherwise."""
    if country.upper() != "NG":
        raise HTTPException(status_code=400, detail="Bank list is only available for Nigeria")
    return await yellowcard.list_banks("NG")


@router.post("/payouts/resolve-account")
async def payout_resolve_account(body: ResolveAccountIn, _user=Depends(get_current_user)):
    """Look up the account holder's name before money is sent (NUBAN check)."""
    res = await yellowcard.resolve_bank_account(body.account_number, body.bank_id)
    if not res.get("success"):
        raise HTTPException(status_code=404, detail=res.get("message") or "Account not found")
    return {"account_name": res["account_name"], "mode": res["mode"]}


@router.get("/app/config")
async def app_config():
    """Public flags the mobile app reads on launch (beta banner etc.)."""
    cfg = await payouts.get_settings()
    return {
        "beta_test_mode": cfg["beta_test_mode"],
        "payout_provider": cfg["provider"],
        "payout_provider_label": payouts.PROVIDER_LABEL[cfg["provider"]],
        "stripe_mode": payouts.stripe_mode(),
    }


async def _probe(provider: str) -> dict:
    """One cheap authenticated call to prove the partner accepts our key."""
    if provider == "kotani":
        if not kotani.live_mode():
            return {"ok": False, "detail": "No API key — running in test mode"}
        r = await kotani.offramp_rate(from_token="USDC", to_currency="KES", crypto_amount=1.0)
        msg = ((r.get("data") or {}).get("message")) or r.get("message")
        return {"ok": bool(r.get("success")), "detail": "Rates OK" if r.get("success") else str(msg)[:200]}
    if not yellowcard.live_mode():
        return {"ok": False, "detail": "No API key — running in test mode"}
    r = await yellowcard.get_rate("KES")
    return {"ok": bool(r.get("success")), "detail": "Rates OK" if r.get("success") else str(r.get("error"))[:200]}


@router.get("/admin/payouts")
async def admin_payouts(_admin=Depends(require_admin)):
    cfg = await payouts.get_settings()
    return {
        "settings": cfg,
        "stripe_mode": payouts.stripe_mode(),
        "providers": {
            "kotani": {"label": "Kotani Pay", "config": kotani.diagnostic_info(), "probe": await _probe("kotani"),
                       "countries": sorted(payouts.SUPPORTED_COUNTRIES["kotani"])},
            "yellowcard": {"label": "Yellow Card", "config": yellowcard.diagnostic_info(), "probe": await _probe("yellowcard"),
                           "countries": sorted(payouts.SUPPORTED_COUNTRIES["yellowcard"])},
        },
    }


@router.put("/admin/payouts")
async def admin_update_payouts(body: PayoutSettingsIn, admin=Depends(require_admin)):
    return {"settings": await payouts.update_settings(body.provider, body.beta_test_mode, admin.get("email", ""))}


@router.post("/payouts/yellowcard/webhook")
async def yellowcard_webhook(request: Request):
    raw = await request.body()
    if not yellowcard.verify_webhook_signature(raw, request.headers.get("X-YC-Signature")):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    try:
        import json
        event = json.loads(raw)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid JSON") from e

    seq = event.get("sequenceId")
    status = event.get("status")
    await db.yellowcard_webhook_log.insert_one({
        "received_at": iso(now_utc()), "event": event.get("event"), "sequence_id": seq,
        "status": status, "payment_id": event.get("id"),
    })
    if not seq:
        return {"ok": True, "handled": "ignored"}
    bucket = yellowcard.classify_status(status)
    update = {"payout.status": (status or "").upper(), "payout.updated_at": iso(now_utc())}
    if bucket in ("settled", "failed"):
        update["status"] = bucket
    # Out-of-order guard: never let a late event overwrite a terminal state.
    res = await db.transactions.update_one(
        {"id": seq, "payout.provider": "yellowcard", "status": {"$nin": ["settled", "failed"]}},
        {"$set": update},
    )
    logger.info("[yellowcard-webhook] seq=%s status=%s matched=%s", seq, status, res.matched_count)
    if bucket == "settled" and res.modified_count:
        from delivery import safe_notify
        await safe_notify(seq)
    return {"ok": True, "handled": bucket}
