"""Admin routes — compliance health, manual EDD approval, sanctions
screening, and audit-log queries. All routes are gated by
`require_admin` (checks against ADMIN_EMAILS on the deployment).

Extracted from server.py during the P2 refactor.
"""
from __future__ import annotations

import hashlib
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from audit import (
    ALL_EVENT_TYPES,
    EventType,
    query_events as audit_query,
    summarize_user as audit_summarize_user,
    write_event as audit_write,
)
from compliance import (
    COUNTRY_BLOCKLIST,
    opensanctions_config_status,
    opensanctions_health,
    screen_sanctions,
)
from deps import db, iso, logger, now_utc, public_user, require_admin
from models import AdminScreenIn, ManualEddApproveIn
from referrals import credit_referral_on_kyc

router = APIRouter()


# ============================================================================
# ADMIN — Compliance health & manual screening tools
# ============================================================================
@router.get("/admin/compliance/health")
async def admin_compliance_health(_admin=Depends(require_admin)):
    """Ping OpenSanctions with a canary query so operators can verify at a
    glance whether sanctions screening is actually live. Also returns the
    current integration config (key present, strict mode, URL, scopes)."""
    health = await opensanctions_health()
    return {
        "opensanctions": {
            "config": opensanctions_config_status(),
            "health": health,
        },
        "corridor_blocklist": {
            "count": len(COUNTRY_BLOCKLIST),
            "codes": sorted(COUNTRY_BLOCKLIST.keys()),
        },
        "checked_at": iso(now_utc()),
    }


# ============================================================================
# MANUAL EDD (Enhanced Due Diligence) — admin-triggered KYC approval
# ============================================================================
# Stripe Identity's automated face-match / document-check algorithms can't
# verify a small proportion of legitimate users (algorithm ceiling — ~3-5%
# of users, often those with older ID photos, non-Western features the model
# was under-trained on, or age-progression edge cases). MLR 2017 Reg 33
# explicitly allows manual EDD in these cases, provided the reviewing admin
# retains records of the documents reviewed + the reason for manual approval.
#
# This endpoint is the digital lever for that: an admin (identified by
# ADMIN_EMAILS on Render) records the EDD outcome, and the user's KYC tier
# is bumped instantly. Every approval is written to the immutable audit log.

@router.post("/admin/kyc/manual-edd-approve")
async def admin_kyc_manual_edd_approve(
    body: ManualEddApproveIn,
    admin=Depends(require_admin),
):
    """Manually mark a user as KYC-verified after reviewing their identity
    documents offline. Records the reviewing admin + reason in audit trail.

    Provide either user_id OR user_email. Returns the updated user summary.
    """
    if not body.user_id and not body.user_email:
        raise HTTPException(status_code=400, detail="Provide user_id or user_email")

    query: dict = {}
    if body.user_id:
        query["id"] = body.user_id
    else:
        query["email"] = (body.user_email or "").lower().strip()

    target = await db.users.find_one(query, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    # Preserve any existing KYC context so audit can reconstruct the "before"
    prior_kyc = target.get("kyc") or {}
    prior_state = {
        "identity_verification_status": prior_kyc.get("identity_verification_status"),
        "tier": prior_kyc.get("tier"),
        "identity_last_error_code": (prior_kyc.get("identity_last_error") or {}).get("code"),
    }

    # Update user KYC state — mark verified + set target tier + record EDD context
    new_kyc = {
        **prior_kyc,
        "identity_verification_status": "verified",
        "tier": body.target_tier,
        "verified_at": iso(now_utc()),
        "manual_edd": {
            "approved_by_admin_email_hash": hashlib.sha256(
                (admin.get("email") or "").lower().encode()
            ).hexdigest()[:12],
            "approved_at": iso(now_utc()),
            "edd_reference": body.edd_reference.strip(),
            "edd_reason": body.edd_reason.strip(),
            "documents_verified": body.documents_verified,
        },
    }
    # Clear the residual "last_error" so the frontend banner disappears
    new_kyc.pop("identity_last_error", None)

    # NOTE: new_kyc already has `identity_last_error` popped above, so a plain
    # $set on the full kyc document is enough. Combining $set on `kyc` with a
    # $unset on `kyc.identity_last_error` in a single update raises a
    # "conflict at 'kyc'" write error in MongoDB.
    await db.users.update_one(
        {"id": target["id"]},
        {"$set": {"kyc": new_kyc}},
    )

    # Write to immutable audit trail — every field required for FCA review
    await audit_write(db, EventType.KYC_MANUAL_EDD_APPROVED, user=target, data={
        "target_user_id": target["id"],
        "target_user_email_hash": hashlib.sha256((target.get("email") or "").lower().encode()).hexdigest()[:12],
        "reviewing_admin_email_hash": hashlib.sha256((admin.get("email") or "").lower().encode()).hexdigest()[:12],
        "target_tier": body.target_tier,
        "edd_reference": body.edd_reference,
        "edd_reason": body.edd_reason,
        "documents_verified": body.documents_verified,
        "prior_state": prior_state,
        "regulatory_basis": "UK MLR 2017 Regulation 33 — Enhanced Due Diligence",
    })

    # Trigger any post-KYC hooks (e.g. referral reward credit)
    try:
        await credit_referral_on_kyc(db, target["id"])
    except Exception as e:  # noqa: BLE001
        logger.warning("credit_referral_on_kyc failed for %s: %s", target["id"], e)

    refreshed = await db.users.find_one({"id": target["id"]}, {"_id": 0})
    return {"ok": True, "user": public_user(refreshed)}


@router.post("/admin/compliance/screen")
async def admin_compliance_screen(body: AdminScreenIn, admin=Depends(require_admin)):
    """Manually screen a name/DOB/country against OpenSanctions. Useful for
    testing after enabling a new API key, and for ad-hoc SAR investigations.
    Returns the full raw screen result (including degraded/reason flags)."""
    result = await screen_sanctions(body.name, dob=body.dob, country=body.country)
    await audit_write(db, EventType.ADMIN_MANUAL_SCREEN, user=admin, data={
        "screened_name_hash": hashlib.sha256((body.name or "").strip().lower().encode()).hexdigest()[:12],
        "screened_country": body.country,
        "has_dob": bool(body.dob),
        "matched": result.get("matched"),
        "degraded": result.get("degraded", False),
        "highest_score": result.get("highest_score"),
    })
    return {"input": body.model_dump(), "result": result}


# ============================================================================
# ADMIN — Audit-log endpoint (FCA / MLR 2017 record-keeping)
# ============================================================================
@router.get("/admin/audit-log")
async def admin_audit_log(
    _admin=Depends(require_admin),
    event_type: Optional[str] = None,
    user_id: Optional[str] = None,
    from_iso: Optional[str] = None,
    to_iso: Optional[str] = None,
    limit: int = 50,
    cursor: Optional[str] = None,
):
    """Cursor-paginated audit event feed. Supports filtering by event_type,
    user_id, and timestamp range (ISO 8601). Newest first. Meant to be
    consumed by ops dashboards, compliance officers, and (eventually) a
    scheduled export job that ships events to a WORM (write-once-read-many)
    archival store for the 5-year MLR 2017 retention requirement."""
    if event_type and event_type not in ALL_EVENT_TYPES:
        raise HTTPException(status_code=400, detail={
            "error": "unknown_event_type",
            "provided": event_type,
            "allowed": sorted(ALL_EVENT_TYPES),
        })
    return await audit_query(
        db,
        event_type=event_type,
        user_id=user_id,
        from_iso=from_iso,
        to_iso=to_iso,
        limit=limit,
        cursor=cursor,
    )


@router.get("/admin/audit-log/event-types")
async def admin_audit_event_types(_admin=Depends(require_admin)):
    """Enumerate every event_type the audit system knows how to write. Useful
    for populating filter dropdowns in an ops UI without hardcoding."""
    return {"event_types": sorted(ALL_EVENT_TYPES)}


@router.get("/admin/audit-log/user/{user_id}")
async def admin_audit_log_for_user(user_id: str, _admin=Depends(require_admin)):
    """Compliance-file view for a single user. Returns every event we've
    recorded for that user, ordered chronologically, plus counts by
    event_type. Consumed by SAR (Suspicious Activity Report) filings and
    ad-hoc regulator requests."""
    return await audit_summarize_user(db, user_id)
