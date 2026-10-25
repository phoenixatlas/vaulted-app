"""Saved recipients — people a user sends money to repeatedly.

Recipients are saved after a send goes through (when the sender leaves the
"Save recipient" box ticked). One row per (user, country, account), so
re-sending to the same person just bumps `last_used_at`.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from deps import db, get_current_user, iso, now_utc

router = APIRouter()


async def save_recipient(user_id: str, *, name: str, country_code: str, currency: str, account: str,
                         rail: str, bank_id: Optional[str] = None, bank_name: Optional[str] = None,
                         verified: bool = False) -> None:
    """Upsert a recipient for this user. Never raises."""
    account = (account or "").strip()
    if not account or not (name or "").strip():
        return
    now = iso(now_utc())
    await db.recipients.update_one(
        {"user_id": user_id, "country_code": country_code.upper(), "account": account},
        {
            "$set": {
                "name": name.strip(), "currency": currency, "rail": rail,
                "bank_id": bank_id, "bank_name": bank_name, "verified": verified, "last_used_at": now,
            },
            "$setOnInsert": {"id": str(uuid.uuid4()), "user_id": user_id, "created_at": now},
            "$inc": {"send_count": 1},
        },
        upsert=True,
    )


@router.get("/recipients")
async def list_recipients(country: Optional[str] = None, user=Depends(get_current_user)):
    q: dict = {"user_id": user["id"]}
    if country:
        q["country_code"] = country.upper()
    rows = await db.recipients.find(q, {"_id": 0, "user_id": 0}).sort("last_used_at", -1).limit(50).to_list(50)
    return {"recipients": rows}


@router.delete("/recipients/{recipient_id}")
async def delete_recipient(recipient_id: str, user=Depends(get_current_user)):
    res = await db.recipients.delete_one({"id": recipient_id, "user_id": user["id"]})
    if not res.deleted_count:
        raise HTTPException(status_code=404, detail="Recipient not found")
    return {"ok": True}
