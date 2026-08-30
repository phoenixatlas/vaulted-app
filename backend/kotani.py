"""Kotani Pay v3 client — off-ramp crypto → fiat (M-Pesa & friends).

Auto-detects mock vs live mode based on `KOTANI_API_KEY`:
- If the env var is empty, missing, or set to a sentinel ("MOCKED",
  "PLACEHOLDER", "REPLACE_ME", "TODO"), every call returns deterministic
  fake data that mirrors the real Kotani v3 response envelope. Nothing is
  billed and nothing hits Kotani's servers.
- The moment a real key is set in /app/backend/.env and the process
  restarts (or the next env re-read for lazy accessors), live_mode() flips
  to True and every helper hits the real sandbox / production endpoints.

v3 Flow (as of June 2026):
  1) POST /api/v3/customer/mobile-money   — register the recipient once
      → returns `customer_key`
  2) POST /api/v3/rate/offramp             — quote crypto→fiat rate
      → returns `data.id` (`rateId`) + fiatAmount + fee etc.
  3) POST /api/v3/offramp                  — book the disbursement
      body: {cryptoAmount, currency, chain, token, referenceId,
             mobileMoneyReceiver: {customerKey}, callbackUrl, rateId}
      → returns `data.referenceId` + `escrowAddress` (where the customer
        must send crypto). Kotani POSTs terminal state to `callbackUrl`.
  4) GET /api/v3/offramp/:referenceId      — poll a single tx

Docs (verified 2026-06):
  - https://documentation.kotanipay.com/v3/quickstart
  - https://documentation.kotanipay.com/v3/flows/offramp-flow
  - https://documentation.kotanipay.com/v3/api-reference/rates/offramp-rate
  - https://documentation.kotanipay.com/v3/api-reference/offramp/create
  - https://documentation.kotanipay.com/v3/api-reference/customers/mobile-money/create

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

_TIMEOUT = httpx.Timeout(20.0, connect=8.0)


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
    """Kotani ref-id is a UUID; we prefix with 'kp_mock_' so audit
    grepping can differentiate mock vs live rows after go-live."""
    return "kp_mock_" + uuid.uuid4().hex[:20]


def _mock_customer_key() -> str:
    return "cust_mock_" + uuid.uuid4().hex[:16]


def _mock_rate_id() -> str:
    return "rate_mock_" + uuid.uuid4().hex[:16]


def _mock_health() -> dict:
    return {
        "success": True,
        "message": "Health check (mocked)",
        "data": {"status": "ok", "mode": "mock", "note": "no KOTANI_API_KEY set"},
    }


def _mock_create_customer(payload: dict) -> dict:
    return {
        "success": True,
        "message": "Customer has been successfully created (mocked)",
        "data": {
            "phone_number": payload.get("phone_number", ""),
            "country_code": payload.get("country_code", "KE"),
            "id": _mock_customer_key(),
            "network": payload.get("network", "MPESA"),
            "customer_key": _mock_customer_key(),
            "account_name": payload.get("account_name") or (
                (payload.get("first_name", "") + " " + payload.get("last_name", "")).strip()
                or "Mock Recipient"
            ),
            "integrator": "vaulted-mock",
            "first_name": payload.get("first_name", ""),
            "last_name": payload.get("last_name", ""),
            "_mock": True,
        },
    }


# Rate table: 1 USDC (≈ 1 USD) → fiat. Approximate Q3 2026 market rates.
_MOCK_RATE_TABLE = {
    "KES": 143.5,
    "GHS": 15.8,
    "NGN": 1585.0,
    "UGX": 3720.0,
    "TZS": 2610.0,
    "ZAR": 18.4,
    "EUR": 0.92,
    "GBP": 0.79,
    "USD": 1.0,
}


def _mock_offramp_rate(from_token: str, to_currency: str, crypto_amount: float) -> dict:
    rate = _MOCK_RATE_TABLE.get(to_currency.upper(), 100.0)
    spread = 0.008  # 0.8% — realistic sandbox spread
    effective_rate = round(rate * (1 - spread), 4)
    fiat_amount = round(crypto_amount * effective_rate, 2)
    fee = round(fiat_amount * 0.02, 2)  # 2% fee mock
    return {
        "success": True,
        "message": "Available exchange rate. (mocked)",
        "data": {
            "id": _mock_rate_id(),
            "from": from_token.upper(),
            "to": to_currency.upper(),
            "value": str(effective_rate),
            "cryptoAmount": crypto_amount,
            "fiatAmount": fiat_amount,
            "transactionAmount": round(fiat_amount - fee, 2),
            "fee": fee,
            "walletDebitAmount": fiat_amount,
            "_mock": True,
        },
    }


def _mock_create_offramp(payload: dict) -> dict:
    ref = payload.get("referenceId") or _mock_reference_id()
    return {
        "success": True,
        "message": "Offramp has been successfully created (mocked)",
        "data": {
            "referenceId": ref,
            "status": "PENDING",
            "onchainStatus": "AWAITING_DEPOSIT",
            "escrowAddress": "0xMOCKescrow0000000000000000000000000000000",
            "senderAddress": payload.get("senderAddress") or "",
            "cryptoAmount": payload.get("cryptoAmount"),
            "fiatAmount": None,
            "fiatCurrency": payload.get("currency", "KES"),
            "chain": payload.get("chain", "BASE"),
            "token": payload.get("token", "USDC"),
            "rate": {},
            "usingIntegratedWallet": False,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "_mock": True,
            "_note": "Simulated: no crypto will be transferred, no fiat delivered.",
        },
    }


def _mock_offramp_status(reference_id: str) -> dict:
    status = "SUCCESS" if reference_id.startswith("kp_mock_") else "PENDING"
    return {
        "success": True,
        "message": "Transaction status (mocked)",
        "data": {
            "referenceId": reference_id,
            "status": status,
            "onchainStatus": "CONFIRMED" if status == "SUCCESS" else "AWAITING_DEPOSIT",
            "fiatCurrency": "KES",
            "fiatAmount": 8650.89,
            "settledAt": _now_iso() if status == "SUCCESS" else None,
            "receipt": {
                "mpesaReceipt": "MPESA-MOCK-" + reference_id[-8:].upper() if status == "SUCCESS" else None,
            },
            "_mock": True,
        },
    }


# ---- Live HTTP calls -------------------------------------------------------
def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_api_key()}",
        "Content-Type": "application/json",
    }


async def _get(path: str, params: dict | None = None) -> dict:
    url = f"{_base_url()}{path}"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as cx:
        r = await cx.get(url, headers=_headers(), params=params or {})
        return _envelope(r, "GET", path)


async def _post(path: str, body: dict) -> dict:
    url = f"{_base_url()}{path}"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as cx:
        r = await cx.post(url, headers=_headers(), json=body)
        return _envelope(r, "POST", path)


def _envelope(r: httpx.Response, method: str, path: str) -> dict:
    ctype = (r.headers.get("content-type") or "").lower()
    is_json = ctype.startswith("application/json")
    if r.status_code >= 400:
        logger.warning("[kotani] %s %s -> %s: %s", method, path, r.status_code, r.text[:300])
        return {
            "success": False,
            "message": f"http {r.status_code}",
            "data": (r.json() if is_json else {"raw": r.text[:600]}),
        }
    if not is_json:
        # Kotani always returns JSON on 2xx; defensively parse.
        return {"success": True, "message": "ok", "data": {"raw": r.text[:600]}}
    return r.json()


# ---- Public API (async, mock-aware) ---------------------------------------
async def health() -> dict:
    if not live_mode():
        return _mock_health()
    return await _get("/health")


# --- Customers -------------------------------------------------------------
# Kotani country codes are ISO-2 (KE, GH, NG, ...). Networks are enums —
# for Kenya use MPESA; Ghana MTN/AIRTEL/VODAFONE; Nigeria depends.
def _default_network_for_country(country_code: str) -> str:
    cc = (country_code or "").upper()[:2]
    return {
        "KE": "MPESA",
        "GH": "MTN",
        "NG": "MTN",
        "UG": "MTN",
        "TZ": "VODACOM",
        "ZM": "MTN",
    }.get(cc, "MPESA")


async def create_mobile_money_customer(
    *,
    phone_number: str,
    country_code: str = "KE",
    network: Optional[str] = None,
    first_name: str = "",
    last_name: str = "",
    account_name: Optional[str] = None,
    email: Optional[str] = None,
) -> dict:
    """Register a mobile money recipient on Kotani. Idempotency: Kotani
    dedupes on phone_number within an integrator; a second call with the
    same phone typically returns the existing record (or a 400 that we
    treat as "already exists" — caller can handle by re-fetching).
    """
    payload = {
        "phone_number": phone_number,
        "country_code": country_code.upper(),
        "network": (network or _default_network_for_country(country_code)).upper(),
    }
    if account_name:
        payload["account_name"] = account_name
    if first_name:
        payload["first_name"] = first_name
    if last_name:
        payload["last_name"] = last_name
    if email:
        payload["email"] = email

    if not live_mode():
        return _mock_create_customer(payload)
    return await _post("/api/v3/customer/mobile-money", payload)


def extract_customer_key(customer_res: dict) -> Optional[str]:
    """Pull the customer_key from a Kotani customer response (or None)."""
    data = (customer_res or {}).get("data") or {}
    return (
        data.get("customer_key")
        or data.get("customerKey")
        or data.get("id")
    )


# --- Rates -----------------------------------------------------------------
# Real endpoint: POST /api/v3/rate/offramp
# Body: {from, to, cryptoAmount, source}
# Returns: {data: {id, from, to, value, cryptoAmount, fiatAmount, fee, ...}}
async def offramp_rate(
    *,
    from_token: str = "USDC",
    to_currency: str = "KES",
    crypto_amount: float,
    source: str = "crypto",
) -> dict:
    """Ask Kotani for a live crypto→fiat rate quote. `data.id` is the
    `rateId` we then pass to `create_offramp` — lock-in-then-book pattern.
    """
    body = {
        "from": from_token.upper(),
        "to": to_currency.upper(),
        "cryptoAmount": crypto_amount,
        "source": source,
    }
    if not live_mode():
        return _mock_offramp_rate(from_token, to_currency, crypto_amount)
    return await _post("/api/v3/rate/offramp", body)


def extract_rate_id(rate_res: dict) -> Optional[str]:
    """Pull the rateId (data.id) from an offramp_rate response."""
    data = (rate_res or {}).get("data") or {}
    return data.get("id") or data.get("rateId")


def extract_fiat_amount(rate_res: dict) -> Optional[float]:
    data = (rate_res or {}).get("data") or {}
    val = data.get("fiatAmount") or data.get("transactionAmount")
    try:
        return float(val) if val is not None else None
    except Exception:  # noqa: BLE001
        return None


# --- Offramp (create + status) --------------------------------------------
# Real endpoint: POST /api/v3/offramp
# Body: {cryptoAmount, currency, chain, token, referenceId,
#        mobileMoneyReceiver:{customerKey}, callbackUrl, rateId, senderAddress?}
async def create_offramp(
    *,
    crypto_amount: float,
    currency: str,           # target fiat (KES, GHS, ...)
    chain: str,              # ETHEREUM, BASE, CELO, SOLANA, STELLAR, ...
    token: str,              # USDC, USDT, ...
    reference_id: str,       # our tx.id — becomes the correlator
    customer_key: str,       # from create_mobile_money_customer
    rate_id: str,            # from offramp_rate
    callback_url: str,
    sender_address: Optional[str] = None,
) -> dict:
    """Create an off-ramp transaction. Returns Kotani envelope with
    `data.referenceId` (echo of ours) and `data.escrowAddress` — the
    on-chain address the customer must fund.
    """
    payload = {
        "cryptoAmount": crypto_amount,
        "currency": currency.upper(),
        "chain": chain.upper(),
        "token": token.upper(),
        "referenceId": reference_id,
        "mobileMoneyReceiver": {"customerKey": customer_key},
        "callbackUrl": callback_url,
        "rateId": rate_id,
    }
    if sender_address:
        payload["senderAddress"] = sender_address

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
        # No secret configured — Kotani sends payload unsigned per docs.
        return True
    if not signature_header:
        logger.warning("[kotani-webhook] missing X-Kotani-Signature header")
        return False
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
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
