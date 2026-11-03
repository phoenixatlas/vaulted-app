"""Partner / business enquiries from phoenix-atlas.com/business.

Stores each lead in `partner_enquiries` and emails the operator team
(waitlist alert recipients, falling back to ADMIN_EMAILS).
"""
import asyncio
import html
import os
import time
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from brand import brand_logo_img
from deps import ADMIN_EMAILS, db, iso, logger, now_utc, require_admin
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
    # Rightmost X-Forwarded-For hop is added by our own ingress (client can't spoof it).
    ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "")).split(",")[-1].strip()
    now = time.time()
    if now - _last_by_ip.get(ip, 0) < 30:
        raise HTTPException(status_code=429, detail="Please wait a moment before sending another enquiry.")
    if len(_last_by_ip) > 5000:
        _last_by_ip.clear()
    _last_by_ip[ip] = now

    lead = {
        "id": str(uuid.uuid4()), "name": body.name.strip(), "email": body.email.lower(),
        "company": body.company.strip(), "corridor": body.corridor.strip(),
        "partner_type": body.partner_type if body.partner_type in PARTNER_TYPES else "other",
        "message": (body.message or "").strip(), "status": "new", "created_at": iso(now_utc()),
    }
    await db.partner_enquiries.insert_one(dict(lead))

    asyncio.create_task(_send_lead_emails(lead))
    return {"ok": True, "id": lead["id"]}


async def _send_lead_emails(lead: dict) -> None:
    """Operator alert + branded auto-reply, sent in the background."""
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
    try:
        await send_email_via_resend(lead["email"], "Thanks for your enquiry — Vaulted", _auto_reply_html(e),
                                    text=f"Hi {lead['name']}, thanks for contacting Vaulted about {lead['corridor']}. "
                                         "The founder will reply personally within 2 working days. — Phoenix-Atlas Technologies Ltd")
    except Exception as ex:  # noqa: BLE001
        logger.warning("[partners] auto-reply failed: %s", ex)


def _auto_reply_html(e: dict) -> str:
    first = e["name"].split()[0] if e["name"] else "there"
    return f"""<div style="background:#0A0807;padding:32px 16px;font-family:Inter,Arial,sans-serif;">
  <div style="max-width:560px;margin:0 auto;background:#161210;border:1px solid #2A221C;border-radius:18px;padding:32px;color:#F5EDDF;">
    {brand_logo_img(64)}
    <h1 style="font-family:Georgia,serif;font-weight:600;font-size:26px;color:#E8D4A8;text-align:center;margin:0 0 18px;">Thanks, {first}.</h1>
    <p style="font-size:15px;line-height:1.6;color:#CFC3B0;">We&rsquo;ve received your partnership enquiry for <b style="color:#F5EDDF;">{e['company']}</b>
      about the <b style="color:#F5EDDF;">{e['corridor']}</b> corridor. The founder reads every enquiry and will reply personally within 2 working days.</p>
    <p style="font-size:15px;line-height:1.6;color:#CFC3B0;">In the meantime you can book a 20-minute call or read more about how we work with partners:</p>
    <p style="text-align:center;margin:24px 0;"><a href="https://www.phoenix-atlas.com/business" style="background:#C9A35B;color:#0F0B08;text-decoration:none;font-weight:700;padding:14px 26px;border-radius:999px;display:inline-block;">Partner information &rarr;</a></p>
    <p style="font-size:12px;line-height:1.6;color:#8A7F70;border-top:1px solid #2A221C;padding-top:16px;margin-top:24px;">
      Vaulted is built by Phoenix-Atlas Technologies Ltd, registered in England and Wales (Company No. 17432346). Vaulted is not currently authorized by the FCA and is not open for customer transactions.
      Reply to this email or write to hello@phoenix-atlas.com.</p>
  </div>
</div>"""


class LeadStatusIn(BaseModel):
    status: str = Field(pattern="^(new|contacted|closed)$")


@router.get("/admin/partners")
async def list_partner_enquiries(_admin=Depends(require_admin)):
    rows = await db.partner_enquiries.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)
    counts = {s: await db.partner_enquiries.count_documents({"status": s}) for s in ("new", "contacted", "closed")}
    return {"enquiries": rows, "total": await db.partner_enquiries.count_documents({}), "counts": counts}


@router.patch("/admin/partners/{lead_id}")
async def update_partner_enquiry(lead_id: str, body: LeadStatusIn, admin=Depends(require_admin)):
    res = await db.partner_enquiries.update_one(
        {"id": lead_id}, {"$set": {"status": body.status, "updated_at": iso(now_utc()), "updated_by": admin.get("email")}})
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Enquiry not found")
    return {"id": lead_id, "status": body.status}
