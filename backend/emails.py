"""Resend transactional email integration + password-reset templates.

Extracted from server.py during the P2 refactor. `send_email_via_resend` is
called by routers directly; `start_resend_domain_poller` is invoked from
server.py's startup hook so the sender identity flips to the verified domain
as soon as Resend reports it as verified (no restart required).
"""
from __future__ import annotations

import asyncio
import os
from typing import Optional

import httpx

from deps import logger


RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
# Sender address - defaults to Resend's shared sandbox until a custom domain is verified.
RESEND_FROM = os.environ.get("RESEND_FROM", "Vaulted <onboarding@resend.dev>")
# Domain we'd like to graduate the sender to once verified.
RESEND_TARGET_DOMAIN = os.environ.get("RESEND_TARGET_DOMAIN", "phoenix-atlas.com")
RESEND_TARGET_FROM = os.environ.get(
    "RESEND_TARGET_FROM", f"Vaulted <noreply@{os.environ.get('RESEND_TARGET_DOMAIN', 'phoenix-atlas.com')}>",
)
# Mutable at runtime - the Resend poller flips this when the target domain verifies.
_resolved_resend_from: Optional[str] = None

# Password reset config
PASSWORD_RESET_TOKEN_TTL_SEC = 30 * 60  # 30 minutes
PASSWORD_RESET_MAX_PER_HOUR = 3


def get_resend_from() -> str:
    return _resolved_resend_from or RESEND_FROM


async def send_email_via_resend(to: str, subject: str, html: str) -> bool:
    """Fire-and-forget email send. Returns True on success, False otherwise.
    Never raises so callers can log-and-continue."""
    if not RESEND_API_KEY:
        logger.warning("RESEND_API_KEY not set; email to %s skipped", to)
        return False
    try:
        async with httpx.AsyncClient(timeout=12) as cx:
            r = await cx.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
                json={"from": get_resend_from(), "to": [to], "subject": subject, "html": html},
            )
            if r.status_code >= 400:
                logger.warning("resend send failed %s: %s", r.status_code, r.text[:200])
                return False
            return True
    except Exception as e:  # noqa: BLE001
        logger.warning("resend send exception: %s", e)
        return False


def password_reset_email_html(name: str, reset_url: str) -> str:
    safe_name = (name or "there").strip() or "there"
    return f"""
    <div style="font-family:-apple-system,Helvetica,Arial,sans-serif;max-width:520px;margin:auto;padding:32px 24px;background:#0F0B08;color:#F5E9C9">
      <div style="font-size:24px;font-weight:700;color:#C9A35B;letter-spacing:-0.4px;margin-bottom:4px">Vaulted</div>
      <div style="font-size:11px;color:#B8AFA1;letter-spacing:2px;text-transform:uppercase;margin-bottom:32px">Password Reset</div>
      <div style="font-size:16px;color:#F5E9C9;margin-bottom:16px">Hi {safe_name},</div>
      <p style="font-size:14px;color:#F5E9C9;line-height:22px;margin:0 0 20px">We received a request to reset the password on your Vaulted account. Tap the button below within the next 30 minutes to set a new password.</p>
      <div style="margin:28px 0">
        <a href="{reset_url}" style="display:inline-block;background:#C9A35B;color:#0F0B08;padding:14px 28px;border-radius:10px;text-decoration:none;font-weight:700;font-size:15px">Reset password</a>
      </div>
      <p style="font-size:12px;color:#B8AFA1;line-height:18px;margin:24px 0 0">Or paste this link into your browser:<br/><span style="color:#E6C879;word-break:break-all">{reset_url}</span></p>
      <div style="border-top:1px solid #2a2320;margin:32px 0 16px"></div>
      <p style="font-size:12px;color:#B8AFA1;line-height:18px;margin:0">If you didn't request this, you can safely ignore this email \u2014 your password will stay the same. Your Vaulted funds remain in your self-custody wallet; only the app login is affected.</p>
      <p style="font-size:11px;color:#6d7a73;margin-top:24px">Vaulted \u00b7 Phoenix Atlas Ltd \u00b7 UK</p>
    </div>
    """


async def _resend_domain_poller():
    """Periodically checks Resend for the target domain. As soon as it flips to
    'verified', we promote the sender by populating `_resolved_resend_from`.
    No env-file rewriting required."""
    global _resolved_resend_from
    if not RESEND_API_KEY:
        logger.info("[resend-poller] no API key set; skipping")
        return
    interval = int(os.environ.get("RESEND_POLL_INTERVAL_SEC", "300"))  # 5 min default
    backoff_until = 0.0
    while True:
        try:
            now = asyncio.get_event_loop().time()
            if now >= backoff_until:
                async with httpx.AsyncClient(timeout=10) as cx:
                    r = await cx.get(
                        "https://api.resend.com/domains",
                        headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
                    )
                if r.status_code == 200:
                    for d in (r.json() or {}).get("data", []):
                        if d.get("name") == RESEND_TARGET_DOMAIN and d.get("status") == "verified":
                            if _resolved_resend_from != RESEND_TARGET_FROM:
                                _resolved_resend_from = RESEND_TARGET_FROM
                                logger.info(
                                    "[resend-poller] %s verified \u2014 sender promoted to %s",
                                    RESEND_TARGET_DOMAIN, RESEND_TARGET_FROM,
                                )
                            return  # done forever
                    # not verified yet, trigger a re-check from Resend's side
                    domain_id = next(
                        (d.get("id") for d in (r.json() or {}).get("data", []) if d.get("name") == RESEND_TARGET_DOMAIN),
                        None,
                    )
                    if domain_id:
                        async with httpx.AsyncClient(timeout=10) as cx2:
                            await cx2.post(
                                f"https://api.resend.com/domains/{domain_id}/verify",
                                headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
                            )
                elif r.status_code in (401, 403):
                    logger.warning("[resend-poller] auth failed (%s); stopping", r.status_code)
                    return
                else:
                    backoff_until = now + 60  # 1 min cool-down on transient errors
        except Exception as e:  # pragma: no cover - best-effort
            logger.warning("[resend-poller] iteration failed: %s", e)
        await asyncio.sleep(interval)


def start_resend_domain_poller() -> None:
    """Fire-and-forget - FastAPI will keep this task alive for the process lifetime."""
    asyncio.create_task(_resend_domain_poller())
