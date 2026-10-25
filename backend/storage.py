"""Emergent Managed Object Storage helpers (screenshots, uploads).

The storage API key never leaves the backend. Every read goes through our
own authenticated routes. Paths: vaulted/<area>/<user_id>/<uuid>.<ext>
"""
from __future__ import annotations

import os
from typing import Optional

import requests
from starlette.concurrency import run_in_threadpool

from deps import logger

APP_NAME = "vaulted"
_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
STORAGE_URL = _BASE.rstrip("/") + "/objstore/api/v1/storage"
_storage_key: Optional[str] = None


def _init() -> str:
    global _storage_key
    if _storage_key:
        return _storage_key
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": os.environ.get("EMERGENT_LLM_KEY")}, timeout=30)
    resp.raise_for_status()
    _storage_key = resp.json()["storage_key"]
    return _storage_key


def _put(path: str, data: bytes, content_type: str) -> dict:
    global _storage_key
    for attempt in range(2):
        resp = requests.put(f"{STORAGE_URL}/objects/{path}",
                            headers={"X-Storage-Key": _init(), "Content-Type": content_type}, data=data, timeout=120)
        if resp.status_code == 503 and attempt == 0:
            _storage_key = None  # stale key → re-init once
            continue
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError("storage unavailable")


def _get(path: str) -> tuple[bytes, str]:
    resp = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": _init()}, timeout=60)
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")


async def put_object(path: str, data: bytes, content_type: str) -> dict:
    return await run_in_threadpool(_put, f"{APP_NAME}/{path}", data, content_type)


async def get_object(full_path: str) -> tuple[bytes, str]:
    return await run_in_threadpool(_get, full_path)


def warm_up() -> None:
    try:
        _init()
    except Exception as e:  # noqa: BLE001
        logger.warning("[storage] init failed: %s", e)
