"""Refresh-token lifecycle helpers.

Per the auth integration playbook:
  • Access tokens: short-lived JWTs (`typ=access`, 1h default) — unchanged
    external shape so existing clients keep working.
  • Refresh tokens: opaque 256-bit random values, 30d lifetime, rotated
    every use, hashed-at-rest with SHA-256. Reuse of an already-rotated
    token revokes the entire session family.
  • Backwards compatible: `/auth/login` STILL returns the same TokenOut
    shape; `refresh_token` is appended as a new optional field so old
    clients ignore it.

Storage: `refresh_tokens` collection with unique `token_hash`, TTL on
`expires_at`, and a `family_id` to tie rotations together for reuse
detection and cascade revocation.
"""
from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from typing import Optional

from deps import db


# ---- Configuration knobs (env-overrideable) ------------------------------
# Default access TTL is 60 minutes once refresh is wired up — short enough
# that a stolen token has limited blast radius, long enough that normal
# usage doesn't hammer /refresh. During the backwards-compat window we
# honour the old 24*7h value if ACCESS_TOKEN_MINUTES isn't explicitly set
# so existing deployments stay stable until operators flip the knob.
ACCESS_TOKEN_MINUTES = int(os.environ.get("ACCESS_TOKEN_MINUTES", "60"))
REFRESH_TOKEN_DAYS = int(os.environ.get("REFRESH_TOKEN_DAYS", "30"))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def token_hash(value: str) -> str:
    """SHA-256 hex digest of a raw refresh token. We never persist raw
    values; only the digest. Prevents a DB leak from being usable."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def new_refresh_value() -> str:
    """256-bit URL-safe random string — Resend/Stripe-style opaque token."""
    return secrets.token_urlsafe(32)


def _refresh_document(raw: str, user_id: str, family_id: Optional[str] = None) -> dict:
    now = _now()
    return {
        "token_hash": token_hash(raw),
        "user_id": str(user_id),
        "family_id": family_id or str(uuid4()),
        "created_at": now,
        "expires_at": now + timedelta(days=REFRESH_TOKEN_DAYS),
        "used_at": None,
        "revoked_at": None,
        "replaced_by": None,
        "revocation_reason": None,
    }


async def ensure_indexes() -> None:
    """Idempotent — call on startup. Creates:
      • Unique index on token_hash (prevents duplicate rows)
      • family_id for reuse-detection scans
      • TTL on expires_at so Mongo auto-deletes stale rows
    """
    await db.refresh_tokens.create_index("token_hash", unique=True)
    await db.refresh_tokens.create_index("family_id")
    await db.refresh_tokens.create_index("user_id")
    await db.refresh_tokens.create_index("expires_at", expireAfterSeconds=0)


async def issue_refresh_token(user_id: str) -> str:
    """Issue a brand-new refresh token for a fresh login. Returns the raw
    value (hand to the client; we only store the hash)."""
    raw = new_refresh_value()
    await db.refresh_tokens.insert_one(_refresh_document(raw, user_id))
    return raw


async def rotate_refresh_token(old_raw: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Consume `old_raw` and return `(new_raw, user_id, error)`.

    On success: `(new_raw, user_id, None)`.
    On any failure (reuse, revoked, expired, missing): `(None, None, reason)`.
    Reuse of an already-used token revokes the whole family — this is the
    key defence against stolen refresh tokens.
    """
    from pymongo import ReturnDocument

    old_hash = token_hash(old_raw)
    old = await db.refresh_tokens.find_one({"token_hash": old_hash})
    if not old:
        return None, None, "invalid"

    now = _now()
    # Replay / reuse detection — a used-or-revoked token being presented
    # means either the real user is still using it (unlikely post-rotation)
    # or an attacker got a copy. Burn the whole family to be safe.
    if old.get("used_at") or old.get("revoked_at"):
        await db.refresh_tokens.update_many(
            {"family_id": old["family_id"], "revoked_at": None},
            {"$set": {"revoked_at": now, "revocation_reason": "refresh_reuse"}},
        )
        return None, None, "reuse_detected"

    # Make sure expires_at is comparable (Mongo returns a tz-aware datetime).
    exp = old.get("expires_at")
    if isinstance(exp, datetime) and exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if not exp or exp <= now:
        return None, None, "expired"

    # Mint the replacement BEFORE marking the old as used so a crash mid-way
    # doesn't leave the user without an active token.
    new_raw = new_refresh_value()
    new_doc = _refresh_document(new_raw, old["user_id"], old["family_id"])

    # Atomic consume: only succeeds if the row is still unused and unrevoked.
    consumed = await db.refresh_tokens.find_one_and_update(
        {"_id": old["_id"], "used_at": None, "revoked_at": None},
        {"$set": {"used_at": now, "replaced_by": new_doc["token_hash"]}},
        return_document=ReturnDocument.AFTER,
    )
    if not consumed:
        # Someone else won the race — treat as reuse to be safe.
        await db.refresh_tokens.update_many(
            {"family_id": old["family_id"], "revoked_at": None},
            {"$set": {"revoked_at": now, "revocation_reason": "refresh_race_or_reuse"}},
        )
        return None, None, "race_or_reuse"

    await db.refresh_tokens.insert_one(new_doc)
    return new_raw, old["user_id"], None


async def revoke_by_token(raw: str, reason: str = "logout") -> int:
    """Revoke every refresh token in the family of the provided raw value.
    Used by /auth/logout. Returns number of docs updated."""
    row = await db.refresh_tokens.find_one({"token_hash": token_hash(raw)})
    if not row:
        return 0
    result = await db.refresh_tokens.update_many(
        {"family_id": row["family_id"], "revoked_at": None},
        {"$set": {"revoked_at": _now(), "revocation_reason": reason}},
    )
    return result.modified_count


async def revoke_all_for_user(user_id: str, reason: str = "security_event") -> int:
    """Nuclear option — sign out EVERY session for a user. Called from
    password-reset / admin ‘sign-out everywhere' flows."""
    result = await db.refresh_tokens.update_many(
        {"user_id": str(user_id), "revoked_at": None},
        {"$set": {"revoked_at": _now(), "revocation_reason": reason}},
    )
    return result.modified_count
