"""KYC / Identity router — Stripe Identity + OpenSanctions integration.

Extracted from server.py's monolith. Preserves every `/api/kyc/*` path
verbatim so no client change is required.

Endpoints (mounted under /api by server.py):
    GET  /kyc/status   — snapshot of the caller's tier, limits, MTD usage,
                         Stripe Identity + sanctions state (frontend banner)
    GET  /kyc/debug    — diagnostic: RAW Stripe Identity report summary for
                         the current user's most recent session (triage aid)
    POST /kyc/session  — create / reuse a Stripe Identity VerificationSession
                         with idempotent behaviour + force_new escape hatch

Also exports the two webhook handlers so server.py can dispatch them from
its central Stripe webhook endpoint (unchanged Stripe-side URL):
    _apply_identity_verified(session_obj)
    _apply_identity_requires_input(session_obj)

These handlers own the sanctions screen, tier bump to kyc_lite (or
`flagged` on high-confidence sanctions hit), verified-name/DOB/country
persistence, referral credit issuance, and audit trail. No behaviour is
changed by the extraction — only the physical file boundary.
"""
from __future__ import annotations

import hashlib
import os

import stripe
from fastapi import APIRouter, Depends, HTTPException

from audit import EventType, write_event as audit_write
from compliance import (
    TIER_LIMITS,
    get_user_tier,
    screen_sanctions,
    sum_this_month_gbp,
    tier_limits,
)
from deps import (
    APP_PUBLIC_URL,
    STRIPE_API_KEY,
    db,
    get_current_user,
    iso,
    logger,
    now_utc,
)
from models import KycSessionIn
from referrals import (
    REFERRAL_REWARD_GBP,
    REFERRAL_SIGNUP_BONUS_GBP,
    credit_referral_on_kyc,
)

router = APIRouter()

# Where Stripe should redirect the user after they finish their doc capture.
# Defaults to the production app URL; overridable via env for staging.
KYC_RETURN_URL = os.environ.get("KYC_RETURN_URL") or (
    (APP_PUBLIC_URL.rstrip("/") + "/kyc-return") if APP_PUBLIC_URL else "https://app.phoenix-atlas.com/kyc-return"
)


@router.get("/kyc/status")
async def kyc_status(user=Depends(get_current_user)):
    """Snapshot of the caller's current tier, limits, and month-to-date usage.
    The frontend polls this to render the KYC banner and after Stripe Identity
    submissions to show a 'Processing' state until the webhook flips the tier."""
    tier = get_user_tier(user)
    limits = tier_limits(tier)
    used = await sum_this_month_gbp(db, user["id"])
    kyc = user.get("kyc") or {}
    return {
        "tier": tier,
        "tier_label": limits["label"],
        "limits": {
            "per_send_gbp": limits["per_send_gbp"],
            "monthly_gbp": limits["monthly_gbp"],
        },
        "usage": {
            "this_month_gbp": used,
            "monthly_remaining_gbp": max(0.0, limits["monthly_gbp"] - used),
            "monthly_used_pct": round((used / limits["monthly_gbp"]) * 100, 1) if limits["monthly_gbp"] else 0,
        },
        "next_tier": limits.get("next_tier"),
        "next_tier_details": TIER_LIMITS[limits["next_tier"]] if limits.get("next_tier") else None,
        # Stripe Identity + sanctions state
        "identity_verification_status": kyc.get("identity_verification_status") or "not_started",
        "identity_last_error": kyc.get("identity_last_error"),
        "sanctions_check": {
            "matched": (kyc.get("sanctions") or {}).get("matched", False),
            "checked_at": (kyc.get("sanctions") or {}).get("checked_at"),
            "degraded": (kyc.get("sanctions") or {}).get("degraded", False),
            "degraded_reason": (kyc.get("sanctions") or {}).get("degraded_reason"),
        },
    }


@router.get("/kyc/debug")
async def kyc_debug(user=Depends(get_current_user)):
    """Diagnostic endpoint — pulls the RAW Stripe Identity verification
    report(s) for the current user's most recent verification session so
    we can see the exact document / selfie / id_number rejection codes.

    Only exposes what Stripe already surfaces to the account owner —
    never leaks other users' data. Safe to call from the client.
    """
    if not STRIPE_API_KEY:
        raise HTTPException(status_code=503, detail="Stripe not configured")

    kyc = user.get("kyc") or {}
    session_id = kyc.get("identity_verification_id") or kyc.get("identity_session_id")
    if not session_id:
        return {
            "ok": False,
            "reason": "no_active_session",
            "hint": "Start a verification session via /kyc/session first.",
        }

    try:
        session = stripe.identity.VerificationSession.retrieve(
            session_id,
            expand=["last_verification_report"],
        )
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reason": "stripe_retrieve_failed", "detail": str(e)[:400]}

    # Build a minimal, safe summary — no raw doc images or full personal
    # data, just the codes / reasons we need for triage.
    summary: dict = {
        "ok": True,
        "session_id": session.get("id"),
        "session_status": session.get("status"),
        "session_type": session.get("type"),
        "session_options": (session.get("options") or {}),
        "session_last_error": session.get("last_error"),
        "created": session.get("created"),
        "attempt_count": session.get("client_reference_id") is not None,
    }

    report = session.get("last_verification_report") or {}
    if isinstance(report, dict):
        doc = report.get("document") or {}
        selfie = report.get("selfie") or {}
        id_number = report.get("id_number") or {}
        summary["last_report"] = {
            "id": report.get("id"),
            "type": report.get("type"),
            "created": report.get("created"),
            "document": {
                "status": doc.get("status"),
                "error": doc.get("error"),
                "type": doc.get("type"),
                "issuing_country": doc.get("issuing_country"),
                "expiration_date": doc.get("expiration_date"),
                # Deliberately NOT returning: files (raw doc images),
                # first_name / last_name / dob / address / number
            },
            "selfie": {
                "status": selfie.get("status"),
                "error": selfie.get("error"),
                # Not returning file ids
            },
            "id_number": {
                "status": id_number.get("status"),
                "error": id_number.get("error"),
            },
        }
    return summary


@router.post("/kyc/session")
async def kyc_session(body: KycSessionIn | None = None, user=Depends(get_current_user)):
    """Create a Stripe Identity VerificationSession and return the hosted URL
    that the frontend redirects the user to. Idempotent per user — if there's
    already an active session that hasn't been canceled, we reuse its URL
    (unless the caller passed `force_new: true`)."""
    if not STRIPE_API_KEY:
        raise HTTPException(status_code=503, detail="Stripe not configured")

    force_new = bool(body and body.force_new)
    kyc = user.get("kyc") or {}
    existing_id = kyc.get("identity_verification_session_id")
    existing_status = kyc.get("identity_verification_status")

    # Reuse the existing active session UNLESS the caller explicitly asked for
    # a brand-new one (prevents Dashboard clutter + Stripe session costs).
    if not force_new and existing_id and existing_status in ("requires_input", "processing"):
        try:
            existing = stripe.identity.VerificationSession.retrieve(existing_id)
            if existing.get("status") in ("requires_input",) and existing.get("url"):
                return {"session_id": existing_id, "url": existing["url"], "reused": True}
        except Exception as e:
            logger.warning(f"kyc: existing session retrieve failed ({existing_id}): {e}")

    # force_new: cancel the existing Stripe session so we don't accumulate
    # zombie sessions on the Dashboard. Best-effort — a failure to cancel is
    # not fatal (the new session will still work).
    if force_new and existing_id:
        try:
            stripe.identity.VerificationSession.cancel(existing_id)
            logger.info(f"kyc: canceled stale session {existing_id} for user {user['id']}")
        except Exception as e:
            logger.warning(f"kyc: cancel stale session failed ({existing_id}): {e}")

    # Bump a per-user attempt counter so the Stripe idempotency key is unique
    # across cancellations. Without this, canceling a session and retrying
    # within 24h would hit Stripe's cached response (the canceled session)
    # and never mint a fresh URL.
    attempt_num = int(kyc.get("session_attempt", 0)) + 1

    try:
        session = stripe.identity.VerificationSession.create(
            type="document",
            return_url=KYC_RETURN_URL,
            options={
                "document": {
                    "allowed_types": ["driving_license", "passport", "id_card"],
                    "require_matching_selfie": True,
                    "require_live_capture": True,
                },
            },
            metadata={
                "user_id": user["id"],
                "target_tier": "kyc_lite",
                "email": user.get("email") or "",
                "attempt": str(attempt_num),
            },
            idempotency_key=f"vaulted-kyc-lite-{user['id']}-{attempt_num}",
        )
    except stripe.error.StripeError as e:  # type: ignore[attr-defined]
        # Detect the "Identity product not enabled" state and surface it as a
        # friendly configuration error rather than a scary raw Stripe message.
        msg = str(e)
        if "not set up to use Identity" in msg or "identity/application" in msg:
            raise HTTPException(status_code=503, detail={
                "error": "stripe_identity_not_activated",
                "message": (
                    "Identity verification is temporarily unavailable — we're finalising "
                    "our Stripe Identity onboarding. Please try again shortly, or "
                    "contact support@phoenix-atlas.com for immediate help."
                ),
            }) from e
        raise HTTPException(status_code=502, detail=f"Stripe Identity error: {e}") from e

    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {
            "kyc.identity_verification_session_id": session["id"],
            "kyc.identity_verification_status": "requires_input",
            "kyc.identity_started_at": iso(now_utc()),
            "kyc.session_attempt": attempt_num,
            # Clear any stale error from the previous session so the UI
            # doesn't confusingly show an old failure alongside the new attempt.
            "kyc.identity_last_error": None,
        }},
    )
    await audit_write(
        db,
        EventType.KYC_SESSION_FORCE_NEW if force_new else EventType.KYC_SESSION_CREATED,
        user=user,
        data={
            "session_id": session["id"],
            "attempt_num": attempt_num,
            "force_new": force_new,
            "previous_session_id": existing_id if force_new else None,
        },
    )
    return {"session_id": session["id"], "url": session["url"], "reused": False}


# --- Webhook handlers (called from server.py's Stripe webhook dispatcher) --
# These are NOT routes — they're pure async functions that the central
# Stripe webhook handler in server.py calls when it receives an
# identity.verification_session.* event. Kept here so all KYC state
# transitions live in one file.

async def _apply_identity_verified(session_obj: dict):
    """Webhook handler for identity.verification_session.verified — bumps the
    user to kyc_lite tier and enqueues an OpenSanctions screen against the
    verified name from the session."""
    user_id = (session_obj.get("metadata") or {}).get("user_id")
    if not user_id:
        logger.warning(f"identity webhook missing user_id metadata: {session_obj.get('id')}")
        return

    # Pull the verified outputs (name + address; DOB requires a restricted key
    # which we can add later). Falls back gracefully if expansion fails.
    verified_name = None
    verified_country = None
    verified_dob = None
    try:
        full = stripe.identity.VerificationSession.retrieve(
            session_obj["id"],
            expand=["verified_outputs"],
        )
        vo = full.get("verified_outputs") or {}
        first = (vo.get("first_name") or "").strip()
        last = (vo.get("last_name") or "").strip()
        verified_name = f"{first} {last}".strip() or None
        addr = vo.get("address") or {}
        verified_country = addr.get("country")
        dob = vo.get("dob") or {}
        if dob.get("year") and dob.get("month") and dob.get("day"):
            verified_dob = f"{dob['year']:04d}-{dob['month']:02d}-{dob['day']:02d}"
    except Exception as e:
        logger.warning(f"identity verified_outputs fetch failed: {e}")

    # Sanctions screening against the verified identity
    sanctions_result = {
        "matched": False,
        "checked_at": iso(now_utc()),
        "degraded": True,
        "degraded_reason": "no_name",
    }
    if verified_name:
        try:
            sanctions_result = await screen_sanctions(verified_name, dob=verified_dob, country=verified_country)
        except Exception as e:
            logger.warning(f"sanctions screen failed for user {user_id}: {e}")
            sanctions_result = {
                "matched": False,
                "checked_at": iso(now_utc()),
                "degraded": True,
                "degraded_reason": f"exception: {type(e).__name__}",
            }

    # If the sanctions check produced a HIGH-confidence match on a sanctions
    # dataset, we do NOT auto-tier the user up — we flag for manual review.
    is_flagged = bool(sanctions_result.get("matched")) and sanctions_result.get("scope") == "sanctions"

    update = {
        "kyc.identity_verification_status": "verified",
        "kyc.identity_verified_at": iso(now_utc()),
        "kyc.verified_name": verified_name,
        "kyc.verified_country": verified_country,
        "kyc.verified_dob": verified_dob,
        "kyc.sanctions": sanctions_result,
    }
    if is_flagged:
        update["kyc.tier"] = "flagged"
        update["kyc.flagged_at"] = iso(now_utc())
    else:
        update["kyc.tier"] = "kyc_lite"

    await db.users.update_one({"id": user_id}, {"$set": update})
    logger.info(f"KYC-lite {'FLAGGED' if is_flagged else 'GRANTED'} for user={user_id}")

    # Audit trail — separate events for verified vs flagged so log filters
    # can trivially count each outcome.
    await audit_write(
        db,
        EventType.KYC_FLAGGED if is_flagged else EventType.KYC_VERIFIED,
        user_id=user_id,
        user_email=(await db.users.find_one({"id": user_id}, {"email": 1}) or {}).get("email"),
        data={
            "session_id": session_obj.get("id"),
            "verified_name_hash": hashlib.sha256((verified_name or "").strip().lower().encode()).hexdigest()[:12] if verified_name else None,
            "verified_country": verified_country,
            "has_dob": bool(verified_dob),
            "tier_before": "unverified",
            "tier_after": "flagged" if is_flagged else "kyc_lite",
            "sanctions": {
                "matched": sanctions_result.get("matched"),
                "highest_score": sanctions_result.get("highest_score"),
                "scope": sanctions_result.get("scope"),
                "degraded": sanctions_result.get("degraded", False),
                "degraded_reason": sanctions_result.get("degraded_reason"),
            },
        },
    )
    # Also record the sanctions screen as its own event so
    # /audit-log?event_type=sanctions.screened counts include the KYC-time
    # screen (not just admin manual ones).
    await audit_write(
        db,
        EventType.SANCTIONS_SCREENED,
        user_id=user_id,
        data={
            "context": "kyc_verified",
            "matched": sanctions_result.get("matched"),
            "highest_score": sanctions_result.get("highest_score"),
            "scope": sanctions_result.get("scope"),
            "degraded": sanctions_result.get("degraded", False),
            "degraded_reason": sanctions_result.get("degraded_reason"),
        },
    )

    # Referral credit — only if the user was NOT flagged. Flagged users
    # (sanctions match) are under manual review; we don't want to hand out
    # credit for a potentially fraudulent signup.
    if not is_flagged:
        try:
            credit_result = await credit_referral_on_kyc(db, user_id)
        except Exception as e:  # noqa: BLE001 — never break the KYC flow
            logger.warning(f"referral: credit_referral_on_kyc failed for {user_id}: {e}")
            credit_result = None
        if credit_result:
            await audit_write(db, EventType.REFERRAL_CREDITED, user_id=user_id, data={
                "referral_id": credit_result["referral_id"],
                "referrer_user_id": credit_result["referrer_user_id"],
                "referred_credit_gbp": REFERRAL_SIGNUP_BONUS_GBP,
                "referrer_credit_gbp": REFERRAL_REWARD_GBP,
            })
            # Emit credit.granted events for both sides so the ledger has
            # a searchable trail per user
            await audit_write(db, EventType.CREDIT_GRANTED,
                              user_id=credit_result["referrer_user_id"],
                              data={
                                  "amount_gbp": REFERRAL_REWARD_GBP,
                                  "source": "referral_reward",
                                  "ledger_id": credit_result["referrer_credit_row"]["id"],
                                  "balance_after_gbp": credit_result["referrer_credit_row"]["balance_after_gbp"],
                              })
            await audit_write(db, EventType.CREDIT_GRANTED,
                              user_id=user_id,
                              data={
                                  "amount_gbp": REFERRAL_SIGNUP_BONUS_GBP,
                                  "source": "referral_signup_bonus",
                                  "ledger_id": credit_result["referred_credit_row"]["id"],
                                  "balance_after_gbp": credit_result["referred_credit_row"]["balance_after_gbp"],
                              })


async def _apply_identity_requires_input(session_obj: dict):
    """Webhook handler for identity.verification_session.requires_input —
    a check failed and the user needs to retry with a better photo/document.

    The session-level `last_error` is only a summary. The real per-step
    reason (document / selfie / id_number) lives in the last verification
    report, which we fetch here so the frontend can show step-specific
    guidance instead of a generic "retake in bright light" message.
    """
    user_id = (session_obj.get("metadata") or {}).get("user_id")
    if not user_id:
        return
    last_error = session_obj.get("last_error") or {}

    # Fetch the detailed report so we can distinguish document vs selfie
    # failures. Falls back gracefully — if this fails we still store the
    # summary error so the flow isn't blocked.
    document_error: dict | None = None
    selfie_error: dict | None = None
    id_number_error: dict | None = None
    report_id = session_obj.get("last_verification_report")
    if report_id and STRIPE_API_KEY:
        try:
            report = stripe.identity.VerificationReport.retrieve(report_id)
            document_error = (report.get("document") or {}).get("error") or None
            selfie_error = (report.get("selfie") or {}).get("error") or None
            id_number_error = (report.get("id_number") or {}).get("error") or None
        except Exception as e:  # noqa: BLE001
            logger.warning("VerificationReport retrieve failed: %s", e)

    # Prefer the most specific error we found. Selfie failures are the most
    # commonly misdiagnosed as "document quality" issues in the wild — check
    # them first so the frontend gets the right step-specific code.
    resolved_code = last_error.get("code")
    resolved_reason = last_error.get("reason")
    if selfie_error and selfie_error.get("code"):
        resolved_code = selfie_error.get("code")
        resolved_reason = selfie_error.get("reason")
    elif document_error and document_error.get("code"):
        resolved_code = document_error.get("code")
        resolved_reason = document_error.get("reason")
    elif id_number_error and id_number_error.get("code"):
        resolved_code = id_number_error.get("code")
        resolved_reason = id_number_error.get("reason")

    await db.users.update_one(
        {"id": user_id},
        {"$set": {
            "kyc.identity_verification_status": "requires_input",
            "kyc.identity_last_error": {
                "code": resolved_code,
                "reason": resolved_reason,
                "at": iso(now_utc()),
                # Also persist the raw sub-step errors for admin diagnostics
                "step_errors": {
                    "document": document_error,
                    "selfie": selfie_error,
                    "id_number": id_number_error,
                    "session": last_error or None,
                },
            },
        }},
    )
    await audit_write(
        db,
        EventType.KYC_REQUIRES_INPUT,
        user_id=user_id,
        data={
            "session_id": session_obj.get("id"),
            "error_code": resolved_code,
            "error_reason": resolved_reason,
            "selfie_error_code": (selfie_error or {}).get("code"),
            "document_error_code": (document_error or {}).get("code"),
            "id_number_error_code": (id_number_error or {}).get("code"),
        },
    )
