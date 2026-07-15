"""Kotani Pay v3 client — off-ramp USDC → KES via M-Pesa.

Auto-detects mock vs live mode based on `KOTANI_API_KEY`:
- If the env var is empty, missing, or explicitly set to the sentinel
  "MOCKED", every call returns deterministic fake data that mirrors
  the real Kotani v3 response envelope. Nothing is billed.
- The moment a real key is set in /app/backend/.env and the process
  restarts, live_mode() flips to True and every helper hits the real
  sandbox / production endpoints.

Design notes:
- All responses match the real `{success, message, data}` envelope
  documented at https://documentation.kotanipay.com/v3/quickstart.
- All amounts are decimal strings (Kotani serialises as strings to
  avoid float rounding on their side).
- We only implement the sub-set our remit flow needs:
    - health()               → sanity check
    - offramp_rate()         → GBP → KES quote (mock uses our own FX)
    - create_offramp()       → book a KES payout to a phone number
    - offramp_status()       → poll a single tx
- Webhook signature verification is provided but only meaningful once
  KOTANI_WEBHOOK_SECRET is set. Absent secret → we accept the call
  and just log it (dev / mock mode behaviour).

Env vars (all optional; sensible sandbox defaults):
    KOTANI_API_KEY           — bearer token. Absent → mock mode.
    KOTANI_BASE_URL          — override for production
                                (default: https://sandbox-api.kotanipay.io)
    KOTANI_WEBHOOK_SECRET    — HMAC secret for X-Kotani-Signature check
    KOTANI_MOCK              — force mock even with a real key (test override)
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

logger = logging.getLogger("vaulted.kotani")

# ---- Environment (lazy) ---------------------------------------------------
# IMPORTANT: server.py imports this module BEFORE it calls load_dotenv(...),
# so we cannot read env vars at import time — the .env file hasn't been
# parsed yet and we'd cache empty strings forever. Every accessor below
# does a fresh os.environ.get() so a real KOTANI_API_KEY landing in
# /app/backend/.env at runtime is picked up on the next call without a
# process restart. Cheap: os.environ is a dict lookup.

# Sentinel used in .env so people can see the intent without committing
# a real key. Treated identically to an empty key.
_MOCK_SENTINELS = {"", "MOCKED", "PLACEHOLDER", "REPLACE_ME", "TODO"}

_TIMEOUT = httpx.Timeout(15.0, connect=8.0)


def _api_key() -> str:
    return os.environ.get("KOTANI_API_KEY", "").strip()


def _base_url() -> str:
    return os.environ.get("KOTANI_BASE_URL", "https://sandbox-api.kotanipay.io").rstrip("/")


def _webhook_secret() -> str:
    return os.environ.get("KOTANI_WEBHOOK_SECRET", "").strip()


def _force_mock() -> bool:
    return os.environ.get("KOTANI_MOCK", "").strip().lower() in ("1", "true", "yes", "on")


def live_mode() -> bool:
    """True when a real API key is present and mock isn't forced."""
    if _force_mock():
        return False
    key = _api_key()
    return key.upper() not in _MOCK_SENTINELS


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def mask_phone(phone: str) -> str:
    """+254712345678 → +254 71• ••• •678 (never log full digits)."""
    if not phone:
        return ""
    digits = "".join(c for c in phone if c.isdigit() or c == "+")
    if len(digits) < 6:
        return digits
    return digits[:5] + "•••••" + digits[-3:]


# ---- Mock responses --------------------------------------------------------
# Every one of these mirrors the real Kotani v3 `{success, message, data}`
# envelope so that swapping to live mode requires zero downstream changes.

def _mock_reference_id() -> str:
    """Kotani ref-id format is a UUID; we prefix with 'kp_mock_' so audit
    grepping can differentiate mock vs live rows after go-live."""
    return "kp_mock_" + uuid.uuid4().hex[:20]


def _mock_health() -> dict:
    return {
        "success": True,
        "message": "Health check (mocked)",
        "data": {"status": "ok", "mode": "mock", "note": "no KOTANI_API_KEY set"},
    }


def _mock_offramp_rate(from_token: str, to_currency: str, amount_usd: float) -> dict:
    """Approximate GBP → KES using the same conservative FX Vaulted uses
    elsewhere (matches compliance module rate at 0.80 for GBP→USD).
    Real Kotani rates fluctuate ~2% either side."""
    # Approximate market rates (Q3 2026 avg)
    RATE_TABLE = {
        "KES": 143.5,   # 1 USD ≈ 143.5 KES
        "GHS": 15.8,
        "NGN": 1585.0,
        "UGX": 3720.0,
        "TZS": 2610.0,
        "ZAR": 18.4,
    }
    rate = RATE_TABLE.get(to_currency.upper(), 100.0)
    kotani_spread = 0.008  # 0.8% spread — realistic for sandbox
    effective_rate = round(rate * (1 - kotani_spread), 4)
    fiat_amount = round(amount_usd * effective_rate, 2)
    return {
        "success": True,
        "message": "Rate quote (mocked)",
        "data": {
            "fromToken": from_token,
            "fromAmount": f"{amount_usd:.6f}",
            "toCurrency": to_currency.upper(),
            "toAmount": f"{fiat_amount:.2f}",
            "rate": str(effective_rate),
            "spread": str(kotani_spread),
            "quoteExpiresAt": _now_iso(),
            "_mock": True,
        },
    }


def _mock_create_offramp(payload: dict) -> dict:
    ref = _mock_reference_id()
    return {
        "success": True,
        "message": "Offramp created (mocked)",
        "data": {
            "referenceId": ref,
            "status": "PENDING",
            "depositAddress": "0xMOCKescrow0000000000000000000000000000000",
            "network": payload.get("chain") or "USDC_BASE",
            "fromToken": payload.get("token") or "USDC",
            "fromAmount": payload.get("amount"),
            "toCurrency": payload.get("currency") or "KES",
            "toAmount": payload.get("estimatedFiatAmount"),
            "recipient": {
                "phoneNumber": mask_phone(payload.get("phoneNumber", "")),
                "network": payload.get("mobileMoneyNetwork") or "MPESA",
                "country": payload.get("country") or "KE",
            },
            "callbackUrl": payload.get("callbackUrl"),
            "createdAt": _now_iso(),
            "_mock": True,
            "_note": "Simulated: no crypto will be transferred, no KES delivered.",
        },
    }


def _mock_offramp_status(reference_id: str) -> dict:
    # Mock progresses PENDING → SUCCESS after 8 seconds since ref was minted.
    # We can't inspect real time from a static ref, so always return SUCCESS
    # for mock refs older than "now" — effectively immediate settlement in dev.
    status = "SUCCESS" if reference_id.startswith("kp_mock_") else "PENDING"
    return {
        "success": True,
        "message": "Transaction status (mocked)",
        "data": {
            "referenceId": reference_id,
            "status": status,
            "toCurrency": "KES",
            "toAmount": "8650.89",
            "settledAt": _now_iso() if status == "SUCCESS" else None,
            "receipt": {
                "mpesaReceipt": "MPESA-MOCK-" + reference_id[-8:].upper() if status == "SUCCESS" else None,
                "smsSentTo": "+254•••••••••",
            },
            "_mock": True,
        },
    }


# ---- Live HTTP calls -------------------------------------------------------
async def _get(path: str, params: dict | None = None) -> dict:
    url = f"{_base_url()}{path}"
    headers = {"Authorization": f"Bearer {_api_key()}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=_TIMEOUT) as cx:
        r = await cx.get(url, headers=headers, params=params or {})
        if r.status_code >= 400:
            logger.warning("[kotani] GET %s -> %s: %s", path, r.status_code, r.text[:200])
            return {"success": False, "message": f"http {r.status_code}", "data": r.json() if r.headers.get("content-type", "").startswith("application/json") else {"raw": r.text[:400]}}
        return r.json()


async def _post(path: str, body: dict) -> dict:
    url = f"{_base_url()}{path}"
    headers = {"Authorization": f"Bearer {_api_key()}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=_TIMEOUT) as cx:
        r = await cx.post(url, headers=headers, json=body)
        if r.status_code >= 400:
            logger.warning("[kotani] POST %s -> %s: %s", path, r.status_code, r.text[:200])
            return {"success": False, "message": f"http {r.status_code}", "data": r.json() if r.headers.get("content-type", "").startswith("application/json") else {"raw": r.text[:400]}}
        return r.json()


# ---- Public API (async, mock-aware) ---------------------------------------
async def health() -> dict:
    if not live_mode():
        return _mock_health()
    return await _get("/health")


async def offramp_rate(
    *,
    from_token: str = "USDC",
    to_currency: str = "KES",
    amount_usd: float,
) -> dict:
    """Ask Kotani for a live GBP-equivalent KES rate for a USDC amount.
    In mock mode we compute it locally with a realistic spread so quotes
    look plausible on the frontend."""
    if not live_mode():
        return _mock_offramp_rate(from_token, to_currency, amount_usd)
    return await _get(
        "/api/v3/rates/offramp-rate",
        params={"fromToken": from_token, "toCurrency": to_currency.upper(), "fromAmount": f"{amount_usd:.6f}"},
    )


async def create_offramp(
    *,
    phone_number: str,
    recipient_name: str,
    amount_usdc: float,
    estimated_kes: float,
    callback_url: str,
    chain: str = "USDC_BASE",
    country: str = "KE",
    currency: str = "KES",
    mobile_money_network: str = "MPESA",
) -> dict:
    """Create an off-ramp transaction: USDC → M-Pesa KES.

    Returns Kotani envelope with `data.referenceId` — persist that in the
    remit transaction record so webhook + status-poll can correlate."""
    payload = {
        "phoneNumber": phone_number,
        "recipientName": recipient_name,
        "amount": f"{amount_usdc:.6f}",
        "token": "USDC",
        "chain": chain,
        "country": country,
        "currency": currency,
        "mobileMoneyNetwork": mobile_money_network,
        "estimatedFiatAmount": f"{estimated_kes:.2f}",
        "callbackUrl": callback_url,
    }
    if not live_mode():
        return _mock_create_offramp(payload)
    return await _post("/api/v3/offramp", payload)


async def offramp_status(reference_id: str) -> dict:
    """Poll a single off-ramp's terminal state."""
    if not live_mode():
        return _mock_offramp_status(reference_id)
    return await _get(f"/api/v3/offramp/{reference_id}")


# ---- Webhook signature verification ---------------------------------------
def verify_webhook_signature(payload: bytes, signature_header: Optional[str]) -> bool:
    """Verify X-Kotani-Signature is a valid HMAC-SHA256 of the raw body
    using the shared webhook secret. Returns True in dev / mock mode when
    no secret is configured (matches Kotani's un-signed delivery mode).
    """
    secret = _webhook_secret()
    if not secret:
        # No secret configured — Kotani sends payload unsigned per docs
        # (delivery mode differs based on dashboard config).
        return True
    if not signature_header:
        logger.warning("[kotani-webhook] missing X-Kotani-Signature header")
        return False
    expected = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()
    # Constant-time compare
    return hmac.compare_digest(expected, signature_header.strip())


# ---- Utility: expose config to admin diagnostics --------------------------
def diagnostic_info() -> dict:
    """Safe-to-log summary of the current config. Returned by
    /api/admin/compliance/health so ops can see mode + endpoint without
    exposing the key."""
    key = _api_key()
    return {
        "mode": "live" if live_mode() else "mock",
        "base_url": _base_url(),
        "api_key_configured": bool(key) and key.upper() not in _MOCK_SENTINELS,
        "webhook_secret_configured": bool(_webhook_secret()),
        "mock_override_env": _force_mock(),
    }
