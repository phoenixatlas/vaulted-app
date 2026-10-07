"""Weekly Settlement Digest
==========================

Monday-morning email summary of the past 7 days: Kotani settlements,
outstanding/pending transactions, waitlist delta, Kotani health status
and partner-use-case email engagement. Sent to a configured recipient
list via Resend.

Lives alongside `receipt.py` and `usecase.py` — those build artefacts
for ad-hoc workflows; this one builds a scheduled operations summary.

Scheduling model:
  * In-process ticker (added to server.py startup) wakes every ~15 min
    and consults `digest_config` in Mongo. If `enabled=True`, the
    current UTC weekday matches `send_weekday` (default Monday), the
    hour is ≥ `send_hour_utc` (default 7) and we haven't already sent
    this week, we send and persist `last_sent_at` + `last_sent_summary`.
  * `POST /api/admin/digest/send-now` for manual firing (used by UI).
  * `POST /api/admin/digest/cron` for external cron providers (header
    auth via `X-Vaulted-Cron-Secret`).
"""
from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from dotenv import load_dotenv

from deps import db, logger
from emails import send_email_via_resend

load_dotenv()

# Default send schedule (overridable per-doc in Mongo).
DEFAULT_WEEKDAY = int(os.environ.get("DIGEST_WEEKDAY", "0"))  # 0 = Monday
DEFAULT_HOUR_UTC = int(os.environ.get("DIGEST_HOUR_UTC", "7"))  # 07:00 UTC = 08:00 BST
DIGEST_SUBJECT_PREFIX = os.environ.get("DIGEST_SUBJECT_PREFIX", "Vaulted · Weekly Operations Digest")
CRON_SECRET = os.environ.get("DIGEST_CRON_SECRET", "")
# Default recipient list falls back to the founder's inbox so the digest
# never silently targets nobody. Operators can replace via API.
DEFAULT_RECIPIENTS = [
    r.strip() for r in os.environ.get(
        "DIGEST_DEFAULT_RECIPIENTS", "umar.sani@phoenix-atlas.com"
    ).split(",") if r.strip()
]


@dataclass
class DigestSummary:
    """Serialisable snapshot captured in Mongo after each successful send."""
    period_start: str
    period_end: str
    tx_settled: int
    tx_pending: int
    usd_equivalent: float
    waitlist_new: int
    waitlist_total: int
    usecase_sends: int
    usecase_opens: int
    kotani_ready: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "period_start": self.period_start,
            "period_end": self.period_end,
            "tx_settled": self.tx_settled,
            "tx_pending": self.tx_pending,
            "usd_equivalent": self.usd_equivalent,
            "waitlist_new": self.waitlist_new,
            "waitlist_total": self.waitlist_total,
            "usecase_sends": self.usecase_sends,
            "usecase_opens": self.usecase_opens,
            "kotani_ready": self.kotani_ready,
        }


# ---------- Data collection -------------------------------------------------
async def collect_digest_data(days: int = 7) -> dict[str, Any]:
    """Pull the raw metrics the digest email needs. Everything is read
    directly from Mongo so there's no RPC chain to break if a sibling
    service is down."""
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    since_iso = since.isoformat()

    # ---- Settlements (settled Kotani offramps) -----------------------------
    settled_cursor = db.transactions.find(
        {
            "status": "settled",
            "kotani.reference_id": {"$exists": True},
            "kotani.settled_at": {"$gte": since_iso},
        },
        {
            "_id": 0, "id": 1, "amount_crypto": 1, "amount_fiat": 1,
            "token": 1, "fiat_currency": 1, "corridor": 1, "kotani": 1,
        },
    )
    tx_settled = 0
    usd_equivalent = 0.0
    fiat_by_currency: dict[str, float] = defaultdict(float)
    corridor_counts: dict[str, int] = defaultdict(int)
    tokens: dict[str, float] = defaultdict(float)
    reconciliation_warnings: list[dict[str, Any]] = []
    sample_tx_ids: list[str] = []
    async for tx in settled_cursor:
        tx_settled += 1
        token = (tx.get("token") or "USDC").upper()
        fiat_cur = (tx.get("fiat_currency") or "???").upper()
        corridor = (tx.get("corridor") or "??").upper()
        amount_crypto = float(tx.get("amount_crypto") or 0)
        quoted_fiat = float(tx.get("amount_fiat") or 0)
        settled_fiat = float((tx.get("kotani") or {}).get("fiat_transaction_amount") or quoted_fiat or 0)
        fiat_by_currency[fiat_cur] += settled_fiat
        corridor_counts[corridor] += 1
        tokens[token] += amount_crypto
        # Flag when effective vs quoted drifts > 0.5% so operators see
        # rate-slip early in the week.
        if quoted_fiat > 0 and abs(settled_fiat - quoted_fiat) / quoted_fiat > 0.005:
            reconciliation_warnings.append({
                "tx_id": tx.get("id"),
                "currency": fiat_cur,
                "quoted": round(quoted_fiat, 2),
                "settled": round(settled_fiat, 2),
                "delta_pct": round((settled_fiat - quoted_fiat) / quoted_fiat * 100, 2),
            })
        if token in {"USDC", "USDT", "DAI"}:
            usd_equivalent += amount_crypto
        if len(sample_tx_ids) < 5 and tx.get("id"):
            sample_tx_ids.append(tx["id"])

    # ---- Outstanding transactions (pending / processing) ------------------
    pending_statuses = ["pending", "processing", "awaiting_confirmation", "booked"]
    tx_pending = await db.transactions.count_documents({"status": {"$in": pending_statuses}})
    oldest_pending_cursor = db.transactions.find(
        {"status": {"$in": pending_statuses}},
        {"_id": 0, "id": 1, "status": 1, "created_at": 1, "corridor": 1, "amount_fiat": 1, "fiat_currency": 1},
    ).sort("created_at", 1).limit(5)
    oldest_pending = await oldest_pending_cursor.to_list(length=5)

    # ---- Waitlist delta ---------------------------------------------------
    waitlist_total = await db.waitlist.count_documents({})
    waitlist_new = await db.waitlist.count_documents({"created_at": {"$gte": since_iso}})

    # ---- Partner use-case engagement -------------------------------------
    usecase_sends = await db.usecase_sends.count_documents({"attempted_at": {"$gte": since_iso}})
    usecase_opens = await db.usecase_sends.count_documents({
        "opened_at": {"$ne": None},
        "attempted_at": {"$gte": since_iso},
    })

    # ---- Kotani health snapshot (cached from last probe) -----------------
    last_probe = await db.kotani_health_history.find_one({}, sort=[("checked_at", -1)]) or {}
    kotani_ready = bool(last_probe.get("overall_ready"))

    return {
        "period_days": days,
        "period_start": since_iso,
        "period_end": now.isoformat(),
        "tx_settled": tx_settled,
        "tx_pending": tx_pending,
        "usd_equivalent": round(usd_equivalent, 2),
        "fiat_by_currency": {k: round(v, 2) for k, v in fiat_by_currency.items()},
        "corridor_counts": dict(corridor_counts),
        "tokens": {k: round(v, 6) for k, v in tokens.items()},
        "reconciliation_warnings": reconciliation_warnings,
        "sample_tx_ids": sample_tx_ids,
        "oldest_pending": oldest_pending,
        "waitlist_new": waitlist_new,
        "waitlist_total": waitlist_total,
        "usecase_sends": usecase_sends,
        "usecase_opens": usecase_opens,
        "kotani_ready": kotani_ready,
        "kotani_last_checked": last_probe.get("checked_at"),
    }


# ---------- HTML builder ---------------------------------------------------
_BRAND_GOLD = "#C9A35B"
_INK = "#1A1510"
_MUTED = "#6B6253"
_LINE = "#E5DFD2"
_BG = "#FDFBF7"


def _format_date(iso_str: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%a %d %b %Y")
    except Exception:
        return iso_str[:10]


def build_weekly_digest_html(data: dict[str, Any], *, app_public_url: str | None = None) -> tuple[str, str]:
    """Return (subject, html). Pure function — no I/O."""
    period_label = f"{_format_date(data['period_start'])} → {_format_date(data['period_end'])}"
    tx_settled = data["tx_settled"]
    tx_pending = data["tx_pending"]
    usd_eq = data["usd_equivalent"]
    fiat_rows = data["fiat_by_currency"]
    corridor_rows = data["corridor_counts"]
    oldest = data["oldest_pending"]
    recon = data["reconciliation_warnings"]

    subject = (
        f"{DIGEST_SUBJECT_PREFIX} · {_format_date(data['period_end'])} · "
        f"{tx_settled} settled · {tx_pending} pending"
    )

    # Small helpers for inline-styled HTML (email clients hate <style>).
    def box(title: str, body_html: str) -> str:
        return (
            f'<table width="100%" cellpadding="0" cellspacing="0" '
            f'style="margin:0 0 16px;border:1px solid {_LINE};border-radius:8px;background:#fff;">'
            f'<tr><td style="padding:14px 18px 10px;">'
            f'<div style="font-size:10px;letter-spacing:1.4px;text-transform:uppercase;'
            f'color:{_MUTED};font-weight:700;margin-bottom:6px;">{title}</div>'
            f'{body_html}'
            f'</td></tr></table>'
        )

    def kv_row(label: str, value: str, muted: bool = False) -> str:
        color = _MUTED if muted else _INK
        return (
            f'<tr><td style="padding:4px 0;color:{_MUTED};font-size:12px;">{label}</td>'
            f'<td style="padding:4px 0;color:{color};font-size:13px;'
            f'font-weight:700;text-align:right;">{value}</td></tr>'
        )

    # Headline metrics
    headline_html = (
        '<table width="100%" cellpadding="0" cellspacing="0">'
        f'<tr>'
        f'<td align="center" style="padding:6px;width:33%;">'
        f'<div style="font-size:28px;font-weight:800;color:{_INK};letter-spacing:-0.5px;">{tx_settled}</div>'
        f'<div style="font-size:10px;color:{_MUTED};text-transform:uppercase;letter-spacing:0.6px;">tx settled</div>'
        f'</td>'
        f'<td align="center" style="padding:6px;width:33%;">'
        f'<div style="font-size:28px;font-weight:800;color:{_INK};letter-spacing:-0.5px;">'
        f'${usd_eq:,.0f}</div>'
        f'<div style="font-size:10px;color:{_MUTED};text-transform:uppercase;letter-spacing:0.6px;">USD equiv</div>'
        f'</td>'
        f'<td align="center" style="padding:6px;width:33%;">'
        f'<div style="font-size:28px;font-weight:800;color:{"#B06B00" if tx_pending > 0 else _INK};letter-spacing:-0.5px;">{tx_pending}</div>'
        f'<div style="font-size:10px;color:{_MUTED};text-transform:uppercase;letter-spacing:0.6px;">pending</div>'
        f'</td>'
        f'</tr></table>'
    )

    # Fiat / corridor breakdown
    if fiat_rows or corridor_rows:
        rows = []
        rows.append('<table width="100%" cellpadding="0" cellspacing="0">')
        if fiat_rows:
            for cur, amt in sorted(fiat_rows.items(), key=lambda x: -x[1]):
                rows.append(kv_row(f"Delivered · {cur}", f"{amt:,.0f}"))
        if corridor_rows:
            for cor, count in sorted(corridor_rows.items(), key=lambda x: -x[1]):
                rows.append(kv_row(f"Corridor · {cor}", f"{count} tx", muted=True))
        rows.append('</table>')
        breakdown_html = "".join(rows)
    else:
        breakdown_html = (
            f'<div style="color:{_MUTED};font-size:12px;line-height:18px;">'
            f'No settlements this week. First successful Kotani payout will appear here.'
            f'</div>'
        )

    # Reconciliation warnings
    if recon:
        rec_rows = ['<table width="100%" cellpadding="0" cellspacing="0" style="font-size:11px;">']
        for w in recon[:6]:
            rec_rows.append(
                f'<tr><td style="padding:3px 0;color:{_INK};">'
                f'<span style="font-family:menlo,monospace;background:#FFF4E1;padding:2px 6px;'
                f'border-radius:3px;">{w["currency"]}</span> '
                f'quoted {w["quoted"]:,.2f} · settled {w["settled"]:,.2f} · '
                f'<b style="color:{"#B06B00" if w["delta_pct"] > 0 else "#8A4A00"};">{w["delta_pct"]:+.2f}%</b></td></tr>'
            )
        rec_rows.append('</table>')
        reconciliation_html = (
            f'<div style="color:#B06B00;font-size:11px;margin-bottom:6px;font-weight:700;">'
            f'{len(recon)} transaction(s) drifted >0.5% from quoted rate'
            f'</div>' + "".join(rec_rows)
        )
    else:
        reconciliation_html = (
            f'<div style="color:#2F7D4F;font-size:12px;">'
            f'✓ All settlements within 0.5% of quoted rate.'
            f'</div>'
        )

    # Outstanding
    if oldest:
        o_rows = ['<table width="100%" cellpadding="0" cellspacing="0" style="font-size:11px;">']
        for t in oldest:
            o_rows.append(
                f'<tr><td style="padding:4px 0;">'
                f'<span style="font-family:menlo,monospace;color:{_MUTED};">{(t.get("id") or "")[:10]}</span>'
                f' · {t.get("status","?")}'
                f' · <b>{(t.get("corridor") or "??").upper()}</b>'
                f' · {_format_date(t.get("created_at",""))}'
                f'</td></tr>'
            )
        o_rows.append('</table>')
        outstanding_html = (
            f'<div style="color:{_MUTED};font-size:11px;margin-bottom:6px;">'
            f'{tx_pending} outstanding transaction(s). Oldest shown first.'
            f'</div>' + "".join(o_rows)
        )
    else:
        outstanding_html = (
            f'<div style="color:#2F7D4F;font-size:12px;">'
            f'✓ No outstanding transactions. Rail is clear.'
            f'</div>'
        )

    # Growth
    growth_html = (
        '<table width="100%" cellpadding="0" cellspacing="0">'
        + kv_row("New waitlist signups", f"+{data['waitlist_new']}")
        + kv_row("Waitlist total", f"{data['waitlist_total']:,}", muted=True)
        + kv_row("Use-case emails sent", f"{data['usecase_sends']}")
        + kv_row("Use-case emails opened", f"{data['usecase_opens']}", muted=True)
        + '</table>'
    )

    # Kotani status pill
    status_color = "#2F7D4F" if data["kotani_ready"] else "#B06B00"
    status_label = "READY" if data["kotani_ready"] else "NOT READY"
    last_checked = (data.get("kotani_last_checked") or "")[:19].replace("T", " ")
    kotani_html = (
        f'<div style="display:inline-block;padding:4px 10px;border-radius:999px;'
        f'background:{status_color}18;border:1px solid {status_color}60;'
        f'color:{status_color};font-size:11px;font-weight:800;letter-spacing:0.5px;">'
        f'KOTANI · {status_label}</div>'
        f'<div style="color:{_MUTED};font-size:11px;margin-top:6px;">'
        f'Last probed {last_checked or "—"} UTC</div>'
    )

    app_url = app_public_url or os.environ.get("APP_PUBLIC_URL") or "https://app.phoenix-atlas.com"
    cta_html = (
        f'<div style="text-align:center;padding:18px 0 6px;">'
        f'<a href="{app_url}/admin" style="display:inline-block;padding:11px 22px;'
        f'background:{_BRAND_GOLD};color:#0F0B08;text-decoration:none;'
        f'border-radius:8px;font-weight:800;font-size:13px;letter-spacing:0.3px;">'
        f'Open admin dashboard</a></div>'
    )

    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{subject}</title>
</head>
<body style="margin:0;padding:0;background:{_BG};font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;color:{_INK};">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:{_BG};">
    <tr><td align="center" style="padding:28px 16px;">
      <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;">
        <tr><td style="padding:0 4px 20px;">
          <div style="font-size:11px;color:{_MUTED};letter-spacing:1.6px;text-transform:uppercase;">Vaulted · operations</div>
          <div style="font-size:22px;font-weight:800;color:{_INK};letter-spacing:-0.5px;margin-top:4px;">Weekly digest</div>
          <div style="font-size:12px;color:{_MUTED};margin-top:4px;">{period_label}</div>
        </td></tr>
        <tr><td>
          {box("THIS WEEK AT A GLANCE", headline_html)}
          {box("SETTLEMENT BREAKDOWN", breakdown_html)}
          {box("RATE RECONCILIATION", reconciliation_html)}
          {box("OUTSTANDING TRANSACTIONS", outstanding_html)}
          {box("GROWTH SIGNALS", growth_html)}
          {box("INFRASTRUCTURE", kotani_html)}
          {cta_html}
        </td></tr>
        <tr><td style="padding:18px 4px;border-top:1px solid {_LINE};">
          <div style="font-size:10px;color:{_MUTED};line-height:14px;">
            Phoenix-Atlas Technologies Ltd · Companies House 15543001 · London, United Kingdom<br>
            This is an automated weekly operations digest. Update recipients from the admin dashboard.
          </div>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""

    return subject, html


# ---------- Config persistence ---------------------------------------------
_CONFIG_ID = "weekly_digest"


async def get_digest_config() -> dict[str, Any]:
    """Load the digest config, hydrating defaults if the doc doesn't exist yet."""
    doc = await db.digest_config.find_one({"_id": _CONFIG_ID}) or {}
    cfg = {
        "_id": _CONFIG_ID,
        "enabled": bool(doc.get("enabled", True)),
        "recipients": doc.get("recipients") or list(DEFAULT_RECIPIENTS),
        "send_weekday": int(doc.get("send_weekday", DEFAULT_WEEKDAY)),
        "send_hour_utc": int(doc.get("send_hour_utc", DEFAULT_HOUR_UTC)),
        "last_sent_at": doc.get("last_sent_at"),
        "last_sent_summary": doc.get("last_sent_summary"),
        "last_error": doc.get("last_error"),
    }
    # Public-facing output excludes internal `_id`.
    public = {k: v for k, v in cfg.items() if k != "_id"}
    return public


async def set_digest_config(
    *,
    enabled: bool | None = None,
    recipients: list[str] | None = None,
    send_weekday: int | None = None,
    send_hour_utc: int | None = None,
) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    if enabled is not None:
        updates["enabled"] = bool(enabled)
    if recipients is not None:
        cleaned = [r.strip() for r in recipients if r and r.strip() and "@" in r]
        updates["recipients"] = cleaned
    if send_weekday is not None:
        updates["send_weekday"] = max(0, min(6, int(send_weekday)))
    if send_hour_utc is not None:
        updates["send_hour_utc"] = max(0, min(23, int(send_hour_utc)))
    if updates:
        await db.digest_config.update_one(
            {"_id": _CONFIG_ID}, {"$set": updates}, upsert=True
        )
    return await get_digest_config()


# ---------- Send pipeline ---------------------------------------------------
async def send_weekly_digest(
    *,
    recipients: list[str] | None = None,
    days: int = 7,
    reason: str = "manual",
) -> dict[str, Any]:
    """Build data, render HTML, send via Resend. Returns a result dict for UI."""
    cfg = await get_digest_config()
    target = recipients if recipients else cfg["recipients"]
    target = [r for r in (target or []) if r and "@" in r]
    if not target:
        return {"ok": False, "error": "No recipients configured", "recipients": []}

    try:
        data = await collect_digest_data(days=days)
        subject, html = build_weekly_digest_html(data)
    except Exception as e:  # noqa: BLE001
        logger.exception("[digest] build failed: %s", e)
        return {"ok": False, "error": f"Build failed: {e}", "recipients": target}

    sent_to: list[str] = []
    errors: list[str] = []
    for rcpt in target:
        ok = await send_email_via_resend(rcpt, subject, html)
        if ok:
            sent_to.append(rcpt)
        else:
            errors.append(rcpt)

    now_iso = datetime.now(timezone.utc).isoformat()
    summary = DigestSummary(
        period_start=data["period_start"],
        period_end=data["period_end"],
        tx_settled=data["tx_settled"],
        tx_pending=data["tx_pending"],
        usd_equivalent=data["usd_equivalent"],
        waitlist_new=data["waitlist_new"],
        waitlist_total=data["waitlist_total"],
        usecase_sends=data["usecase_sends"],
        usecase_opens=data["usecase_opens"],
        kotani_ready=data["kotani_ready"],
    )
    set_fields = {
        "last_sent_at": now_iso,
        "last_sent_summary": summary.to_dict(),
        "last_sent_reason": reason,
        "last_sent_recipients": sent_to,
    }
    if errors:
        set_fields["last_error"] = f"Failed to send to: {', '.join(errors)}"
    else:
        set_fields["last_error"] = None

    await db.digest_config.update_one(
        {"_id": _CONFIG_ID}, {"$set": set_fields}, upsert=True
    )
    # Also log into an audit-style ledger so operators can see history.
    await db.digest_log.insert_one({
        "sent_at": now_iso,
        "reason": reason,
        "recipients": sent_to,
        "errors": errors,
        "subject": subject,
        "summary": summary.to_dict(),
    })

    return {
        "ok": not errors,
        "subject": subject,
        "sent_to": sent_to,
        "errors": errors,
        "summary": summary.to_dict(),
        "reason": reason,
    }


# ---------- Scheduler tick --------------------------------------------------
async def digest_scheduler_tick() -> dict[str, Any]:
    """Called every ~15 min from server startup task. Fires the digest if
    it's the configured weekday + hour and we haven't already sent this
    7-day window.
    """
    cfg = await get_digest_config()
    if not cfg.get("enabled"):
        return {"skipped": "disabled"}
    now = datetime.now(timezone.utc)
    if now.weekday() != cfg["send_weekday"]:
        return {"skipped": "wrong_weekday", "weekday": now.weekday()}
    if now.hour < cfg["send_hour_utc"]:
        return {"skipped": "too_early", "hour": now.hour}
    last_sent_at = cfg.get("last_sent_at")
    if last_sent_at:
        try:
            last_dt = datetime.fromisoformat(last_sent_at.replace("Z", "+00:00"))
            if (now - last_dt).total_seconds() < 6 * 24 * 3600:
                return {"skipped": "already_sent_this_week", "last_sent_at": last_sent_at}
        except Exception:
            pass
    logger.info("[digest] scheduler firing weekly digest")
    return await send_weekly_digest(reason="scheduler")


def verify_cron_secret(provided: str | None) -> bool:
    """Protect `/admin/digest/cron` against unauthenticated hits. If no secret
    is configured the endpoint is admin-only via its router guard; the secret
    is for cases where the external cron can't carry a JWT."""
    if not CRON_SECRET:
        return False
    return bool(provided) and provided == CRON_SECRET
