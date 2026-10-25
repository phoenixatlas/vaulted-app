"""Yellow Card Payments API client — stablecoin → African fiat payouts.

Backup payout partner to Kotani Pay. Mock-aware exactly like kotani.py:
runs in MOCK mode until YC_API_KEY + YC_API_SECRET are present in the env
(or YC_MOCK=true forces mock). Mock rates are derived from Vaulted's live
FX cache so quotes stay realistic even before keys arrive.

Docs (2026):
  - Auth:     https://docs.yellowcard.engineering/docs/authentication-api
  - Send:     https://docs.yellowcard.engineering/reference/submit-send
  - Webhooks: https://docs.yellowcard.engineering/docs/webhooks-api
  - Sandbox:  https://docs.yellowcard.engineering/docs/sandbox-testing-api

Signing: Authorization: YcHmacV1 <key>:<b64(hmac_sha256(secret, ts+path+METHOD[+b64(sha256(body))]))>
         X-YC-Timestamp: <ISO-8601 UTC>   (path includes /business, no query string)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

import httpx

logger = logging.getLogger("vaulted.yellowcard")

_TIMEOUT = httpx.Timeout(20.0, connect=8.0)
_SENTINELS = {"", "MOCKED", "PLACEHOLDER", "REPLACE_ME", "TODO"}

# Countries Yellow Card can pay out to from Vaulted's corridor list, and the
# rail type we expect for each (momo = mobile money, bank = bank account).
PAYOUT_RAILS: dict[str, str] = {
    "KE": "momo", "GH": "momo", "UG": "momo", "TZ": "momo", "ZM": "momo", "NG": "bank",
}
COUNTRY_CURRENCY = {"KE": "KES", "GH": "GHS", "UG": "UGX", "TZ": "TZS", "ZM": "ZMW", "NG": "NGN"}


def _key() -> str:
    return os.environ.get("YC_API_KEY", "").strip()


def _secret() -> str:
    return os.environ.get("YC_API_SECRET", "").strip()


def _webhook_secret() -> str:
    # Per Yellow Card docs, webhooks are signed with the secret of the API
    # key that created the payment — so the API secret IS the default
    # signing secret. YC_WEBHOOK_SECRET only overrides it if YC issues one.
    return os.environ.get("YC_WEBHOOK_SECRET", "").strip() or _secret()


def base_url() -> str:
    return os.environ.get("YC_BASE_URL", "https://sandbox.api.yellowcard.io/business").rstrip("/")


def is_sandbox() -> bool:
    return "sandbox" in base_url()


def live_mode() -> bool:
    if os.environ.get("YC_MOCK", "").strip().lower() in ("1", "true", "yes", "on"):
        return False
    return _key().upper() not in _SENTINELS and _secret().upper() not in _SENTINELS


def diagnostic_info() -> dict:
    return {
        "mode": "live" if live_mode() else "mock",
        "base_url": base_url(),
        "sandbox": is_sandbox(),
        "api_key_configured": _key().upper() not in _SENTINELS,
        "api_secret_configured": _secret().upper() not in _SENTINELS,
        "webhook_secret_configured": bool(_webhook_secret()),
    }


# ---- Signing ----------------------------------------------------------------
def _sign_headers(method: str, path: str, body: bytes) -> dict:
    ts = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    msg = ts + path + method.upper()
    if method.upper() in ("POST", "PUT"):
        msg += base64.b64encode(hashlib.sha256(body).digest()).decode()
    sig = base64.b64encode(hmac.new(_secret().encode(), msg.encode(), hashlib.sha256).digest()).decode()
    return {
        "Authorization": f"YcHmacV1 {_key()}:{sig}",
        "X-YC-Timestamp": ts,
        "Content-Type": "application/json",
    }


async def _call(method: str, suffix: str, payload: Optional[dict] = None, params: Optional[dict] = None) -> dict:
    """Signed request. Returns {success, status, data} — never raises on HTTP errors."""
    path = urlparse(base_url()).path + suffix  # e.g. /business/rates
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode() if payload is not None else b""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as cx:
            r = await cx.request(method, base_url() + suffix, params=params, content=body or None,
                                 headers=_sign_headers(method, path, body))
    except httpx.HTTPError as e:
        logger.warning("[yellowcard] %s %s network error: %s", method, suffix, e)
        return {"success": False, "status": 0, "data": {"message": f"network error: {e}"}}
    try:
        data = r.json()
    except ValueError:
        data = {"raw": r.text[:600]}
    if r.status_code >= 400:
        logger.warning("[yellowcard] %s %s -> %s: %s", method, suffix, r.status_code, r.text[:300])
        return {"success": False, "status": r.status_code, "data": data}
    return {"success": True, "status": r.status_code, "data": data}


# ---- Public API ---------------------------------------------------------------
async def get_rate(currency: str) -> dict:
    """USD → local rate for payouts. Returns {success, rate, rate_id, raw}.
    Yellow Card quotes local-currency units per 1 USD; for disbursements
    (USD in, local out) we use the `buy` side."""
    res = await _call("GET", "/rates", params={"currency": currency.upper()})
    if not res["success"]:
        return {"success": False, "error": res}
    rows = (res["data"] or {}).get("rates") or (res["data"] if isinstance(res["data"], list) else [])
    row = next((x for x in rows if (x.get("code") or x.get("currency") or "").upper() == currency.upper()), None)
    if not row:
        return {"success": False, "error": {"status": 404, "data": {"message": f"no {currency} rate"}}}
    return {"success": True, "rate": float(row.get("buy") or 0), "rate_id": row.get("rateId"), "raw": row}


async def _pick_channel_and_network(country: str, rail: str) -> tuple[Optional[dict], Optional[dict]]:
    ch = await _call("GET", "/channels", params={"country": country})
    channels = (ch["data"] or {}).get("channels", []) if ch["success"] else []
    channel = next((c for c in channels
                    if c.get("status") == "active" and c.get("channelType") == rail
                    and c.get("rampType", "withdraw") == "withdraw"), None)
    if not channel:
        return None, None
    nw = await _call("GET", "/networks", params={"country": country})
    networks = (nw["data"] or {}).get("networks", []) if nw["success"] else []
    candidates = [n for n in networks if n.get("status") == "active" and channel.get("id") in (n.get("channelIds") or [])]
    # Kenya: prefer M-Pesa / Safaricom network.
    network = next((n for n in candidates if "pesa" in (n.get("name") or "").lower()
                    or "safaricom" in (n.get("name") or "").lower()), None) or (candidates[0] if candidates else None)
    return channel, network


async def create_payout(*, sequence_id: str, country: str, amount_usd: float, recipient_name: str,
                        recipient_account: str, sender: dict, network_id: Optional[str] = None) -> dict:
    """Submit + accept a Send. Returns {success, reference_id, status, error?}.
    Mock mode returns an instantly-complete payout."""
    if not live_mode():
        return {"success": True, "reference_id": "yc_mock_" + uuid.uuid4().hex[:16], "status": "complete", "mock": True}

    rail = PAYOUT_RAILS.get(country.upper())
    if not rail:
        return {"success": False, "error": {"message": f"Yellow Card payouts not configured for {country}"}}
    channel, network = await _pick_channel_and_network(country.upper(), rail)
    if network_id:  # sender picked a specific bank (Nigeria)
        network = {"id": network_id}
    if not channel or not network:
        return {"success": False, "error": {"message": f"no active {rail} channel/network for {country}"}}

    destination = {"accountName": recipient_name, "accountType": rail, "networkId": network["id"]}
    if rail == "momo":
        destination["phoneNumber"] = recipient_account
    else:
        destination["accountNumber"] = recipient_account
    body = {
        "channelId": channel["id"],
        "sequenceId": sequence_id,
        "amount": round(amount_usd, 2),
        "reason": "other",
        "customerType": "retail",
        "forceAccept": True,  # user already confirmed + paid inside Vaulted
        "sender": sender,
        "destination": destination,
    }
    res = await _call("POST", "/send", payload=body)
    if not res["success"]:
        return {"success": False, "error": res}
    data = res["data"] or {}
    return {"success": True, "reference_id": data.get("id") or sequence_id, "status": data.get("status") or "process"}


async def payout_status(reference_id: str) -> dict:
    if not live_mode():
        return {"success": True, "status": "complete", "mock": True}
    res = await _call("GET", f"/send/{reference_id}")
    return {"success": res["success"], "status": (res["data"] or {}).get("status"), "raw": res["data"]}


def classify_status(status: Optional[str]) -> str:
    s = (status or "").lower()
    if s in ("complete", "completed", "success", "successful"):
        return "settled"
    if s in ("failed", "expired", "cancelled", "canceled", "rejected"):
        return "failed"
    return "processing"


def verify_webhook_signature(raw_body: bytes, signature: Optional[str]) -> bool:
    secret = _webhook_secret()
    if not secret or not signature:
        return False
    expected = base64.b64encode(hmac.new(secret.encode(), raw_body, hashlib.sha256).digest()).decode()
    return hmac.compare_digest(expected, signature.strip())


# ---- Nigeria bank list + account-name lookup ---------------------------------
# Used in mock mode (no keys yet). IDs are prefixed `ng_` so they can never be
# confused with real Yellow Card network IDs once live.
_MOCK_NG_BANKS = [
    ("Access Bank", "044"), ("Ecobank", "050"), ("Fidelity Bank", "070"), ("First Bank", "011"),
    ("FCMB", "214"), ("GTBank", "058"), ("Jaiz Bank", "301"), ("Keystone Bank", "082"),
    ("Kuda", "50211"), ("Moniepoint", "50515"), ("OPay", "999992"), ("PalmPay", "999991"),
    ("Polaris Bank", "076"), ("Providus Bank", "101"), ("Stanbic IBTC", "221"), ("Sterling Bank", "232"),
    ("UBA", "033"), ("Union Bank", "032"), ("Wema Bank", "035"), ("Zenith Bank", "057"),
]


async def list_banks(country: str = "NG") -> dict:
    """Return {banks: [{id, name, code}], mode}."""
    if not live_mode():
        return {"mode": "mock", "banks": [{"id": f"ng_{c}", "name": n, "code": c} for n, c in _MOCK_NG_BANKS]}
    ch = await _call("GET", "/channels", params={"country": country})
    channels = (ch["data"] or {}).get("channels", []) if ch["success"] else []
    bank_ch = {c["id"] for c in channels if c.get("status") == "active" and c.get("channelType") == "bank"}
    nw = await _call("GET", "/networks", params={"country": country})
    networks = (nw["data"] or {}).get("networks", []) if nw["success"] else []
    banks = [{"id": n["id"], "name": n.get("name"), "code": n.get("code")}
             for n in networks if n.get("status") == "active" and bank_ch & set(n.get("channelIds") or [])]
    return {"mode": "live", "banks": sorted(banks, key=lambda b: (b["name"] or "").lower())}


async def resolve_bank_account(account_number: str, network_id: str) -> dict:
    """Return {success, account_name, mode} or {success: False, message}."""
    if not live_mode():
        if account_number.startswith("0000"):
            return {"success": False, "message": "Account not found"}
        return {"success": True, "account_name": "TEST ACCOUNT HOLDER", "mode": "mock"}
    res = await _call("POST", "/details/bank", payload={"accountNumber": account_number, "networkId": network_id})
    if not res["success"]:
        return {"success": False, "message": (res["data"] or {}).get("message") or "Account not found"}
    name = (res["data"] or {}).get("accountName")
    return {"success": bool(name), "account_name": name, "mode": "live",
            **({} if name else {"message": "Account not found"})}
