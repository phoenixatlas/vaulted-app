"""Flutterwave v4 payouts client — bank (Nigeria) and mobile money (Kenya
M-Pesa, Ghana, Uganda, Tanzania, Rwanda) transfers.

Auth: OAuth client-credentials (FLW_PUBLIC_KEY = client ID,
FLW_SECRET_KEY = client secret) → 10-minute bearer token, cached.
Base URL: FLW_BASE_URL (default = sandbox). Docs: developer.flutterwave.com/v4.0.0
Runs in MOCK mode (instant fake success) when keys are missing.
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Optional

import httpx

logger = logging.getLogger("vaulted.flutterwave")

_TOKEN_URL = "https://idp.flutterwave.com/realms/flutterwave/protocol/openid-connect/token"
_TIMEOUT = httpx.Timeout(25.0, connect=8.0)
_token: dict = {"value": None, "exp": 0.0}

COUNTRY_CURRENCY = {"NG": "NGN", "KE": "KES", "GH": "GHS", "UG": "UGX", "TZ": "TZS", "RW": "RWF"}
# Default mobile-money network per country (Nigeria pays to banks).
MOMO_NETWORK = {"KE": "Mpesa", "GH": "MTN", "UG": "MTN", "TZ": "airtel", "RW": "MTN"}
SUPPORTED = set(COUNTRY_CURRENCY)


def base_url() -> str:
    return os.environ.get("FLW_BASE_URL", "https://developersandbox-api.flutterwave.com").rstrip("/")


def is_sandbox() -> bool:
    return "sandbox" in base_url()


def live_mode() -> bool:
    return bool(os.environ.get("FLW_PUBLIC_KEY", "").strip() and os.environ.get("FLW_SECRET_KEY", "").strip())


def diagnostic_info() -> dict:
    return {"mode": "live" if live_mode() else "mock", "base_url": base_url(), "sandbox": is_sandbox(),
            "api_key_configured": live_mode()}


async def _access_token() -> str:
    if _token["value"] and time.time() < _token["exp"]:
        return _token["value"]
    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        r = await c.post(_TOKEN_URL, data={
            "client_id": os.environ["FLW_PUBLIC_KEY"].strip(),
            "client_secret": os.environ["FLW_SECRET_KEY"].strip(),
            "grant_type": "client_credentials",
        })
    r.raise_for_status()
    body = r.json()
    _token.update(value=body["access_token"], exp=time.time() + int(body.get("expires_in", 600)) - 60)
    return _token["value"]


async def _call(method: str, path: str, payload: Optional[dict] = None, params: Optional[dict] = None,
                idempotency_key: Optional[str] = None) -> dict:
    """Returns {success, status, data, message}. Never raises."""
    try:
        headers = {"Authorization": f"Bearer {await _access_token()}", "Content-Type": "application/json",
                   "X-Trace-Id": uuid.uuid4().hex}
        if idempotency_key:
            headers["X-Idempotency-Key"] = idempotency_key
            if is_sandbox():  # sandbox: force the "successful" transfer scenario
                headers["X-Scenario-Key"] = "scenario:successful"
        async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
            r = await c.request(method, base_url() + path, json=payload, params=params, headers=headers)
        body = r.json() if r.content else {}
        if r.status_code == 401:
            _token.update(value=None, exp=0.0)
        ok = r.status_code < 400 and body.get("status") == "success"
        err = body.get("error") or {}
        msg = body.get("message") or err.get("message")
        if err.get("validation_errors"):
            msg = f"{msg}: {err['validation_errors']}"
        return {"success": ok, "status": r.status_code, "data": body.get("data"), "message": msg}
    except Exception as e:  # noqa: BLE001
        logger.warning("[flutterwave] %s %s failed: %s", method, path, e)
        return {"success": False, "status": 0, "data": None, "message": str(e)[:200]}


# ---- Nigeria banks + account-name check ---------------------------------------
async def list_banks(country: str = "NG") -> dict:
    """{mode, banks: [{id, name, code}]} — id is the bank code."""
    res = await _call("GET", "/banks", params={"country": country.upper()})
    banks, seen = [], set()
    for b in res["data"] or []:
        name = " ".join((b.get("name") or "").split())
        if b.get("code") and b["code"] not in seen and name:
            seen.add(b["code"])
            banks.append({"id": b["code"], "name": name, "code": b["code"]})
    return {"mode": "live", "banks": sorted(banks, key=lambda b: b["name"].lower())}


async def resolve_bank_account(account_number: str, bank_code: str) -> dict:
    """{success, account_name, mode} or {success: False, message}."""
    res = await _call("POST", "/banks/account-resolve",
                      payload={"account": {"code": bank_code, "number": account_number}, "currency": "NGN"})
    name = (res["data"] or {}).get("account_name") if res["success"] else None
    if not name:
        return {"success": False, "message": res.get("message") or "Account not found"}
    return {"success": True, "account_name": name, "mode": "live"}


# ---- Transfers ----------------------------------------------------------------
def _split_name(full: str) -> dict:
    parts = (full or "Vaulted Recipient").strip().split()
    return {"first": parts[0], "last": " ".join(parts[1:]) or parts[0]}


async def create_payout(*, reference: str, country: str, amount_local: float, recipient_name: str,
                        recipient_account: str, bank_code: Optional[str] = None) -> dict:
    """Send local currency to a bank account (NG) or mobile wallet.
    Returns {success, reference_id, status, mock?, error?}."""
    if not live_mode():
        return {"success": True, "reference_id": "flw_mock_" + uuid.uuid4().hex[:16], "status": "SUCCESSFUL", "mock": True}
    country = country.upper()
    currency = COUNTRY_CURRENCY.get(country)
    if not currency:
        return {"success": False, "error": f"Flutterwave payouts not configured for {country}"}
    account = "".join(ch for ch in recipient_account if ch.isdigit())
    if country == "NG":
        kind, recipient = "bank", {"bank": {"account_number": account, "code": bank_code}}
    else:
        kind = "mobile_money"
        recipient = {"name": _split_name(recipient_name),
                     "mobile_money": {"network": MOMO_NETWORK[country], "msisdn": account}}
    body = {
        "action": "instant", "type": kind, "reference": reference, "narration": "Vaulted transfer",
        "payment_instruction": {
            "source_currency": currency, "destination_currency": currency,
            "amount": {"applies_to": "destination_currency", "value": round(amount_local, 2)},
            "recipient": recipient,
        },
    }
    res = await _call("POST", "/direct-transfers", payload=body, idempotency_key=reference)
    if not res["success"]:
        return {"success": False, "error": res.get("message") or f"HTTP {res['status']}"}
    data = res["data"] or {}
    return {"success": True, "reference_id": data.get("id"), "status": data.get("status") or "NEW"}


async def payout_status(transfer_id: str) -> dict:
    res = await _call("GET", f"/transfers/{transfer_id}")
    return {"success": res["success"], "status": (res["data"] or {}).get("status")}


def classify_status(status: Optional[str]) -> str:
    s = (status or "").upper()
    if s in ("SUCCESSFUL", "SUCCEEDED", "COMPLETED"):
        return "settled"
    if s in ("FAILED", "CANCELLED", "REVERSED"):
        return "failed"
    return "processing"
