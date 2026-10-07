"""Weekly Settlement Digest — admin routes.

See `digest.py` for the data pipeline and HTML renderer. These endpoints
are the UI's keyboard: toggle enabled, add/remove recipients, preview
the next send, trigger a one-off, and expose a cron sink for external
schedulers (Render Cron, GitHub Actions, UptimeRobot) that cannot carry
an admin JWT.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from deps import require_admin, logger
from digest import (
    build_weekly_digest_html,
    collect_digest_data,
    digest_scheduler_tick,
    get_digest_config,
    send_weekly_digest,
    set_digest_config,
    verify_cron_secret,
)

router = APIRouter()


class DigestConfigIn(BaseModel):
    enabled: Optional[bool] = None
    recipients: Optional[List[EmailStr]] = None
    send_weekday: Optional[int] = Field(default=None, ge=0, le=6)
    send_hour_utc: Optional[int] = Field(default=None, ge=0, le=23)


@router.get("/admin/digest/config")
async def digest_config_get(_admin=Depends(require_admin)):
    """Return the current digest config + last-sent summary. Hydrates
    defaults if the config doc hasn't been persisted yet so the UI always
    has something sensible to render on first load."""
    return await get_digest_config()


@router.post("/admin/digest/config")
async def digest_config_set(
    payload: DigestConfigIn,
    _admin=Depends(require_admin),
):
    """Partial update — only the fields present in the payload are mutated.
    `recipients` fully replaces the stored list."""
    return await set_digest_config(
        enabled=payload.enabled,
        recipients=[str(r) for r in payload.recipients] if payload.recipients is not None else None,
        send_weekday=payload.send_weekday,
        send_hour_utc=payload.send_hour_utc,
    )


@router.get("/admin/digest/preview")
async def digest_preview(
    days: int = 7,
    _admin=Depends(require_admin),
):
    """Return the subject + HTML that *would* be sent right now. Used by
    the admin UI's preview pane and by operators for debugging the
    renderer without wasting a Resend quota slot."""
    days = max(1, min(days, 30))
    data = await collect_digest_data(days=days)
    subject, html = build_weekly_digest_html(data)
    return {"subject": subject, "html": html, "data": data}


class SendNowIn(BaseModel):
    recipients: Optional[List[EmailStr]] = None
    days: int = Field(default=7, ge=1, le=30)


@router.post("/admin/digest/send-now")
async def digest_send_now(
    payload: SendNowIn,
    _admin=Depends(require_admin),
):
    """Fire the digest immediately. Falls back to configured recipients
    when `recipients` is omitted. Logs to `digest_log` either way."""
    return await send_weekly_digest(
        recipients=[str(r) for r in payload.recipients] if payload.recipients else None,
        days=payload.days,
        reason="manual",
    )


@router.post("/admin/digest/cron")
async def digest_cron(request: Request):
    """External cron sink. Must carry `X-Vaulted-Cron-Secret` matching
    `DIGEST_CRON_SECRET` env var. Idempotent — the scheduler tick
    gates on `last_sent_at` so repeated hits in the same window are no-ops."""
    secret = request.headers.get("X-Vaulted-Cron-Secret") or request.query_params.get("secret")
    if not verify_cron_secret(secret):
        raise HTTPException(status_code=401, detail="Invalid or missing cron secret")
    result = await digest_scheduler_tick()
    logger.info("[digest] cron tick: %s", result)
    return result


@router.get("/admin/digest/log")
async def digest_log(
    limit: int = 20,
    _admin=Depends(require_admin),
):
    """Recent send history — useful when the UI needs to show a
    'last 5 digests' timeline."""
    from deps import db
    limit = max(1, min(limit, 100))
    rows = await db.digest_log.find({}, {"_id": 0}).sort("sent_at", -1).limit(limit).to_list(length=limit)
    return {"rows": rows, "total": await db.digest_log.count_documents({})}
