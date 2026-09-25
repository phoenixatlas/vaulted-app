"""Investor one-pager download & lead-capture router.

Product goal:
  Serve a boardroom-ready PDF one-pager summarising Vaulted's reverse-corridor
  unit economics, gated by an email so we can (a) capture the investor lead
  into a dedicated Resend audience and (b) follow up with a data-room invite
  after a soft NDA.

Flow:
  1. Investor submits POST /api/investor/onepager/request with
     {email, name?, company?, note?, meeting_context?}
  2. We record the lead in db.investor_leads (upsert by email so refreshes
     don't create duplicates), fire off a Resend contact-add to the
     "Vaulted Investor Leads" audience, and email them a signed download
     link with a PDF attachment.
  3. Response contains {ok: true, download_url: "/api/investor/onepager/download?token=..."}.
     Frontend triggers download immediately for a delightful UX.
  4. Signed token = HMAC(email + expiry, JWT_SECRET), 24-hour TTL.

Public endpoints:
  POST /api/investor/onepager/request  — capture + return signed download URL
  GET  /api/investor/onepager/download — serves the PDF given a valid token

Admin endpoints (require_admin):
  GET  /api/admin/investor/leads       — list captured leads + counts
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, EmailStr, Field
from io import BytesIO

import asyncio

from deps import db, iso, now_utc, logger, JWT_SECRET, require_admin
from emails import RESEND_API_KEY, send_email_via_resend
from onepager import build_onepager_pdf

router = APIRouter()

# ---- Signed download tokens ---------------------------------------------
# We roll a tiny HMAC-based signer here rather than reuse the auth JWT so a
# stolen investor token can never do anything except download a public PDF.
# 24-hour TTL is generous enough that email delays don't lock investors out.
TOKEN_TTL_SECONDS = 24 * 60 * 60


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _sign_token(email: str, expires_at: int) -> str:
    payload = json.dumps({"e": email.lower(), "x": expires_at}, separators=(",", ":")).encode()
    mac = hmac.new(JWT_SECRET.encode(), payload, hashlib.sha256).digest()
    return f"{_b64url_encode(payload)}.{_b64url_encode(mac)}"


def _verify_token(token: str) -> Optional[str]:
    """Return the email on success, None on any failure."""
    try:
        payload_b, mac_b = token.split(".", 1)
        payload = _b64url_decode(payload_b)
        expected = hmac.new(JWT_SECRET.encode(), payload, hashlib.sha256).digest()
        actual = _b64url_decode(mac_b)
        if not hmac.compare_digest(expected, actual):
            return None
        data = json.loads(payload)
        if int(data.get("x", 0)) < int(time.time()):
            return None
        return data.get("e")
    except Exception:
        return None


# ---- Resend audience for investor leads ---------------------------------
INVESTOR_AUDIENCE_NAME = "Vaulted Investor Leads"


async def _get_or_create_investor_audience() -> Optional[str]:
    """Mongo-cached Resend audience id for investor leads. Same pattern as
    the corridor audiences in routers/waitlist.py — see there for context."""
    if not RESEND_API_KEY:
        return None
    cached = await db.resend_audiences.find_one({"kind": "investor"}, {"_id": 0})
    if cached and cached.get("audience_id"):
        return cached["audience_id"]

    try:
        async with httpx.AsyncClient(timeout=15) as h:
            r = await h.post(
                "https://api.resend.com/audiences",
                headers={
                    "Authorization": f"Bearer {RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={"name": INVESTOR_AUDIENCE_NAME},
            )
            if r.status_code in (200, 201):
                body = r.json() or {}
                aid = body.get("id") or (body.get("data") or {}).get("id")
                if aid:
                    await db.resend_audiences.update_one(
                        {"kind": "investor"},
                        {"$set": {
                            "kind": "investor",
                            "audience_id": aid,
                            "name": INVESTOR_AUDIENCE_NAME,
                            "created_at": iso(now_utc()),
                        }},
                        upsert=True,
                    )
                    return aid
            logger.warning("[investor] audience create failed: %s", r.status_code)
    except Exception as e:  # noqa: BLE001
        logger.warning("[investor] audience create exception: %s", e)
    return None


async def _add_investor_to_resend(email: str, name: str, company: str) -> Optional[str]:
    if not RESEND_API_KEY:
        return None
    audience_id = await _get_or_create_investor_audience()
    endpoint = (
        f"https://api.resend.com/audiences/{audience_id}/contacts"
        if audience_id else "https://api.resend.com/contacts"
    )
    # Encode company tag into the contact record so Resend's dashboard is
    # still useful for skim-reads without an API call.
    company_tag = (company or "").strip()[:60]
    payload = {
        "email": email,
        "unsubscribed": False,
        "first_name": (name or "").strip()[:60],
        "last_name": f"[Investor · {company_tag or 'Independent'}]",
    }
    try:
        async with httpx.AsyncClient(timeout=15) as h:
            r = await h.post(
                endpoint,
                headers={
                    "Authorization": f"Bearer {RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            if r.status_code in (200, 201):
                b = r.json() or {}
                return b.get("id") or (b.get("data") or {}).get("id")
            logger.warning("[investor] contact add %s", r.status_code)
    except Exception as e:  # noqa: BLE001
        logger.warning("[investor] contact add exception: %s", e)
    return None


# ---- Follow-up email (with PDF attached) --------------------------------
async def _email_pdf(email: str, name: str, download_url: str, pdf_bytes: bytes) -> None:
    """Send investor a thank-you email with the PDF attached. Non-fatal:
    logs and returns even if Resend rejects the attachment."""
    greeting = f"Hi {name.split()[0]}," if name and name.split() else "Hi,"
    subject = "Vaulted — reverse-corridor investor one-pager"
    body_html = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 560px; margin: 0 auto; padding: 24px; color: #1a1a1a;">
      <div style="text-align: center; padding: 24px 0;">
        <div style="width: 52px; height: 52px; margin: 0 auto 14px; background: #C9A35B; border-radius: 12px; display: inline-flex; align-items: center; justify-content: center;">
          <span style="color: white; font-size: 22px; font-weight: 700;">V</span>
        </div>
      </div>
      <p style="margin: 0 0 12px;">{greeting}</p>
      <p style="margin: 0 0 12px;">Thanks for the interest in <strong>Vaulted</strong>. The reverse-corridor one-pager is attached.</p>
      <p style="margin: 0 0 12px;">If it would be useful, a quick 20-minute call to walk through the live sandbox demo and Phase-2 rail architecture is our next step:</p>
      <ul style="margin: 0 0 16px; padding-left: 20px; color: #333; font-size: 14px;">
        <li>Live Kotani on-ramp rates for KE and ZA (running now)</li>
        <li>UK/EU payout PSP shortlist &amp; timelines</li>
        <li>Fee waterfall on a real £1,000 send</li>
      </ul>
      <p style="margin: 0 0 12px;">Reply to this email to lock in a slot &mdash; or hit the button below to open the doc in a browser.</p>
      <div style="text-align: center; margin: 24px 0;">
        <a href="{download_url}" style="display: inline-block; background: #C9A35B; color: #0F0B08; padding: 12px 24px; border-radius: 999px; text-decoration: none; font-weight: 700; font-size: 14px;">Open the one-pager</a>
      </div>
      <p style="margin: 24px 0 4px; font-size: 12px; color: #666;">Oumar Sanii &middot; Founder</p>
      <p style="margin: 0; font-size: 12px; color: #666;">Phoenix-Atlas Technologies Ltd &middot; London</p>
    </div>
    """
    if not RESEND_API_KEY:
        logger.info("[investor] RESEND_API_KEY missing — email skipped for %s", email)
        return
    # Resend's public API supports attachments as a top-level field. Send
    # via a raw httpx call because emails.send_email_via_resend doesn't
    # expose the attachments arg.
    try:
        b64_pdf = base64.b64encode(pdf_bytes).decode()
        async with httpx.AsyncClient(timeout=30) as h:
            r = await h.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": "Vaulted <invest@phoenix-atlas.com>",
                    "to": [email],
                    "subject": subject,
                    "html": body_html,
                    "attachments": [{
                        "filename": "Vaulted-Reverse-Corridor-OnePager.pdf",
                        "content": b64_pdf,
                    }],
                },
            )
            if r.status_code >= 300:
                logger.warning("[investor] email send %s: %s", r.status_code, r.text[:300])
                # Fall back to a plain email (no attachment) via the helper
                await send_email_via_resend(email, subject, body_html)
    except Exception as e:  # noqa: BLE001
        logger.warning("[investor] email exception: %s", e)


# ---- Request/response models --------------------------------------------
class InvestorLeadIn(BaseModel):
    email: EmailStr
    name: Optional[str] = Field(default=None, max_length=120)
    company: Optional[str] = Field(default=None, max_length=120)
    role: Optional[str] = Field(default=None, max_length=80)
    note: Optional[str] = Field(default=None, max_length=1000)
    source: Optional[str] = Field(default="landing", max_length=40)


@router.post("/investor/onepager/request")
async def onepager_request(body: InvestorLeadIn, request: Request):
    email = body.email.lower().strip()
    name = (body.name or "").strip()
    company = (body.company or "").strip()
    ip = request.client.host if request.client else ""

    # Upsert into db.investor_leads. Track submission count so we can spot
    # repeat visitors (a proxy for real interest).
    existing = await db.investor_leads.find_one({"email": email}, {"_id": 0})
    now = iso(now_utc())
    await db.investor_leads.update_one(
        {"email": email},
        {
            "$set": {
                "email": email,
                "name": name,
                "company": company,
                "role": (body.role or "").strip(),
                "note": (body.note or "").strip(),
                "source": (body.source or "landing").strip()[:40],
                "last_ip": ip,
                "last_seen_at": now,
            },
            "$setOnInsert": {"first_seen_at": now},
            "$inc": {"downloads": 1},
        },
        upsert=True,
    )

    # Build the signed download URL immediately (works even if the async
    # Resend calls flake out — investor still gets the doc).
    expires_at = int(time.time()) + TOKEN_TTL_SECONDS
    token = _sign_token(email, expires_at)
    download_url = f"/api/investor/onepager/download?token={token}"

    # Fire-and-forget background side effects (Resend + email).
    async def _bg() -> None:
        contact_id = await _add_investor_to_resend(email, name, company)
        if contact_id:
            try:
                await db.investor_leads.update_one(
                    {"email": email}, {"$set": {"resend_contact_id": contact_id}}
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("[investor] persist contact_id failed: %s", e)
        # Build the PDF once, attach to email + used by the download endpoint's cache.
        try:
            pdf_bytes = await build_onepager_pdf(db)
            # Cache the fresh PDF for fast re-download within TTL
            pass  # (Rebuilt on each download for now — PDF gen is < 300ms.)
            # Public URL for the button in the email — use APP_PUBLIC_URL if set.
            from deps import APP_PUBLIC_URL
            public_base = (APP_PUBLIC_URL or "").rstrip("/")
            absolute_url = f"{public_base}{download_url}" if public_base else download_url
            await _email_pdf(email, name, absolute_url, pdf_bytes)
        except Exception as e:  # noqa: BLE001
            logger.warning("[investor] pdf/email background failed: %s", e)

    asyncio.create_task(_bg())

    logger.info(
        "[investor] onepager request email=%s company=%s repeat=%s",
        email, company or "-", bool(existing),
    )
    return {
        "ok": True,
        "already_requested": bool(existing),
        "download_url": download_url,
        "expires_at": expires_at,
    }


@router.get("/investor/onepager/download")
async def onepager_download(token: str = Query(..., min_length=10)):
    email = _verify_token(token)
    if not email:
        raise HTTPException(status_code=403, detail="Download link expired or invalid — please request a new one.")

    # Best-effort: bump the download counter so we can see re-opens.
    try:
        await db.investor_leads.update_one(
            {"email": email},
            {"$inc": {"downloads": 1}, "$set": {"last_download_at": iso(now_utc())}},
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("[investor] download counter bump failed: %s", e)

    pdf_bytes = await build_onepager_pdf(db)
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                'inline; filename="Vaulted-Reverse-Corridor-OnePager.pdf"'
            ),
            "Cache-Control": "private, no-store",
        },
    )


# ---- Admin: leads list --------------------------------------------------
@router.get("/admin/investor/leads")
async def admin_investor_leads(_=Depends(require_admin), limit: int = Query(default=100, ge=1, le=500)):
    total = await db.investor_leads.count_documents({})
    total_repeat = await db.investor_leads.count_documents({"downloads": {"$gte": 2}})
    cursor = db.investor_leads.find({}, {"_id": 0}).sort("last_seen_at", -1).limit(limit)
    rows = await cursor.to_list(length=limit)

    # Company breakdown (top 10)
    company_cursor = db.investor_leads.aggregate([
        {"$match": {"company": {"$nin": [None, ""]}}},
        {"$group": {"_id": "$company", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ])
    top_companies = [
        {"company": r.get("_id"), "count": int(r.get("count", 0))}
        async for r in company_cursor
    ]

    return {
        "total": total,
        "total_repeat_visitors": total_repeat,
        "top_companies": top_companies,
        "leads": rows,
    }
