"""FCA-facing audit log — immutable event trail for KYC decisions, sanctions
screening outcomes, and remittance sends. Required for UK Money Laundering
Regulations 2017 record-keeping (5-year retention) and for the FCA
money-transmission authorisation application.

Design principles:
  1. Append-only from application code — we never expose an update/delete API
     for this collection. Enforce at the database level (MongoDB role) in
     production.
  2. Privacy-preserving — all PII (name, email, address) is stored as
     SHA-256 prefixes only. Regulators can still search by hash if given the
     source PII, but a compromised log dump does not leak identities.
  3. Structured shape — every event is `{id, event_type, user_id,
     user_email_hash, timestamp, data}`, so ingestion into log warehouses
     (Datadog, BigQuery, etc.) is trivial.
  4. Fire-and-forget from the request path — audit writes must NEVER block a
     user-facing send; wrap in try/except and log a WARNING on failure.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional


logger = logging.getLogger("vaulted.audit")


# ---- Canonical event-type constants ----------------------------------------
class EventType:
    KYC_SESSION_CREATED = "kyc.session_created"
    KYC_SESSION_FORCE_NEW = "kyc.session_force_new"
    KYC_VERIFIED = "kyc.verified"
    KYC_REQUIRES_INPUT = "kyc.requires_input"
    KYC_CANCELED = "kyc.canceled"
    KYC_FLAGGED = "kyc.flagged"

    SANCTIONS_SCREENED = "sanctions.screened"

    REMIT_QUOTE_GENERATED = "remit.quote_generated"
    REMIT_SEND_SUCCESS = "remit.send_success"
    REMIT_SEND_BLOCKED = "remit.send_blocked"

    CORRIDOR_BLOCKED = "corridor.blocked"

    # For manual admin actions (support ticket handling, etc.)
    ADMIN_MANUAL_SCREEN = "admin.manual_screen"

    # Referral / credit lifecycle
    REFERRAL_SIGNUP = "referral.signup"     # someone registered with a code
    REFERRAL_CREDITED = "referral.credited"  # KYC completed → both sides paid
    CREDIT_GRANTED = "credit.granted"        # any credit added to ledger
    CREDIT_SPENT = "credit.spent"            # credit consumed on a fee

    # Password reset lifecycle
    AUTH_FORGOT_PASSWORD_REQUESTED = "auth.forgot_password_requested"
    AUTH_PASSWORD_RESET_COMPLETED = "auth.password_reset_completed"
    AUTH_PASSWORD_RESET_INVALID_TOKEN = "auth.password_reset_invalid_token"

    # Off-ramp (Kotani Pay / M-Pesa) lifecycle
    OFFRAMP_MPESA_INITIATED = "offramp.mpesa_initiated"
    OFFRAMP_MPESA_SUCCESS = "offramp.mpesa_success"
    OFFRAMP_MPESA_FAILED = "offramp.mpesa_failed"
    OFFRAMP_MPESA_REFUNDED = "offramp.mpesa_refunded"
    OFFRAMP_WEBHOOK_INVALID_SIGNATURE = "offramp.webhook_invalid_signature"


ALL_EVENT_TYPES = {
    v for k, v in vars(EventType).items() if not k.startswith("_") and isinstance(v, str)
}


# ---- Hashing helpers -------------------------------------------------------
def _hash_short(value: Optional[str]) -> Optional[str]:
    """SHA-256 → hex[:12] for pseudonymised log searching. Case-insensitive,
    whitespace-trimmed. Returns None for empty/None input so downstream
    queries can filter on `null` vs `absent`."""
    if not value or not str(value).strip():
        return None
    return hashlib.sha256(str(value).strip().lower().encode()).hexdigest()[:12]


def _iso_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


# ---- Write helper (fire-and-forget) ----------------------------------------
async def write_event(
    db,
    event_type: str,
    *,
    user: Optional[dict] = None,
    user_id: Optional[str] = None,
    user_email: Optional[str] = None,
    data: Optional[dict[str, Any]] = None,
) -> Optional[str]:
    """Persist an audit event. Returns the event id on success, None on
    failure. NEVER raises — audit failures must not break user-facing flows.

    Callers may pass `user` (full doc) OR `user_id`+`user_email` directly.
    Anonymous events (no user) are permitted but discouraged.
    """
    try:
        if user:
            uid = user.get("id")
            uemail = user.get("email")
        else:
            uid = user_id
            uemail = user_email

        event_id = str(uuid.uuid4())
        doc = {
            "id": event_id,
            "event_type": event_type,
            "user_id": uid,
            "user_email_hash": _hash_short(uemail),
            "timestamp": _iso_now(),
            "data": data or {},
        }
        await db.audit_events.insert_one(doc)
        # Mirror to stdout so log aggregators pick it up even if the DB fails
        # silently later. Structured extra keeps the field schema uniform
        # with the earlier iter-19 sanctions_screen line.
        logger.info(
            "audit_event",
            extra={
                "event": "audit_event",
                "audit_id": event_id,
                "event_type": event_type,
                "user_id": uid,
                "user_email_hash": doc["user_email_hash"],
                "timestamp": doc["timestamp"],
            },
        )
        return event_id
    except Exception as e:
        logger.warning(f"audit: write_event({event_type}) failed: {e}")
        return None


# ---- Query helper for admin endpoint ---------------------------------------
async def query_events(
    db,
    *,
    event_type: Optional[str] = None,
    user_id: Optional[str] = None,
    from_iso: Optional[str] = None,
    to_iso: Optional[str] = None,
    limit: int = 50,
    cursor: Optional[str] = None,   # opaque; we use the timestamp of the last-seen doc
) -> dict:
    """Cursor-paginated list of audit events. Newest first."""
    query: dict = {}
    if event_type:
        query["event_type"] = event_type
    if user_id:
        query["user_id"] = user_id
    ts_range: dict = {}
    if from_iso:
        ts_range["$gte"] = from_iso
    if to_iso:
        ts_range["$lte"] = to_iso
    if cursor:
        ts_range["$lt"] = cursor
    if ts_range:
        query["timestamp"] = ts_range

    limit = max(1, min(200, limit))
    cursor_it = (
        db.audit_events
        .find(query, {"_id": 0})
        .sort("timestamp", -1)
        .limit(limit + 1)
    )
    docs = await cursor_it.to_list(length=limit + 1)
    has_more = len(docs) > limit
    if has_more:
        docs = docs[:limit]
    next_cursor = docs[-1]["timestamp"] if has_more and docs else None
    return {
        "events": docs,
        "count": len(docs),
        "has_more": has_more,
        "next_cursor": next_cursor,
    }


async def summarize_user(db, user_id: str) -> dict:
    """Compliance-file style summary for a single user — every recorded event
    plus aggregate counts. Used for SAR files or regulator ad-hoc requests."""
    all_events_cursor = (
        db.audit_events
        .find({"user_id": user_id}, {"_id": 0})
        .sort("timestamp", 1)  # oldest first for a chronological narrative
    )
    events = await all_events_cursor.to_list(length=10_000)
    counts: dict[str, int] = {}
    for ev in events:
        counts[ev["event_type"]] = counts.get(ev["event_type"], 0) + 1
    return {
        "user_id": user_id,
        "event_count": len(events),
        "counts_by_type": counts,
        "first_event_at": events[0]["timestamp"] if events else None,
        "last_event_at": events[-1]["timestamp"] if events else None,
        "events": events,
    }


__all__ = [
    "EventType",
    "ALL_EVENT_TYPES",
    "write_event",
    "query_events",
    "summarize_user",
]
