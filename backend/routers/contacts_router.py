"""Partner contact book — CRUD for recipient contacts per PSB.

Lets admins save the MD / Head of Partnerships / etc. for each bank once,
then auto-fill the use-case dispatcher form with one tap. Simple key-by-
`bank_short` + per-row contact id, no ACL beyond "must be admin".

Shape:
    {
      id: str,                # uuid4
      bank_short: "9PSB",     # upper-case, becomes the group key
      bank_name: str,
      name: str,
      title: Optional[str],
      email: str,
      notes: Optional[str],
      is_primary: bool,       # default to first contact per bank
      created_at, updated_at, created_by, last_used_at
    }
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field

from deps import db
from deps import iso, now_utc
from routers.admin import require_admin  # reuse the admin dependency

router = APIRouter()


def _normalise_short(s: str) -> str:
    return (s or "").strip().upper()[:24] or "UNKNOWN"


class ContactIn(BaseModel):
    bank_short: str = Field(min_length=1, max_length=24)
    bank_name: Optional[str] = Field(default=None, max_length=160)
    name: str = Field(min_length=1, max_length=120)
    title: Optional[str] = Field(default=None, max_length=120)
    email: EmailStr
    notes: Optional[str] = Field(default=None, max_length=400)
    is_primary: bool = False


class ContactPatch(BaseModel):
    bank_name: Optional[str] = Field(default=None, max_length=160)
    name: Optional[str] = Field(default=None, max_length=120)
    title: Optional[str] = Field(default=None, max_length=120)
    email: Optional[EmailStr] = None
    notes: Optional[str] = Field(default=None, max_length=400)
    is_primary: Optional[bool] = None


@router.get("/admin/contacts")
async def list_contacts(
    bank_short: Optional[str] = None,
    _admin=Depends(require_admin),
):
    """List contacts. Filter by `bank_short` to scope to one PSB."""
    q: dict = {}
    if bank_short:
        q["bank_short"] = _normalise_short(bank_short)
    cursor = db.partner_contacts.find(q, {"_id": 0}).sort([
        ("bank_short", 1), ("is_primary", -1), ("name", 1),
    ])
    rows = await cursor.to_list(length=500)
    # Group for the UI — easier to render as sections than filter client-side.
    by_bank: dict[str, list] = {}
    for r in rows:
        by_bank.setdefault(r["bank_short"], []).append(r)
    return {"total": len(rows), "by_bank": by_bank, "contacts": rows}


@router.post("/admin/contacts")
async def create_contact(body: ContactIn, admin=Depends(require_admin)):
    now = iso(now_utc())
    bank_short = _normalise_short(body.bank_short)
    cid = f"ctc_{uuid.uuid4().hex[:16]}"

    doc = {
        "id": cid,
        "bank_short": bank_short,
        "bank_name": body.bank_name or f"{bank_short} Ltd",
        "name": body.name.strip(),
        "title": (body.title or "").strip() or None,
        "email": body.email.lower(),
        "notes": (body.notes or "").strip() or None,
        "is_primary": body.is_primary,
        "created_at": now,
        "updated_at": now,
        "created_by": admin.get("email") if isinstance(admin, dict) else None,
        "last_used_at": None,
    }

    # If marking primary, demote any other primary for that bank.
    if body.is_primary:
        await db.partner_contacts.update_many(
            {"bank_short": bank_short, "is_primary": True},
            {"$set": {"is_primary": False, "updated_at": now}},
        )
    else:
        # If this is the first contact for this bank, promote it to
        # primary so the dispatcher auto-selects it next time.
        existing = await db.partner_contacts.count_documents({"bank_short": bank_short})
        if existing == 0:
            doc["is_primary"] = True

    await db.partner_contacts.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.patch("/admin/contacts/{contact_id}")
async def patch_contact(contact_id: str, body: ContactPatch, _admin=Depends(require_admin)):
    existing = await db.partner_contacts.find_one({"id": contact_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Contact not found")

    updates: dict = {"updated_at": iso(now_utc())}
    for field in ("bank_name", "name", "title", "email", "notes"):
        v = getattr(body, field)
        if v is not None:
            updates[field] = v.strip() if isinstance(v, str) else v

    if body.is_primary is True:
        # Demote others before promoting this one.
        await db.partner_contacts.update_many(
            {"bank_short": existing["bank_short"], "is_primary": True, "id": {"$ne": contact_id}},
            {"$set": {"is_primary": False, "updated_at": updates["updated_at"]}},
        )
        updates["is_primary"] = True
    elif body.is_primary is False:
        updates["is_primary"] = False

    await db.partner_contacts.update_one({"id": contact_id}, {"$set": updates})
    doc = await db.partner_contacts.find_one({"id": contact_id}, {"_id": 0})
    return doc


@router.delete("/admin/contacts/{contact_id}")
async def delete_contact(contact_id: str, _admin=Depends(require_admin)):
    result = await db.partner_contacts.delete_one({"id": contact_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Contact not found")
    return {"ok": True, "deleted": contact_id}


@router.post("/admin/contacts/{contact_id}/touch")
async def touch_contact(contact_id: str, _admin=Depends(require_admin)):
    """Bump `last_used_at` when the dispatcher auto-fills from this contact.
    Used by the admin UI to sort "most recently used" at the top of the
    picker without manual tagging."""
    row = await db.partner_contacts.find_one_and_update(
        {"id": contact_id},
        {"$set": {"last_used_at": iso(now_utc())}},
        return_document=True,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Contact not found")
    return {"ok": True}
