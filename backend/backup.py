"""Vaulted — Mongo backup snapshot
=================================

Weekly dump of the critical collections (waitlist, transactions,
usecase_sends, usecase_drafts, contacts, kotani_health_history,
digest_log, waitlist_sync_log) into a timestamped JSON file and emailed
to the configured operators via Resend. Keeps recovery straightforward
without needing shell access to the production Mongo.

Scheduling model mirrors the weekly digest: an in-process ticker in
`server.py` wakes every 15 min, inspects `backup_config`, and fires
once per week on the configured weekday + hour. Idempotent — gates on
`last_sent_at` so a mid-window restart never produces two backups.
"""
from __future__ import annotations

import gzip
import io
import json
import os
from datetime import datetime, timezone, timedelta
from typing import Any

from dotenv import load_dotenv

from deps import db, logger
from emails import send_email_via_resend_with_attachment

load_dotenv()

DEFAULT_WEEKDAY = int(os.environ.get("BACKUP_WEEKDAY", "6"))  # Sunday
DEFAULT_HOUR_UTC = int(os.environ.get("BACKUP_HOUR_UTC", "3"))  # 03:00 UTC
DEFAULT_RECIPIENTS = [
    r.strip() for r in os.environ.get("BACKUP_RECIPIENTS", "").split(",")
    if r.strip() and "@" in r
]
# Keep the dump focused — these are the collections we actually care
# about recovering. Admins can override via BACKUP_COLLECTIONS env var
# or by patching `backup_config.collections` from the UI.
DEFAULT_COLLECTIONS = [
    "waitlist",
    "transactions",
    "usecase_sends",
    "usecase_drafts",
    "contacts",
    "kotani_health_history",
    "digest_log",
    "waitlist_sync_log",
    "waitlist_alert_config",
    "digest_config",
    "waitlist_sync_config",
    "resend_audiences",
    "webhook_log",
]
if os.environ.get("BACKUP_COLLECTIONS"):
    DEFAULT_COLLECTIONS = [
        c.strip() for c in os.environ["BACKUP_COLLECTIONS"].split(",") if c.strip()
    ]

_CONFIG_ID = "weekly_backup"


def _json_default(obj: Any):
    """Mongo documents can carry datetimes + bson types that stdlib json
    can't serialise natively. We stringify datetimes and anything else
    we can't recognise so the dump always finishes."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    try:
        return str(obj)
    except Exception:
        return None


async def _collect_dump(collections: list[str]) -> tuple[dict, dict]:
    """Return `(dump, stats)` where `dump` is the full JSON-serialisable
    snapshot and `stats` is a per-collection row-count summary used in
    the email body."""
    stats: dict[str, int] = {}
    dump: dict[str, list[dict]] = {}
    for col in collections:
        try:
            rows = await db[col].find({}, {"_id": 0}).to_list(length=100_000)
        except Exception as e:  # noqa: BLE001
            logger.warning("[backup] collect %s failed: %s", col, e)
            rows = []
        dump[col] = rows
        stats[col] = len(rows)
    return dump, stats


def _format_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:,.0f} {unit}" if unit == "B" else f"{n/1:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


async def get_backup_config() -> dict:
    doc = await db.backup_config.find_one({"_id": _CONFIG_ID}) or {}
    return {
        "enabled": bool(doc.get("enabled", bool(DEFAULT_RECIPIENTS))),
        "recipients": doc.get("recipients") or list(DEFAULT_RECIPIENTS),
        "send_weekday": int(doc.get("send_weekday", DEFAULT_WEEKDAY)),
        "send_hour_utc": int(doc.get("send_hour_utc", DEFAULT_HOUR_UTC)),
        "collections": doc.get("collections") or list(DEFAULT_COLLECTIONS),
        "last_sent_at": doc.get("last_sent_at"),
        "last_total_docs": doc.get("last_total_docs"),
        "last_size_bytes": doc.get("last_size_bytes"),
        "last_sent_recipients": doc.get("last_sent_recipients", []),
        "last_error": doc.get("last_error"),
    }


async def set_backup_config(
    *,
    enabled: bool | None = None,
    recipients: list[str] | None = None,
    send_weekday: int | None = None,
    send_hour_utc: int | None = None,
    collections: list[str] | None = None,
) -> dict:
    updates: dict = {}
    if enabled is not None:
        updates["enabled"] = bool(enabled)
    if recipients is not None:
        updates["recipients"] = [r.strip() for r in recipients if r and "@" in r]
    if send_weekday is not None:
        updates["send_weekday"] = max(0, min(6, int(send_weekday)))
    if send_hour_utc is not None:
        updates["send_hour_utc"] = max(0, min(23, int(send_hour_utc)))
    if collections is not None:
        updates["collections"] = [c.strip() for c in collections if c and c.strip()]
    if updates:
        await db.backup_config.update_one(
            {"_id": _CONFIG_ID}, {"$set": updates}, upsert=True
        )
    return await get_backup_config()


async def run_backup(*, reason: str = "manual") -> dict:
    cfg = await get_backup_config()
    recipients = [r for r in cfg["recipients"] if r and "@" in r]
    if not recipients:
        return {"ok": False, "error": "No recipients configured"}

    dump, stats = await _collect_dump(cfg["collections"])
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    payload = {
        "backup_version": 1,
        "generated_at": now_iso,
        "reason": reason,
        "collections": cfg["collections"],
        "stats": stats,
        "data": dump,
    }
    # Serialise then gzip — Resend's attachment ceiling is ~20MB and
    # Mongo dumps compress 10-20x on waitlist / transaction data.
    raw = json.dumps(payload, default=_json_default, ensure_ascii=False).encode("utf-8")
    gz_buf = io.BytesIO()
    with gzip.GzipFile(fileobj=gz_buf, mode="wb", compresslevel=6) as gz:
        gz.write(raw)
    gz_bytes = gz_buf.getvalue()

    date_str = now.strftime("%Y%m%d-%H%M")
    filename = f"vaulted-backup-{date_str}.json.gz"
    total_docs = sum(stats.values())

    # Email body — operators scan this at a glance to confirm nothing
    # unexpected happened (e.g. transactions dropped from 42 to 0).
    rows_html = "".join(
        f'<tr><td style="padding:4px 10px 4px 0;color:#1A1510;font-family:menlo,monospace;font-size:12px;">{c}</td>'
        f'<td style="padding:4px 0;color:#1A1510;font-weight:700;text-align:right;">{stats[c]:,}</td></tr>'
        for c in cfg["collections"]
    )
    subject = f"Vaulted · weekly backup · {date_str} · {total_docs:,} docs · {_format_bytes(len(gz_bytes))}"
    html = f"""
    <div style="font-family:-apple-system,Helvetica,Arial,sans-serif;max-width:580px;margin:auto;padding:28px 24px;background:#FDFBF7;border:1px solid #E5DFD2;border-radius:12px;color:#1A1510;">
      <div style="font-size:11px;letter-spacing:1.6px;text-transform:uppercase;color:#6B6253;">Vaulted · operations</div>
      <div style="font-size:22px;font-weight:800;margin-top:4px;letter-spacing:-0.5px;">Weekly backup snapshot</div>
      <div style="font-size:12px;color:#6B6253;margin-top:4px;">{now.strftime('%A %d %B %Y · %H:%M UTC')} · reason: {reason}</div>

      <div style="margin-top:18px;padding:14px 16px;border:1px solid #E5DFD2;border-radius:8px;background:#fff;">
        <div style="font-size:10px;letter-spacing:1.2px;text-transform:uppercase;color:#6B6253;">Totals</div>
        <div style="font-size:16px;font-weight:800;margin-top:3px;">{total_docs:,} documents · {_format_bytes(len(gz_bytes))}</div>
        <div style="font-size:11px;color:#6B6253;margin-top:3px;">File: <span style="font-family:menlo,monospace;">{filename}</span></div>
      </div>

      <table width="100%" cellpadding="0" cellspacing="0" style="margin-top:14px;">
        {rows_html}
      </table>

      <div style="margin-top:18px;font-size:10.5px;color:#6B6253;line-height:14px;">
        Attached is a gzip of a JSON dump of the collections above. Restore
        with <span style="font-family:menlo,monospace;">gunzip -c &lt;file&gt; | mongoimport</span>
        or a one-liner Python script. Keep these somewhere safe — treat
        them the same as production database credentials.<br><br>
        Phoenix-Atlas Technologies Ltd · Companies House 15543001
      </div>
    </div>
    """

    sent_to: list[str] = []
    errors: list[str] = []
    for r in recipients:
        res = await send_email_via_resend_with_attachment(
            to=r,
            subject=subject,
            html=html,
            attachment_bytes=gz_bytes,
            attachment_filename=filename,
            tags=[{"name": "artefact", "value": "weekly_backup"}],
        )
        if res.get("ok"):
            sent_to.append(r)
        else:
            errors.append(f"{r}: {res.get('error','unknown')}")

    set_fields = {
        "last_sent_at": now_iso,
        "last_total_docs": total_docs,
        "last_size_bytes": len(gz_bytes),
        "last_sent_recipients": sent_to,
        "last_reason": reason,
        "last_error": None if not errors else "; ".join(errors),
    }
    await db.backup_config.update_one(
        {"_id": _CONFIG_ID}, {"$set": set_fields}, upsert=True
    )
    await db.backup_log.insert_one({
        "sent_at": now_iso,
        "reason": reason,
        "recipients": sent_to,
        "errors": errors,
        "total_docs": total_docs,
        "size_bytes": len(gz_bytes),
        "subject": subject,
    })
    logger.info(
        "[backup] weekly snapshot sent docs=%d size=%s recipients=%d errors=%d",
        total_docs, _format_bytes(len(gz_bytes)), len(sent_to), len(errors),
    )
    return {
        "ok": not errors,
        "subject": subject,
        "filename": filename,
        "total_docs": total_docs,
        "size_bytes": len(gz_bytes),
        "size_human": _format_bytes(len(gz_bytes)),
        "sent_to": sent_to,
        "errors": errors,
        "stats": stats,
    }


async def backup_scheduler_tick() -> dict:
    cfg = await get_backup_config()
    if not cfg.get("enabled"):
        return {"skipped": "disabled"}
    if not cfg.get("recipients"):
        return {"skipped": "no_recipients"}
    now = datetime.now(timezone.utc)
    if now.weekday() != cfg["send_weekday"]:
        return {"skipped": "wrong_weekday", "weekday": now.weekday()}
    if now.hour < cfg["send_hour_utc"] or now.hour > cfg["send_hour_utc"] + 1:
        return {"skipped": "outside_window", "hour": now.hour}
    last_sent_at = cfg.get("last_sent_at")
    if last_sent_at:
        try:
            last_dt = datetime.fromisoformat(last_sent_at.replace("Z", "+00:00"))
            if (now - last_dt).total_seconds() < 6 * 24 * 3600:
                return {"skipped": "already_sent_this_week", "last_sent_at": last_sent_at}
        except Exception:
            pass
    logger.info("[backup] scheduler firing weekly backup")
    return await run_backup(reason="scheduler")
