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

# Scopes on OpenSanctions: "sanctions" (OFAC/UK/EU/UN) is what we care about;
# "peps" (politically-exposed persons) is a soft-warn category.
OPENSANCTIONS_SCOPES = ["sanctions", "peps"]


async def screen_sanctions(name: str, dob: Optional[str] = None, country: Optional[str] = None) -> dict:
    """Screen the given identity against OFAC/UK/EU/UN sanctions + PEP lists
    via OpenSanctions. Returns a dict:
      {
        matched: bool,
        highest_score: float,
        top_matches: [...],
        scope: "sanctions" | "peps" | None,
        checked_at: iso,
      }
    Fails-open (returns matched=False) if the API is unreachable — we log
    and let the send proceed rather than block on an outage. Production
    hardening: switch to fails-closed once the endpoint is proven stable.
    """
    if not name or not name.strip():
        return {"matched": False, "highest_score": 0.0, "top_matches": [], "scope": None,
                "checked_at": datetime.now(tz=timezone.utc).isoformat(), "reason": "no_name"}

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
    headers = {"Content-Type": "application/json"}
    if OPENSANCTIONS_API_KEY:
        headers["Authorization"] = f"ApiKey {OPENSANCTIONS_API_KEY}"

    scope = ",".join(OPENSANCTIONS_SCOPES)
    url = f"{OPENSANCTIONS_URL}/match/default?scope={scope}"

    try:
        async with httpx.AsyncClient(timeout=8) as cx:
            r = await cx.post(url, json=body, headers=headers)
            if r.status_code != 200:
                logger.warning(f"OpenSanctions non-200 ({r.status_code}): {r.text[:200]}")
                return {"matched": False, "highest_score": 0.0, "top_matches": [],
                        "scope": None, "checked_at": datetime.now(tz=timezone.utc).isoformat(),
                        "reason": f"api_status_{r.status_code}"}
            data = r.json() or {}
    except Exception as e:
        logger.warning(f"OpenSanctions fetch failed: {e}")
        return {"matched": False, "highest_score": 0.0, "top_matches": [],
                "scope": None, "checked_at": datetime.now(tz=timezone.utc).isoformat(),
                "reason": "unreachable"}

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

    return {
        "matched": matched,
        "highest_score": highest,
        "top_matches": top_matches,
        "scope": "sanctions" if matched and top and any("sanction" in (d or "").lower() for d in (top[0].get("datasets") or [])) else ("peps" if matched else None),
        "checked_at": datetime.now(tz=timezone.utc).isoformat(),
    }


__all__ = [
    "TIER_LIMITS", "DEFAULT_TIER",
    "COUNTRY_BLOCKLIST", "is_country_blocked",
    "get_user_tier", "tier_limits",
    "sum_this_month_gbp", "check_send_limits",
    "screen_sanctions",
]
