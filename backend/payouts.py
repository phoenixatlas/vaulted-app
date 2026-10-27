"""Payout orchestrator — picks the active off-ramp partner (Flutterwave,
Kotani Pay or Yellow Card), enforces Beta test-money mode, and degrades gracefully to a
simulated payout / live-FX estimate when a partner is unavailable.

Settings live in `db.config` under `_id: "payouts"`:
    provider        "kotani" | "yellowcard"
    beta_test_mode  bool — when True, no real money moves:
                      * partner calls only hit SANDBOX endpoints
                      * if a partner rejects/blocks us, the payout is simulated
                      * Stripe checkouts refuse to run on a live (sk_live_) key
"""
from __future__ import annotations

import os
import uuid
from typing import Optional

from fastapi import HTTPException

import flutterwave
import kotani
import yellowcard
from deps import STRIPE_API_KEY, db, iso, logger, now_utc
from delivery import safe_notify
from remit import refresh_fx_rates

PROVIDERS = ("flutterwave", "kotani", "yellowcard")
PROVIDER_LABEL = {"flutterwave": "Flutterwave", "kotani": "Kotani Pay", "yellowcard": "Yellow Card"}
SUPPORTED_COUNTRIES = {"flutterwave": flutterwave.SUPPORTED, "kotani": {"KE"}, "yellowcard": set(yellowcard.PAYOUT_RAILS)}
_CLIENTS = {"flutterwave": flutterwave, "yellowcard": yellowcard}

# Estimated-rate spread/fee used when no partner quote is available.
_EST_SPREAD = 0.008
_EST_FEE_PCT = 0.015


def _env_bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None or v.strip() == "":
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


async def get_settings() -> dict:
    doc = await db.config.find_one({"_id": "payouts"}, {"_id": 0}) or {}
    provider = doc.get("provider") or os.environ.get("PAYOUT_PROVIDER", "flutterwave")
    if provider not in PROVIDERS:
        provider = "flutterwave"
    return {
        "provider": provider,
        "beta_test_mode": bool(doc["beta_test_mode"]) if "beta_test_mode" in doc else _env_bool("BETA_TEST_MODE", True),
        "updated_at": doc.get("updated_at"),
    }


async def update_settings(provider: Optional[str], beta_test_mode: Optional[bool], admin_email: str) -> dict:
    patch: dict = {"updated_at": iso(now_utc()), "updated_by": admin_email}
    if provider is not None:
        if provider not in PROVIDERS:
            raise HTTPException(status_code=400, detail=f"provider must be one of {PROVIDERS}")
        patch["provider"] = provider
    if beta_test_mode is not None:
        patch["beta_test_mode"] = bool(beta_test_mode)
    await db.config.update_one({"_id": "payouts"}, {"$set": patch}, upsert=True)
    return await get_settings()


def stripe_mode() -> str:
    if not STRIPE_API_KEY:
        return "off"
    return "live" if STRIPE_API_KEY.startswith(("sk_live", "rk_live")) else "test"


async def assert_test_money_ok() -> None:
    """Block real card charges while Beta test-money mode is on."""
    cfg = await get_settings()
    if cfg["beta_test_mode"] and stripe_mode() == "live":
        raise HTTPException(
            status_code=409,
            detail="Card payments are paused during the Vaulted beta — no real money can be charged yet.",
        )


def _provider_live(provider: str) -> bool:
    return kotani.live_mode() if provider == "kotani" else _CLIENTS[provider].live_mode()


def _provider_sandbox(provider: str) -> bool:
    return "sandbox" in (kotani._base_url() if provider == "kotani" else _CLIENTS[provider].base_url())


# ---- Nigeria bank list / account check (active bank-capable partner) ----------
async def _bank_client():
    cfg = await get_settings()
    return flutterwave if cfg["provider"] == "flutterwave" and flutterwave.live_mode() else yellowcard


async def list_ng_banks() -> dict:
    return await (await _bank_client()).list_banks("NG")


async def resolve_ng_account(account_number: str, bank_id: str) -> dict:
    return await (await _bank_client()).resolve_bank_account(account_number, bank_id)


async def reconcile_flutterwave() -> int:
    """Poll in-flight Flutterwave transfers and settle/fail them (no webhook needed)."""
    done = 0
    rows = await db.transactions.find(
        {"payout.provider": "flutterwave", "payout.mode": "live", "status": {"$nin": ["settled", "failed"]}},
        {"_id": 0, "id": 1, "payout.reference_id": 1},
    ).limit(25).to_list(25)
    for r in rows:
        st = await flutterwave.payout_status(r["payout"]["reference_id"])
        if not st["success"]:
            continue
        bucket = flutterwave.classify_status(st["status"])
        update = {"payout.status": (st["status"] or "").upper(), "payout.updated_at": iso(now_utc())}
        if bucket in ("settled", "failed"):
            update["status"] = bucket
        res = await db.transactions.update_one({"id": r["id"], "status": {"$nin": ["settled", "failed"]}}, {"$set": update})
        if bucket == "settled" and res.modified_count:
            done += 1
            await safe_notify(r["id"])
    return done


# ---- Rates ------------------------------------------------------------------
async def estimated_offramp(currency: str, amount_usd: float) -> Optional[dict]:
    """Live-FX based estimate (open.er-api cache) in the Kotani envelope shape."""
    fx = await refresh_fx_rates(db)
    mid = (fx.get("rates") or {}).get(currency.upper())
    if not mid:
        return None
    rate = round(mid * (1 - _EST_SPREAD), 4)
    gross = round(amount_usd * rate, 2)
    fee = round(gross * _EST_FEE_PCT, 2)
    return {"success": True, "message": "Estimated from live FX", "data": {
        "id": None, "from": "USDC", "to": currency.upper(), "value": str(rate),
        "cryptoAmount": amount_usd, "fiatAmount": gross, "transactionAmount": round(gross - fee, 2), "fee": fee,
    }}


async def estimated_onramp(currency: str, fiat_amount: float) -> Optional[dict]:
    fx = await refresh_fx_rates(db)
    mid = (fx.get("rates") or {}).get(currency.upper())
    if not mid:
        return None
    rate = round(mid * (1 + 0.010), 4)
    fee = round(fiat_amount * 0.025, 2)
    return {"success": True, "message": "Estimated from live FX", "data": {
        "id": None, "from": currency.upper(), "to": "USDC", "value": str(rate),
        "fiatAmount": fiat_amount, "cryptoAmount": round(fiat_amount / rate, 6), "fee": fee,
    }}


async def partner_offramp_quote(currency: str, amount_usd: float) -> tuple[dict, str, str]:
    """Return (kotani-shaped envelope, mode, provider). mode ∈ live|mock|estimated."""
    cfg = await get_settings()
    provider = cfg["provider"]
    if provider == "yellowcard":
        if yellowcard.live_mode():
            r = await yellowcard.get_rate(currency)
            if r.get("success") and r.get("rate"):
                gross = round(amount_usd * r["rate"], 2)
                return ({"success": True, "data": {"id": r.get("rate_id"), "value": str(r["rate"]),
                                                   "fiatAmount": gross, "fee": 0}}, "live", provider)
    elif provider == "kotani":
        res = await kotani.offramp_rate(from_token="USDC", to_currency=currency, crypto_amount=amount_usd)
        if res.get("success"):
            return res, ("live" if kotani.live_mode() else "mock"), provider
    est = await estimated_offramp(currency, amount_usd)
    return (est or {"success": False, "data": {}}), "estimated", provider


# ---- Payout dispatch ----------------------------------------------------------
async def _simulate(record: dict, provider: str, reason: str) -> dict:
    payout = {
        "provider": provider,
        "provider_label": PROVIDER_LABEL[provider],
        "mode": "simulated",
        "reference_id": "sim_" + uuid.uuid4().hex[:16],
        "status": "SUCCESSFUL",
        "reason": reason,
        "initiated_at": iso(now_utc()),
    }
    await db.transactions.update_one({"id": record["id"]}, {"$set": {"payout": payout, "status": "settled"}})
    await safe_notify(record["id"])
    return payout


def _sender_kyc(user: dict) -> dict:
    kyc = (user or {}).get("kyc") or {}
    return {
        "name": user.get("name") or "Vaulted Customer",
        "country": (kyc.get("country") or "GB").upper(),
        "phone": kyc.get("phone") or "+441234567890",
        "email": user.get("email") or "",
        "address": kyc.get("address") or "London, United Kingdom",
        "dob": kyc.get("dob") or "01/01/1990",
        "idNumber": kyc.get("id_number") or "VAULTED-" + (user.get("id") or "")[:8],
        "idType": kyc.get("id_type") or "passport",
    }


async def dispatch_payout_for_remit(record: dict) -> dict:
    """Pay the recipient of a fiat-funded remit via the active partner.
    Never raises — the user's payment already succeeded."""
    cfg = await get_settings()
    provider, beta = cfg["provider"], cfg["beta_test_mode"]
    country = ((record.get("remit") or {}).get("destination_country_code") or "").upper()

    if country not in SUPPORTED_COUNTRIES[provider]:
        if beta:
            return {"payout": await _simulate(record, provider, f"{country} not yet supported by {PROVIDER_LABEL[provider]}")}
        return {"payout": {"skipped": True, "reason": f"{country} not supported by {provider}"}}

    if beta and _provider_live(provider) and not _provider_sandbox(provider):
        return {"payout": await _simulate(record, provider, "Beta test mode — production partner disabled")}

    if provider == "flutterwave":
        return {"payout": await _dispatch_flutterwave(record, country, beta)}

    if provider == "kotani":
        from routers.offramp import trigger_kotani_offramp_for_remit
        res = (await trigger_kotani_offramp_for_remit(record)).get("kotani") or {}
        ok = not res.get("skipped") and res.get("status") not in ("UNKNOWN", "FAILED")
        if not ok:
            if beta:
                return {"payout": await _simulate(record, provider, f"Kotani unavailable: {res.get('reason') or res.get('status')}")}
            failed = {"provider": provider, "failed": True, "reason": res.get("reason") or res.get("status"),
                      "initiated_at": iso(now_utc())}
            await db.transactions.update_one({"id": record["id"]}, {"$set": {"payout": failed}})
            return {"payout": failed}
        payout = {"provider": provider, "provider_label": PROVIDER_LABEL[provider], **res, "initiated_at": iso(now_utc())}
        await db.transactions.update_one({"id": record["id"]}, {"$set": {"payout": payout}})
        return {"payout": payout}

    # Yellow Card
    if not yellowcard.live_mode() and not beta:
        # No keys and real-money mode: never pretend the recipient was paid.
        failed = {"provider": provider, "failed": True, "reason": "Yellow Card keys not configured",
                  "initiated_at": iso(now_utc())}
        await db.transactions.update_one({"id": record["id"]}, {"$set": {"payout": failed}})
        return {"payout": failed}
    user = await db.users.find_one({"id": record["user_id"]}, {"_id": 0}) or {}
    remit_ctx = record.get("remit") or {}
    amount_usd = await _usd_amount(record)
    res = await yellowcard.create_payout(
        sequence_id=record["id"], country=country, amount_usd=amount_usd,
        recipient_name=record.get("recipient_name") or "Vaulted Recipient",
        recipient_account=(record.get("counterparty") or "").replace(" ", ""),
        sender=_sender_kyc(user),
        network_id=(record.get("recipient_bank") or {}).get("id"),
    )
    if not res.get("success"):
        logger.warning("[payouts] yellowcard payout failed for %s: %s", record["id"], res.get("error"))
        if beta:
            return {"payout": await _simulate(record, provider, "Yellow Card unavailable")}
        failed = {"provider": provider, "failed": True, "reason": str(res.get("error"))[:300],
                  "initiated_at": iso(now_utc())}
        await db.transactions.update_one({"id": record["id"]}, {"$set": {"payout": failed}})
        return {"payout": failed}

    mode = "mock" if res.get("mock") else "live"
    bucket = yellowcard.classify_status(res.get("status"))
    payout = {
        "provider": provider, "provider_label": PROVIDER_LABEL[provider], "mode": mode,
        "reference_id": res["reference_id"], "status": (res.get("status") or "").upper(),
        "fiat_currency": remit_ctx.get("destination_currency"), "initiated_at": iso(now_utc()),
    }
    update = {"payout": payout}
    if bucket == "settled" and mode == "mock":
        update["status"] = "settled"
    await db.transactions.update_one({"id": record["id"]}, {"$set": update})
    if update.get("status") == "settled":
        await safe_notify(record["id"])
    return {"payout": payout}


async def _dispatch_flutterwave(record: dict, country: str, beta: bool) -> dict:
    remit_ctx = record.get("remit") or {}
    res = await flutterwave.create_payout(
        reference="vlt" + "".join(ch for ch in record["id"] if ch.isalnum())[:28], country=country,
        amount_local=float(remit_ctx.get("destination_amount") or 0),
        recipient_name=record.get("recipient_name") or "Vaulted Recipient",
        recipient_account=record.get("counterparty") or "",
        bank_code=(record.get("recipient_bank") or {}).get("id"),
    )
    if not res.get("success"):
        logger.warning("[payouts] flutterwave payout failed for %s: %s", record["id"], res.get("error"))
        if beta:
            return await _simulate(record, "flutterwave", f"Flutterwave unavailable: {res.get('error')}")
        failed = {"provider": "flutterwave", "failed": True, "reason": str(res.get("error"))[:300],
                  "initiated_at": iso(now_utc())}
        await db.transactions.update_one({"id": record["id"]}, {"$set": {"payout": failed}})
        return failed
    mode = "mock" if res.get("mock") else "live"
    payout = {
        "provider": "flutterwave", "provider_label": "Flutterwave", "mode": mode,
        "sandbox": flutterwave.is_sandbox(), "reference_id": res["reference_id"],
        "status": (res.get("status") or "").upper(), "fiat_currency": remit_ctx.get("destination_currency"),
        "initiated_at": iso(now_utc()),
    }
    update = {"payout": payout}
    if mode == "mock":
        update["status"] = "settled"
    await db.transactions.update_one({"id": record["id"]}, {"$set": update})
    if mode == "mock":
        await safe_notify(record["id"])
    return payout


async def _usd_amount(record: dict) -> float:
    remit_ctx = record.get("remit") or {}
    src = (remit_ctx.get("source_currency") or "USD").upper()
    amt = float(remit_ctx.get("source_amount") or record.get("amount") or 0)
    if src == "USD":
        return amt
    rates = (await refresh_fx_rates(db)).get("rates") or {}
    return round(amt / rates[src], 2) if rates.get(src) else amt
