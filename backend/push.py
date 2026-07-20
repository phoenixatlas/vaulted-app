"""Emergent-managed push notifications integration.

Exposes:
- `send_push(recipients, data, idempotency_key)` - fire-and-forget helper
  used across chat/message send, multi-sig approvals, remit receipts.
- `register_push_route` - APIRouter for the /api/register-push relay that
  the mobile app hits at app-launch time with its device token.

Note: `register-push` is mounted directly onto `app` (not `api`) to match
the existing prod path `/api/register-push` (no `/api/api/` double prefix).

Extracted from server.py during the P2 refactor.
"""
from __future__ import annotations

import os
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException

from deps import logger
from models import RegisterPushBody


PUSH_BASE_URL = "https://integrations.emergentagent.com"
EMERGENT_PUSH_KEY = os.environ.get("EMERGENT_PUSH_KEY", "placeholder")

_push_client = httpx.AsyncClient(
    base_url=PUSH_BASE_URL,
    headers={"X-Push-Key": EMERGENT_PUSH_KEY},
    timeout=10.0,
)


# The registration endpoint uses a raw /api/register-push path (no double
# /api/api/), so we mount it in server.py with the full path rather than
# via the api router prefix.
register_push_router = APIRouter()


@register_push_router.post("/api/register-push", status_code=201)
async def register_push(body: RegisterPushBody):
    """Relay device-token registration to the Emergent Push service."""
    try:
        resp = await _push_client.post(
            "/api/v1/push/users/register", json=body.model_dump()
        )
        if resp.status_code == 401:
            raise HTTPException(500, "EMERGENT_PUSH_KEY missing or invalid")
        if resp.status_code >= 500:
            raise HTTPException(502, "Push provider unavailable")
        resp.raise_for_status()
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("register-push relay failed: %s", e)
        raise HTTPException(502, "Push provider unavailable") from e
    return {"status": "registered"}


async def send_push(
    recipients: list[str],
    data: dict,
    idempotency_key: Optional[str] = None,
) -> None:
    """Fire a push to one or more user_ids via Emergent. Never raises."""
    try:
        if not recipients:
            return
        if "title" not in data or "message" not in data:
            logger.warning("send_push payload missing title/message: %s", data)
            return
        # chunk to <= 100
        for i in range(0, len(recipients), 100):
            chunk = recipients[i:i + 100]
            payload: dict = {"recipients": chunk, "data": data}
            if idempotency_key:
                payload["$idempotency_key"] = f"{idempotency_key}-{i}"
            resp = await _push_client.post("/api/v1/push/trigger", json=payload)
            if resp.status_code >= 400:
                logger.warning("send_push %s -> %s body=%s", chunk, resp.status_code, resp.text[:200])
    except Exception as e:  # pragma: no cover - best-effort
        logger.warning("send_push failed (non-blocking): %s", e)
