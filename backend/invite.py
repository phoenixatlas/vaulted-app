"""Beta invite code — one shared, admin-configurable code for NEW sign-ups.

Existing accounts and login are untouched. The code is checked only on the
server (never shipped in the app bundle) with a timing-safe comparison.
It is stored in plain text in `db.config{_id:"invite"}` because admins need
to read it back to share it with testers; it is a low-value shared secret,
not a credential.
"""
from __future__ import annotations

import hmac
import os
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from deps import db, iso, now_utc, require_admin

router = APIRouter()
DEFAULT_CODE = os.environ.get("BETA_INVITE_CODE", "VAULTED-BETA")


def _norm(code: Optional[str]) -> str:
    return (code or "").strip().upper()


async def get_invite_cfg() -> dict:
    doc = await db.config.find_one({"_id": "invite"}, {"_id": 0}) or {}
    return {"enabled": doc.get("enabled", True), "code": doc.get("code") or DEFAULT_CODE,
            "updated_at": doc.get("updated_at")}


async def invite_ok(supplied: Optional[str]) -> bool:
    cfg = await get_invite_cfg()
    if not cfg["enabled"]:
        return True
    return hmac.compare_digest(_norm(supplied).encode(), _norm(cfg["code"]).encode())


class InviteIn(BaseModel):
    code: Optional[str] = Field(default=None, min_length=4, max_length=40, pattern=r"^[A-Za-z0-9-]+$")
    enabled: Optional[bool] = None


@router.get("/auth/invite-required")
async def invite_required():
    return {"required": (await get_invite_cfg())["enabled"]}


@router.get("/admin/invite")
async def admin_get_invite(_admin=Depends(require_admin)):
    cfg = await get_invite_cfg()
    used = await db.users.count_documents({"invited_with": {"$exists": True}})
    return {**cfg, "signups_with_code": used}


@router.put("/admin/invite")
async def admin_set_invite(body: InviteIn, admin=Depends(require_admin)):
    patch: dict = {"updated_at": iso(now_utc()), "updated_by": admin.get("email")}
    if body.code is not None:
        patch["code"] = _norm(body.code)
    if body.enabled is not None:
        patch["enabled"] = body.enabled
    await db.config.update_one({"_id": "invite"}, {"$set": patch}, upsert=True)
    return await admin_get_invite(admin)
