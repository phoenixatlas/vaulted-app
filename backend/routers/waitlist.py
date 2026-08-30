"""Public waitlist router — landing-page signups.

Wires the landing-page "Join the waitlist" form to Resend Contacts so
leads land in our ESP instead of a `mailto:` fallback. Also stores a
copy in Mongo `waitlist` collection (belt-and-braces — we own the list
too and can export/re-import at will if we ever switch ESPs).

Endpoint:
    POST /api/waitlist/join
        body: {"email": "you@example.com", "source"?: "landing"}
        response: {"ok": true, "already_joined": bool}

Rate-limit + abuse:
    - Simple in-memory per-IP dedupe (same IP within RATE_WINDOW_SEC → 429).
    - No bot-CAPTCHA yet (Cloudflare in front of Render already blocks
      the worst offenders). We can add hCaptcha later if the volume
      requires it.

Confirmation email:
    - Sent via existing Resend transactional path. Reply-to points to
      umar.sani@phoenix-atlas.com so users can reach a human.
    - Fire-and-forget: email failure never bubbles up to the caller.

Resend API (as of Aug 2026):
    POST https://api.resend.com/contacts
    body: {email, first_name?, last_name?, unsubscribed: false}
    Audience_id is deprecated — contacts are now global. Segments can
    be added later from the Resend dashboard.

Docs: https://resend.com/docs/api-reference/contacts/create-contact
"""
from __future__ import annotations

import asyncio
import re
import time
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from deps import db, iso, logger, now_utc
from emails import RESEND_API_KEY, get_resend_from, send_email_via_resend

router = APIRouter()

# ---- Simple in-memory rate limit (per-IP) ---------------------------------
# 1 signup per IP per 5 seconds. Enough to stop naive form-refresh spam;
# real DDoS is handled upstream. Dict is process-local; that's fine for
# our single-worker Render deployment.
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
    """Extract client IP, honouring Render / Cloudflare X-Forwarded-For."""
    fwd = request.headers.get("x-forwarded-for") or ""
    if fwd:
        # left-most is the original client
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ---- Resend Contacts helper -----------------------------------------------
async def _add_resend_contact(email: str, source: str) -> Optional[str]:
    """Add contact to Resend. Returns Resend's contact id on success, None
    on failure (never raises — waitlist join is best-effort with Resend).
    """
    if not RESEND_API_KEY:
        logger.warning("[waitlist] RESEND_API_KEY missing — skipping Resend add")
        return None
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0)) as cx:
            r = await cx.post(
                "https://api.resend.com/contacts",
                headers={
                    "Authorization": f"Bearer {RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "email": email,
                    "unsubscribed": False,
                    # Tag the acquisition source in the contact metadata so
                    # we can segment later ("landing", "referral", etc.).
                    # Resend accepts arbitrary custom fields on contacts.
                    "first_name": "",
                    "last_name": f"[waitlist:{source}]",
                },
            )
            if r.status_code == 201 or r.status_code == 200:
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
_CONFIRMATION_HTML = """\
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 560px; margin: 0 auto; padding: 24px; color: #1a1a1a;">
  <div style="text-align: center; padding: 32px 0 24px;">
    <div style="width: 56px; height: 56px; margin: 0 auto 16px; background: #C9A35B; border-radius: 14px; display: inline-flex; align-items: center; justify-content: center;">
      <span style="color: white; font-size: 24px; font-weight: 700;">V</span>
    </div>
    <h1 style="font-size: 22px; font-weight: 700; margin: 0 0 8px; color: #1a1a1a;">Welcome to the Vaulted waitlist.</h1>
    <p style="color: #666; margin: 0; font-size: 14px;">Thanks for signing up — we'll be in touch.</p>
  </div>

  <div style="background: #FAF7F1; border-radius: 12px; padding: 20px; margin: 24px 0; border-left: 3px solid #C9A35B;">
    <p style="margin: 0 0 12px; font-size: 15px; line-height: 1.6;"><strong>What happens next?</strong></p>
    <ul style="margin: 0; padding-left: 20px; font-size: 14px; line-height: 1.7; color: #333;">
      <li>You'll get one email the moment your corridor goes live.</li>
      <li>No spam. No card required.</li>
      <li>Early waitlisters get first access to send-side subsidies.</li>
    </ul>
  </div>

  <p style="font-size: 14px; line-height: 1.6; color: #333; margin: 24px 0 12px;">
    Vaulted is a UK fintech in build. We're currently in <strong>waitlist mode</strong> ahead of authorization from the Financial Conduct Authority (FCA). Meantime you can explore the preview app — everything works except real settlement.
  </p>

  <div style="text-align: center; margin: 28px 0 16px;">
    <a href="https://app.phoenix-atlas.com" style="display: inline-block; background: #C9A35B; color: white; text-decoration: none; padding: 12px 28px; border-radius: 999px; font-weight: 600; font-size: 14px;">Preview the app →</a>
  </div>

  <hr style="border: none; border-top: 1px solid #EAE5D8; margin: 32px 0 16px;">
  <p style="font-size: 12px; color: #999; text-align: center; margin: 0;">
    Questions? Reply to this email — a human will get back to you.<br>
    Phoenix Atlas Ltd · UK Company No. registered<br>
    <a href="https://app.phoenix-atlas.com/risk-disclosure.html" style="color: #C9A35B;">Cryptoasset risk disclosure</a>
  </p>
</div>
"""


async def _send_confirmation_email(email: str) -> None:
    try:
        await send_email_via_resend(email, _CONFIRMATION_SUBJECT, _CONFIRMATION_HTML)
    except Exception as e:  # noqa: BLE001
        logger.warning("[waitlist] confirmation email failed for %s: %s", email, e)


# ---- Request model --------------------------------------------------------
class WaitlistJoinIn(BaseModel):
    email: EmailStr
    source: Optional[str] = Field(default="landing", max_length=40)


# Rough regex for last-line email sanity in case pydantic EmailStr is missing.
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


@router.post("/waitlist/join")
async def waitlist_join(body: WaitlistJoinIn, request: Request):
    email = str(body.email).strip().lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Invalid email address")

    ip = _client_ip(request)
    if _too_fast(ip):
        raise HTTPException(status_code=429, detail="Slow down — one submission at a time.")

    ua = (request.headers.get("user-agent") or "")[:200]
    source = (body.source or "landing").strip()[:40]

    # Upsert into Mongo. `already_joined` = existed before this call.
    existing = await db.waitlist.find_one({"email": email}, {"_id": 0, "email": 1})
    already_joined = bool(existing)

    now = iso(now_utc())
    doc_set = {
        "email": email,
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

    # Fire-and-forget: add to Resend + send confirmation email in parallel.
    # We DO wait for these so we can surface a partial-failure signal in
    # logs, but they're wrapped so no failure ever fails the HTTP call —
    # the visitor sees "you're on the list" as long as we saved to Mongo.
    if not already_joined:
        asyncio.create_task(_add_and_confirm(email, source))

    logger.info("[waitlist] joined email=%s source=%s already=%s", email, source, already_joined)
    return {"ok": True, "already_joined": already_joined}


async def _add_and_confirm(email: str, source: str) -> None:
    """Background task — Resend contact add + confirmation email."""
    contact_id = await _add_resend_contact(email, source)
    if contact_id:
        try:
            await db.waitlist.update_one(
                {"email": email},
                {"$set": {"resend_contact_id": contact_id}},
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("[waitlist] persist resend_contact_id failed: %s", e)
    await _send_confirmation_email(email)
