"""E2E encryption public-key registry. Very thin - stores and returns
NaCl box public keys keyed by user_id. Used by chat/send-crypto flows to
encrypt payloads client-to-client so the server can't read them.

Extracted from server.py during the P2 refactor.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from deps import db, get_current_user
from models import RegisterKeyIn

router = APIRouter()


@router.post("/keys/register")
async def register_public_key(body: RegisterKeyIn, user=Depends(get_current_user)):
    """Persist the caller's NaCl box public key so others can encrypt to them.
    Idempotent - safe to call on every app launch."""
    if len(body.public_key) > 512:
        raise HTTPException(status_code=400, detail="Public key too long")
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"public_key": body.public_key}},
    )
    return {"public_key": body.public_key}


@router.get("/keys/{user_id}")
async def get_public_key(user_id: str, _=Depends(get_current_user)):
    """Look up another user's E2E public key. Auth-gated but not scoped to
    a specific relationship - any authenticated user can look up any other
    user's public key (that's the point of a public key)."""
    u = await db.users.find_one({"id": user_id}, {"_id": 0, "public_key": 1, "id": 1, "name": 1})
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    return {"id": u["id"], "public_key": u.get("public_key")}
