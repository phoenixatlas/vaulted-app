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
# ADMIN — Kotani Pay sandbox health probe
# ============================================================================
# Real-time introspection of the Kotani off-ramp integration: mode
# (live/mock), endpoint the SDK is pointed at, and — critically — which of
# the four service surfaces are actually enabled on the integrator
# account. Kotani gates services individually on the dashboard side
# (`integratorEnabled` flags per service), so a valid API key doesn't
# imply every call will succeed. This endpoint probes each surface with a
# harmless request and reports back so we can see the gate flip
# server-side the moment Kotani support enables it.
@router.get("/admin/kotani/health")
async def admin_kotani_health(_admin=Depends(require_admin)):
    """Probe Kotani sandbox surfaces and report per-service health so
    operators can eyeball what's actually enabled without SSH-ing in."""
    # Import inside the handler so a missing kotani module never breaks
    # the whole admin router at boot.
    import kotani

    diagnostic = kotani.diagnostic_info()
    checked_at = iso(now_utc())

    async def _probe_health() -> dict:
        try:
            r = await kotani.health()
            return {
                "ok": bool(r.get("success", True)),
                "status_code": 200,
                "detail": (r.get("data") or {}).get("status") or r.get("message"),
            }
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "status_code": None, "detail": f"exception: {type(e).__name__}: {str(e)[:200]}"}

    async def _probe_rate() -> dict:
        """A rate quote is safe / non-mutating — pings USDC→KES for $1."""
        try:
            r = await kotani.offramp_rate(from_token="USDC", to_currency="KES", crypto_amount=1.0)
            if r.get("success"):
                data = r.get("data") or {}
                return {
                    "ok": True,
                    "detail": f"1 USDC ≈ {data.get('fiatAmount')} KES (rate={data.get('value')})",
                }
            # Extract inner error for 403 propagation via kotani._envelope
            inner = (r.get("data") or {})
            return {
                "ok": False,
                "detail": inner.get("message") or r.get("message") or "unknown",
                "error_code": inner.get("error_code"),
                "service": (inner.get("data") or {}).get("service"),
                "integrator_enabled": (inner.get("data") or {}).get("integratorEnabled"),
            }
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "detail": f"exception: {type(e).__name__}: {str(e)[:200]}"}

    async def _probe_customer_create() -> dict:
        """Attempt to (idempotently) register the +254 sandbox test number.
        Kotani docs list +254712345678 as a safe sandbox recipient. If the
        service isn't enabled we get the specific error string we're
        watching for; if it succeeds we get a customer_key."""
        try:
            r = await kotani.create_mobile_money_customer(
                phone_number="+254712345678",
                country_code="KE",
                network="MPESA",
                first_name="Vaulted",
                last_name="HealthProbe",
                account_name="Vaulted Health Probe",
            )
            if r.get("success"):
                return {
                    "ok": True,
                    "detail": f"customer_key {kotani.extract_customer_key(r)}",
                }
            inner = (r.get("data") or {})
            return {
                "ok": False,
                "detail": inner.get("message") or r.get("message") or "unknown",
                "error_code": inner.get("error_code"),
                "service": (inner.get("data") or {}).get("service"),
                "integrator_enabled": (inner.get("data") or {}).get("integratorEnabled"),
            }
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "detail": f"exception: {type(e).__name__}: {str(e)[:200]}"}

    health_res = await _probe_health()
    rate_res = await _probe_rate()
    customer_res = await _probe_customer_create()

    # Overall readiness gate: all four v3 surfaces must be green before
    # we can flip the app off of mock mode in production. We don't probe
    # `create_offramp` in health because it would mutate real Kotani state
    # (mint a session) — we infer from `customer_create` succeeding that
    # `offramp` is in the same permission group.
    overall_ready = health_res["ok"] and rate_res["ok"] and customer_res["ok"]

    # Persist a rolling history of probes so admins can see when the gate
    # flipped (Kotani doesn't email you when they enable a service).
    row = {
        "checked_at": checked_at,
        "mode": diagnostic.get("mode"),
        "overall_ready": overall_ready,
        "health": health_res,
        "rate_quote": rate_res,
        "customer_create": customer_res,
    }
    try:
        await db.kotani_health_probes.insert_one(row)
        # Keep only last 50 probes to avoid unbounded growth.
        count = await db.kotani_health_probes.count_documents({})
        if count > 50:
            oldest = await db.kotani_health_probes.find({}, {"_id": 1}).sort("checked_at", 1).limit(count - 50).to_list(length=count - 50)
            if oldest:
                await db.kotani_health_probes.delete_many({"_id": {"$in": [o["_id"] for o in oldest]}})
    except Exception as e:  # noqa: BLE001
        logger.warning("kotani_health_probes insert failed: %s", e)

    # Get the last 5 probes for a mini history strip in the UI.
    history_cursor = db.kotani_health_probes.find({}, {"_id": 0}).sort("checked_at", -1).limit(5)
    history = await history_cursor.to_list(length=5)

    return {
        "diagnostic": diagnostic,
        "overall_ready": overall_ready,
        "probes": {
            "health": health_res,
            "rate_quote": rate_res,
            "customer_create": customer_res,
        },
        "history": history,
        "checked_at": checked_at,
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
