"""Weekly Mongo backup — admin endpoints.

See `backup.py` for the dump + email pipeline. The endpoints here are
thin HTTP wrappers so the admin UI can toggle, preview and manually
trigger backups.
"""
from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr, Field

from deps import require_admin
from backup import get_backup_config, set_backup_config, run_backup

router = APIRouter()


class BackupConfigIn(BaseModel):
    enabled: Optional[bool] = None
    recipients: Optional[List[EmailStr]] = None
    send_weekday: Optional[int] = Field(default=None, ge=0, le=6)
    send_hour_utc: Optional[int] = Field(default=None, ge=0, le=23)
    collections: Optional[List[str]] = None


@router.get("/admin/backup/config")
async def backup_config_get(_admin=Depends(require_admin)):
    return await get_backup_config()


@router.post("/admin/backup/config")
async def backup_config_set(
    payload: BackupConfigIn,
    _admin=Depends(require_admin),
):
    return await set_backup_config(
        enabled=payload.enabled,
        recipients=[str(r) for r in payload.recipients] if payload.recipients is not None else None,
        send_weekday=payload.send_weekday,
        send_hour_utc=payload.send_hour_utc,
        collections=payload.collections,
    )


@router.post("/admin/backup/run-now")
async def backup_run_now(_admin=Depends(require_admin)):
    """Fire a backup immediately. Useful for first-time setup verification
    and ad-hoc dumps before risky maintenance work."""
    return await run_backup(reason="manual")
