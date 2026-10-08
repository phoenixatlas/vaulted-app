"""Admin routes — compliance health, manual EDD approval, sanctions
screening, and audit-log queries. All routes are gated by
`require_admin` (checks against ADMIN_EMAILS on the deployment).

Extracted from server.py during the P2 refactor.
"""
from __future__ import annotations

import hashlib
import os
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

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
# ADMIN — Kotani webhook echo (last ~20 raw deliveries)
# ============================================================================
# Primary use case: diagnosing "nothing is firing from the Kotani dashboard"
# complaints. Every POST to /api/offramp/callback is persisted to
# `kotani_webhook_log` by the webhook handler (bounded to 100 rows). This
# endpoint surfaces the latest 20 so operators can:
#   • Confirm Kotani actually posts to our URL (signature header, event
#     name, raw body)
#   • Compare observed signature header vs. our expected format
#   • Spot a misconfigured service (e.g. `transaction.deposit.*` arriving
#     when they only expected `transaction.offramp.*`)
#   • Replay a payload via curl against staging without having to wait
#     for Kotani to re-fire
#
# Also returns the exact URL + required env vars so the operator can copy
# it straight into the Kotani dashboard without hunting through infra.
@router.get("/admin/kotani/webhook-echo")
async def admin_kotani_webhook_echo(_admin=Depends(require_admin)):
    """Return the last ~20 raw Kotani webhook deliveries + the public URL
    Kotani should be posting to. Used by operators to debug dashboard
    config before go-live."""
    import os
    import kotani

    public_url = (os.environ.get("APP_PUBLIC_URL") or "").rstrip("/")
    expected_webhook_url = f"{public_url}/api/offramp/callback" if public_url else None

    # Classify the host so the UI can warn operators when they're pointing
    # Kotani at an ephemeral preview URL instead of a stable production host.
    host_type = "unset"
    host_label = "⚠ APP_PUBLIC_URL not set"
    host_warning: Optional[str] = (
        "Set APP_PUBLIC_URL on your hosting provider to the backend's "
        "public HTTPS base URL, then redeploy."
    )
    if public_url:
        lowered = public_url.lower()
        if "emergentagent.com" in lowered or "preview" in lowered:
            host_type = "preview"
            host_label = "Emergent preview"
            host_warning = (
                "This is an Emergent preview URL. Fine for sandbox testing "
                "today, but switch to your permanent Render / production URL "
                "before go-live — preview hosts can rotate."
            )
        elif "onrender.com" in lowered or "render.com" in lowered:
            host_type = "render"
            host_label = "Render (production)"
            host_warning = None
        elif "localhost" in lowered or "127.0.0.1" in lowered or ".local" in lowered:
            host_type = "localhost"
            host_label = "Localhost (unreachable by Kotani)"
            host_warning = (
                "Kotani cannot reach localhost. Use ngrok / cloudflared for "
                "local testing, or deploy to Render first."
            )
        else:
            host_type = "custom"
            host_label = "Custom domain"
            host_warning = None

    rows = await db.kotani_webhook_log \
        .find({}, {"_id": 0}) \
        .sort("received_at", -1) \
        .limit(20).to_list(length=20)

    diag = kotani.diagnostic_info()
    recommended_events = [
        "transaction.offramp.status.updated",
        "transaction.onramp.status.updated",
        "transaction.deposit.status.updated",
        "transaction.withdrawal.status.updated",
        "kyc.status.changed",
        "refund.completed",
        "refund.failed",
    ]

    # Quick counters so the UI can show "No deliveries yet" vs. "Last was
    # 3h ago" without re-scanning the full array.
    total = await db.kotani_webhook_log.count_documents({})
    bad_sig = await db.kotani_webhook_log.count_documents({"signature_valid": False})

    return {
        "expected_webhook_url": expected_webhook_url,
        "host_type": host_type,
        "host_label": host_label,
        "host_warning": host_warning,
        "diagnostic": diag,
        "config_checklist": {
            "webhook_url_registered": bool(total > 0),
            "signature_valid_count": total - bad_sig,
            "signature_invalid_count": bad_sig,
            "webhook_secret_configured": diag.get("webhook_secret_configured"),
            "api_key_configured": diag.get("api_key_configured"),
            "mode": diag.get("mode"),
        },
        "recommended_events": recommended_events,
        "total_received": total,
        "deliveries": rows,
        "setup_hint": (
            "In the Kotani integrator dashboard: Settings → Webhooks → "
            f"paste {expected_webhook_url or '<set APP_PUBLIC_URL>'} as the "
            "endpoint, select the recommended events, save the signing "
            "secret to KOTANI_WEBHOOK_SECRET in your backend env, redeploy, "
            "then pull-to-refresh this screen."
        ),
    }


# ============================================================================
# ADMIN — Dev-only: fire a mock Kotani webhook at ourselves
# ============================================================================
# Nice for proving the dispatcher works end-to-end before Kotani is
# actually configured. Builds a canonical signed envelope (if secret is
# configured) or a direct-callback body (if not), then POSTs it to our
# own /api/offramp/callback — same code path a real Kotani delivery hits.
@router.post("/admin/kotani/webhook-echo/replay")
async def admin_kotani_webhook_replay(
    body: Optional[dict] = None,
    _admin=Depends(require_admin),
):
    """Replay a synthetic offramp SUCCESSFUL event through our live
    webhook handler. If `body` is provided it's used verbatim; otherwise
    we fabricate a canonical v3 offramp success envelope.

    Returns the HTTP status, parsed response, and any db side-effects so
    the operator can confirm the dispatcher updated a tx.
    """
    import json as _json
    import os
    import hmac as _hmac
    import hashlib as _hashlib
    import httpx

    public_url = (os.environ.get("APP_PUBLIC_URL") or "").rstrip("/")
    if not public_url:
        raise HTTPException(status_code=400, detail="APP_PUBLIC_URL not set")

    envelope = body or {
        "event": "transaction.offramp.status.updated",
        "data": {
            "referenceId": "kp_replay_demo",
            "status": "SUCCESSFUL",
            "onchainStatus": "SUCCESSFUL",
            "fiatAmount": 5000,
            "fiatTransactionAmount": 4850,
            "cryptoAmount": 38.5,
            "fiatCurrency": "KES",
            "customerKey": "cust_mock_replay",
            "senderAddress": "0xabc123",
            "escrowAddress": "0xescrow",
            "telcoId": "MPESA-REPLAY-XYZ",
            "transactionHash": "0xdef456",
        },
    }

    secret = os.environ.get("KOTANI_WEBHOOK_SECRET", "")
    canonical = _json.dumps(
        {"event": envelope.get("event"), "data": envelope.get("data")},
        ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8")

    headers = {"Content-Type": "application/json"}
    if secret:
        sig = _hmac.new(secret.encode(), canonical, _hashlib.sha256).hexdigest()
        headers["X-Kotani-Signature"] = f"sha256={sig}"
        headers["X-Kotani-Event"] = envelope["event"]
        envelope["signature"] = f"sha256={sig}"

    url = f"{public_url}/api/offramp/callback"
    async with httpx.AsyncClient(timeout=15.0) as cx:
        r = await cx.post(url, content=_json.dumps(envelope), headers=headers)

    try:
        parsed = r.json()
    except Exception:  # noqa: BLE001
        parsed = {"raw": r.text[:600]}

    return {
        "posted_to": url,
        "status_code": r.status_code,
        "response": parsed,
        "envelope_sent": envelope,
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



# ============================================================================
# ADMIN — Kotani end-to-end smoke test
# ============================================================================
# Validates the entire offramp stack in a single tap: rate quote → customer
# create → booking → status poll. The caller gets step-by-step pass/fail so
# they can see exactly which Kotani permission is still missing when things
# are blocked. All side effects (db writes, external calls) are tagged as
# `source: "smoke-test"` so they're trivially filterable.
#
# Design calls:
#   • No real USDC moves — we book the smallest possible fiat amount
#     (1 unit of local fiat) and we don't disburse. Kotani holds the
#     booking in `PENDING` until the referenceId naturally times out.
#   • Each step runs independently; one failure doesn't block the next.
#     That's crucial because the common "insufficient permissions" error
#     on rate-quote shouldn't prevent us from testing customer-create.
#   • The response shape stays small + flat so the admin UI renders it
#     as a stepper without recursion.
@router.post("/admin/kotani/smoke-test")
async def admin_kotani_smoke_test(
    corridor: str = "KE",
    _admin=Depends(require_admin),
):
    """Run a full offramp dry-run against Kotani. Returns per-step results."""
    import time
    import kotani

    corridor = (corridor or "KE").upper()
    # Pick a reasonable test configuration per corridor. These match the
    # live Kotani sandbox corridors documented at
    # https://documentation.kotanipay.com/v3/corridors
    corridor_config = {
        "KE": {"currency": "KES", "country": "KE", "mobile": "254712345678", "crypto_amount": 0.5, "name": "Smoke Test KE", "network": "MPESA"},
        "NG": {"currency": "NGN", "country": "NG", "mobile": "2348012345678", "crypto_amount": 0.5, "name": "Smoke Test NG", "network": "MTN"},
        "GH": {"currency": "GHS", "country": "GH", "mobile": "233501234567", "crypto_amount": 0.5, "name": "Smoke Test GH", "network": "MTN"},
        "UG": {"currency": "UGX", "country": "UG", "mobile": "256701234567", "crypto_amount": 0.5, "name": "Smoke Test UG", "network": "MTN"},
        "TZ": {"currency": "TZS", "country": "TZ", "mobile": "255712345678", "crypto_amount": 0.5, "name": "Smoke Test TZ", "network": "VODACOM"},
        "ZA": {"currency": "ZAR", "country": "ZA", "mobile": "27712345678", "crypto_amount": 0.5, "name": "Smoke Test ZA", "network": "MTN"},
    }
    cfg = corridor_config.get(corridor)
    if not cfg:
        raise HTTPException(status_code=400, detail=f"Unsupported corridor {corridor}")

    started = time.perf_counter()
    steps: list[dict] = []

    def _step(name: str, call: str) -> dict:
        return {"name": name, "call": call, "ok": False, "ms": 0, "detail": None, "error": None}

    def _finish(step: dict, *, ok: bool, detail: Any = None, error: Optional[str] = None, t0: float = 0.0):
        step["ok"] = ok
        step["ms"] = round((time.perf_counter() - t0) * 1000, 1)
        if detail is not None:
            step["detail"] = detail
        if error is not None:
            step["error"] = error[:400]  # cap error payload size
        steps.append(step)

    # ---- Step 1: Health check -----------------------------------------
    s1 = _step("Health check", "GET /health")
    t0 = time.perf_counter()
    try:
        health = await kotani.health()
        # Kotani v3 nests the status under `data.status`; older sandbox
        # builds returned it flat. Accept both.
        nested_status = (health or {}).get("data", {}).get("status") if isinstance(health, dict) else None
        flat_status = (health or {}).get("status") if isinstance(health, dict) else None
        ok = bool(
            (health or {}).get("ok")
            or (health or {}).get("success")
            or nested_status in {"ok", "healthy", "OK", "up"}
            or flat_status in {"ok", "healthy", "OK", "up"}
        )
        _finish(s1, ok=ok, detail={"status": nested_status or flat_status}, t0=t0)
    except Exception as e:  # noqa: BLE001
        _finish(s1, ok=False, error=str(e), t0=t0)

    # ---- Step 2: Rate quote -------------------------------------------
    s2 = _step("Rate quote", "POST /api/v3/rate/offramp")
    t0 = time.perf_counter()
    rate_quote = None
    rate_id = None
    try:
        rate_quote = await kotani.offramp_rate(
            from_token="USDC",
            to_currency=cfg["currency"],
            crypto_amount=cfg["crypto_amount"],
        )
        rate_id = kotani.extract_rate_id(rate_quote)
        ok = bool(rate_id)
        _finish(s2, ok=ok, detail={
            "rate_id": rate_id,
            "fiat_amount": kotani.extract_fiat_amount(rate_quote),
            "currency": cfg["currency"],
        }, t0=t0)
    except Exception as e:  # noqa: BLE001
        _finish(s2, ok=False, error=str(e), t0=t0)

    # ---- Step 3: Customer create --------------------------------------
    s3 = _step("Customer create", "POST /api/v3/customer/mobile-money")
    t0 = time.perf_counter()
    customer = None
    customer_key = None
    try:
        customer = await kotani.create_mobile_money_customer(
            phone_number=cfg["mobile"],
            country_code=cfg["country"],
            network=cfg["network"],
            first_name="Smoke",
            last_name=f"Test {corridor}",
            account_name=cfg["name"],
        )
        customer_key = kotani.extract_customer_key(customer)
        ok = bool(customer_key)
        # Surface Kotani's error payload when there's no key — this is
        # how we show "integratorEnabled: false" blocking messages so
        # ops can forward them to Kotani support.
        detail = {"customer_key": customer_key}
        if not ok and isinstance(customer, dict):
            detail["kotani_error"] = (
                customer.get("message")
                or (customer.get("data") or {}).get("message")
                or customer.get("error")
                or "No customerKey returned — service likely disabled on your account"
            )
            detail["raw"] = {k: v for k, v in customer.items() if k != "success"}
        _finish(s3, ok=ok, detail=detail, t0=t0)
    except Exception as e:  # noqa: BLE001
        _finish(s3, ok=False, error=str(e), t0=t0)

    # ---- Step 4: Offramp booking (DRY RUN — PENDING, no disbursal) ----
    s4 = _step("Offramp booking", "POST /api/v3/offramp (dry-run)")
    t0 = time.perf_counter()
    try:
        if not customer_key:
            raise RuntimeError("Skipped — no customerKey from previous step")
        if not rate_id:
            raise RuntimeError("Skipped — no rateId from previous step")
        booking = await kotani.create_offramp(
            crypto_amount=cfg["crypto_amount"],
            currency=cfg["currency"],
            chain="POLYGON",
            token="USDC",
            reference_id=f"smoke_{corridor.lower()}_{int(time.time())}",
            customer_key=customer_key,
            rate_id=rate_id,
            sender_address="0x0000000000000000000000000000000000000001",
            callback_url=f"{(os.environ.get('APP_PUBLIC_URL') or '').rstrip('/')}/api/offramp/callback",
        )
        ref_id = (booking or {}).get("data", {}).get("referenceId")
        ok = bool(ref_id)
        _finish(s4, ok=ok, detail={
            "reference_id": ref_id,
            "status": (booking or {}).get("data", {}).get("status"),
            "escrow_address": (booking or {}).get("data", {}).get("escrowAddress"),
        }, t0=t0)
    except Exception as e:  # noqa: BLE001
        _finish(s4, ok=False, error=str(e), t0=t0)

    # ---- Step 5: Dispatcher self-test (fire a synthetic webhook) ------
    s5 = _step("Dispatcher self-test", "POST /api/offramp/callback (replay)")
    t0 = time.perf_counter()
    try:
        import json as _json
        import hmac as _hmac
        import hashlib as _hashlib
        import httpx

        public_url = (os.environ.get("APP_PUBLIC_URL") or "").rstrip("/")
        secret = os.environ.get("KOTANI_WEBHOOK_SECRET", "")
        envelope = {
            "event": "transaction.offramp.status.updated",
            "data": {
                "referenceId": f"smoke_dispatch_{int(time.time())}",
                "status": "SUCCESSFUL",
                "fiatAmount": 100,  # synthetic; dispatcher only cares about structure
                "fiatCurrency": cfg["currency"],
                "telcoId": "SMOKE-TEST-MPESA",
            },
        }
        canonical = _json.dumps({"event": envelope["event"], "data": envelope["data"]},
                                ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if secret:
            sig = _hmac.new(secret.encode(), canonical, _hashlib.sha256).hexdigest()
            headers["X-Kotani-Signature"] = f"sha256={sig}"
            headers["X-Kotani-Event"] = envelope["event"]
            envelope["signature"] = f"sha256={sig}"

        async with httpx.AsyncClient(timeout=15.0) as cx:
            r = await cx.post(f"{public_url}/api/offramp/callback",
                              content=_json.dumps(envelope), headers=headers)
        resp = {}
        try:
            resp = r.json()
        except Exception:
            resp = {"raw": r.text[:200]}
        _finish(s5, ok=(r.status_code == 200), detail={"status_code": r.status_code, "response": resp}, t0=t0)
    except Exception as e:  # noqa: BLE001
        _finish(s5, ok=False, error=str(e), t0=t0)

    passed = sum(1 for s in steps if s["ok"])
    overall_ms = round((time.perf_counter() - started) * 1000, 1)
    verdict = (
        "all_green" if passed == len(steps)
        else "partial" if passed > 0
        else "all_failed"
    )
    return {
        "corridor": corridor,
        "verdict": verdict,
        "passed": passed,
        "total": len(steps),
        "elapsed_ms": overall_ms,
        "steps": steps,
        "started_at": iso(now_utc()),
    }


# ============================================================================
# ADMIN — Live settlement view (daily rollup of offramp activity)
# ============================================================================
# Aggregates settled offramp transactions by day so operators can see:
#   • Total crypto out (USDC / USDT)
#   • Total fiat delivered (KES / NGN / GHS / etc.)
#   • USD-equivalent value (approximated via tx-level rate)
#   • Reconciliation delta: what we expected to deliver (quoted fiat)
#     vs. what Kotani actually settled (fiat_transaction_amount).
#     A persistent delta > 0.5% is the early-warning signal for a
#     corridor rate drift or a Kotani fee change.
#
# This endpoint does the aggregation inline on Mongo. Fine for our volume
# today (few hundred tx/day target); if we hit >50k/day we move it to a
# materialised view with a daily cron.
@router.get("/admin/kotani/settlements")
async def admin_kotani_settlements(
    days: int = 30,
    _admin=Depends(require_admin),
):
    """Return per-day settlement rollup for the last `days` days. Caps at 90."""
    from datetime import datetime as _dt, timedelta as _td, timezone as _tz
    from collections import defaultdict

    days = max(1, min(days or 30, 90))
    since = _dt.now(_tz.utc) - _td(days=days)

    # Pull only settled offramp txs with a kotani reference — anything
    # else can't be a settlement for this view. Project just the fields
    # we aggregate on to keep the cursor light.
    cursor = db.transactions.find(
        {
            "status": "settled",
            "kotani.reference_id": {"$exists": True},
            "kotani.settled_at": {"$gte": since.isoformat()},
        },
        {
            "_id": 0, "id": 1, "amount_crypto": 1, "amount_fiat": 1,
            "token": 1, "fiat_currency": 1, "rate": 1, "corridor": 1,
            "kotani": 1, "created_at": 1,
        },
    )

    daily: dict[str, dict] = defaultdict(lambda: {
        "date": None,
        "tx_count": 0,
        "crypto_sent": defaultdict(float),       # by token symbol
        "fiat_delivered": defaultdict(float),    # by fiat currency
        "usd_equivalent": 0.0,
        "quoted_total": defaultdict(float),
        "settled_total": defaultdict(float),
        "corridors": defaultdict(int),
        "sample_tx_ids": [],
    })

    corridor_total: dict[str, int] = defaultdict(int)
    overall = {
        "tx_count": 0,
        "crypto_sent": defaultdict(float),
        "fiat_delivered": defaultdict(float),
        "usd_equivalent": 0.0,
    }

    async for tx in cursor:
        k = tx.get("kotani") or {}
        settled_at = k.get("settled_at") or tx.get("created_at")
        try:
            day_key = _dt.fromisoformat(settled_at.replace("Z", "+00:00")).date().isoformat()
        except Exception:
            day_key = "unknown"

        row = daily[day_key]
        row["date"] = day_key
        row["tx_count"] += 1
        overall["tx_count"] += 1

        token = (tx.get("token") or "USDC").upper()
        fiat_cur = (tx.get("fiat_currency") or k.get("fiat_currency") or "???").upper()
        corridor = (tx.get("corridor") or "??").upper()
        corridor_total[corridor] += 1
        row["corridors"][corridor] += 1

        amount_crypto = float(tx.get("amount_crypto") or 0)
        quoted_fiat = float(tx.get("amount_fiat") or 0)
        settled_fiat = float(k.get("fiat_transaction_amount") or quoted_fiat or 0)
        # For USDC/USDT, 1 token ≈ 1 USD. Any other asset would need a
        # live spot rate — out of scope for now.
        usd_eq = amount_crypto if token in {"USDC", "USDT", "DAI"} else 0.0

        row["crypto_sent"][token] += amount_crypto
        row["fiat_delivered"][fiat_cur] += settled_fiat
        row["quoted_total"][fiat_cur] += quoted_fiat
        row["settled_total"][fiat_cur] += settled_fiat
        row["usd_equivalent"] += usd_eq

        overall["crypto_sent"][token] += amount_crypto
        overall["fiat_delivered"][fiat_cur] += settled_fiat
        overall["usd_equivalent"] += usd_eq

        if len(row["sample_tx_ids"]) < 5:
            row["sample_tx_ids"].append(tx.get("id"))

    # Collapse defaultdicts → plain dicts + compute reconciliation delta
    rows_out = []
    for day_key, row in sorted(daily.items(), reverse=True):
        reconciliation = []
        for cur, quoted in row["quoted_total"].items():
            settled = row["settled_total"].get(cur, 0.0)
            delta = settled - quoted
            pct = (delta / quoted * 100) if quoted > 0 else 0.0
            reconciliation.append({
                "currency": cur,
                "quoted": round(quoted, 2),
                "settled": round(settled, 2),
                "delta": round(delta, 2),
                "delta_pct": round(pct, 3),
            })
        rows_out.append({
            "date": row["date"],
            "tx_count": row["tx_count"],
            "crypto_sent": {k: round(v, 6) for k, v in row["crypto_sent"].items()},
            "fiat_delivered": {k: round(v, 2) for k, v in row["fiat_delivered"].items()},
            "usd_equivalent": round(row["usd_equivalent"], 2),
            "corridors": dict(row["corridors"]),
            "reconciliation": reconciliation,
            "sample_tx_ids": row["sample_tx_ids"],
        })

    return {
        "window_days": days,
        "since": since.isoformat(),
        "overall": {
            "tx_count": overall["tx_count"],
            "crypto_sent": {k: round(v, 6) for k, v in overall["crypto_sent"].items()},
            "fiat_delivered": {k: round(v, 2) for k, v in overall["fiat_delivered"].items()},
            "usd_equivalent": round(overall["usd_equivalent"], 2),
            "corridor_breakdown": dict(corridor_total),
        },
        "daily": rows_out,
    }


# ============================================================================
# ADMIN — One-click PSB use case email dispatcher
# ============================================================================
# Sends the branded 2-page PSB use case PDF as a Resend attachment with
# Umar's cover email. Every send is logged to `usecase_sends` so the
# admin UI can show a history ("sent 02 Oct to MD @ 9PSB · delivered") and
# correlate reply tracking via Resend webhooks.
#
# Design notes:
#   • `reply_to` defaults to `umar.sani@phoenix-atlas.com` so every reply
#     lands in Umar's personal inbox — the recipient never sees `noreply`.
#   • We attach a Resend `tag` with the send_id so delivery / open / click
#     webhooks posted to `/api/admin/usecase/resend-webhook` can be
#     correlated to the source send row for reply tracking.
#   • Idempotency: if `send_id` is provided by the client we honour it;
#     otherwise we mint a uuid4 so retries from a flaky network don't
#     fire duplicate emails if the client is well-behaved.
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import List
import re as _re


def _split_recipients(raw: str) -> list[str]:
    """Split an operator-pasted recipient string into clean, deduped
    emails. We accept any mix of commas, semicolons, whitespace or
    newlines — same forgiveness operators get in Gmail's To field —
    then validate each individually and preserve order."""
    if not raw:
        return []
    parts = [p.strip() for p in _re.split(r"[,;\s]+", str(raw)) if p and p.strip()]
    seen: set[str] = set()
    out: list[str] = []
    # Loose check — the actual EmailStr validation happens below, this
    # is just to catch obviously malformed segments early so the user
    # sees a sharp error message that names the offender.
    EMAIL_RE = _re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    for p in parts:
        low = p.lower()
        if low in seen:
            continue
        if not EMAIL_RE.match(p):
            raise ValueError(f"not a valid email: {p!r}")
        seen.add(low)
        out.append(p)
    return out


class UseCaseSendIn(BaseModel):
    # String rather than EmailStr so operators can paste comma-separated
    # lists directly ("foo@bar.com, baz@qux.com"). Validated into a
    # cleaned list by the field_validator below.
    recipient_email: str = Field(..., max_length=2000)
    recipient_name: str = Field(default="", max_length=120)
    recipient_title: Optional[str] = Field(default=None, max_length=120)
    bank_short: str = Field(default="9PSB", max_length=24)
    bank_name: Optional[str] = Field(default=None, max_length=160)
    recipient_address_1: Optional[str] = Field(default=None, max_length=160)
    recipient_address_2: Optional[str] = Field(default=None, max_length=160)
    cover_note: Optional[str] = Field(default=None, max_length=2000)
    cc: Optional[List[str]] = Field(default=None)
    subject_override: Optional[str] = Field(default=None, max_length=200)
    booking_url: Optional[str] = Field(default=None, max_length=400)
    send_id: Optional[str] = Field(default=None, max_length=64)

    @field_validator("recipient_email")
    @classmethod
    def _validate_recipients(cls, v: str) -> str:
        # Trigger split+validate at parse time so a malformed segment
        # fails with a specific message rather than letting Resend
        # bounce the whole send later.
        _split_recipients(v)
        return v

    def recipient_list(self) -> list[str]:
        return _split_recipients(self.recipient_email)


@router.post("/admin/usecase/send")
async def admin_usecase_send(
    payload: UseCaseSendIn,
    admin=Depends(require_admin),
):
    """One-click dispatch of the PSB use case PDF via Resend.

    Accepts a single email OR a comma/semicolon-separated list in
    `recipient_email`. Each recipient receives their own personalised
    send (same subject, same PDF) so individual deliverability and
    open/click tracking stays per-person.

    Returns `{ok, send_id, status}` for a single-recipient call for
    back-compat, and `{ok, batch, results: [...]}` when multiple
    recipients were supplied.
    """
    import uuid
    from datetime import datetime as _dt, timezone as _tz
    import usecase
    from emails import send_email_via_resend_with_attachment

    recipients = payload.recipient_list()
    if not recipients:
        raise HTTPException(status_code=422, detail="recipient_email is empty")

    # Build the attached PDF once — identical across every recipient so
    # we save CPU + guarantee all recipients get the exact same file.
    pdf_overrides = {
        "bank_short": payload.bank_short,
        "bank_name": payload.bank_name,
        "recipient_name": payload.recipient_name or "The Managing Director",
        "recipient_title": payload.recipient_title,
        "recipient_address_1": payload.recipient_address_1,
        "recipient_address_2": payload.recipient_address_2,
    }
    pdf_overrides = {k: v for k, v in pdf_overrides.items() if v}
    try:
        pdf_bytes = usecase.build_psb_usecase_pdf(**pdf_overrides)
    except Exception as e:  # noqa: BLE001
        logger.exception("[usecase-send] PDF build failed: %s", e)
        raise HTTPException(status_code=500, detail=f"PDF build failed: {e}")

    html = usecase.build_usecase_cover_html(
        recipient_name=payload.recipient_name or payload.bank_short,
        bank_short=payload.bank_short,
        bank_name=payload.bank_name,
        cover_note=payload.cover_note,
        booking_url=payload.booking_url,
    )
    subject = (
        payload.subject_override
        or f"Vaulted — Strategic Use Case for {payload.bank_short}"
    )
    filename = f"Vaulted-UseCase-{payload.bank_short.replace(' ', '-')}.pdf"

    base_send_id = payload.send_id or f"ucs_{uuid.uuid4().hex[:16]}"

    results: list[dict] = []
    for idx, rcpt in enumerate(recipients):
        # Mint a unique send_id per recipient so analytics stays
        # per-person and Resend webhook correlations work. Preserve
        # idempotency: a client that supplied `send_id` ends up with
        # deterministic sub-ids too.
        send_id = base_send_id if len(recipients) == 1 else f"{base_send_id}_{idx+1}"

        # Guard against accidental duplicate sends from double-click.
        existing = await db.usecase_sends.find_one({"send_id": send_id}, {"_id": 0})
        if existing and existing.get("status") in {"sent", "delivered"}:
            results.append({
                "ok": True,
                "recipient": rcpt,
                "send_id": send_id,
                "already_sent": True,
                "resend_id": existing.get("resend_id"),
                "sent_at": existing.get("sent_at"),
            })
            continue

        tags = [
            {"name": "artefact", "value": "psb_usecase"},
            {"name": "send_id", "value": send_id},
            {"name": "bank_short", "value": payload.bank_short.lower()},
        ]

        result = await send_email_via_resend_with_attachment(
            to=rcpt,
            subject=subject,
            html=html,
            attachment_bytes=pdf_bytes,
            attachment_filename=filename,
            cc=payload.cc or None,
            tags=tags,
        )

        now = _dt.now(_tz.utc).isoformat()
        status = "sent" if result.get("ok") else "failed"
        row = {
            "send_id": send_id,
            "resend_id": result.get("resend_id"),
            "status": status,
            "error": result.get("error"),
            "sent_at": now if status == "sent" else None,
            "attempted_at": now,
            "sent_by": admin.get("email") if isinstance(admin, dict) else None,
            "recipient_email": rcpt,
            "recipient_name": payload.recipient_name,
            "recipient_title": payload.recipient_title,
            "bank_short": payload.bank_short,
            "bank_name": payload.bank_name or f"{payload.bank_short} Ltd",
            "subject": subject,
            "cover_note_present": bool(payload.cover_note),
            "cc": payload.cc or [],
            "delivered_at": None,
            "opened_at": None,
            "clicked_at": None,
            "last_event_at": now,
            "events": [],
            "batch_id": base_send_id if len(recipients) > 1 else None,
        }
        await db.usecase_sends.update_one(
            {"send_id": send_id}, {"$set": row}, upsert=True
        )

        results.append({
            "ok": bool(result.get("ok")),
            "recipient": rcpt,
            "send_id": send_id,
            "resend_id": result.get("resend_id"),
            "status": status,
            "error": result.get("error"),
            "sent_at": now if status == "sent" else None,
        })

    # Back-compat response for single-recipient callers so existing
    # UI tests / integrations keep passing.
    if len(results) == 1:
        r = results[0]
        return {
            "ok": r["ok"],
            "send_id": r["send_id"],
            "resend_id": r.get("resend_id"),
            "status": r.get("status"),
            "sent_at": r.get("sent_at"),
            "error": r.get("error"),
            "already_sent": r.get("already_sent", False),
        }

    sent_count = sum(1 for r in results if r["ok"])
    return {
        "ok": sent_count == len(results),
        "batch": base_send_id,
        "sent_count": sent_count,
        "failed_count": len(results) - sent_count,
        "results": results,
    }


@router.get("/admin/usecase/sends")
async def admin_usecase_sends(
    limit: int = 25,
    _admin=Depends(require_admin),
):
    """List recent use-case email dispatches with their current delivery
    status (populated by the Resend webhook)."""
    limit = max(1, min(limit, 100))
    rows = await db.usecase_sends \
        .find({}, {"_id": 0, "events": 0}) \
        .sort("attempted_at", -1) \
        .limit(limit).to_list(length=limit)
    total = await db.usecase_sends.count_documents({})
    sent = await db.usecase_sends.count_documents({"status": {"$in": ["sent", "delivered"]}})
    delivered = await db.usecase_sends.count_documents({"delivered_at": {"$ne": None}})
    opened = await db.usecase_sends.count_documents({"opened_at": {"$ne": None}})
    return {
        "total": total,
        "sent_count": sent,
        "delivered_count": delivered,
        "opened_count": opened,
        "rows": rows,
    }


@router.post("/admin/usecase/resend-webhook")
async def admin_usecase_resend_webhook(request: Request):
    """Resend webhook sink — correlates delivery / open / click events to
    our `usecase_sends` rows via the `send_id` tag.

    Resend posts: `{type, created_at, data: {email_id, to, tags: [...]}}`
    The `tags` list carries our `send_id` for look-up.
    """
    try:
        body = await request.json()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")

    etype = (body.get("type") or "").strip()
    data = body.get("data") or {}
    tags = data.get("tags") or []
    send_id = None
    for t in tags if isinstance(tags, list) else []:
        if isinstance(t, dict) and t.get("name") == "send_id":
            send_id = t.get("value")
            break
    if not send_id:
        logger.info("[usecase-webhook] event w/o send_id tag: %s", etype)
        return {"ok": True, "handled": "no_send_id"}

    from datetime import datetime as _dt, timezone as _tz
    now = _dt.now(_tz.utc).isoformat()
    updates: dict = {"last_event_at": now}
    if etype == "email.delivered":
        updates["delivered_at"] = now
        updates["status"] = "delivered"
    elif etype == "email.opened":
        updates["opened_at"] = now
    elif etype == "email.clicked":
        updates["clicked_at"] = now
    elif etype == "email.bounced":
        updates["status"] = "bounced"
        updates["bounce_reason"] = (data.get("reason") or "")[:200]
    elif etype == "email.complained":
        updates["status"] = "complained"

    event_log = {
        "type": etype,
        "at": now,
        "resend_event": data.get("email_id"),
    }
    await db.usecase_sends.update_one(
        {"send_id": send_id},
        {"$set": updates, "$push": {"events": event_log}},
    )
    return {"ok": True, "send_id": send_id, "event": etype}

