"""Public waitlist router — landing-page signups with corridor segmentation.

Wires the landing-page "Join the waitlist" form to Resend Contacts so
leads land in your ESP + a Mongo `waitlist` collection (belt-and-braces —
we own the list too and can export/re-import at will if we ever switch ESPs).

Endpoints:
    POST /api/waitlist/join
        body: {"email": "you@example.com", "corridor"?: "KE",
               "source"?: "landing"}
        response: {"ok": true, "already_joined": bool}

    GET /api/waitlist/stats   (admin-only)
        response: {"total": 42, "by_corridor": {"KE": 12, "GH": 8, ...}}

Corridor segmentation:
    Users pick a target destination country at signup (KE, GH, NG, UG, TZ,
    ZM, XX for "other/coming soon"). We:
      1. Persist the corridor on the Mongo waitlist doc (source of truth)
      2. Auto-create-if-missing a per-corridor Resend Audience ("Vaulted
         Waitlist – Kenya", etc.) and add the contact to it
    That means when Kenya goes live you can send a corridor-specific launch
    email to just the Kenya audience from the Resend dashboard — one click.

Rate-limit + abuse:
    - Simple in-memory per-IP dedupe (same IP within RATE_WINDOW_SEC → 429)
    - No bot-CAPTCHA yet (Cloudflare upstream blocks the worst offenders)

Docs: https://resend.com/docs/api-reference/audiences/create-audience
      https://resend.com/docs/api-reference/contacts/create-contact
"""
from __future__ import annotations

import asyncio
import re
import time
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from deps import db, iso, logger, now_utc
from emails import RESEND_API_KEY, send_email_via_resend

router = APIRouter()

# ---- Corridor catalogue ---------------------------------------------------
# Keep in sync with the landing page `<select>` and the KOTANI_CORRIDORS
# map on the remit screen. `XX` is the escape hatch for users whose
# corridor isn't in the list yet.
CORRIDORS: dict[str, str] = {
    "KE": "Kenya",
    "GH": "Ghana",
    "NG": "Nigeria",
    "UG": "Uganda",
    "TZ": "Tanzania",
    "ZM": "Zambia",
    "ZA": "South Africa",
    "XX": "Other / Coming soon",
}


def _normalize_corridor(value: Optional[str]) -> str:
    v = (value or "").strip().upper()[:2]
    if v in CORRIDORS:
        return v
    return "XX"


# ---- Rate limit (per-IP) --------------------------------------------------
_RATE_WINDOW_SEC = 5
_last_seen_by_ip: dict[str, float] = {}


def _too_fast(ip: str) -> bool:
    now = time.time()
    last = _last_seen_by_ip.get(ip)
    _last_seen_by_ip[ip] = now
    if last is None:
        return False
    return (now - last) < _RATE_WINDOW_SEC


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for") or ""
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ---- Resend Audience routing ---------------------------------------------
# Per-corridor audience id cache (Mongo-backed for durability across restarts).
# Keys: {"corridor": "KE"} → {"corridor": "KE", "audience_id": "aud_...",
#                             "name": "Vaulted Waitlist – Kenya",
#                             "created_at": iso}
async def _get_or_create_corridor_audience(corridor: str) -> Optional[str]:
    """Return the Resend audience id for the given corridor, creating it
    on-demand the first time it's needed. Cached in Mongo (durable across
    process restarts) so we never re-create.

    Returns None on any failure — caller falls back to plain `POST /contacts`.
    """
    if not RESEND_API_KEY:
        return None
    if corridor not in CORRIDORS:
        corridor = "XX"

    cached = await db.resend_audiences.find_one({"corridor": corridor}, {"_id": 0})
    if cached and cached.get("audience_id"):
        return cached["audience_id"]

    name = f"Vaulted Waitlist – {CORRIDORS[corridor]}"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0)) as cx:
            r = await cx.post(
                "https://api.resend.com/audiences",
                headers={
                    "Authorization": f"Bearer {RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={"name": name},
            )
            if r.status_code in (200, 201):
                body = r.json() or {}
                # Resend returns {id, name, object, created_at}
                aid = body.get("id") or (body.get("data") or {}).get("id")
                if aid:
                    await db.resend_audiences.update_one(
                        {"corridor": corridor},
                        {"$set": {
                            "corridor": corridor,
                            "audience_id": aid,
                            "name": name,
                            "created_at": iso(now_utc()),
                        }},
                        upsert=True,
                    )
                    logger.info("[waitlist] created resend audience %s → %s", corridor, aid)
                    return aid
            logger.warning("[waitlist] audience create %s: %s", r.status_code, r.text[:300])
            return None
    except Exception as e:  # noqa: BLE001
        logger.warning("[waitlist] audience create exception: %s", e)
        return None


async def _add_resend_contact(email: str, source: str, corridor: str) -> Optional[str]:
    """Add contact to the corridor-specific Resend audience. Falls back
    to Resend's global contacts endpoint if audience creation fails.
    Returns Resend's contact id on success, None on failure (never raises).
    """
    if not RESEND_API_KEY:
        logger.warning("[waitlist] RESEND_API_KEY missing — skipping Resend add")
        return None

    audience_id = await _get_or_create_corridor_audience(corridor)

    # If we have an audience, use the per-audience endpoint so the contact
    # is properly slotted for future corridor blasts. Otherwise fall back
    # to the global endpoint (still captures the lead in Resend).
    if audience_id:
        endpoint = f"https://api.resend.com/audiences/{audience_id}/contacts"
    else:
        endpoint = "https://api.resend.com/contacts"

    # Encode acquisition source + corridor in a Resend-visible field so
    # you can eyeball corridor mix from the dashboard even without an API
    # call (Resend's public contact schema is limited to first_name /
    # last_name / email — no arbitrary metadata yet).
    payload = {
        "email": email,
        "unsubscribed": False,
        "first_name": "",
        "last_name": f"[{corridor} · {source}]",
    }

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0)) as cx:
            r = await cx.post(
                endpoint,
                headers={
                    "Authorization": f"Bearer {RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            if r.status_code in (200, 201):
                data = (r.json() or {}).get("data") or r.json() or {}
                return data.get("id")
            # 422 = duplicate email — treat as success (already on list).
            if r.status_code == 422 and "already exists" in r.text.lower():
                logger.info("[waitlist] resend duplicate for %s — ok", email)
                return None
            logger.warning("[waitlist] resend contact create %s: %s", r.status_code, r.text[:300])
            return None
    except Exception as e:  # noqa: BLE001
        logger.warning("[waitlist] resend contact exception: %s", e)
        return None


# ---- Confirmation email ---------------------------------------------------
_CONFIRMATION_SUBJECT = "You're on the Vaulted waitlist ✨"


def _confirmation_html(corridor: str) -> str:
    """Corridor-personalized confirmation email. The subject and shell
    are constant; only the corridor line changes."""
    corridor_line = ""
    if corridor and corridor != "XX":
        corridor_line = (
            f'<p style="margin: 0 0 12px; font-size: 14px; color: #666;">'
            f'We\u2019ve tagged you as interested in the '
            f'<strong>{CORRIDORS.get(corridor, corridor)}</strong> corridor '
            f'\u2014 you\u2019ll be the first to know when we go live there.</p>'
        )
    return (
        '<div style="font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, sans-serif; max-width: 560px; margin: 0 auto; padding: 24px; color: #1a1a1a;">'
        '<div style="text-align: center; padding: 32px 0 24px;">'
        '<div style="width: 56px; height: 56px; margin: 0 auto 16px; background: #C9A35B; border-radius: 14px; display: inline-flex; align-items: center; justify-content: center;">'
        '<span style="color: white; font-size: 24px; font-weight: 700;">V</span>'
        '</div>'
        '<h1 style="font-size: 22px; font-weight: 700; margin: 0 0 8px; color: #1a1a1a;">Welcome to the Vaulted waitlist.</h1>'
        '<p style="color: #666; margin: 0; font-size: 14px;">Thanks for signing up \u2014 we\u2019ll be in touch.</p>'
        f'{corridor_line}'
        '</div>'
        '<div style="background: #FAF7F1; border-radius: 12px; padding: 20px; margin: 24px 0; border-left: 3px solid #C9A35B;">'
        '<p style="margin: 0 0 12px; font-size: 15px; line-height: 1.6;"><strong>What happens next?</strong></p>'
        '<ul style="margin: 0; padding-left: 20px; font-size: 14px; line-height: 1.7; color: #333;">'
        '<li>You\u2019ll get one email the moment your corridor goes live.</li>'
        '<li>No spam. No card required.</li>'
        '<li>Early waitlisters get first access to send-side subsidies.</li>'
        '</ul>'
        '</div>'
        '<p style="font-size: 14px; line-height: 1.6; color: #333; margin: 24px 0 12px;">'
        'Vaulted is a UK fintech in build. We\u2019re currently in <strong>waitlist mode</strong> ahead of authorization from the Financial Conduct Authority (FCA). Meantime you can explore the preview app \u2014 everything works except real settlement.'
        '</p>'
        '<div style="text-align: center; margin: 28px 0 16px;">'
        '<a href="https://app.phoenix-atlas.com" style="display: inline-block; background: #C9A35B; color: white; text-decoration: none; padding: 12px 28px; border-radius: 999px; font-weight: 600; font-size: 14px;">Preview the app \u2192</a>'
        '</div>'
        '<hr style="border: none; border-top: 1px solid #EAE5D8; margin: 32px 0 16px;">'
        '<p style="font-size: 12px; color: #999; text-align: center; margin: 0;">'
        'Questions? Reply to this email \u2014 a human will get back to you.<br>'
        'Phoenix-Atlas Technologies Ltd \u00b7 UK Company No. 17432346<br>'
        '<a href="https://app.phoenix-atlas.com/risk-disclosure.html" style="color: #C9A35B;">Cryptoasset risk disclosure</a>'
        '</p>'
        '</div>'
    )


async def _send_confirmation_email(email: str, corridor: str) -> None:
    try:
        await send_email_via_resend(email, _CONFIRMATION_SUBJECT, _confirmation_html(corridor))
    except Exception as e:  # noqa: BLE001
        logger.warning("[waitlist] confirmation email failed for %s: %s", email, e)


# ---- Request model --------------------------------------------------------
class WaitlistJoinIn(BaseModel):
    email: EmailStr
    corridor: Optional[str] = Field(default=None, max_length=2)
    source: Optional[str] = Field(default="landing", max_length=40)


_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


@router.post("/waitlist/join")
async def waitlist_join(body: WaitlistJoinIn, request: Request):
    email = str(body.email).strip().lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Invalid email address")

    ip = _client_ip(request)
    if _too_fast(ip):
        raise HTTPException(status_code=429, detail="Slow down — one submission at a time.")

    corridor = _normalize_corridor(body.corridor)
    ua = (request.headers.get("user-agent") or "")[:200]
    source = (body.source or "landing").strip()[:40]

    existing = await db.waitlist.find_one({"email": email}, {"_id": 0, "email": 1, "corridor": 1})
    already_joined = bool(existing)

    now = iso(now_utc())
    doc_set = {
        "email": email,
        "corridor": corridor,
        "corridor_name": CORRIDORS[corridor],
        "source": source,
        "updated_at": now,
        "last_ip": ip,
        "last_user_agent": ua,
    }
    doc_setoninsert = {"joined_at": now}
    await db.waitlist.update_one(
        {"email": email},
        {"$set": doc_set, "$setOnInsert": doc_setoninsert},
        upsert=True,
    )

    # Background: Resend audience add + confirmation email. Only fire once
    # per email — a re-submit with the same corridor should be a no-op.
    # If the user CHANGES corridor on a re-submit we still re-process so
    # they end up in the right audience.
    should_process = (
        not already_joined
        or (existing and existing.get("corridor") != corridor)
    )
    if should_process:
        asyncio.create_task(_add_and_confirm(email, source, corridor))

    logger.info(
        "[waitlist] joined email=%s corridor=%s source=%s already=%s",
        email, corridor, source, already_joined,
    )
    return {"ok": True, "already_joined": already_joined, "corridor": corridor}


async def _add_and_confirm(email: str, source: str, corridor: str) -> None:
    """Background task — Resend contact add + confirmation email."""
    contact_id = await _add_resend_contact(email, source, corridor)
    if contact_id:
        try:
            await db.waitlist.update_one(
                {"email": email},
                {"$set": {"resend_contact_id": contact_id}},
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("[waitlist] persist resend_contact_id failed: %s", e)
    await _send_confirmation_email(email, corridor)


# ---- Admin stats ----------------------------------------------------------
# Small helper endpoint so ops can eyeball corridor mix without opening
# Mongo directly. Admin-guarded via the same require_admin dep every other
# admin route uses.
try:  # avoid a hard import at module top so a missing admin dep doesn't
    # break the whole router — the endpoint just won't register.
    from deps import require_admin

    @router.get("/waitlist/stats")
    async def waitlist_stats(_=Depends(require_admin)):
        """Corridor breakdown of the waitlist. Admin-only."""
        total = await db.waitlist.count_documents({})
        # Mongo aggregation: group by corridor.
        cursor = db.waitlist.aggregate([
            {"$group": {"_id": "$corridor", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ])
        by_corridor: dict[str, int] = {}
        async for row in cursor:
            key = row.get("_id") or "XX"
            by_corridor[key] = int(row.get("count", 0))
        # Pretty-name each corridor for the admin dashboard.
        breakdown = [
            {
                "corridor": k,
                "corridor_name": CORRIDORS.get(k, k),
                "count": v,
            }
            for k, v in by_corridor.items()
        ]
        return {
            "total": total,
            "by_corridor": by_corridor,
            "breakdown": breakdown,
            "corridors": CORRIDORS,
        }
except ImportError:
    pass
