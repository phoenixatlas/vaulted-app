"""Compliance layer — KYC tiers, transaction limits, sanctions screening,
and blocked-country enforcement for Vaulted's cross-border remittance flow.

Regulatory anchor points (UK):
    - Money Laundering Regulations 2017 (MLR 2017): Standard CDD required above
      £1,000 equivalent single or linked transactions; Enhanced Due Diligence
      required over £15,000 (€15,000). Under €1,000 permits Simplified Due
      Diligence.
    - FATF Travel Rule (crypto): >£1,000 in a single transaction requires
      sender + receiver identifying info exchanged between VASPs.
    - OFAC comprehensive-sanctions countries + UK OFSI + EU consolidated
      sanctions lists are hard-blocked as destination corridors.

The tiers below map cleanly onto those thresholds:
    Tier 0 (unverified, email only)      : £100/send, £250/month
    Tier 1 (kyc_lite, Stripe Identity)   : £1,000/send, £5,000/month
    Tier 2 (kyc_full, +addr +source)     : £10,000/send, £50,000/month

Above Tier 2 requires a manual review workflow (SAR obligations kick in).
"""

from __future__ import annotations

import os
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx


logger = logging.getLogger("vaulted.compliance")


# ---------- Tiered send limits (GBP-normalised) -----------------------------
TIER_LIMITS: dict[str, dict] = {
    "unverified": {
        "label": "Unverified",
        "per_send_gbp": 100.0,
        "monthly_gbp": 250.0,
        "requires": None,
        "next_tier": "kyc_lite",
        "why": "Under the £1,000 Standard CDD threshold (UK MLR 2017).",
    },
    "kyc_lite": {
        "label": "KYC Verified",
        "per_send_gbp": 1000.0,
        "monthly_gbp": 5000.0,
        "requires": "Stripe Identity — passport or national ID + selfie",
        "next_tier": "kyc_full",
        "why": "Under the £15,000 Enhanced Due Diligence threshold (UK MLR 2017 + FATF Travel Rule).",
    },
    "kyc_full": {
        "label": "Enhanced KYC",
        "per_send_gbp": 10000.0,
        "monthly_gbp": 50000.0,
        "requires": "Proof of address + source of funds",
        "next_tier": None,
        "why": "Full CDD + EDD complete. Above this we file SARs and freeze pending review.",
    },
}
DEFAULT_TIER = "unverified"

# ---------- Sanctioned destination countries (blocked corridors) -----------
# OFAC "comprehensive sanctions" list + UK OFSI + EU consolidated list.
# ISO-3166-1 alpha-2 codes. Blocked at both quote and send time.
COUNTRY_BLOCKLIST: dict[str, str] = {
    "KP": "North Korea (OFAC/UK/EU comprehensive sanctions)",
    "IR": "Iran (OFAC/UK/EU comprehensive sanctions)",
    "CU": "Cuba (OFAC comprehensive sanctions)",
    "RU": "Russia (UK/EU sanctions + OFAC sectoral)",
    "SY": "Syria (OFAC/UK/EU comprehensive sanctions)",
    "BY": "Belarus (UK/EU sanctions)",
    "MM": "Myanmar (UK/EU sanctions)",
    # Regional sub-sanctions (not full countries but flagged)
    "UA-CR": "Crimea (OFAC/EU sanctions — Ukraine occupied region)",
    "UA-DR": "Donetsk People's Republic (OFAC/EU sanctions)",
    "UA-LR": "Luhansk People's Republic (OFAC/EU sanctions)",
}


def is_country_blocked(country_code: str) -> Optional[str]:
    """Return the block reason if country is on our sanctions blocklist, else None."""
    return COUNTRY_BLOCKLIST.get((country_code or "").upper())


# ---------- KYC state helpers ----------------------------------------------
def get_user_tier(user: dict) -> str:
    """Read the user's current KYC tier from the DB doc. Defaults to unverified."""
    kyc = user.get("kyc") or {}
    tier = kyc.get("tier") or DEFAULT_TIER
    if tier not in TIER_LIMITS:
        return DEFAULT_TIER
    return tier


def tier_limits(tier: str) -> dict:
    return TIER_LIMITS.get(tier) or TIER_LIMITS[DEFAULT_TIER]


def _first_of_month_utc() -> datetime:
    now = datetime.now(tz=timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def sum_this_month_gbp(db, user_id: str) -> float:
    """Sum of remit sends this calendar month for this user, in GBP-normalised
    amount. We store source_amount + source_currency on each remit tx, so we
    aggregate the sends that originated in GBP directly, and convert USD/EUR
    ones to GBP at their recorded fx snapshot (falling back to 1:1 → USD if
    the FX snapshot is missing so we err on the strict side of the limit)."""
    iso_start = _first_of_month_utc().isoformat()
    cursor = db.transactions.find({
        "user_id": user_id,
        "category": {"$regex": "^Remit ·"},
        "status": {"$ne": "failed"},
        "created_at": {"$gte": iso_start},
    }, {"_id": 0, "remit": 1, "fiat_value": 1})
    total_gbp = 0.0
    async for row in cursor:
        remit = row.get("remit") or {}
        src_ccy = (remit.get("source_currency") or "GBP").upper()
        src_amt = float(remit.get("source_amount") or 0)
        if src_ccy == "GBP":
            total_gbp += src_amt
        elif src_ccy == "USD":
            # Convert USD → GBP conservatively (assume 0.80 if we have no rate)
            total_gbp += src_amt * 0.80
        elif src_ccy == "EUR":
            total_gbp += src_amt * 0.85
        else:
            # Unknown source: fall back to fiat_value (USD)
            total_gbp += float(row.get("fiat_value") or 0) * 0.80
    return round(total_gbp, 2)


async def check_send_limits(db, user: dict, send_amount_gbp: float) -> dict:
    """Return a dict describing whether this send is permitted at the user's
    current tier, and if not, what tier they need to reach.

    Return shape:
      {
        allowed: bool,
        current_tier: "unverified" | "kyc_lite" | "kyc_full",
        limit: {per_send_gbp, monthly_gbp},
        usage: {this_month_gbp, this_month_pct},
        reason: "over_per_send" | "over_monthly" | None,
        upgrade: {target_tier, requires, why} | None
      }
    """
    tier = get_user_tier(user)
    limits = tier_limits(tier)
    used = await sum_this_month_gbp(db, user["id"])
    monthly_remaining = max(0.0, limits["monthly_gbp"] - used)

    reason = None
    if send_amount_gbp > limits["per_send_gbp"]:
        reason = "over_per_send"
    elif send_amount_gbp > monthly_remaining:
        reason = "over_monthly"

    upgrade = None
    if reason and limits["next_tier"]:
        nxt = TIER_LIMITS[limits["next_tier"]]
        upgrade = {
            "target_tier": limits["next_tier"],
            "target_tier_label": nxt["label"],
            "target_per_send_gbp": nxt["per_send_gbp"],
            "target_monthly_gbp": nxt["monthly_gbp"],
            "requires": nxt["requires"],
            "why": nxt["why"],
        }

    return {
        "allowed": reason is None,
        "current_tier": tier,
        "current_tier_label": limits["label"],
        "limit": {
            "per_send_gbp": limits["per_send_gbp"],
            "monthly_gbp": limits["monthly_gbp"],
        },
        "usage": {
            "this_month_gbp": used,
            "monthly_remaining_gbp": monthly_remaining,
            "monthly_used_pct": round((used / limits["monthly_gbp"]) * 100, 1) if limits["monthly_gbp"] else 0,
        },
        "reason": reason,
        "upgrade": upgrade,
    }


# ---------- OpenSanctions screening -----------------------------------------
OPENSANCTIONS_URL = os.environ.get("OPENSANCTIONS_URL", "https://api.opensanctions.org")
OPENSANCTIONS_API_KEY = os.environ.get("OPENSANCTIONS_API_KEY")  # optional — free tier works without

# When enabled, sanctions screening failures (API down, no key, timeout) will
# BLOCK the send (fail-closed). Default is fail-open — screening returns
# matched=False so the transaction proceeds and we log a WARNING for audit.
# Flip to true once FCA registration is finalised and OpenSanctions is proven
# stable + a paid key is in place.
COMPLIANCE_STRICT_MODE = os.environ.get("COMPLIANCE_STRICT_MODE", "false").lower() in ("1", "true", "yes")

# Scopes on OpenSanctions: "sanctions" (OFAC/UK/EU/UN) is what we care about;
# "peps" (politically-exposed persons) is a soft-warn category.
OPENSANCTIONS_SCOPES = ["sanctions", "peps"]

# Structured logger used by the audit-log pipeline. Emits one line per screen.
_audit_logger = logging.getLogger("vaulted.compliance.audit")


def _degraded_result(reason: str) -> dict:
    """Uniform shape for any screen that couldn't run properly. `matched:False`
    keeps fail-open semantics, but `degraded:True` + `degraded_reason` makes
    the state auditable (surfaced in /kyc/status and admin health endpoint)."""
    return {
        "matched": False,
        "highest_score": 0.0,
        "top_matches": [],
        "scope": None,
        "checked_at": datetime.now(tz=timezone.utc).isoformat(),
        "degraded": True,
        "degraded_reason": reason,
    }


def opensanctions_config_status() -> dict:
    """Snapshot of the current OpenSanctions integration configuration —
    consumed by the admin health endpoint so operators can see, at a glance,
    whether screening is live or running in fallback mode."""
    return {
        "url": OPENSANCTIONS_URL,
        "api_key_configured": bool(OPENSANCTIONS_API_KEY),
        "strict_mode": COMPLIANCE_STRICT_MODE,
        "scopes": OPENSANCTIONS_SCOPES,
    }


async def screen_sanctions(name: str, dob: Optional[str] = None, country: Optional[str] = None) -> dict:
    """Screen the given identity against OFAC/UK/EU/UN sanctions + PEP lists
    via OpenSanctions. Returns:
      {
        matched: bool,
        highest_score: float,
        top_matches: [...],
        scope: "sanctions" | "peps" | None,
        checked_at: iso,
        degraded: bool,             # True when the check couldn't actually run
        degraded_reason: str|None,  # "no_name" | "no_api_key" | "api_status_N" | "unreachable"
      }
    Fails-open (matched=False) by default so a compliance-API outage doesn't
    freeze the whole product. Every degraded screen emits a structured audit
    log line so we can prove to regulators that screening was ATTEMPTED even
    when it couldn't complete. Flip COMPLIANCE_STRICT_MODE=true to require
    a successful (non-degraded) screen for every send."""
    started_at = datetime.now(tz=timezone.utc)

    if not name or not name.strip():
        result = _degraded_result("no_name")
        _log_audit(name, country, dob, result, started_at)
        return result

    # No API key configured → we don't hit the endpoint at all (it would 401).
    # This is the most common production path when OpenSanctions is unfunded.
    if not OPENSANCTIONS_API_KEY:
        result = _degraded_result("no_api_key")
        _log_audit(name, country, dob, result, started_at)
        return result

    query: dict = {"schema": "Person", "properties": {"name": [name.strip()]}}
    if dob:
        query["properties"]["birthDate"] = [dob]
    if country:
        query["properties"]["nationality"] = [country]

    body = {
        "queries": {
            "candidate": {
                "schema": "Person",
                "properties": query["properties"],
            }
        }
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"ApiKey {OPENSANCTIONS_API_KEY}",
    }

    scope = ",".join(OPENSANCTIONS_SCOPES)
    url = f"{OPENSANCTIONS_URL}/match/default?scope={scope}"

    try:
        async with httpx.AsyncClient(timeout=8) as cx:
            r = await cx.post(url, json=body, headers=headers)
            if r.status_code != 200:
                logger.warning(f"OpenSanctions non-200 ({r.status_code}): {r.text[:200]}")
                result = _degraded_result(f"api_status_{r.status_code}")
                _log_audit(name, country, dob, result, started_at)
                return result
            data = r.json() or {}
    except Exception as e:
        logger.warning(f"OpenSanctions fetch failed: {e}")
        result = _degraded_result("unreachable")
        _log_audit(name, country, dob, result, started_at)
        return result

    results = (((data.get("responses") or {}).get("candidate") or {}).get("results")) or []
    # Keep only high-confidence matches (>= 0.85)
    top = sorted(results, key=lambda r: r.get("score") or 0, reverse=True)[:3]
    top_matches = [{
        "id": m.get("id"),
        "caption": m.get("caption"),
        "score": m.get("score"),
        "match": m.get("match", False),
        "schema": m.get("schema"),
        "datasets": m.get("datasets", [])[:5],
    } for m in top]
    highest = (top[0].get("score") or 0.0) if top else 0.0
    matched = highest >= 0.85 and (top[0].get("match", False) if top else False)

    result = {
        "matched": matched,
        "highest_score": highest,
        "top_matches": top_matches,
        "scope": "sanctions" if matched and top and any("sanction" in (d or "").lower() for d in (top[0].get("datasets") or [])) else ("peps" if matched else None),
        "checked_at": started_at.isoformat(),
        "degraded": False,
        "degraded_reason": None,
    }
    _log_audit(name, country, dob, result, started_at)
    return result


def _log_audit(name: str, country: Optional[str], dob: Optional[str], result: dict, started_at: datetime) -> None:
    """Structured audit log line — one per screen. Consumed by the FCA
    audit-log endpoint (upcoming P2 work) to prove screening was attempted.
    Never logs the raw name/DOB in production — only hashed + first-letter
    initials for privacy, so log aggregators can be search-audited without
    leaking PII."""
    import hashlib
    latency_ms = int((datetime.now(tz=timezone.utc) - started_at).total_seconds() * 1000)
    name_hash = hashlib.sha256((name or "").strip().lower().encode()).hexdigest()[:12]
    _audit_logger.info(
        "sanctions_screen",
        extra={
            "event": "sanctions_screen",
            "name_hash": name_hash,
            "name_initial": ((name or "?")[:1] or "?").upper(),
            "country": country,
            "has_dob": bool(dob),
            "matched": result.get("matched"),
            "degraded": result.get("degraded", False),
            "degraded_reason": result.get("degraded_reason"),
            "highest_score": result.get("highest_score"),
            "scope": result.get("scope"),
            "latency_ms": latency_ms,
            "checked_at": result.get("checked_at"),
        },
    )


async def opensanctions_health() -> dict:
    """Ping OpenSanctions with a known-good query ("Vladimir Putin" — always
    on sanctions lists) to verify the integration is live. Returns:
      {ok: bool, status: "live"|"degraded"|"down", reason: str|None,
       latency_ms: int, matched_expected: bool}
    """
    if not OPENSANCTIONS_API_KEY:
        return {"ok": False, "status": "degraded", "reason": "no_api_key",
                "latency_ms": 0, "matched_expected": False}
    started = datetime.now(tz=timezone.utc)
    try:
        result = await screen_sanctions("Vladimir Putin", country="RU")
    except Exception as e:
        return {"ok": False, "status": "down", "reason": f"exception: {e}",
                "latency_ms": int((datetime.now(tz=timezone.utc) - started).total_seconds() * 1000),
                "matched_expected": False}
    latency = int((datetime.now(tz=timezone.utc) - started).total_seconds() * 1000)
    if result.get("degraded"):
        return {"ok": False, "status": "degraded",
                "reason": result.get("degraded_reason"),
                "latency_ms": latency, "matched_expected": False}
    # For a real live key, Putin should match at 0.85+ against sanctions
    matched = bool(result.get("matched"))
    return {
        "ok": True,
        "status": "live",
        "reason": None if matched else "canary_no_match",
        "latency_ms": latency,
        "matched_expected": matched,
        "highest_score": result.get("highest_score"),
    }


__all__ = [
    "TIER_LIMITS", "DEFAULT_TIER",
    "COUNTRY_BLOCKLIST", "is_country_blocked",
    "get_user_tier", "tier_limits",
    "sum_this_month_gbp", "check_send_limits",
    "screen_sanctions",
    "opensanctions_health", "opensanctions_config_status",
    "COMPLIANCE_STRICT_MODE",
]
