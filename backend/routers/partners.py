"""Partner / business enquiries from phoenix-atlas.com/business.

Stores each lead in `partner_enquiries` and emails the operator team
(waitlist alert recipients, falling back to ADMIN_EMAILS).
"""
import html
import os
import time
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from deps import ADMIN_EMAILS, db, iso, logger, now_utc
from emails import send_email_via_resend

router = APIRouter()

PARTNER_TYPES = {"payment_bank", "psp_emi", "offramp", "mobile_money", "liquidity", "other"}
_last_by_ip: dict = {}


class PartnerEnquiryIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    company: str = Field(min_length=1, max_length=160)
    partner_type: str = "other"
    corridor: str = Field(min_length=1, max_length=120)
    message: Optional[str] = Field(default="", max_length=2000)
    website: Optional[str] = ""  # honeypot — real users never fill it


async def _recipients() -> list:
    cfg = await db.waitlist_alert_config.find_one({"_id": "signup_alert"}) or {}
    rec = cfg.get("recipients") or [r.strip() for r in os.environ.get("WAITLIST_ALERT_RECIPIENTS", "").split(",") if "@" in r]
    return rec or list(ADMIN_EMAILS)


@router.post("/partners/enquiry")
async def partner_enquiry(body: PartnerEnquiryIn, request: Request):
    if body.website:
        return {"ok": True}  # silently drop bots
    ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "")).split(",")[0].strip()
    if time.time() - _last_by_ip.get(ip, 0) < 30:
        raise HTTPException(status_code=429, detail="Please wait a moment before sending another enquiry.")
    _last_by_ip[ip] = time.time()

    lead = {
        "id": str(uuid.uuid4()), "name": body.name.strip(), "email": body.email.lower(),
        "company": body.company.strip(), "corridor": body.corridor.strip(),
        "partner_type": body.partner_type if body.partner_type in PARTNER_TYPES else "other",
        "message": (body.message or "").strip(), "status": "new", "created_at": iso(now_utc()),
    }
    await db.partner_enquiries.insert_one(dict(lead))

    e = {k: html.escape(str(v)) for k, v in lead.items()}
    page = (
        f"<h2>New partner enquiry — {e['company']}</h2>"
        f"<p><b>Name:</b> {e['name']}<br><b>Email:</b> <a href='mailto:{e['email']}'>{e['email']}</a><br>"
        f"<b>Company:</b> {e['company']}<br><b>Type:</b> {e['partner_type'].replace('_', ' ')}<br>"
        f"<b>Corridor:</b> {e['corridor']}</p>"
        f"<p><b>Message:</b><br>{e['message'] or '—'}</p>"
    )
    for to in await _recipients():
        try:
            await send_email_via_resend(to, f"Partner lead: {lead['company']} · {lead['corridor']}", page,
                                        text=f"{lead['name']} ({lead['email']}) from {lead['company']} — {lead['corridor']}")
        except Exception as ex:  # noqa: BLE001
            logger.warning("[partners] alert email failed: %s", ex)
    return {"ok": True, "id": lead["id"]}
