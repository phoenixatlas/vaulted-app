"""Referral loop + credit-ledger routes. Extracted from server.py during
the P2 refactor. Powers the invite-link viral growth + £5 GBP credit
sub-system.
"""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends

from deps import APP_PUBLIC_URL, db, get_current_user
from referrals import (
    REFERRAL_REWARD_GBP,
    REFERRAL_SIGNUP_BONUS_GBP,
    ensure_referral_code,
    get_balance_gbp,
    referral_summary,
    user_by_referral_code,
)

router = APIRouter()


REFERRAL_LINK_BASE = os.environ.get("REFERRAL_LINK_BASE") or (
    APP_PUBLIC_URL.rstrip("/") if APP_PUBLIC_URL else "https://app.phoenix-atlas.com"
)


@router.get("/referrals/me")
async def referrals_me(user=Depends(get_current_user)):
    """Everything the /referral screen needs in one call: my code, my
    shareable link, my credit balance, and my referral history."""
    code = await ensure_referral_code(db, user)
    balance = await get_balance_gbp(db, user["id"])
    summary = await referral_summary(db, user["id"])
    share_link = f"{REFERRAL_LINK_BASE}/?ref={code}"
    return {
        "referral_code": code,
        "share_link": share_link,
        "share_message": (
            f"Send money home for less on Vaulted. Sign up with my code {code} "
            f"and we both get £{REFERRAL_REWARD_GBP:.0f} credit."
        ),
        "credit_balance_gbp": balance,
        "reward_per_side_gbp": REFERRAL_REWARD_GBP,
        "signup_bonus_gbp": REFERRAL_SIGNUP_BONUS_GBP,
        **summary,
    }


@router.get("/referrals/validate/{code}")
async def referrals_validate(code: str):
    """Public endpoint used by the signup form to preview who invited them —
    returns just enough to build trust without leaking full PII."""
    referrer = await user_by_referral_code(db, code)
    if not referrer:
        return {"valid": False}
    name = (referrer.get("name") or "").strip()
    # Show first name + last initial (Sarah B.) at most
    parts = name.split()
    display = (parts[0] if parts else "A friend") + (
        f" {parts[1][:1]}." if len(parts) > 1 and parts[1] else ""
    )
    return {
        "valid": True,
        "referrer_name_masked": display,
        "reward_per_side_gbp": REFERRAL_REWARD_GBP,
    }


@router.get("/credit/balance")
async def credit_balance(user=Depends(get_current_user)):
    """Current GBP credit balance for the caller."""
    balance = await get_balance_gbp(db, user["id"])
    return {"balance_gbp": balance}


@router.get("/credit/ledger")
async def credit_ledger(user=Depends(get_current_user), limit: int = 50):
    """Paginated credit ledger — newest first. Includes source labels the
    frontend can render (referral_reward, referral_signup_bonus,
    remit_fee_offset, admin_grant)."""
    limit = max(1, min(200, int(limit)))
    rows = await db.credit_ledger.find(
        {"user_id": user["id"]}, {"_id": 0},
    ).sort("created_at", -1).limit(limit).to_list(length=limit)
    return {"entries": rows, "count": len(rows)}
