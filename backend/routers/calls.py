"""Daily.co video-call routes. A single endpoint that spins up a private
room + meeting token on-demand. Falls back to a clear "configure key"
stub if DAILY_API_KEY isn't set on the deployment.

Extracted from server.py during the P2 refactor.
"""
from __future__ import annotations

import secrets
from datetime import timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException

from deps import DAILY_API_KEY, get_current_user, now_utc
from models import CallRoomIn

router = APIRouter()


@router.post("/calls/room")
async def create_call_room(body: CallRoomIn, user=Depends(get_current_user)):
    """Returns a Daily.co room URL + meeting token. If DAILY_API_KEY is unset,
    returns a clear stub so the UI can show a 'configure key' state."""
    if not DAILY_API_KEY:
        return {
            "configured": False,
            "room_url": None,
            "token": None,
            "message": "DAILY_API_KEY is not set on the server. Add it to /app/backend/.env to enable real video calls.",
        }
    room_name = f"vlt-{secrets.token_hex(6)}"
    exp = int((now_utc() + timedelta(hours=1)).timestamp())
    headers = {"Authorization": f"Bearer {DAILY_API_KEY}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=15) as cx:
            r1 = await cx.post(
                "https://api.daily.co/v1/rooms",
                headers=headers,
                json={
                    "name": room_name,
                    "privacy": "private",
                    "properties": {"exp": exp, "enable_chat": False, "enable_screenshare": True, "start_video_off": False},
                },
            )
            if r1.status_code >= 400:
                raise HTTPException(status_code=502, detail=f"Daily create-room failed: {r1.text}")
            room = r1.json()
            r2 = await cx.post(
                "https://api.daily.co/v1/meeting-tokens",
                headers=headers,
                json={"properties": {"room_name": room_name, "user_name": user["name"], "exp": exp}},
            )
            token = r2.json().get("token") if r2.status_code < 400 else None
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Daily.co error: {e}")
    return {"configured": True, "room_url": room["url"], "token": token, "name": room_name}
