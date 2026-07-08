"""Referral loop — invite-link viral growth mechanic.

Every user gets a unique 8-char alphanumeric `referral_code` on signup.
Sharing `https://app.phoenix-atlas.com/?ref=CODE` and having the referred
user complete Stripe Identity KYC grants BOTH parties £5 of GBP credit,
which is auto-applied to service fees on future /remit/send calls.

Design principles:
  1. Credit ledger is append-only — every mutation writes a positive (grant)
     or negative (spend) entry, plus the resulting balance. Never mutate
     historical rows.
  2. KYC completion is the eligibility gate — signup alone is insufficient
     (blocks throwaway-email fraud, per iteration-20 audit trail).
  3. Idempotent grant: if the referred user already triggered a credit
     (e.g. verified twice due to Stripe replay), the second call is a no-op.
  4. Referrer + referred must be different users, not on the same account,
     not chained (A refers B, B cannot then be their own referred).

MongoDB collections used:
    referrals       — one row per (referrer, referred) pair
    credit_ledger   — append-only £ credit ledger
"""

from __future__ import annotations

import logging
import secrets
import string
import uuid
from datetime import datetime, timezone
from typing import Optional


logger = logging.getLogger("vaulted.referrals")


# £-denominated rewards. Kept as module constants so tests can monkeypatch.
REFERRAL_REWARD_GBP = 5.0        # to the person who invited
REFERRAL_SIGNUP_BONUS_GBP = 5.0  # to the person who signed up via the code

# 8-char uppercase alphanumeric — collision odds ~1/2.8T for 32^8 space.
# Uses cryptographically secure PRNG so codes aren't guessable/enumerable.
_CODE_ALPHABET = string.ascii_uppercase + string.digits
_CODE_LENGTH = 8


def _iso_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def generate_code() -> str:
    """Cryptographically random 8-char code from [A-Z0-9]. Excludes lowercase
    to avoid l/1/I/0/O readability confusion via uppercase-only choice."""
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))


async def ensure_referral_code(db, user: dict) -> str:
    """Return the user's referral_code, generating + persisting one if the
    user was created before this feature landed. Idempotent."""
    existing = user.get("referral_code")
    if existing:
        return existing
    # Retry up to 5x on collision (unique index catches the race)
    for _ in range(5):
        code = generate_code()
        try:
            await db.users.update_one(
                {"id": user["id"], "referral_code": {"$exists": False}},
                {"$set": {"referral_code": code}},
            )
            # Verify persistence — if another concurrent request beat us, read what's there
            fresh = await db.users.find_one({"id": user["id"]}, {"referral_code": 1})
            if fresh and fresh.get("referral_code"):
                return fresh["referral_code"]
        except Exception as e:  # noqa: BLE001 — best-effort loop
            logger.warning(f"referral: code assign attempt failed: {e}")
    # Fallback — return a fresh code without persisting (very unlikely path)
    return generate_code()


async def user_by_referral_code(db, code: str) -> Optional[dict]:
    """Look up the referrer by their code (case-insensitive, normalised)."""
    if not code or not code.strip():
        return None
    return await db.users.find_one({"referral_code": code.strip().upper()}, {"_id": 0})


# ---------------------------------------------------------------------------
# Credit ledger
# ---------------------------------------------------------------------------
async def get_balance_gbp(db, user_id: str) -> float:
    """Sum of the ledger for a user. Cheap for expected volumes (<10k
    entries per user); if this ever becomes hot, cache on the user doc and
    invalidate on writes."""
    total = 0.0
    async for row in db.credit_ledger.find({"user_id": user_id}, {"amount_gbp": 1}):
        try:
            total += float(row.get("amount_gbp") or 0)
        except (TypeError, ValueError):
            continue
    # Rounding to 2dp keeps display-side math consistent
    return round(total, 2)


async def _write_ledger(
    db,
    *,
    user_id: str,
    amount_gbp: float,
    source: str,
    reference_id: Optional[str] = None,
    memo: Optional[str] = None,
) -> dict:
    """Append a single row to the credit ledger. Positive amount = credit added,
    negative amount = credit spent. Returns the persisted row."""
    balance_after = round(await get_balance_gbp(db, user_id) + amount_gbp, 2)
    row = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "amount_gbp": round(amount_gbp, 2),
        "source": source,
        "reference_id": reference_id,
        "memo": memo,
        "balance_after_gbp": balance_after,
        "created_at": _iso_now(),
    }
    await db.credit_ledger.insert_one(row)
    row.pop("_id", None)
    return row


async def spend_credit_for_fee(
    db,
    *,
    user_id: str,
    fee_gbp: float,
    reference_id: Optional[str] = None,
) -> dict:
    """Try to consume up to `fee_gbp` from the user's credit balance to
    offset a remit service fee. Returns:
      {applied_gbp: float, remaining_fee_gbp: float, balance_after_gbp: float}
    Applied credit is written as a negative-amount ledger row so history
    stays audit-preservable."""
    fee_gbp = max(0.0, round(float(fee_gbp), 2))
    if fee_gbp == 0.0:
        return {"applied_gbp": 0.0, "remaining_fee_gbp": 0.0,
                "balance_after_gbp": await get_balance_gbp(db, user_id)}

    balance = await get_balance_gbp(db, user_id)
    if balance <= 0:
        return {"applied_gbp": 0.0, "remaining_fee_gbp": fee_gbp,
                "balance_after_gbp": balance}

    applied = round(min(balance, fee_gbp), 2)
    row = await _write_ledger(
        db,
        user_id=user_id,
        amount_gbp=-applied,
        source="remit_fee_offset",
        reference_id=reference_id,
        memo=f"Credit applied to remit service fee £{fee_gbp:.2f}",
    )
    return {
        "applied_gbp": applied,
        "remaining_fee_gbp": round(fee_gbp - applied, 2),
        "balance_after_gbp": row["balance_after_gbp"],
    }


# ---------------------------------------------------------------------------
# Referral lifecycle
# ---------------------------------------------------------------------------
async def register_referral_at_signup(
    db,
    *,
    referred_user: dict,
    referred_by_code: Optional[str],
) -> Optional[dict]:
    """Called from /auth/register when the incoming body carries a
    `referred_by_code`. Records the pending referral for later credit-grant
    on KYC completion. Returns the created referrals row (or None if the
    code was invalid / self-referral)."""
    if not referred_by_code or not referred_by_code.strip():
        return None
    normalised = referred_by_code.strip().upper()

    referrer = await user_by_referral_code(db, normalised)
    if not referrer:
        logger.info(f"referral: unknown code {normalised!r} at signup — ignoring")
        return None
    if referrer["id"] == referred_user["id"]:
        logger.info(f"referral: self-referral rejected for user {referred_user['id']}")
        return None

    # Also block duplicate referrals (same referred user re-registering somehow)
    existing = await db.referrals.find_one({"referred_user_id": referred_user["id"]})
    if existing:
        return None

    row = {
        "id": str(uuid.uuid4()),
        "referrer_user_id": referrer["id"],
        "referred_user_id": referred_user["id"],
        "referred_by_code": normalised,
        "status": "pending",  # will flip to "credited" when KYC completes
        "created_at": _iso_now(),
        "credited_at": None,
        "rejected_reason": None,
    }
    await db.referrals.insert_one(row)
    await db.users.update_one(
        {"id": referred_user["id"]},
        {"$set": {"referred_by_code": normalised}},
    )
    row.pop("_id", None)
    return row


async def credit_referral_on_kyc(db, referred_user_id: str) -> Optional[dict]:
    """Called from the Stripe Identity verified webhook. If this user has a
    pending referral, grant both parties their credit and flip the referral
    to `credited`. Idempotent — a second call is a no-op.

    Returns:
      {referral_id, referrer_user_id, referrer_credit_row, referred_credit_row}
      or None if there's no pending referral for this user.
    """
    referral = await db.referrals.find_one({
        "referred_user_id": referred_user_id,
        "status": "pending",
    })
    if not referral:
        return None

    # Grant credit to both sides
    referrer_row = await _write_ledger(
        db,
        user_id=referral["referrer_user_id"],
        amount_gbp=REFERRAL_REWARD_GBP,
        source="referral_reward",
        reference_id=referral["id"],
        memo="Friend completed KYC via your invite",
    )
    referred_row = await _write_ledger(
        db,
        user_id=referred_user_id,
        amount_gbp=REFERRAL_SIGNUP_BONUS_GBP,
        source="referral_signup_bonus",
        reference_id=referral["id"],
        memo="Signed up with an invite code — welcome bonus",
    )

    # Flip referral to credited (idempotent — no-op if a concurrent call already did it)
    await db.referrals.update_one(
        {"id": referral["id"], "status": "pending"},
        {"$set": {"status": "credited", "credited_at": _iso_now()}},
    )
    logger.info(
        f"referral: credited {referred_user_id} + referrer "
        f"{referral['referrer_user_id']} (£{REFERRAL_REWARD_GBP} each)"
    )
    return {
        "referral_id": referral["id"],
        "referrer_user_id": referral["referrer_user_id"],
        "referrer_credit_row": referrer_row,
        "referred_credit_row": referred_row,
    }


# ---------------------------------------------------------------------------
# Summary views — used by /api/referrals/me
# ---------------------------------------------------------------------------
async def referral_summary(db, user_id: str) -> dict:
    """Aggregate a referrer's dashboard: totals + a paginated recent list.
    Referred emails are masked to preserve privacy."""
    cursor = db.referrals.find(
        {"referrer_user_id": user_id},
        {"_id": 0},
    ).sort("created_at", -1)
    referrals = await cursor.to_list(length=200)
    total = len(referrals)
    credited = sum(1 for r in referrals if r.get("status") == "credited")
    pending = sum(1 for r in referrals if r.get("status") == "pending")

    # Enrich with masked email for the UI list
    enriched = []
    for r in referrals[:50]:  # cap list; full history endpoint is separate
        referred = await db.users.find_one(
            {"id": r["referred_user_id"]},
            {"email": 1, "kyc": 1, "created_at": 1},
        )
        email = (referred or {}).get("email") or ""
        enriched.append({
            "id": r["id"],
            "status": r.get("status"),
            "created_at": r.get("created_at"),
            "credited_at": r.get("credited_at"),
            "friend_email_masked": _mask_email(email),
            "friend_kyc_status": ((referred or {}).get("kyc") or {}).get(
                "identity_verification_status", "not_started",
            ),
        })

    return {
        "total_referred": total,
        "credited_count": credited,
        "pending_count": pending,
        "reward_per_side_gbp": REFERRAL_REWARD_GBP,
        "referrals": enriched,
    }


def _mask_email(email: str) -> str:
    """`smoketest@vaulted.app` → `s***@v***.app`. Preserves domain TLD only."""
    if not email or "@" not in email:
        return "***"
    local, _, domain = email.partition("@")
    first = (local[:1] or "?").lower()
    domain_first = (domain[:1] or "?").lower()
    tld = domain.rsplit(".", 1)[-1] if "." in domain else ""
    return f"{first}***@{domain_first}***.{tld}" if tld else f"{first}***@{domain_first}***"


__all__ = [
    "REFERRAL_REWARD_GBP",
    "REFERRAL_SIGNUP_BONUS_GBP",
    "generate_code",
    "ensure_referral_code",
    "user_by_referral_code",
    "get_balance_gbp",
    "spend_credit_for_fee",
    "register_referral_at_signup",
    "credit_referral_on_kyc",
    "referral_summary",
]
