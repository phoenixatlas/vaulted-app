"""Public waitlist router — landing-page signups with corridor segmentation.

Wires the landing-page "Join the waitlist" form to Resend Contacts so
leads land in your ESP + a Mongo `waitlist` collection (belt-and-braces —
we own the list too and can export/re-import at will if we ever switch ESPs).

Endpoints:
    POST /api/waitlist/join
        body: {"email": "you@example.com", "corridor"?: "KE",
               "source"?: "landing"}
        response: {"ok": true, "already_joined": bool}

    GET /api/waitlist/stats   (admin-only)
        response: {"total": 42, "by_corridor": {"KE": 12, "GH": 8, ...}}

Corridor segmentation:
    Users pick a target destination country at signup (KE, GH, NG, UG, TZ,
    ZM, XX for "other/coming soon"). We:
      1. Persist the corridor on the Mongo waitlist doc (source of truth)
      2. Auto-create-if-missing a per-corridor Resend Audience ("Vaulted
         Waitlist – Kenya", etc.) and add the contact to it
    That means when Kenya goes live you can send a corridor-specific launch
    email to just the Kenya audience from the Resend dashboard — one click.

Rate-limit + abuse:
    - Simple in-memory per-IP dedupe (same IP within RATE_WINDOW_SEC → 429)
    - No bot-CAPTCHA yet (Cloudflare upstream blocks the worst offenders)

Docs: https://resend.com/docs/api-reference/audiences/create-audience
      https://resend.com/docs/api-reference/contacts/create-contact
"""
from __future__ import annotations

import asyncio
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from deps import db, iso, logger, now_utc
from emails import RESEND_API_KEY, send_email_via_resend

router = APIRouter()


# ---- Referral queue-jump mechanics --------------------------------------
# Every successful referral gives the *referrer* a queue-boost equivalent
# to moving up N positions. We implement this by subtracting `boost_seconds`
# from their effective join time when computing position — so somebody
# joining right now with 10 prior referrals appears above people who
# joined an hour ago with none. This is O(1) per lookup once we've cached
# the total waitlist size.
REFERRAL_BOOST_INTERVAL = 3            # every N successful refs...
REFERRAL_BOOST_SPOTS = 25              # ...moves them up 25 spots
FOUNDING_MEMBER_THRESHOLD = 5          # ≥5 refs → "Founding Member" badge

# Rough calibration: assume ~1 signup / 30 sec average during launch push,
# so 25 spots ≈ 12.5 minutes of virtual head-start. Tune post-launch once
# we have real signup velocity data.
_SPOT_TO_SECONDS = 30


def _referral_boost_seconds(referral_count: int) -> int:
    """Convert a referral count into seconds of virtual head-start."""
    if referral_count <= 0:
        return 0
    tiers = referral_count // REFERRAL_BOOST_INTERVAL
    return tiers * REFERRAL_BOOST_SPOTS * _SPOT_TO_SECONDS


def _generate_referral_code() -> str:
    """8-char URL-safe referral code. Collision-safe up to millions of users."""
    return secrets.token_urlsafe(6).replace("-", "").replace("_", "")[:8].upper()


async def _mint_referral_code_for(email: str) -> str:
    """Idempotent: return the user's existing code or create+persist a new one."""
    doc = await db.waitlist.find_one({"email": email}, {"_id": 0, "referral_code": 1})
    if doc and doc.get("referral_code"):
        return doc["referral_code"]
    # Retry a few times on the ~1-in-a-trillion collision case.
    for _ in range(4):
        code = _generate_referral_code()
        clash = await db.waitlist.find_one({"referral_code": code}, {"_id": 1})
        if not clash:
            await db.waitlist.update_one(
                {"email": email},
                {"$set": {"referral_code": code}},
            )
            return code
    # Give up gracefully — the caller can re-mint next time.
    return _generate_referral_code()


async def _compute_position(email: str) -> tuple[int, int]:
    """Return (position, total) for a given waitlist member.

    Position is 1-indexed. Position accounts for referral boost — a member
    with 3 refs is 25 slots ahead of where their joined_at alone would put them.
    Runs a single Mongo count against their `effective_joined_at`.
    """
    doc = await db.waitlist.find_one(
        {"email": email},
        {"_id": 0, "joined_at": 1, "referral_count": 1},
    )
    if not doc:
        total = await db.waitlist.count_documents({})
        return (total + 1, total)

    total = await db.waitlist.count_documents({})
    joined_at = doc.get("joined_at")
    if not joined_at:
        return (total, total)

    ref_count = int(doc.get("referral_count") or 0)
    boost_s = _referral_boost_seconds(ref_count)

    # Turn joined_at (ISO string) into datetime for effective calculation
    try:
        joined_dt = datetime.fromisoformat(joined_at.replace("Z", "+00:00"))
    except Exception:
        return (total, total)
    effective_dt = joined_dt - timedelta(seconds=boost_s)

    # Count everybody whose effective_joined_at is strictly earlier.
    # For members without a cached effective time, fall back to joined_at
    # (equivalent to boost=0). This aggregation is O(N) but N ≤ 100k for
    # launch. We can add an index later.
    pipeline = [
        {"$addFields": {
            "_ref_count": {"$ifNull": ["$referral_count", 0]},
            "_joined_dt": {"$toDate": "$joined_at"},
        }},
        # boost_seconds = floor(ref/3) * 25 * 30 = ref/3 * 750
        {"$addFields": {
            "_effective_dt": {
                "$dateSubtract": {
                    "startDate": "$_joined_dt",
                    "unit": "second",
                    "amount": {
                        "$multiply": [
                            {"$floor": {"$divide": ["$_ref_count", REFERRAL_BOOST_INTERVAL]}},
                            REFERRAL_BOOST_SPOTS * _SPOT_TO_SECONDS,
                        ],
                    },
                },
            },
        }},
        {"$match": {"_effective_dt": {"$lt": effective_dt}}},
        {"$count": "ahead"},
    ]
    try:
        rows = [r async for r in db.waitlist.aggregate(pipeline)]
        ahead = int(rows[0]["ahead"]) if rows else 0
    except Exception as e:  # noqa: BLE001
        logger.warning("[waitlist] position aggregate failed, using joined_at fallback: %s", e)
        ahead = await db.waitlist.count_documents({"joined_at": {"$lt": joined_at}})

    return (ahead + 1, total)

# ---- Corridor catalogue ---------------------------------------------------
# Keep in sync with the landing page `<select>` and the KOTANI_CORRIDORS
# map on the remit screen. `XX` is the escape hatch for users whose
# corridor isn't in the list yet.
CORRIDORS: dict[str, str] = {
    "KE": "Kenya",
    "GH": "Ghana",
    "NG": "Nigeria",
    "UG": "Uganda",
    "TZ": "Tanzania",
    "ZM": "Zambia",
    "ZA": "South Africa",
    "XX": "Other / Coming soon",
}


def _normalize_corridor(value: Optional[str]) -> str:
    v = (value or "").strip().upper()[:2]
    if v in CORRIDORS:
        return v
    return "XX"


# ---- Direction (outbound vs inbound) ------------------------------------
# outbound: user is IN the UK/EU sending money TO Africa (original product)
# inbound:  user is IN Africa sending money TO the UK/EU (reverse corridor,
#           unlocked in Phase 1 of the bi-directional launch)
ALLOWED_DIRECTIONS: set[str] = {"outbound", "inbound"}


def _normalize_direction(value: Optional[str]) -> str:
    v = (value or "").strip().lower()
    if v in ALLOWED_DIRECTIONS:
        return v
    return "outbound"


# ---- Rate limit (per-IP) --------------------------------------------------
_RATE_WINDOW_SEC = 5
_last_seen_by_ip: dict[str, float] = {}


def _too_fast(ip: str) -> bool:
    now = time.time()
    last = _last_seen_by_ip.get(ip)
    _last_seen_by_ip[ip] = now
    if last is None:
        return False
    return (now - last) < _RATE_WINDOW_SEC


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for") or ""
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ---- Resend Audience routing ---------------------------------------------
# Per-corridor audience id cache (Mongo-backed for durability across restarts).
# Keys: {"corridor": "KE", "direction": "outbound"} →
#   {"corridor": "KE", "direction": "outbound",
#    "audience_id": "aud_...", "name": "Vaulted Waitlist – Kenya → UK/EU",
#    "created_at": iso}
# Direction is folded into the audience name so campaigns can target the
# right side of the corridor (UK diaspora vs African senders).
async def _get_or_create_corridor_audience(corridor: str, direction: str = "outbound") -> Optional[str]:
    """Return the Resend audience id for the given corridor + direction,
    creating it on-demand the first time it's needed. Cached in Mongo
    (durable across process restarts) so we never re-create.

    Returns None on any failure — caller falls back to plain `POST /contacts`.
    """
    if not RESEND_API_KEY:
        return None
    if corridor not in CORRIDORS:
        corridor = "XX"
    if direction not in ALLOWED_DIRECTIONS:
        direction = "outbound"

    cached = await db.resend_audiences.find_one(
        {"corridor": corridor, "direction": direction}, {"_id": 0}
    )
    if cached and cached.get("audience_id"):
        return cached["audience_id"]

    # Legacy audiences created before direction was introduced have no
    # `direction` field — treat them as "outbound" (the original product)
    # so we don't create a duplicate on the first inbound signup.
    if direction == "outbound":
        legacy = await db.resend_audiences.find_one(
            {"corridor": corridor, "direction": {"$exists": False}}, {"_id": 0}
        )
        if legacy and legacy.get("audience_id"):
            await db.resend_audiences.update_one(
                {"corridor": corridor, "direction": {"$exists": False}},
                {"$set": {"direction": "outbound"}},
            )
            return legacy["audience_id"]

    arrow = "→ UK/EU" if direction == "inbound" else "← UK/EU"
    name = f"Vaulted Waitlist – {CORRIDORS[corridor]} {arrow}"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0)) as cx:
            r = await cx.post(
                "https://api.resend.com/audiences",
                headers={
                    "Authorization": f"Bearer {RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={"name": name},
            )
            if r.status_code in (200, 201):
                body = r.json() or {}
                # Resend returns {id, name, object, created_at}
                aid = body.get("id") or (body.get("data") or {}).get("id")
                if aid:
                    await db.resend_audiences.update_one(
                        {"corridor": corridor, "direction": direction},
                        {"$set": {
                            "corridor": corridor,
                            "direction": direction,
                            "audience_id": aid,
                            "name": name,
                            "created_at": iso(now_utc()),
                        }},
                        upsert=True,
                    )
                    logger.info("[waitlist] created resend audience %s (%s) → %s", corridor, direction, aid)
                    return aid
            logger.warning("[waitlist] audience create %s (%s): %s", corridor, direction, r.status_code)
            return None
    except Exception as e:  # noqa: BLE001
        logger.warning("[waitlist] audience create exception: %s", e)
        return None


async def _add_resend_contact(email: str, source: str, corridor: str, direction: str = "outbound") -> Optional[str]:
    """Add contact to the corridor+direction-specific Resend audience.
    Falls back to Resend's global contacts endpoint if audience creation
    fails. Returns Resend's contact id on success, None on failure (never
    raises).
    """
    if not RESEND_API_KEY:
        logger.warning("[waitlist] RESEND_API_KEY missing — skipping Resend add")
        return None

    audience_id = await _get_or_create_corridor_audience(corridor, direction)

    # If we have an audience, use the per-audience endpoint so the contact
    # is properly slotted for future corridor blasts. Otherwise fall back
    # to the global endpoint (still captures the lead in Resend).
    if audience_id:
        endpoint = f"https://api.resend.com/audiences/{audience_id}/contacts"
    else:
        endpoint = "https://api.resend.com/contacts"

    # Encode acquisition source + corridor + direction in a Resend-visible
    # field so you can eyeball corridor+direction mix from the dashboard
    # even without an API call.
    dir_tag = "in" if direction == "inbound" else "out"
    payload = {
        "email": email,
        "unsubscribed": False,
        "first_name": "",
        "last_name": f"[{corridor}·{dir_tag}·{source}]",
    }

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0)) as cx:
            r = await cx.post(
                endpoint,
                headers={
                    "Authorization": f"Bearer {RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            if r.status_code in (200, 201):
                data = (r.json() or {}).get("data") or r.json() or {}
                return data.get("id")
            # 422 = duplicate email — treat as success (already on list).
            if r.status_code == 422 and "already exists" in r.text.lower():
                logger.info("[waitlist] resend duplicate for %s — ok", email)
                return None
            logger.warning("[waitlist] resend contact create %s: %s", r.status_code, r.text[:300])
            return None
    except Exception as e:  # noqa: BLE001
        logger.warning("[waitlist] resend contact exception: %s", e)
        return None


# ---- Confirmation email ---------------------------------------------------
_CONFIRMATION_SUBJECT = "You're on the Vaulted waitlist ✨"


def _confirmation_html(
    corridor: str, direction: str = "outbound",
    referral_code: str = "", position: int = 0, total: int = 0,
) -> str:
    """Corridor + direction personalized confirmation email. The subject
    and shell are constant; only the corridor line + intro varies."""
    corridor_line = ""
    if corridor and corridor != "XX":
        if direction == "inbound":
            corridor_line = (
                f'<p style="margin: 0 0 12px; font-size: 14px; color: #666;">'
                f'We\u2019ve tagged you for the '
                f'<strong>{CORRIDORS.get(corridor, corridor)} \u2192 UK/EU</strong> corridor '
                f'\u2014 sending money out of {CORRIDORS.get(corridor, corridor)} '
                f'to pay UK/EU school fees, medical bills, or family. '
                f'You\u2019ll be first in when this goes live.</p>'
            )
        else:
            corridor_line = (
                f'<p style="margin: 0 0 12px; font-size: 14px; color: #666;">'
                f'We\u2019ve tagged you as interested in the '
                f'<strong>UK/EU \u2192 {CORRIDORS.get(corridor, corridor)}</strong> corridor '
                f'\u2014 you\u2019ll be the first to know when we go live there.</p>'
            )

    # Position block — only render if we have real numbers.
    position_block = ""
    if position > 0 and total > 0:
        position_block = (
            '<div style="text-align: center; margin: 20px 0 8px;">'
            '<div style="display: inline-block; padding: 14px 24px; border-radius: 14px; background: #0F0B08; color: #F5EDDF;">'
            '<div style="font-size: 11px; color: #C9A35B; letter-spacing: 1.2px; font-weight: 700; margin-bottom: 4px;">YOUR SPOT</div>'
            f'<div style="font-size: 28px; font-weight: 800; letter-spacing: -0.5px;">#{position:,}</div>'
            f'<div style="font-size: 11px; color: #C9A35B; opacity: 0.75; margin-top: 4px;">of {total:,} on the list</div>'
            '</div>'
            '</div>'
        )

    # Referral / skip-the-queue block.
    referral_block = ""
    if referral_code:
        share_url = f"https://phoenix-atlas.com/?ref={referral_code}"
        # Pre-baked, URL-encoded share intents for one-tap sharing.
        share_text = (
            "Just joined the Vaulted waitlist \u2014 UK\u2194Africa remittance in ~2 min. "
            "Skip the queue with my link:"
        )
        # Simple URL-encode fallback (we don't have urllib here in template)
        # These are static strings so hand-encoding is safe.
        tweet_intent = (
            "https://twitter.com/intent/tweet?url=" + share_url.replace(":", "%3A").replace("/", "%2F").replace("?", "%3F").replace("=", "%3D")
            + "&text=" + share_text.replace(" ", "+").replace("\u2014", "%E2%80%94").replace("\u2194", "%E2%86%94")
        )
        wa_intent = "https://wa.me/?text=" + (share_text + " " + share_url).replace(" ", "%20").replace(":", "%3A").replace("/", "%2F").replace("?", "%3F").replace("=", "%3D")
        referral_block = (
            '<div style="background: linear-gradient(135deg, #FBF7EE 0%, #F5EDDF 100%); border-radius: 14px; padding: 20px; margin: 24px 0; border: 1px solid rgba(201,163,91,0.4);">'
            '<p style="margin: 0 0 8px; font-size: 15px; font-weight: 700; color: #0F0B08;">\U0001F680 Skip the queue.</p>'
            '<p style="margin: 0 0 14px; font-size: 13px; line-height: 1.6; color: #4A4238;">'
            f'Every <strong>{REFERRAL_BOOST_INTERVAL} friends</strong> who join with your link moves you up <strong>{REFERRAL_BOOST_SPOTS} spots</strong>. Get <strong>{FOUNDING_MEMBER_THRESHOLD}</strong> and unlock a <strong>Founding Member</strong> badge (lifetime 50% off Vaulted fees).'
            '</p>'
            '<div style="background: white; padding: 12px 14px; border-radius: 10px; border: 1px dashed #C9A35B; margin-bottom: 14px; text-align: center;">'
            '<div style="font-size: 10px; letter-spacing: 1.2px; color: #8A6D2E; font-weight: 700; margin-bottom: 4px;">YOUR REFERRAL LINK</div>'
            f'<a href="{share_url}" style="font-family: \'SF Mono\', Menlo, monospace; font-size: 13px; color: #0F0B08; text-decoration: none; font-weight: 600; word-break: break-all;">phoenix-atlas.com/?ref={referral_code}</a>'
            '</div>'
            '<div style="text-align: center;">'
            f'<a href="{tweet_intent}" style="display: inline-block; padding: 10px 18px; background: #0F0B08; color: white; text-decoration: none; border-radius: 999px; font-size: 12px; font-weight: 700; margin: 0 4px 6px;">Share on X</a>'
            f'<a href="{wa_intent}" style="display: inline-block; padding: 10px 18px; background: #25D366; color: white; text-decoration: none; border-radius: 999px; font-size: 12px; font-weight: 700; margin: 0 4px 6px;">Share on WhatsApp</a>'
            '</div>'
            '</div>'
        )

    return (
        '<div style="font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, sans-serif; max-width: 560px; margin: 0 auto; padding: 24px; color: #1a1a1a;">'
        '<div style="text-align: center; padding: 32px 0 24px;">'
        '<div style="width: 56px; height: 56px; margin: 0 auto 16px; background: #C9A35B; border-radius: 14px; display: inline-flex; align-items: center; justify-content: center;">'
        '<span style="color: white; font-size: 24px; font-weight: 700;">V</span>'
        '</div>'
        '<h1 style="font-size: 22px; font-weight: 700; margin: 0 0 8px; color: #1a1a1a;">Welcome to the Vaulted waitlist.</h1>'
        '<p style="color: #666; margin: 0; font-size: 14px;">Thanks for signing up \u2014 we\u2019ll be in touch.</p>'
        f'{corridor_line}'
        '</div>'
        f'{position_block}'
        f'{referral_block}'
        '<div style="background: #FAF7F1; border-radius: 12px; padding: 20px; margin: 24px 0; border-left: 3px solid #C9A35B;">'
        '<p style="margin: 0 0 12px; font-size: 15px; line-height: 1.6;"><strong>What happens next?</strong></p>'
        '<ul style="margin: 0; padding-left: 20px; font-size: 14px; line-height: 1.7; color: #333;">'
        '<li>You\u2019ll get one email the moment your corridor goes live.</li>'
        '<li>No spam. No card required.</li>'
        '<li>Early waitlisters get first access to send-side subsidies.</li>'
        '</ul>'
        '</div>'
        '<p style="font-size: 14px; line-height: 1.6; color: #333; margin: 24px 0 12px;">'
        'Vaulted is a UK fintech in build. We\u2019re currently in <strong>waitlist mode</strong> ahead of authorization from the Financial Conduct Authority (FCA). Meantime you can explore the preview app \u2014 everything works except real settlement.'
        '</p>'
        '<div style="text-align: center; margin: 28px 0 16px;">'
        '<a href="https://app.phoenix-atlas.com" style="display: inline-block; background: #C9A35B; color: white; text-decoration: none; padding: 12px 28px; border-radius: 999px; font-weight: 600; font-size: 14px;">Preview the app \u2192</a>'
        '</div>'
        '<hr style="border: none; border-top: 1px solid #EAE5D8; margin: 32px 0 16px;">'
        '<p style="font-size: 12px; color: #999; text-align: center; margin: 0;">'
        'Questions? Reply to this email \u2014 a human will get back to you.<br>'
        'Phoenix-Atlas Technologies Ltd \u00b7 UK Company No. 17432346<br>'
        '<a href="https://app.phoenix-atlas.com/risk-disclosure.html" style="color: #C9A35B;">Cryptoasset risk disclosure</a>'
        '</p>'
        '</div>'
    )


async def _send_confirmation_email(
    email: str, corridor: str, direction: str = "outbound",
    referral_code: str = "", position: int = 0, total: int = 0,
) -> None:
    try:
        await send_email_via_resend(
            email, _CONFIRMATION_SUBJECT,
            _confirmation_html(corridor, direction, referral_code, position, total),
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("[waitlist] confirmation email failed for %s: %s", email, e)


# ---- Request model --------------------------------------------------------
class WaitlistJoinIn(BaseModel):
    email: EmailStr
    corridor: Optional[str] = Field(default=None, max_length=2)
    direction: Optional[str] = Field(default=None, max_length=16)
    source: Optional[str] = Field(default="landing", max_length=40)
    ref: Optional[str] = Field(default=None, max_length=16, description="Referral code from the URL")


_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


@router.post("/waitlist/join")
async def waitlist_join(body: WaitlistJoinIn, request: Request):
    email = str(body.email).strip().lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Invalid email address")

    ip = _client_ip(request)
    if _too_fast(ip):
        raise HTTPException(status_code=429, detail="Slow down — one submission at a time.")

    corridor = _normalize_corridor(body.corridor)
    direction = _normalize_direction(body.direction)
    ua = (request.headers.get("user-agent") or "")[:200]
    source = (body.source or "landing").strip()[:40]

    existing = await db.waitlist.find_one(
        {"email": email}, {"_id": 0, "email": 1, "corridor": 1, "direction": 1}
    )
    already_joined = bool(existing)

    now = iso(now_utc())
    doc_set = {
        "email": email,
        "corridor": corridor,
        "corridor_name": CORRIDORS[corridor],
        "direction": direction,
        "source": source,
        "updated_at": now,
        "last_ip": ip,
        "last_user_agent": ua,
    }
    doc_setoninsert = {"joined_at": now, "referral_count": 0}
    await db.waitlist.update_one(
        {"email": email},
        {"$set": doc_set, "$setOnInsert": doc_setoninsert},
        upsert=True,
    )

    # Mint (or reuse) the user's own referral code so we can hand it back
    # in the response for the "share to skip the queue" CTA in the email.
    referral_code = await _mint_referral_code_for(email)

    # Handle inbound referral: if a valid `ref` was passed AND this is a
    # NEW signup, increment the referrer's counter. We don't award boost
    # for re-submits (an existing email hitting refresh) or self-referrals.
    referred_by = None
    if body.ref and not already_joined:
        ref_code = body.ref.strip().upper()[:16]
        if ref_code and ref_code != referral_code:
            referrer = await db.waitlist.find_one(
                {"referral_code": ref_code},
                {"_id": 0, "email": 1, "referral_count": 1},
            )
            if referrer and referrer.get("email") != email:
                referred_by = referrer["email"]
                await db.waitlist.update_one(
                    {"email": email},
                    {"$set": {"referred_by": referred_by, "referred_by_code": ref_code}},
                )
                # Bump referrer's counter atomically. Their queue-boost is
                # recomputed on-the-fly next time _compute_position runs.
                await db.waitlist.update_one(
                    {"email": referred_by},
                    {"$inc": {"referral_count": 1}},
                )
                logger.info("[waitlist] referral credited to=%s from=%s", referred_by, email)

    # Compute position for the email response — happens AFTER the referrer
    # bump so their new position is reflected if they're the same signup
    # (edge case, but correct).
    position, total = await _compute_position(email)

    # Background: Resend audience add + confirmation email. Only fire once
    # per email — a re-submit with the same corridor+direction should be a
    # no-op. If either changes, we re-process so they land in the right bucket.
    prev_corridor = existing.get("corridor") if existing else None
    prev_direction = (existing.get("direction") if existing else None) or "outbound"
    should_process = (
        not already_joined
        or prev_corridor != corridor
        or prev_direction != direction
    )
    if should_process:
        asyncio.create_task(_add_and_confirm(email, source, corridor, direction, referral_code, position, total))

    logger.info(
        "[waitlist] joined email=%s corridor=%s direction=%s source=%s already=%s pos=%d/%d ref_by=%s",
        email, corridor, direction, source, already_joined, position, total, referred_by or "-",
    )
    return {
        "ok": True,
        "already_joined": already_joined,
        "corridor": corridor,
        "direction": direction,
        "referral_code": referral_code,
        "position": position,
        "total": total,
        "referred_by": referred_by,
    }


async def _add_and_confirm(
    email: str, source: str, corridor: str, direction: str = "outbound",
    referral_code: str = "", position: int = 0, total: int = 0,
) -> None:
    """Background task — Resend contact add + confirmation email."""
    contact_id = await _add_resend_contact(email, source, corridor, direction)
    if contact_id:
        try:
            await db.waitlist.update_one(
                {"email": email},
                {"$set": {"resend_contact_id": contact_id}},
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("[waitlist] persist resend_contact_id failed: %s", e)
    await _send_confirmation_email(email, corridor, direction, referral_code, position, total)


# ---- Position + referral lookup endpoints -------------------------------
@router.get("/waitlist/position")
async def waitlist_position(email: str):
    """Public lookup — returns {position, total, referral_code, referral_count,
    founding_member} for an existing email. Used by the confirmation-email
    "view your spot" link and any post-signup landing page state.
    """
    if not email or not _EMAIL_RE.match(email.lower()):
        raise HTTPException(status_code=400, detail="Invalid email")
    doc = await db.waitlist.find_one(
        {"email": email.lower()},
        {"_id": 0, "referral_code": 1, "referral_count": 1, "corridor": 1, "direction": 1},
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Not on the waitlist yet")
    position, total = await _compute_position(email.lower())
    ref_count = int(doc.get("referral_count") or 0)
    return {
        "email": email.lower(),
        "position": position,
        "total": total,
        "referral_code": doc.get("referral_code"),
        "referral_count": ref_count,
        "founding_member": ref_count >= FOUNDING_MEMBER_THRESHOLD,
        "next_boost_at": REFERRAL_BOOST_INTERVAL - (ref_count % REFERRAL_BOOST_INTERVAL),
        "corridor": doc.get("corridor"),
        "direction": doc.get("direction"),
    }


@router.get("/waitlist/refer/{code}")
async def waitlist_referral_lookup(code: str):
    """Public — validates a referral code and returns the (redacted) referrer's
    identity. Powers the landing-page banner: "You've been referred by o***@example.com,
    join now and both of you move up the queue."
    """
    code = (code or "").strip().upper()[:16]
    if not code:
        raise HTTPException(status_code=400, detail="Invalid code")
    doc = await db.waitlist.find_one(
        {"referral_code": code}, {"_id": 0, "email": 1, "corridor": 1}
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Code not found")
    email = doc["email"]
    # Redact for privacy: "o***@example.com"
    local, _, domain = email.partition("@")
    redacted = f"{local[0]}{'*' * max(2, len(local) - 1)}@{domain}" if local else email
    return {"ok": True, "referrer": redacted, "code": code, "corridor": doc.get("corridor")}


# ---- Admin stats ----------------------------------------------------------
# Small helper endpoint so ops can eyeball corridor mix without opening
# Mongo directly. Admin-guarded via the same require_admin dep every other
# admin route uses.
try:  # avoid a hard import at module top so a missing admin dep doesn't
    # break the whole router — the endpoint just won't register.
    from deps import require_admin

    @router.get("/admin/waitlist/stats")
    async def waitlist_stats(_=Depends(require_admin)):
        """Corridor + direction breakdown of the waitlist. Admin-only."""
        total = await db.waitlist.count_documents({})
        # Mongo aggregation: group by corridor.
        cursor = db.waitlist.aggregate([
            {"$group": {"_id": "$corridor", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ])
        by_corridor: dict[str, int] = {}
        async for row in cursor:
            key = row.get("_id") or "XX"
            by_corridor[key] = int(row.get("count", 0))
        # Pretty-name each corridor for the admin dashboard.
        breakdown = [
            {
                "corridor": k,
                "corridor_name": CORRIDORS.get(k, k),
                "count": v,
            }
            for k, v in by_corridor.items()
        ]

        # Direction split (outbound = UK→Africa; inbound = Africa→UK/EU).
        dir_cursor = db.waitlist.aggregate([
            {"$group": {"_id": {"$ifNull": ["$direction", "outbound"]}, "count": {"$sum": 1}}},
        ])
        by_direction: dict[str, int] = {"outbound": 0, "inbound": 0}
        async for row in dir_cursor:
            key = row.get("_id") or "outbound"
            by_direction[key] = int(row.get("count", 0))

        # Corridor × direction matrix — the useful investor-facing view.
        matrix_cursor = db.waitlist.aggregate([
            {"$group": {
                "_id": {
                    "corridor": "$corridor",
                    "direction": {"$ifNull": ["$direction", "outbound"]},
                },
                "count": {"$sum": 1},
            }},
            {"$sort": {"count": -1}},
        ])
        matrix: list[dict] = []
        async for row in matrix_cursor:
            k = row.get("_id") or {}
            matrix.append({
                "corridor": k.get("corridor") or "XX",
                "corridor_name": CORRIDORS.get(k.get("corridor") or "XX", "Unknown"),
                "direction": k.get("direction") or "outbound",
                "count": int(row.get("count", 0)),
            })

        return {
            "total": total,
            "by_corridor": by_corridor,
            "by_direction": by_direction,
            "breakdown": breakdown,
            "matrix": matrix,
            "corridors": CORRIDORS,
        }

    @router.get("/admin/waitlist/analytics/daily-signups")
    async def waitlist_daily_signups(
        _=Depends(require_admin),
        days: int = 30,
    ):
        """Daily signup counts for the last `days` days. Returns a dense
        series (every day filled with 0 for gaps) so the admin chart can
        just draw the line without client-side gap-filling.
        """
        days = max(1, min(days, 180))
        since = now_utc() - timedelta(days=days - 1)
        # Truncate to start-of-day for a clean bucket boundary.
        since_day = since.replace(hour=0, minute=0, second=0, microsecond=0)

        pipeline = [
            {"$addFields": {"_dt": {"$toDate": "$joined_at"}}},
            {"$match": {"_dt": {"$gte": since_day}}},
            {"$group": {
                "_id": {
                    "y": {"$year": "$_dt"},
                    "m": {"$month": "$_dt"},
                    "d": {"$dayOfMonth": "$_dt"},
                    "direction": {"$ifNull": ["$direction", "outbound"]},
                },
                "count": {"$sum": 1},
            }},
        ]
        raw: dict[str, dict[str, int]] = {}
        try:
            async for row in db.waitlist.aggregate(pipeline):
                _id = row.get("_id") or {}
                key = f"{_id.get('y', 0):04d}-{_id.get('m', 0):02d}-{_id.get('d', 0):02d}"
                dir_key = _id.get("direction") or "outbound"
                bucket = raw.setdefault(key, {"outbound": 0, "inbound": 0, "total": 0})
                cnt = int(row.get("count", 0))
                bucket[dir_key] = bucket.get(dir_key, 0) + cnt
                bucket["total"] = bucket["outbound"] + bucket["inbound"]
        except Exception as e:  # noqa: BLE001
            logger.warning("[waitlist] daily signups aggregate failed: %s", e)

        # Dense fill: every day from since_day to today, even if zero.
        series: list[dict] = []
        for i in range(days):
            day_dt = since_day + timedelta(days=i)
            key = day_dt.strftime("%Y-%m-%d")
            bucket = raw.get(key) or {"outbound": 0, "inbound": 0, "total": 0}
            series.append({
                "date": key,
                "outbound": bucket.get("outbound", 0),
                "inbound": bucket.get("inbound", 0),
                "total": bucket.get("total", 0),
            })

        # Roll-up metrics
        total_signups = sum(p["total"] for p in series)
        peak = max((p["total"] for p in series), default=0)
        peak_day = next((p["date"] for p in series if p["total"] == peak and peak > 0), None)

        return {
            "days": days,
            "series": series,
            "totals": {
                "signups": total_signups,
                "outbound": sum(p["outbound"] for p in series),
                "inbound": sum(p["inbound"] for p in series),
                "peak_day": peak_day,
                "peak_count": peak,
                "average_per_day": round(total_signups / days, 1),
            },
        }

    @router.get("/admin/waitlist/analytics/referrals")
    async def waitlist_referral_leaderboard(_=Depends(require_admin), limit: int = 10):
        """Top referrers on the waitlist. Powers a leaderboard card on /admin.

        Returns emails redacted for privacy (o***@example.com style) — the
        admin can still tell who's who by matching against Resend but the
        raw list isn't exposed if the /admin dashboard is ever screenshotted.
        """
        limit = max(1, min(limit, 100))
        cursor = db.waitlist.find(
            {"referral_count": {"$gt": 0}},
            {"_id": 0, "email": 1, "referral_count": 1, "corridor": 1, "referral_code": 1},
        ).sort("referral_count", -1).limit(limit)

        leaders = []
        async for row in cursor:
            email = row.get("email") or ""
            local, _, domain = email.partition("@")
            redacted = f"{local[0]}{'*' * max(2, len(local) - 1)}@{domain}" if local else email
            ref_count = int(row.get("referral_count") or 0)
            leaders.append({
                "email_redacted": redacted,
                "email_hash": local[:2] + domain[:3],  # for stable UI keying
                "referral_count": ref_count,
                "corridor": row.get("corridor"),
                "referral_code": row.get("referral_code"),
                "founding_member": ref_count >= FOUNDING_MEMBER_THRESHOLD,
            })

        # Aggregate totals
        total_referred = await db.waitlist.count_documents({"referred_by": {"$exists": True}})
        founding_count = await db.waitlist.count_documents(
            {"referral_count": {"$gte": FOUNDING_MEMBER_THRESHOLD}}
        )

        return {
            "leaders": leaders,
            "totals": {
                "total_referred_signups": total_referred,
                "founding_members": founding_count,
                "boost_interval": REFERRAL_BOOST_INTERVAL,
                "boost_spots": REFERRAL_BOOST_SPOTS,
                "founding_threshold": FOUNDING_MEMBER_THRESHOLD,
            },
        }
except ImportError:
    pass
