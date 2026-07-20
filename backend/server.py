from fastapi import FastAPI, APIRouter, Depends, HTTPException, status, Request, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import asyncio
import uuid
import secrets
import json
import hashlib
import httpx
import stripe
from eth_account import Account
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Literal

from pydantic import BaseModel, EmailStr, Field
from passlib.context import CryptContext
import jwt

from multichain import (
    derive_addresses,
    fetch_btc_balance_sats,
    fetch_sol_balance_lamports,
    fetch_usdc_balance_micro,
    fetch_xlm_balance_stroops,
    fetch_xrp_balance_drops,
    encode_usdc_transfer,
    explorer_url_btc,
    explorer_url_sol,
    explorer_url_xlm,
    explorer_url_xrp,
    btc_send,
    sol_send,
    xlm_send,
    xrp_send,
    USDC_CONTRACT,
    BTC_TESTNET,
    USE_MAINNET,
)
from remit import (
    CORRIDORS,
    SOURCE_FIATS,
    REMIT_CHAINS,
    refresh_fx_rates,
    convert_fiat,
    choose_chain,
    vaulted_fee_usd,
)
from evm import (
    list_evm_chains,
    evm_chain_config,
    fetch_usdc_balance_on_chain,
    fetch_native_balance_on_chain,
    usdc_send_on_chain,
    explorer_url_evm,
)
from compliance import (
    TIER_LIMITS,
    DEFAULT_TIER,
    COUNTRY_BLOCKLIST,
    is_country_blocked,
    get_user_tier,
    tier_limits,
    sum_this_month_gbp,
    check_send_limits,
    screen_sanctions,
    opensanctions_health,
    opensanctions_config_status,
    COMPLIANCE_STRICT_MODE,
)
from audit import (
    EventType,
    ALL_EVENT_TYPES,
    write_event as audit_write,
    query_events as audit_query,
    summarize_user as audit_summarize_user,
)
from referrals import (
    REFERRAL_REWARD_GBP,
    REFERRAL_SIGNUP_BONUS_GBP,
    ensure_referral_code,
    register_referral_at_signup,
    credit_referral_on_kyc,
    get_balance_gbp,
    spend_credit_for_fee,
    referral_summary,
)
import kotani


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

mongo_url = os.environ["MONGO_URL"]
# Pass certifi's CA bundle explicitly when connecting to Atlas (mongodb+srv://).
# Fixes "SSL handshake failed: TLSV1_ALERT_INTERNAL_ERROR" on hosted platforms
# (Render, Railway, etc.) whose default OS trust store can be stale/incomplete.
_mongo_kwargs: dict = {}
if "mongodb+srv" in mongo_url or "mongodb.net" in mongo_url:
    try:
        import certifi
        _mongo_kwargs["tlsCAFile"] = certifi.where()
    except Exception:
        pass
client = AsyncIOMotorClient(mongo_url, **_mongo_kwargs)
db = client[os.environ["DB_NAME"]]

JWT_SECRET = os.environ.get("JWT_SECRET", "vaulted-dev-secret-change-me")
JWT_ALG = "HS256"
JWT_EXPIRE_HOURS = 24 * 7

STRIPE_API_KEY = os.environ.get("STRIPE_API_KEY", "")
# Treat the well-known placeholder as "unconfigured" so endpoints degrade gracefully.
if STRIPE_API_KEY in ("sk_test_emergent", "sk_test_placeholder", "your_stripe_key_here"):
    STRIPE_API_KEY = ""
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
DAILY_API_KEY = os.environ.get("DAILY_API_KEY", "")
DAILY_DOMAIN = os.environ.get("DAILY_DOMAIN", "")
VAULT_PRO_PRICE_USD = float(os.environ.get("VAULT_PRO_PRICE_USD", "9.99"))
APP_PUBLIC_URL = os.environ.get("APP_PUBLIC_URL", "")
SEPOLIA_RPC_URL = os.environ.get("SEPOLIA_RPC_URL", "https://ethereum-sepolia-rpc.publicnode.com")
SEPOLIA_CHAIN_ID = 11155111

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
# Sender address — defaults to Resend's shared sandbox until a custom domain is verified.
RESEND_FROM = os.environ.get("RESEND_FROM", "Vaulted <onboarding@resend.dev>")
# Domain we'd like to graduate the sender to once verified.
RESEND_TARGET_DOMAIN = os.environ.get("RESEND_TARGET_DOMAIN", "phoenix-atlas.com")
RESEND_TARGET_FROM = os.environ.get(
    "RESEND_TARGET_FROM", f"Vaulted <noreply@{os.environ.get('RESEND_TARGET_DOMAIN', 'phoenix-atlas.com')}>"
)
# Mutable at runtime — the Resend poller flips this when the target domain verifies.
_resolved_resend_from: Optional[str] = None


def get_resend_from() -> str:
    return _resolved_resend_from or RESEND_FROM


MULTISIG_THRESHOLD_ETH = float(os.environ.get("MULTISIG_THRESHOLD_ETH", "0.01"))
APPROVAL_TTL_HOURS = 24

# Enable HD wallet features
Account.enable_unaudited_hdwallet_features()

if STRIPE_API_KEY:
    stripe.api_key = STRIPE_API_KEY

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer = HTTPBearer(auto_error=False)

app = FastAPI(title="Vaulted Wallet API")
api = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("vaulted")


# ----------------------------- Models -----------------------------
class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    name: str = Field(min_length=1, max_length=80)
    # Optional 8-char alphanumeric invite code. Case-insensitive.
    referred_by_code: Optional[str] = Field(default=None, max_length=16)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class SendCryptoIn(BaseModel):
    asset: str
    amount: float = Field(gt=0)
    to_address: str
    memo: Optional[str] = None


class FiatTxIn(BaseModel):
    amount: float = Field(gt=0)
    currency: str = "USD"
    method: Literal["card", "bank", "applepay"] = "card"


class SendMessageIn(BaseModel):
    conversation_id: str
    text: str = Field(min_length=1, max_length=8000)
    nonce: Optional[str] = None  # base64 NaCl secretbox nonce when encrypted
    encrypted: bool = False


class SendChatCryptoIn(BaseModel):
    conversation_id: str
    amount_eth: float = Field(gt=0, le=1.0)
    to_contact_id: Optional[str] = None  # required for group chats; ignored for 1-on-1


class CreateGroupIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    contact_ids: list[str] = Field(min_length=1, max_length=20)


class StartConversationIn(BaseModel):
    contact_id: str


class UpdateLanguageIn(BaseModel):
    language: str


class RegisterKeyIn(BaseModel):
    public_key: str  # base64 NaCl box public key


class StripeDepositIn(BaseModel):
    amount_usd: float = Field(gt=0, le=10000)


class StripeSyncIn(BaseModel):
    session_id: str


class CallRoomIn(BaseModel):
    conversation_id: Optional[str] = None


class CosignerInviteIn(BaseModel):
    email: EmailStr
    label: Optional[str] = None


class ApprovalActionIn(BaseModel):
    token: str
    decision: Literal["approve", "reject"]


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    token: str
    new_password: str = Field(min_length=6, max_length=128)


class RemitFundIn(BaseModel):
    """Fund a cross-border send with fiat (card / Apple Pay / bank transfer)
    via Stripe. Backend stores the intended remit in Checkout metadata; on
    successful payment (webhook or /stripe/sync poll) the on-chain leg is
    executed automatically.  Users who prefer to spend crypto keep using
    /remit/send unchanged."""
    source_fiat: str = Field(min_length=3, max_length=3)
    amount: float = Field(gt=0)
    destination_code: str = Field(min_length=2, max_length=2)
    recipient_address: str
    recipient_name: Optional[str] = None
    memo: Optional[str] = None
    payment_method: Literal["card", "apple_pay", "google_pay", "bank"] = "card"


# ----------------------------- Helpers -----------------------------
def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def make_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "iat": int(now_utc().timestamp()),
        "exp": int((now_utc() + timedelta(hours=JWT_EXPIRE_HOURS)).timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def is_user_pro(u: dict) -> bool:
    """Single source of truth: a user is 'Pro' if their Stripe subscription is
    active or trialing. Used by every fee/paywall check across the app to
    avoid the previous bug where /remit read a `u["is_pro"]` field that
    only existed on the public_user() response, never on the raw DB doc."""
    return ((u.get("subscription") or {}).get("status") in ("active", "trialing"))


async def _ensure_eth_private_key(user: dict) -> Optional[str]:
    """Derive + persist eth_private_key on-the-fly for legacy users who signed
    up before the field was added to the schema. Returns the key or None if
    even the mnemonic is missing (unrecoverable)."""
    if user.get("eth_private_key"):
        return user["eth_private_key"]
    mnemonic = user.get("eth_mnemonic") or user.get("mnemonic")
    if not mnemonic:
        return None
    try:
        Account.enable_unaudited_hdwallet_features()
        acct = Account.from_mnemonic(mnemonic)
    except Exception as e:
        logger.warning(f"eth_private_key backfill from mnemonic failed: {e}")
        return None
    pk_hex = "0x" + acct.key.hex()
    # Persist so we only pay the KDF cost once
    await db.users.update_one({"id": user["id"]}, {"$set": {"eth_private_key": pk_hex}})
    user["eth_private_key"] = pk_hex
    return pk_hex


def public_user(u: dict) -> dict:
    sub = u.get("subscription") or {}
    return {
        "id": u["id"],
        "email": u["email"],
        "name": u["name"],
        "language": u.get("language", "en"),
        "avatar": u.get("avatar"),
        "wallet_address": u.get("wallet_address"),
        "biometric_enabled": u.get("biometric_enabled", False),
        "multisig_enabled": u.get("multisig_enabled", False),
        "public_key": u.get("public_key"),
        "onboarding_seed_acknowledged": u.get("onboarding_seed_acknowledged", False),
        "referral_code": u.get("referral_code"),
        "subscription": {
            "tier": sub.get("tier", "free"),
            "status": sub.get("status", "inactive"),
            "current_period_end": sub.get("current_period_end"),
        },
        "is_pro": is_user_pro(u),
    }


async def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
) -> dict:
    if not creds or not creds.credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        data = jwt.decode(creds.credentials, JWT_SECRET, algorithms=[JWT_ALG])
        uid = data.get("sub")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = await db.users.find_one({"id": uid}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


# ---- Admin auth: comma-separated ADMIN_EMAILS env var. Any authed user
# whose email is on that list can hit /api/admin/* endpoints. Kept intentionally
# simple — we don't need RBAC granularity for the current admin footprint
# (health checks, manual sanctions screens). Upgrade to a role field on the
# user doc if the admin surface grows.
ADMIN_EMAILS: set[str] = {
    e.strip().lower()
    for e in (os.environ.get("ADMIN_EMAILS", "") or "").split(",")
    if e.strip()
}


async def require_admin(user=Depends(get_current_user)) -> dict:
    if not ADMIN_EMAILS:
        # No admin list configured on this deployment → lock everything down
        # rather than accidentally open the endpoints wide.
        raise HTTPException(status_code=403, detail="Admin endpoints not configured")
    email = (user.get("email") or "").strip().lower()
    if email not in ADMIN_EMAILS:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


DEFAULT_ASSETS = [
    {"symbol": "BTC", "name": "Bitcoin", "price_usd": 67234.12, "icon": "bitcoin"},
    {"symbol": "ETH", "name": "Ethereum", "price_usd": 3582.40, "icon": "ethereum"},
    {"symbol": "USDC", "name": "USD Coin", "price_usd": 1.00, "icon": "usdc"},
    {"symbol": "SOL", "name": "Solana", "price_usd": 158.22, "icon": "solana"},
    {"symbol": "XLM", "name": "Stellar Lumens", "price_usd": 0.12, "icon": "stellar"},
    {"symbol": "XRP", "name": "XRP", "price_usd": 0.52, "icon": "ripple"},
]

SEED_BALANCES = {"BTC": 0, "ETH": 0, "USDC": 0, "SOL": 0, "XLM": 0, "XRP": 0}

SEED_CONTACTS = [
    {"name": "Maya Chen", "email": "maya@vaulted.app", "priority": False,
     "avatar": "https://images.pexels.com/photos/8384889/pexels-photo-8384889.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=200&w=200"},
    {"name": "Daniel Park", "email": "daniel@vaulted.app", "priority": False,
     "avatar": "https://images.pexels.com/photos/35334114/pexels-photo-35334114.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=200&w=200"},
    {"name": "Vault Support", "email": "support@vaulted.app", "priority": True,
     "avatar": "https://images.unsplash.com/photo-1534528741775-53994a69daeb?crop=entropy&cs=srgb&fm=jpg&w=200&h=200&fit=crop"},
]


async def seed_user_data(user_id: str) -> None:
    # Seed balances
    for a in DEFAULT_ASSETS:
        await db.balances.insert_one({
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "symbol": a["symbol"],
            "name": a["name"],
            "amount": SEED_BALANCES.get(a["symbol"], 0),
            "icon": a["icon"],
            "updated_at": iso(now_utc()),
        })
    # Seed contacts + welcome conversation
    for c in SEED_CONTACTS:
        cid = str(uuid.uuid4())
        await db.contacts.insert_one({
            "id": cid,
            "user_id": user_id,
            "name": c["name"],
            "email": c["email"],
            "avatar": c["avatar"],
            "priority": c.get("priority", False),
            "created_at": iso(now_utc()),
        })
        conv_id = str(uuid.uuid4())
        await db.conversations.insert_one({
            "id": conv_id,
            "user_id": user_id,
            "contact_id": cid,
            "contact_name": c["name"],
            "contact_avatar": c["avatar"],
            "last_message": "Welcome to Vaulted secure chat.",
            "last_message_at": iso(now_utc()),
            "encrypted": True,
            "priority": c.get("priority", False),
            "unread": 1,
        })
        await db.messages.insert_one({
            "id": str(uuid.uuid4()),
            "conversation_id": conv_id,
            "user_id": user_id,
            "sender": "contact",
            "text": f"Hi! I'm {c['name']}. Welcome to Vaulted — your messages here are end-to-end encrypted.",
            "created_at": iso(now_utc()),
        })

    # Welcome transaction
    await db.transactions.insert_one({
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "type": "receive",
        "category": "crypto",
        "asset": "USDC",
        "amount": 1250.00,
        "fiat_value": 1250.00,
        "counterparty": "Welcome Bonus",
        "status": "completed",
        "created_at": iso(now_utc()),
    })


# ----------------------------- Routes -----------------------------
@api.get("/")
async def root():
    return {"service": "vaulted", "status": "ok"}


@api.post("/auth/register", response_model=TokenOut)
async def register(body: RegisterIn):
    existing = await db.users.find_one({"email": body.email.lower()})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    uid = str(uuid.uuid4())
    # Generate a real Ethereum keypair + BIP-39 mnemonic for Sepolia testnet
    acct, mnemonic_phrase = Account.create_with_mnemonic()
    # Assign a fresh referral code up-front. ensure_referral_code() will
    # regenerate on the very unlikely 8-char collision, but a direct
    # generate_code() at signup is faster and lands in the doc atomically.
    from referrals import generate_code as _gen_ref_code
    referral_code = _gen_ref_code()
    user_doc = {
        "id": uid,
        "email": body.email.lower(),
        "name": body.name.strip(),
        "password_hash": pwd_ctx.hash(body.password),
        "language": "en",
        "wallet_address": acct.address,
        "eth_private_key": "0x" + acct.key.hex(),
        "eth_mnemonic": mnemonic_phrase,
        "mnemonic_origin": "eth_native",  # derives ETH key via BIP44 m/44'/60'/0'/0/0
        "onboarding_seed_acknowledged": False,
        "biometric_enabled": False,
        "multisig_enabled": False,
        "referral_code": referral_code,
        "created_at": iso(now_utc()),
    }
    await db.users.insert_one(user_doc)
    await seed_user_data(uid)

    # If they signed up via an invite code, record the pending referral now
    # (credit is granted later, on KYC completion).
    if body.referred_by_code:
        row = await register_referral_at_signup(
            db,
            referred_user=user_doc,
            referred_by_code=body.referred_by_code,
        )
        if row:
            await audit_write(db, EventType.REFERRAL_SIGNUP, user=user_doc, data={
                "referral_id": row["id"],
                "referrer_user_id": row["referrer_user_id"],
                "referred_by_code": row["referred_by_code"],
            })
    return TokenOut(access_token=make_token(uid), user=public_user(user_doc))


@api.post("/auth/login", response_model=TokenOut)
async def login(body: LoginIn):
    u = await db.users.find_one({"email": body.email.lower()}, {"_id": 0})
    if not u or not pwd_ctx.verify(body.password, u["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return TokenOut(access_token=make_token(u["id"]), user=public_user(u))


@api.get("/auth/me")
async def me(user=Depends(get_current_user)):
    return public_user(user)


@api.patch("/auth/language")
async def update_language(body: UpdateLanguageIn, user=Depends(get_current_user)):
    await db.users.update_one({"id": user["id"]}, {"$set": {"language": body.language}})
    return {"language": body.language}


@api.patch("/auth/security")
async def update_security(
    body: dict, user=Depends(get_current_user)
):
    updates = {}
    if "biometric_enabled" in body:
        updates["biometric_enabled"] = bool(body["biometric_enabled"])
    if "multisig_enabled" in body:
        updates["multisig_enabled"] = bool(body["multisig_enabled"])
    if updates:
        await db.users.update_one({"id": user["id"]}, {"$set": updates})
    u = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    return public_user(u)


# ============================================================================
# PASSWORD RESET — Resend transactional email + single-use JWT reset token
# ============================================================================
# Rate limit: max 3 password-reset requests per email per hour. We do NOT
# reveal whether an email is registered — the endpoint always returns 200
# with a generic message.  Every reset event is written to the audit log.

PASSWORD_RESET_TOKEN_TTL_SEC = 30 * 60  # 30 minutes
PASSWORD_RESET_MAX_PER_HOUR = 3


async def _send_email_via_resend(to: str, subject: str, html: str) -> bool:
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


def _password_reset_email_html(name: str, reset_url: str) -> str:
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
      <p style="font-size:12px;color:#B8AFA1;line-height:18px;margin:0">If you didn't request this, you can safely ignore this email — your password will stay the same. Your Vaulted funds remain in your self-custody wallet; only the app login is affected.</p>
      <p style="font-size:11px;color:#6d7a73;margin-top:24px">Vaulted · Phoenix Atlas Ltd · UK</p>
    </div>
    """


@api.post("/auth/forgot-password")
async def forgot_password(body: ForgotPasswordIn):
    """Idempotent: always returns the same generic success message so we
    never disclose whether an email is registered.  Rate-limited to 3
    requests per email per hour.  When the email exists we mint a 30-min
    single-use JWT and email a reset link."""
    email = body.email.lower().strip()

    # Rate-limit BEFORE the DB lookup so the timing is uniform regardless
    # of email existence (defeats email-enumeration via response latency).
    one_hour_ago = now_utc() - timedelta(hours=1)
    recent_count = await db.password_resets.count_documents({
        "email": email,
        "created_at": {"$gte": iso(one_hour_ago)},
    })
    if recent_count >= PASSWORD_RESET_MAX_PER_HOUR:
        # Same generic response — but skip the actual work.
        return {"ok": True, "message": "If an account exists for that email, a reset link has been sent."}

    user = await db.users.find_one({"email": email}, {"_id": 0})
    if user:
        # Mint a single-use reset token: JWT with a nonce we persist so we
        # can invalidate it after use / on password-change.
        nonce = secrets.token_urlsafe(24)
        exp = now_utc() + timedelta(seconds=PASSWORD_RESET_TOKEN_TTL_SEC)
        payload = {"sub": user["id"], "purpose": "password_reset", "nonce": nonce, "exp": exp}
        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)

        await db.password_resets.insert_one({
            "id": str(uuid.uuid4()),
            "user_id": user["id"],
            "email": email,
            "nonce": nonce,
            "used_at": None,
            "expires_at": iso(exp),
            "created_at": iso(now_utc()),
        })

        # Build reset URL — prefer APP_PUBLIC_URL (production landing/app),
        # fallback to a sensible default so dev works too.
        base = (APP_PUBLIC_URL or "https://app.phoenix-atlas.com").rstrip("/")
        reset_url = f"{base}/reset-password?token={token}"
        html = _password_reset_email_html(user.get("name") or "", reset_url)
        await _send_email_via_resend(email, "Reset your Vaulted password", html)

        await audit_write(db, EventType.AUTH_FORGOT_PASSWORD_REQUESTED, user=user, data={
            "delivered": True,
            "rate_limit_hits_in_window": recent_count,
        })
    else:
        # Silently record the attempt so we can spot enumeration probing
        # in the audit log. We DON'T write user-scoped audit for a missing
        # email — hash it into the data payload instead so it's still
        # correlateable but never surfaces PII.
        await db.password_resets.insert_one({
            "id": str(uuid.uuid4()),
            "user_id": None,
            "email": email,
            "nonce": None,
            "used_at": None,
            "expires_at": None,
            "created_at": iso(now_utc()),
            "no_user": True,
        })

    return {"ok": True, "message": "If an account exists for that email, a reset link has been sent."}


@api.post("/auth/reset-password")
async def reset_password(body: ResetPasswordIn):
    """Validate the single-use reset token, set the new password hash,
    burn the nonce so the token cannot be replayed."""
    # 1) Decode + verify the JWT
    try:
        payload = jwt.decode(body.token, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.ExpiredSignatureError as e:
        await audit_write(db, EventType.AUTH_PASSWORD_RESET_INVALID_TOKEN, user=None, data={"reason": "expired"})
        raise HTTPException(status_code=400, detail="Reset link has expired. Request a new one.") from e
    except Exception as e:  # noqa: BLE001
        await audit_write(db, EventType.AUTH_PASSWORD_RESET_INVALID_TOKEN, user=None, data={"reason": "invalid_jwt"})
        raise HTTPException(status_code=400, detail="Invalid reset link.") from e

    if payload.get("purpose") != "password_reset":
        raise HTTPException(status_code=400, detail="Invalid reset link.")
    user_id = payload.get("sub")
    nonce = payload.get("nonce")
    if not user_id or not nonce:
        raise HTTPException(status_code=400, detail="Invalid reset link.")

    # 2) Verify the nonce still exists + hasn't been used
    row = await db.password_resets.find_one({"user_id": user_id, "nonce": nonce})
    if not row:
        await audit_write(db, EventType.AUTH_PASSWORD_RESET_INVALID_TOKEN, user=None, data={"reason": "nonce_not_found"})
        raise HTTPException(status_code=400, detail="Invalid reset link.")
    if row.get("used_at"):
        await audit_write(db, EventType.AUTH_PASSWORD_RESET_INVALID_TOKEN, user=None, data={"reason": "nonce_already_used"})
        raise HTTPException(status_code=400, detail="This reset link has already been used. Request a new one.")

    # 3) Update the password + burn the nonce (both atomically-ish)
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=400, detail="Invalid reset link.")

    new_hash = pwd_ctx.hash(body.new_password)
    await db.users.update_one({"id": user_id}, {"$set": {"password_hash": new_hash}})
    await db.password_resets.update_one(
        {"user_id": user_id, "nonce": nonce},
        {"$set": {"used_at": iso(now_utc())}},
    )
    # Belt-and-braces: mark any OTHER outstanding tokens for this user as
    # consumed too, so a password change invalidates every parallel link.
    await db.password_resets.update_many(
        {"user_id": user_id, "nonce": {"$ne": nonce}, "used_at": None},
        {"$set": {"used_at": iso(now_utc()), "invalidated_by_reset": True}},
    )

    await audit_write(db, EventType.AUTH_PASSWORD_RESET_COMPLETED, user=user, data={
        "nonce_prefix": nonce[:8],
    })

    return {"ok": True, "message": "Password updated. You can now sign in with your new password."}


# Wallet
async def _eth_rpc(method: str, params: list) -> dict:
    async with httpx.AsyncClient(timeout=12) as cx:
        r = await cx.post(SEPOLIA_RPC_URL, json={"jsonrpc": "2.0", "method": method, "params": params, "id": 1})
        return r.json()


async def _fetch_eth_balance_wei(addr: str) -> int:
    data = await _eth_rpc("eth_getBalance", [addr, "latest"])
    return int(data.get("result", "0x0"), 16)


@api.get("/wallet/assets")
async def wallet_assets(user=Depends(get_current_user)):
    cursor = db.balances.find({"user_id": user["id"]}, {"_id": 0})
    items = await cursor.to_list(100)

    # Backfill: ensure every DEFAULT_ASSET has a balance row for this user.
    # This is critical for existing users who registered BEFORE a new chain
    # (e.g. XLM) was added — otherwise the asset never appears in their wallet.
    existing_syms = {b.get("symbol") for b in items}
    for a in DEFAULT_ASSETS:
        if a["symbol"] not in existing_syms:
            row = {
                "id": str(uuid.uuid4()),
                "user_id": user["id"],
                "symbol": a["symbol"],
                "name": a["name"],
                "amount": SEED_BALANCES.get(a["symbol"], 0),
                "icon": a["icon"],
                "updated_at": iso(now_utc()),
            }
            try:
                await db.balances.insert_one(row)
            except Exception as e:
                logger.warning(f"balance backfill failed for {a['symbol']}: {e}")
            # `insert_one` mutates `row` by injecting a Mongo `_id` (ObjectId),
            # which breaks FastAPI's JSON encoder. Strip it before appending.
            row.pop("_id", None)
            items.append(row)

    # Fetch live prices + sparklines (cached server-side)
    market = await _refresh_market_prices()
    market_assets = market.get("assets") or {}
    price_map = {sym: ma.get("price_usd", 0) for sym, ma in market_assets.items()}
    # Fall back to defaults for any missing symbol
    for a in DEFAULT_ASSETS:
        price_map.setdefault(a["symbol"], a["price_usd"])

    # Fetch live ETH balance from Sepolia
    addr = user.get("wallet_address")
    eth_wei = 0
    if addr and addr.startswith("0x") and len(addr) == 42:
        try:
            eth_wei = await _fetch_eth_balance_wei(addr)
        except Exception as e:
            logger.warning(f"eth balance fetch failed: {e}")
    eth_amount = eth_wei / 1e18

    # Ensure BTC + SOL + XLM + XRP addresses exist (derived from the user's mnemonic).
    multichain_addrs = await _ensure_multichain_addresses(user)
    btc_addr = multichain_addrs.get("btc")
    sol_addr = multichain_addrs.get("sol")
    xlm_addr = multichain_addrs.get("xlm")
    xrp_addr = multichain_addrs.get("xrp")

    # Live balances on the real testnets
    btc_amount = 0.0
    sol_amount = 0.0
    usdc_amount = 0.0
    xlm_amount = 0.0
    xrp_amount = 0.0
    try:
        if btc_addr:
            btc_amount = (await fetch_btc_balance_sats(btc_addr)) / 1e8
    except Exception as e:
        logger.warning(f"btc balance fetch failed: {e}")
    try:
        if sol_addr:
            sol_amount = (await fetch_sol_balance_lamports(sol_addr)) / 1e9
    except Exception as e:
        logger.warning(f"sol balance fetch failed: {e}")
    try:
        if addr and addr.startswith("0x"):
            usdc_amount = (await fetch_usdc_balance_micro(addr)) / 1e6
    except Exception as e:
        logger.warning(f"usdc balance fetch failed: {e}")
    # L2 USDC aggregation — fetch USDC across Polygon, Base, Arbitrum and sum
    # into the wallet's headline USDC number. Per-chain breakdown is exposed
    # via /api/wallet/evm/chains for the Send screen's L2 picker.
    usdc_by_chain = {"sepolia": usdc_amount}
    if addr and addr.startswith("0x"):
        for l2 in ("polygon", "base", "arbitrum"):
            try:
                bal = (await fetch_usdc_balance_on_chain(l2, addr)) / 1e6
                usdc_by_chain[l2] = bal
                usdc_amount += bal
            except Exception as e:
                logger.warning(f"USDC balance fetch failed on {l2}: {e}")
                usdc_by_chain[l2] = 0.0
    try:
        if xlm_addr:
            xlm_amount = (await fetch_xlm_balance_stroops(xlm_addr)) / 1e7
    except Exception as e:
        logger.warning(f"xlm balance fetch failed: {e}")
    try:
        if xrp_addr:
            xrp_amount = (await fetch_xrp_balance_drops(xrp_addr)) / 1e6
    except Exception as e:
        logger.warning(f"xrp balance fetch failed: {e}")

    on_chain_amount = {"ETH": eth_amount, "BTC": btc_amount, "USDC": usdc_amount, "SOL": sol_amount, "XLM": xlm_amount, "XRP": xrp_amount}
    network_for = {
        "ETH": "Mainnet" if USE_MAINNET else "Sepolia",
        "USDC": "Mainnet" if USE_MAINNET else "Sepolia",
        "BTC": "Mainnet" if not BTC_TESTNET else "Testnet3",
        "SOL": "Mainnet" if USE_MAINNET else "Devnet",
        "XLM": "Mainnet" if USE_MAINNET else "Testnet",
        "XRP": "Mainnet" if USE_MAINNET else "Testnet",
    }
    address_for = {"ETH": addr, "USDC": addr, "BTC": btc_addr, "SOL": sol_addr, "XLM": xlm_addr, "XRP": xrp_addr}

    total_usd = 0.0
    out = []
    for b in items:
        sym = b["symbol"]
        p = price_map.get(sym, 0)
        amt = b["amount"]
        on_chain = False
        if sym in on_chain_amount:
            amt = on_chain_amount[sym]
            on_chain = True
            await db.balances.update_one(
                {"user_id": user["id"], "symbol": sym},
                {"$set": {"amount": amt, "updated_at": iso(now_utc())}},
            )
        fiat = round(amt * p, 2)
        total_usd += fiat
        ma = market_assets.get(sym, {})
        out.append({
            **b,
            "amount": amt,
            "price_usd": p,
            "fiat_value": fiat,
            "on_chain": on_chain,
            "network": network_for.get(sym) if on_chain else None,
            "wallet_address": address_for.get(sym),
            "change_24h_pct": ma.get("change_24h_pct", 0.0),
            "sparkline_7d": ma.get("sparkline_7d", []),
        })
    out.sort(key=lambda x: x["fiat_value"], reverse=True)
    return {
        "total_usd": round(total_usd, 2),
        "wallet_address": addr,
        "btc_address": btc_addr,
        "sol_address": sol_addr,
        "xlm_address": xlm_addr,
        "xrp_address": xrp_addr,
        "usdc_by_chain": usdc_by_chain,
        "assets": out,
        "prices_fetched_at": market.get("fetched_at"),
    }


@api.get("/wallet/eth/info")
async def eth_info(user=Depends(get_current_user)):
    addr = user.get("wallet_address")
    if not addr:
        raise HTTPException(status_code=400, detail="No wallet address")
    try:
        wei = await _fetch_eth_balance_wei(addr)
        gas_price_resp = await _eth_rpc("eth_gasPrice", [])
        gas_price_wei = int(gas_price_resp.get("result", "0x0"), 16)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Sepolia RPC error: {e}")
    return {
        "address": addr,
        "balance_wei": str(wei),
        "balance_eth": wei / 1e18,
        "chain_id": SEPOLIA_CHAIN_ID,
        "network": "Sepolia",
        "gas_price_wei": str(gas_price_wei),
        "gas_price_gwei": gas_price_wei / 1e9,
        "explorer": f"https://sepolia.etherscan.io/address/{addr}",
        "faucet": "https://sepoliafaucet.com/",
    }


# ---------- Multichain (BTC + SOL + XLM + XRP) ------------------------------
async def _ensure_multichain_addresses(user: dict) -> dict:
    """Derive BTC + SOL + XLM + XRP addresses from the user's mnemonic if not yet stored.
    For legacy accounts created before BIP-39 onboarding, a fresh mnemonic is
    generated transparently — the old ETH key is preserved untouched (multichain
    derivation just needs *a* mnemonic, not the one that birthed the ETH key)."""
    if (
        user.get("btc_address")
        and user.get("sol_address")
        and user.get("xlm_address")
        and user.get("xrp_address")
    ):
        return {
            "btc": user["btc_address"],
            "sol": user["sol_address"],
            "xlm": user["xlm_address"],
            "xrp": user["xrp_address"],
        }
    mnemonic = user.get("eth_mnemonic") or user.get("mnemonic")
    update: dict = {}
    if not mnemonic:
        try:
            Account.enable_unaudited_hdwallet_features()
            _, mnemonic = Account.create_with_mnemonic()
        except Exception as e:
            logger.warning(f"legacy mnemonic backfill failed: {e}")
            return {"btc": None, "sol": None, "xlm": None, "xrp": None}
        update["eth_mnemonic"] = mnemonic
        update["mnemonic_origin"] = "multichain_only"
    try:
        addrs = derive_addresses(mnemonic)
    except Exception as e:
        logger.warning(f"multichain derivation failed: {e}")
        return {"btc": None, "sol": None, "xlm": None, "xrp": None}
    update["btc_address"] = addrs["btc"]
    update["sol_address"] = addrs["sol"]
    update["xlm_address"] = addrs["xlm"]
    update["xrp_address"] = addrs["xrp"]
    await db.users.update_one({"id": user["id"]}, {"$set": update})
    user.update(update)
    return {
        "btc": addrs["btc"],
        "sol": addrs["sol"],
        "xlm": addrs["xlm"],
        "xrp": addrs["xrp"],
    }


@api.get("/wallet/btc/info")
async def btc_info(user=Depends(get_current_user)):
    addrs = await _ensure_multichain_addresses(user)
    a = addrs["btc"]
    if not a:
        raise HTTPException(status_code=400, detail="No BTC address (mnemonic missing)")
    try:
        sats = await fetch_btc_balance_sats(a)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"BTC RPC error: {e}")
    return {
        "address": a,
        "balance_sats": sats,
        "balance_btc": sats / 1e8,
        "network": "Mainnet" if not BTC_TESTNET else "Testnet",
        "explorer": explorer_url_btc(a),
        "faucet": "https://coinfaucet.eu/en/btc-testnet/" if BTC_TESTNET else None,
        "send_supported": True,
    }


@api.get("/wallet/sol/info")
async def sol_info(user=Depends(get_current_user)):
    addrs = await _ensure_multichain_addresses(user)
    a = addrs["sol"]
    if not a:
        raise HTTPException(status_code=400, detail="No SOL address (mnemonic missing)")
    try:
        lamports = await fetch_sol_balance_lamports(a)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"SOL RPC error: {e}")
    return {
        "address": a,
        "balance_lamports": lamports,
        "balance_sol": lamports / 1e9,
        "network": "Mainnet" if USE_MAINNET else "Devnet",
        "explorer": explorer_url_sol(a),
        "faucet": "https://faucet.solana.com/" if not USE_MAINNET else None,
        "send_supported": True,
    }


@api.get("/wallet/usdc/info")
async def usdc_info(user=Depends(get_current_user)):
    addr = user.get("wallet_address")
    if not addr:
        raise HTTPException(status_code=400, detail="No wallet address")
    try:
        micro = await fetch_usdc_balance_micro(addr)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"USDC balance error: {e}")
    return {
        "address": addr,
        "balance_micro": micro,
        "balance_usdc": micro / 1e6,
        "network": "Mainnet" if USE_MAINNET else "Sepolia",
        "contract": USDC_CONTRACT,
        "explorer": f"https://sepolia.etherscan.io/address/{addr}",
        "send_supported": True,
    }


class SendUsdcIn(BaseModel):
    to_address: str
    amount_usdc: float = Field(gt=0)


@api.post("/wallet/usdc/send")
async def usdc_send(body: SendUsdcIn, user=Depends(get_current_user)):
    pk = user.get("eth_private_key")
    addr = user.get("wallet_address")
    if not pk or not addr:
        raise HTTPException(status_code=400, detail="No ETH key on file")
    to = body.to_address.strip()
    if not (to.startswith("0x") and len(to) == 42):
        raise HTTPException(status_code=400, detail="Invalid recipient address")

    # Pre-flight USDC balance check (in micro-USDC)
    try:
        bal_micro = await fetch_usdc_balance_micro(addr)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"USDC balance error: {e}")
    need_micro = int(round(body.amount_usdc * 1_000_000))
    if bal_micro < need_micro:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient USDC (need {body.amount_usdc}, have {bal_micro/1e6})",
        )

    # Build + sign + broadcast an ERC-20 transfer
    try:
        data = encode_usdc_transfer(to, body.amount_usdc)
        nonce_resp = await _eth_rpc("eth_getTransactionCount", [addr, "latest"])
        nonce = int(nonce_resp.get("result", "0x0"), 16)
        gas_price_resp = await _eth_rpc("eth_gasPrice", [])
        gas_price = int(gas_price_resp.get("result", "0x0"), 16)

        tx = {
            "to": USDC_CONTRACT,
            "value": 0,
            "gas": 100000,
            "gasPrice": gas_price,
            "nonce": nonce,
            "data": data,
            "chainId": SEPOLIA_CHAIN_ID,
        }
        signed = Account.from_key(pk).sign_transaction(tx)
        raw_hex = signed.raw_transaction.hex() if hasattr(signed, "raw_transaction") else signed.rawTransaction.hex()
        if not raw_hex.startswith("0x"):
            raw_hex = "0x" + raw_hex
        bcast = await _eth_rpc("eth_sendRawTransaction", [raw_hex])
        tx_hash = bcast.get("result")
        if not tx_hash:
            err = bcast.get("error", {})
            raise HTTPException(status_code=400, detail=err.get("message", "Broadcast failed"))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"USDC send failed: {e}")

    fiat = round(body.amount_usdc * 1.0, 2)  # USDC ≈ $1
    record = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "type": "send",
        "category": "Crypto · USDC",
        "asset": "USDC",
        "amount": body.amount_usdc,
        "fiat_value": fiat,
        "counterparty": to,
        "network": "Mainnet" if USE_MAINNET else "Sepolia",
        "tx_hash": tx_hash,
        "explorer_url": f"https://sepolia.etherscan.io/tx/{tx_hash}",
        "status": "pending",
        "service_fee_usd": 0.0,
        "created_at": iso(now_utc()),
    }
    await db.transactions.insert_one(record)
    record.pop("_id", None)
    return record


# ============================================================================
# EVM L2 CHAINS — Polygon, Base, Arbitrum (cheap USDC route for remittances)
# ============================================================================
@api.get("/wallet/evm/chains")
async def evm_chains(user=Depends(get_current_user)):
    """List every supported EVM chain with the current user's USDC balance and
    a live native-token balance (for gas). Powers the Send screen's L2 picker
    and the Remit chain selection UI."""
    addr = user.get("wallet_address")
    out = []
    for cfg in list_evm_chains(include_sepolia=True):
        usdc_bal = 0.0
        native_bal_wei = 0
        if addr and addr.startswith("0x"):
            try:
                usdc_bal = (await fetch_usdc_balance_on_chain(cfg["chain"], addr)) / 1e6
            except Exception as e:
                logger.warning(f"USDC balance failed on {cfg['chain']}: {e}")
            # Best-effort native balance — never block the response on this
            try:
                native_bal_wei = await fetch_native_balance_on_chain(cfg["chain"], addr)
            except Exception:
                native_bal_wei = 0
        out.append({
            **cfg,
            "usdc_balance": round(usdc_bal, 6),
            "native_balance": native_bal_wei / 1e18,
            "wallet_address": addr,
        })
    return {"chains": out}


class SendEvmUsdcIn(BaseModel):
    chain: str  # "polygon" | "base" | "arbitrum" | "sepolia"
    to_address: str
    amount_usdc: float = Field(gt=0)


@api.post("/wallet/evm/usdc/send")
async def evm_usdc_send(body: SendEvmUsdcIn, user=Depends(get_current_user)):
    """Broadcast a USDC transfer on the specified EVM chain (Polygon / Base /
    Arbitrum / Sepolia). Reuses the user's existing ETH private key — the
    same 0x address holds USDC on every EVM chain, so no new key derivation
    is needed."""
    # 1) Validate chain first — cheap fail
    chain = body.chain.lower().strip()
    try:
        cfg = evm_chain_config(chain)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    # 2) Validate recipient address
    to = body.to_address.strip()
    if not (to.startswith("0x") and len(to) == 42):
        raise HTTPException(status_code=400, detail="Invalid recipient (0x-prefixed 42 chars required)")

    # 3) Require signing material — auto-backfill from mnemonic if legacy user
    pk = await _ensure_eth_private_key(user)
    addr = user.get("wallet_address")
    if not pk or not addr:
        raise HTTPException(status_code=400, detail="No ETH key on file")

    # 4) Pre-flight USDC balance on the specified chain
    try:
        bal_micro = await fetch_usdc_balance_on_chain(chain, addr)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"USDC balance error on {chain}: {e}") from e
    need_micro = int(round(body.amount_usdc * 1_000_000))
    if bal_micro < need_micro:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Insufficient USDC on {cfg['display_name']} "
                f"(need {body.amount_usdc}, have {bal_micro/1e6}). "
                f"Top up via {cfg.get('faucet_usdc') or 'the Circle faucet'}."
            ),
        )

    try:
        result = await usdc_send_on_chain(chain, pk, addr, to, body.amount_usdc)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"USDC send failed on {chain}: {str(e)[:200]}") from e

    fiat = round(body.amount_usdc * 1.0, 2)  # USDC ≈ $1
    record = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "type": "send",
        "category": f"Crypto · USDC ({cfg['short']})",
        "asset": "USDC",
        "amount": body.amount_usdc,
        "fiat_value": fiat,
        "counterparty": to,
        "network": cfg["network"],
        "chain": chain,
        "chain_id": cfg["chain_id"],
        "tx_hash": result["tx_hash"],
        "explorer_url": result["explorer_url"],
        "status": "pending",
        "service_fee_usd": 0.0,
        "created_at": iso(now_utc()),
    }
    await db.transactions.insert_one(record)
    record.pop("_id", None)
    return record


class SendCoinIn(BaseModel):
    to_address: str
    amount: float = Field(gt=0)


@api.post("/wallet/btc/send")
async def btc_send_route(body: SendCoinIn, user=Depends(get_current_user)):
    """Broadcast a BTC transfer (testnet3 by default). `bit` selects UTXOs and
    handles change automatically. The mnemonic is loaded from the user's doc;
    addresses are auto-derived on first call."""
    # ensure addresses are derived + mnemonic backfilled if needed
    await _ensure_multichain_addresses(user)
    mnemonic = user.get("eth_mnemonic") or user.get("mnemonic")
    if not mnemonic:
        raise HTTPException(status_code=400, detail="No mnemonic on file")
    to = body.to_address.strip()
    # Loose validation — bit will reject bad addresses on its own with a clearer error.
    if not to or len(to) < 26:
        raise HTTPException(status_code=400, detail="Invalid recipient address")

    # Pre-flight balance check so we surface a clean 400 (not a 502 HTML ingress page)
    # when the user has zero/insufficient testnet UTXOs.
    btc_addr = user.get("btc_address")
    if btc_addr:
        try:
            sats = await fetch_btc_balance_sats(btc_addr)
        except Exception:
            sats = None
        if sats is not None:
            have = sats / 1e8
            # Reserve ~1000 sats (1e-5 BTC) buffer for the miner fee
            if have < body.amount + 0.00001:
                raise HTTPException(
                    status_code=400,
                    detail=f"Insufficient BTC (need {body.amount}+fee, have {have})",
                )

    try:
        result = await btc_send(mnemonic, to, body.amount)
    except Exception as e:
        msg = str(e)
        if "insufficient" in msg.lower():
            raise HTTPException(status_code=400, detail="Insufficient BTC (incl. miner fee)") from e
        # Return 400 (not 502) so the JSON body survives the ingress
        raise HTTPException(status_code=400, detail=f"BTC broadcast failed: {msg[:200]}") from e

    fiat_value = await _btc_to_usd(body.amount)
    record = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "type": "send",
        "category": "Crypto · BTC",
        "asset": "BTC",
        "amount": body.amount,
        "fiat_value": fiat_value,
        "counterparty": to,
        "network": "Mainnet" if not BTC_TESTNET else "Testnet",
        "tx_hash": result["tx_hash"],
        "explorer_url": result["explorer_url"],
        "status": "pending",
        "service_fee_usd": 0.0,
        "created_at": iso(now_utc()),
    }
    await db.transactions.insert_one(record)
    record.pop("_id", None)
    return record


@api.post("/wallet/sol/send")
async def sol_send_route(body: SendCoinIn, user=Depends(get_current_user)):
    """Broadcast a SOL transfer (devnet by default). Signs via solders ed25519."""
    await _ensure_multichain_addresses(user)
    mnemonic = user.get("eth_mnemonic") or user.get("mnemonic")
    if not mnemonic:
        raise HTTPException(status_code=400, detail="No mnemonic on file")
    to = body.to_address.strip()
    if not to or len(to) < 32:
        raise HTTPException(status_code=400, detail="Invalid Solana address")

    # Pre-flight balance check so we surface the friendly error before signing
    addr = user.get("sol_address")
    if addr:
        try:
            bal = await fetch_sol_balance_lamports(addr)
        except Exception:
            bal = None
        if bal is not None:
            need = int(round(body.amount * 1_000_000_000))
            # Leave a tiny buffer for the fee (~5000 lamports)
            if bal < need + 5000:
                raise HTTPException(
                    status_code=400,
                    detail=f"Insufficient SOL (need {body.amount}+fee, have {bal/1e9})",
                )

    try:
        result = await sol_send(mnemonic, to, body.amount)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"SOL broadcast failed: {str(e)[:200]}") from e

    fiat_value = await _sol_to_usd(body.amount)
    record = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "type": "send",
        "category": "Crypto · SOL",
        "asset": "SOL",
        "amount": body.amount,
        "fiat_value": fiat_value,
        "counterparty": to,
        "network": "Mainnet" if USE_MAINNET else "Devnet",
        "tx_hash": result["tx_hash"],
        "explorer_url": result["explorer_url"],
        "status": "pending",
        "service_fee_usd": 0.0,
        "created_at": iso(now_utc()),
    }
    await db.transactions.insert_one(record)
    record.pop("_id", None)
    return record


async def _btc_to_usd(amount_btc: float) -> float:
    try:
        market = await _refresh_market_prices()
        price = next((a.get("price_usd", 0) for a in market.get("assets", []) if a.get("symbol") == "BTC"), 0)
        return round(amount_btc * price, 2)
    except Exception:
        return 0.0


async def _sol_to_usd(amount_sol: float) -> float:
    try:
        market = await _refresh_market_prices()
        price = next((a.get("price_usd", 0) for a in market.get("assets", []) if a.get("symbol") == "SOL"), 0)
        return round(amount_sol * price, 2)
    except Exception:
        return 0.0


async def _xlm_to_usd(amount_xlm: float) -> float:
    try:
        market = await _refresh_market_prices()
        price = next((a.get("price_usd", 0) for a in market.get("assets", []) if a.get("symbol") == "XLM"), 0)
        return round(amount_xlm * price, 2)
    except Exception:
        return 0.0


@api.get("/wallet/xlm/info")
async def xlm_info(user=Depends(get_current_user)):
    addrs = await _ensure_multichain_addresses(user)
    a = addrs["xlm"]
    if not a:
        raise HTTPException(status_code=400, detail="No XLM address (mnemonic missing)")
    try:
        stroops = await fetch_xlm_balance_stroops(a)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"XLM Horizon error: {e}")
    return {
        "address": a,
        "balance_stroops": stroops,
        "balance_xlm": stroops / 1e7,
        "network": "Mainnet" if USE_MAINNET else "Testnet",
        "explorer": explorer_url_xlm(a),
        "faucet": "https://friendbot.stellar.org/?addr=" + a if not USE_MAINNET else None,
        "send_supported": True,
        "min_reserve_xlm": 1.0,  # Stellar's activation reserve (1 XLM = 0.5 base + 0.5 per subentry)
    }


class SendXlmIn(BaseModel):
    to_address: str
    amount: float = Field(gt=0)
    memo: Optional[str] = None


@api.post("/wallet/xlm/send")
async def xlm_send_route(body: SendXlmIn, user=Depends(get_current_user)):
    """Broadcast a native XLM payment via Stellar Horizon. Signs via stellar-sdk (ed25519)."""
    await _ensure_multichain_addresses(user)
    mnemonic = user.get("eth_mnemonic") or user.get("mnemonic")
    if not mnemonic:
        raise HTTPException(status_code=400, detail="No mnemonic on file")
    to = body.to_address.strip()
    if not to.startswith("G") or len(to) != 56:
        raise HTTPException(status_code=400, detail="Invalid Stellar (G...) address")

    # Pre-flight balance check — Stellar accounts must retain a 1 XLM base reserve
    addr = user.get("xlm_address")
    if addr:
        try:
            stroops = await fetch_xlm_balance_stroops(addr)
        except Exception:
            stroops = None
        if stroops is not None:
            have_xlm = stroops / 1e7
            # Reserve 1.0001 XLM (1 base reserve + tiny fee headroom)
            if have_xlm < body.amount + 1.0001:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Insufficient XLM (need {body.amount}+1 reserve, have {have_xlm:.4f}). "
                        f"Stellar requires a 1 XLM minimum reserve to keep accounts active."
                    ),
                )

    try:
        result = await xlm_send(mnemonic, to, body.amount, memo=body.memo)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"XLM submission failed: {str(e)[:200]}") from e

    fiat_value = await _xlm_to_usd(body.amount)
    record = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "type": "send",
        "category": "Crypto · XLM",
        "asset": "XLM",
        "amount": body.amount,
        "fiat_value": fiat_value,
        "counterparty": to,
        "memo": body.memo,
        "network": "Mainnet" if USE_MAINNET else "Testnet",
        "tx_hash": result["tx_hash"],
        "explorer_url": result["explorer_url"],
        "status": "pending",
        "service_fee_usd": 0.0,
        "created_at": iso(now_utc()),
    }
    await db.transactions.insert_one(record)
    record.pop("_id", None)
    return record


async def _xrp_to_usd(amount_xrp: float) -> float:
    try:
        market = await _refresh_market_prices()
        price = next((a.get("price_usd", 0) for a in market.get("assets", []) if a.get("symbol") == "XRP"), 0)
        return round(amount_xrp * price, 2)
    except Exception:
        return 0.0


@api.get("/wallet/xrp/info")
async def xrp_info(user=Depends(get_current_user)):
    addrs = await _ensure_multichain_addresses(user)
    a = addrs["xrp"]
    if not a:
        raise HTTPException(status_code=400, detail="No XRP address (mnemonic missing)")
    try:
        drops = await fetch_xrp_balance_drops(a)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"XRPL RPC error: {e}")
    return {
        "address": a,
        "balance_drops": drops,
        "balance_xrp": drops / 1e6,
        "network": "Mainnet" if USE_MAINNET else "Testnet",
        "explorer": explorer_url_xrp(a),
        # XRPL testnet faucet — POST endpoint that funds new accounts with 100 XRP
        "faucet": "https://faucet.altnet.rippletest.net/accounts" if not USE_MAINNET else None,
        "send_supported": True,
        # 10 XRP base reserve on mainnet, 1 XRP on testnet (per validated ledger)
        "min_reserve_xrp": 10.0 if USE_MAINNET else 1.0,
    }


class SendXrpIn(BaseModel):
    to_address: str
    amount: float = Field(gt=0)
    memo: Optional[str] = None


@api.post("/wallet/xrp/send")
async def xrp_send_route(body: SendXrpIn, user=Depends(get_current_user)):
    """Broadcast a native XRP payment via the XRPL JSON-RPC. Signs via xrpl-py (secp256k1)."""
    await _ensure_multichain_addresses(user)
    mnemonic = user.get("eth_mnemonic") or user.get("mnemonic")
    if not mnemonic:
        raise HTTPException(status_code=400, detail="No mnemonic on file")
    to = body.to_address.strip()
    if not to.startswith("r") or not (25 <= len(to) <= 40):
        raise HTTPException(status_code=400, detail="Invalid XRP (r...) address")

    # Pre-flight balance check — XRPL accounts must retain a base reserve
    addr = user.get("xrp_address")
    reserve_xrp = 10.0 if USE_MAINNET else 1.0
    if addr:
        try:
            drops = await fetch_xrp_balance_drops(addr)
        except Exception:
            drops = None
        if drops is not None:
            have_xrp = drops / 1e6
            if have_xrp < body.amount + reserve_xrp + 0.001:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Insufficient XRP (need {body.amount}+{reserve_xrp} reserve, have {have_xrp:.6f}). "
                        f"XRPL requires a {reserve_xrp} XRP minimum reserve to keep accounts active."
                    ),
                )

    try:
        result = await xrp_send(mnemonic, to, body.amount, memo=body.memo)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"XRP submission failed: {str(e)[:200]}") from e

    fiat_value = await _xrp_to_usd(body.amount)
    record = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "type": "send",
        "category": "Crypto · XRP",
        "asset": "XRP",
        "amount": body.amount,
        "fiat_value": fiat_value,
        "counterparty": to,
        "memo": body.memo,
        "network": "Mainnet" if USE_MAINNET else "Testnet",
        "tx_hash": result["tx_hash"],
        "explorer_url": result["explorer_url"],
        "status": "pending",
        "service_fee_usd": 0.0,
        "created_at": iso(now_utc()),
    }
    await db.transactions.insert_one(record)
    record.pop("_id", None)
    return record


# ============================================================================
# CROSS-BORDER REMITTANCE — fiat-first UX (Phase B)
# ============================================================================
FREE_TIER_REMIT_LIMIT = 3  # per calendar month, per user


def _first_of_month_utc() -> datetime:
    """UTC timestamp for 00:00 on the first day of the current month."""
    now = now_utc()
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def _remit_send_count_this_month(user_id: str) -> int:
    """Count of remittance sends the user has completed in the current month."""
    return await db.transactions.count_documents({
        "user_id": user_id,
        "category": {"$regex": "^Remit ·"},
        "status": {"$ne": "failed"},
        "created_at": {"$gte": iso(_first_of_month_utc())},
    })


@api.get("/remit/corridors")
async def remit_corridors():
    """Public — no auth needed for the marketing landing to preview corridors."""
    return {
        "source_fiats": SOURCE_FIATS,
        "corridors": [{"code": code, **info} for code, info in CORRIDORS.items()],
    }


class RemitQuoteIn(BaseModel):
    source_fiat: str = Field(min_length=3, max_length=3)
    amount: float = Field(gt=0)
    destination_code: str = Field(min_length=2, max_length=2)


@api.post("/remit/quote")
async def remit_quote(body: RemitQuoteIn, user=Depends(get_current_user)):
    """Return the best chain, fees, and destination-fiat receive amount for a corridor."""
    src = body.source_fiat.upper()
    if src not in SOURCE_FIATS:
        raise HTTPException(status_code=400, detail=f"Unsupported source currency: {src}")
    corridor = CORRIDORS.get(body.destination_code.upper())
    if not corridor:
        raise HTTPException(status_code=400, detail="Unsupported destination corridor")

    # Hard-block OFAC/UK/EU comprehensive-sanctions countries at quote time
    # so users never see a "send" CTA to a jurisdiction we can't legally serve.
    block_reason = is_country_blocked(body.destination_code)
    if block_reason:
        raise HTTPException(status_code=403, detail={
            "error": "corridor_blocked",
            "message": f"We cannot send money to {corridor['country']}. {block_reason}",
        })

    # 1) FX rates
    fx = await refresh_fx_rates(db)
    rates = fx.get("rates") or {}
    # Convert send amount to USD (all internal math is USD-normalised)
    amount_usd = convert_fiat(body.amount, src, "USD", rates)
    if amount_usd <= 0:
        raise HTTPException(status_code=400, detail="Invalid quote amount")

    # 2) Crypto prices + user's on-chain holdings
    market = await _refresh_market_prices()
    market_assets = market.get("assets") or {}
    crypto_prices_usd = {sym: (ma.get("price_usd") or 0) for sym, ma in market_assets.items()}

    # Refresh live balances so quote reflects reality (not stale DB rows).
    # This mirrors what /wallet/assets does but only for remit-eligible chains.
    multichain_addrs = await _ensure_multichain_addresses(user)
    holdings: dict[str, float] = {}
    try:
        xlm_addr = multichain_addrs.get("xlm")
        if xlm_addr:
            holdings["XLM"] = (await fetch_xlm_balance_stroops(xlm_addr)) / 1e7
    except Exception as e:
        logger.warning(f"remit: XLM balance fetch failed: {e}")
        holdings["XLM"] = 0.0
    try:
        xrp_addr = multichain_addrs.get("xrp")
        if xrp_addr:
            holdings["XRP"] = (await fetch_xrp_balance_drops(xrp_addr)) / 1e6
    except Exception as e:
        logger.warning(f"remit: XRP balance fetch failed: {e}")
        holdings["XRP"] = 0.0
    try:
        eth_addr = user.get("wallet_address")
        if eth_addr and eth_addr.startswith("0x"):
            holdings["USDC"] = (await fetch_usdc_balance_micro(eth_addr)) / 1e6
            # Also probe every L2 for cheap USDC routes
            for l2, key in (("polygon", "USDC_POLYGON"), ("base", "USDC_BASE"), ("arbitrum", "USDC_ARBITRUM")):
                try:
                    holdings[key] = (await fetch_usdc_balance_on_chain(l2, eth_addr)) / 1e6
                except Exception as e:
                    logger.warning(f"remit: USDC {l2} balance fetch failed: {e}")
                    holdings[key] = 0.0
    except Exception as e:
        logger.warning(f"remit: USDC balance fetch failed: {e}")
        holdings["USDC"] = 0.0

    # 3) Chain selection
    pick = choose_chain(amount_usd, holdings, crypto_prices_usd)

    # 4) Vaulted service fee (Pro discount applies)
    is_pro = is_user_pro(user)
    svc_fee_usd = vaulted_fee_usd(amount_usd, is_pro)

    # 5) Recipient amount in destination fiat
    dst_fiat = corridor["currency"]
    dst_amount = convert_fiat(amount_usd, "USD", dst_fiat, rates)

    # 6) Free-tier gate — advisory here, enforced at /remit/send.
    remit_used = await _remit_send_count_this_month(user["id"])
    remit_remaining = max(0, FREE_TIER_REMIT_LIMIT - remit_used) if not is_pro else None
    paywall_required = (not is_pro) and (remit_used >= FREE_TIER_REMIT_LIMIT)

    # 7) KYC/AML tier limits — hard regulatory gate independent of Pro status
    send_gbp = convert_fiat(body.amount, src, "GBP", rates)
    kyc_check = await check_send_limits(db, user, send_gbp)

    quote = {
        "quote_id": str(uuid.uuid4()),
        "source": {"currency": src, "amount": body.amount, "amount_usd": round(amount_usd, 2), "amount_gbp": round(send_gbp, 2)},
        "destination": {
            "code": body.destination_code.upper(),
            "country": corridor["country"],
            "currency": dst_fiat,
            "flag": corridor["flag"],
            "receive_via": corridor["receive_via"],
            "eta": corridor["eta"],
            "amount": round(dst_amount, 2),
        },
        "chain": pick,  # may be None if insufficient liquidity
        "fees": {
            "vaulted_service_usd": svc_fee_usd,
            "chain_fee_usd": (pick or {}).get("chain_fee_usd", 0.0),
            "total_fee_usd": round(svc_fee_usd + (pick or {}).get("chain_fee_usd", 0.0), 2),
        },
        "fx_rate": round(convert_fiat(1.0, src, dst_fiat, rates), 6),
        "fx_fetched_at": fx.get("fetched_at"),
        "free_tier": {
            "limit_per_month": FREE_TIER_REMIT_LIMIT,
            "used_this_month": remit_used,
            "remaining_this_month": remit_remaining,
            "paywall_required": paywall_required,
            "is_pro": is_pro,
        },
        "kyc": kyc_check,
        "sufficient_balance": pick is not None,
        "reason_if_no_chain": (
            "Not enough XLM, XRP, or USDC to cover this send + chain fee. "
            "Tap Receive on any of those assets to top up, then try again."
        ) if pick is None else None,
    }
    return quote


class RemitSendIn(BaseModel):
    source_fiat: str = Field(min_length=3, max_length=3)
    amount: float = Field(gt=0)
    destination_code: str = Field(min_length=2, max_length=2)
    recipient_address: str  # crypto address the recipient controls (until Phase C off-ramp)
    recipient_name: Optional[str] = None
    memo: Optional[str] = None


@api.post("/remit/send")
async def remit_send(body: RemitSendIn, user=Depends(get_current_user)):
    """Fiat-first send: re-quotes, enforces free-tier gate, then broadcasts on the picked chain."""
    is_pro = is_user_pro(user)

    # 0) Hard-block sanctioned destination corridors (defense-in-depth — /quote
    #    already 403s, but we re-check on /send in case the corridor list
    #    shifted between quote and send).
    block_reason = is_country_blocked(body.destination_code)
    if block_reason:
        await audit_write(db, EventType.CORRIDOR_BLOCKED, user=user, data={
            "destination_code": body.destination_code, "reason": block_reason,
            "attempted_amount": body.amount, "source_fiat": body.source_fiat,
        })
        await audit_write(db, EventType.REMIT_SEND_BLOCKED, user=user, data={
            "block_type": "corridor_blocked",
            "destination_code": body.destination_code,
            "attempted_amount": body.amount, "source_fiat": body.source_fiat,
        })
        raise HTTPException(status_code=403, detail={
            "error": "corridor_blocked",
            "message": f"We cannot send to that destination. {block_reason}",
        })

    remit_used = await _remit_send_count_this_month(user["id"])
    if (not is_pro) and remit_used >= FREE_TIER_REMIT_LIMIT:
        await audit_write(db, EventType.REMIT_SEND_BLOCKED, user=user, data={
            "block_type": "free_tier_exhausted",
            "monthly_count": remit_used, "limit": FREE_TIER_REMIT_LIMIT,
            "destination_code": body.destination_code, "attempted_amount": body.amount,
        })
        raise HTTPException(
            status_code=402,
            detail={
                "error": "free_tier_exhausted",
                "message": (
                    f"You've used your {FREE_TIER_REMIT_LIMIT} free cross-border sends this month. "
                    f"Upgrade to Vault Pro for unlimited sends + 50% off service fees."
                ),
                "cta": "upgrade_to_pro",
            },
        )

    # 0.5) COMPLIANCE_STRICT_MODE gate — refuse to send if the user's last
    #      sanctions screen was DEGRADED (no key / API down). Off by default
    #      so early-stage ops can ship without OpenSanctions live; flip on
    #      once a paid key + FCA registration are in place. Verified users
    #      whose screen ran successfully bypass this gate.
    if COMPLIANCE_STRICT_MODE:
        user_kyc = user.get("kyc") or {}
        sanctions = user_kyc.get("sanctions") or {}
        if sanctions.get("degraded", True):
            await audit_write(db, EventType.REMIT_SEND_BLOCKED, user=user, data={
                "block_type": "sanctions_screening_unavailable",
                "degraded_reason": sanctions.get("degraded_reason"),
                "destination_code": body.destination_code,
                "attempted_amount": body.amount,
            })
            raise HTTPException(status_code=503, detail={
                "error": "sanctions_screening_unavailable",
                "message": (
                    "Cross-border sends are temporarily paused — our sanctions "
                    "screening provider is unavailable. Please try again in a few minutes "
                    "or contact support@phoenix-atlas.com."
                ),
                "degraded_reason": sanctions.get("degraded_reason"),
            })

    # Re-run the quote server-side so the client can't cheat rates/chain selection
    quote = await remit_quote(
        RemitQuoteIn(
            source_fiat=body.source_fiat,
            amount=body.amount,
            destination_code=body.destination_code,
        ),
        user=user,
    )
    if not quote["sufficient_balance"] or not quote.get("chain"):
        await audit_write(db, EventType.REMIT_SEND_BLOCKED, user=user, data={
            "block_type": "insufficient_balance",
            "destination_code": body.destination_code,
            "attempted_amount": body.amount, "source_fiat": body.source_fiat,
            "reason": quote.get("reason_if_no_chain"),
        })
        raise HTTPException(status_code=400, detail=quote.get("reason_if_no_chain") or "Insufficient balance")

    # KYC/AML tier gate — HARD block. Cannot be bypassed by Pro subscription;
    # regulatory limits apply regardless of Vaulted product tier.
    kyc = quote.get("kyc") or {}
    if not kyc.get("allowed"):
        await audit_write(db, EventType.REMIT_SEND_BLOCKED, user=user, data={
            "block_type": "kyc_required",
            "reason": kyc.get("reason"),
            "current_tier": kyc.get("current_tier"),
            "destination_code": body.destination_code,
            "attempted_amount": body.amount, "source_fiat": body.source_fiat,
        })
        raise HTTPException(status_code=403, detail={
            "error": "kyc_required",
            "reason": kyc.get("reason"),
            "current_tier": kyc.get("current_tier"),
            "current_tier_label": kyc.get("current_tier_label"),
            "limit": kyc.get("limit"),
            "usage": kyc.get("usage"),
            "upgrade": kyc.get("upgrade"),
            "message": (
                f"This send exceeds your {kyc.get('current_tier_label')} tier limit. "
                f"Verify your identity to unlock up to £{(kyc.get('upgrade') or {}).get('target_per_send_gbp', 0):,.0f} per send."
            ),
        })

    chain = quote["chain"]["chain"]
    crypto_amount = float(quote["chain"]["crypto_amount"])
    to = body.recipient_address.strip()

    # Address validation per chain
    if chain == "XLM" and not (to.startswith("G") and len(to) == 56):
        raise HTTPException(status_code=400, detail="Recipient must be a valid Stellar (G...) address")
    if chain == "XRP" and not (to.startswith("r") and 25 <= len(to) <= 40):
        raise HTTPException(status_code=400, detail="Recipient must be a valid XRP (r...) address")
    if chain.startswith("USDC") and not (to.startswith("0x") and len(to) == 42):
        raise HTTPException(status_code=400, detail="Recipient must be a valid Ethereum (0x...) address")

    mnemonic = user.get("eth_mnemonic") or user.get("mnemonic")
    if not mnemonic:
        raise HTTPException(status_code=400, detail="No mnemonic on file")

    memo_short = (body.memo or f"Vaulted-{body.destination_code.upper()}")[:28]

    # Map remit chain identifier → concrete on-chain send function
    _L2_MAP = {"USDC_POLYGON": "polygon", "USDC_BASE": "base", "USDC_ARBITRUM": "arbitrum", "USDC": "sepolia"}

    try:
        if chain == "XLM":
            result = await xlm_send(mnemonic, to, crypto_amount, memo=memo_short)
        elif chain == "XRP":
            result = await xrp_send(mnemonic, to, crypto_amount, memo=memo_short)
        elif chain in _L2_MAP:
            evm_chain = _L2_MAP[chain]
            pk = user.get("eth_private_key")
            eth_addr = user.get("wallet_address")
            if not pk or not eth_addr:
                raise HTTPException(status_code=400, detail="No ETH key on file")
            result = await usdc_send_on_chain(evm_chain, pk, eth_addr, to, crypto_amount)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported chain: {chain}")
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"{chain} submission failed: {str(e)[:200]}") from e

    dst = quote["destination"]
    tx_id = str(uuid.uuid4())

    # Referral credit — apply to the service fee. Credit is GBP-denominated,
    # so we convert the USD fee via a conservative 0.80 rate (matches the
    # compliance module's FX approximation). If credit fully covers the
    # fee, the user pays nothing on top; otherwise the residual USD fee
    # still applies. Credit spending is fire-and-forget — a ledger failure
    # must NOT block a paid-for send.
    service_fee_usd = float(quote["fees"]["vaulted_service_usd"])
    service_fee_gbp = round(service_fee_usd * 0.80, 4)
    credit_applied_gbp = 0.0
    credit_balance_after_gbp = 0.0
    try:
        offset = await spend_credit_for_fee(
            db, user_id=user["id"], fee_gbp=service_fee_gbp, reference_id=tx_id,
        )
        credit_applied_gbp = offset["applied_gbp"]
        credit_balance_after_gbp = offset["balance_after_gbp"]
        if credit_applied_gbp > 0:
            await audit_write(db, EventType.CREDIT_SPENT, user=user, data={
                "amount_gbp": credit_applied_gbp,
                "reference_id": tx_id,
                "source": "remit_fee_offset",
                "balance_after_gbp": credit_balance_after_gbp,
            })
    except Exception as e:  # noqa: BLE001
        logger.warning(f"credit offset failed for remit {tx_id}: {e}")

    # Effective fee paid by the user after credit offset (still USD-denominated
    # on the tx record for continuity with existing history/analytics).
    remaining_fee_gbp = max(0.0, round(service_fee_gbp - credit_applied_gbp, 4))
    effective_fee_usd = round(remaining_fee_gbp / 0.80, 4) if remaining_fee_gbp else 0.0

    record = {
        "id": tx_id,
        "user_id": user["id"],
        "type": "send",
        "category": f"Remit · {dst['country']}",
        "asset": "USDC" if chain.startswith("USDC") else chain,
        "amount": crypto_amount,
        "fiat_value": quote["source"]["amount_usd"],  # USD-normalised
        "counterparty": to,
        "recipient_name": body.recipient_name,
        "memo": memo_short,
        "network": "Mainnet" if USE_MAINNET else "Testnet",
        "tx_hash": result["tx_hash"],
        "explorer_url": result["explorer_url"],
        "status": "pending",
        "service_fee_usd": effective_fee_usd,
        "gross_service_fee_usd": service_fee_usd,   # for accounting / rev metrics
        "credit_applied_gbp": credit_applied_gbp,
        "credit_balance_after_gbp": credit_balance_after_gbp,
        "created_at": iso(now_utc()),
        # Remit-specific context — used by the receipt screen + activity feed
        "remit": {
            "source_currency": quote["source"]["currency"],
            "source_amount": quote["source"]["amount"],
            "destination_currency": dst["currency"],
            "destination_amount": dst["amount"],
            "destination_country": dst["country"],
            "destination_flag": dst["flag"],
            "chain": chain,
            "fx_rate": quote["fx_rate"],
            "receive_via": dst["receive_via"],
        },
    }
    await db.transactions.insert_one(record)
    record.pop("_id", None)

    # Success audit — the golden path event, one row per completed send
    user_kyc = user.get("kyc") or {}
    user_sanctions = user_kyc.get("sanctions") or {}
    await audit_write(db, EventType.REMIT_SEND_SUCCESS, user=user, data={
        "tx_id": record["id"],
        "tx_hash": record["tx_hash"],
        "chain": chain,
        "source_currency": record["remit"]["source_currency"],
        "source_amount": record["remit"]["source_amount"],
        "destination_country": record["remit"]["destination_country"],
        "destination_currency": record["remit"]["destination_currency"],
        "destination_amount": record["remit"]["destination_amount"],
        "recipient_address_hash": hashlib.sha256(to.lower().encode()).hexdigest()[:12],
        "recipient_name_hash": hashlib.sha256((body.recipient_name or "").strip().lower().encode()).hexdigest()[:12] if body.recipient_name else None,
        "service_fee_usd": record["service_fee_usd"],
        "gross_service_fee_usd": service_fee_usd,
        "credit_applied_gbp": credit_applied_gbp,
        "fiat_value_usd": record["fiat_value"],
        "tier_at_send": user_kyc.get("tier"),
        "sanctions_state_at_send": {
            "matched": user_sanctions.get("matched", False),
            "degraded": user_sanctions.get("degraded", True),
            "degraded_reason": user_sanctions.get("degraded_reason"),
        },
    })
    return record


# ============================================================================
# REMIT / FIAT FUNDING — pay a cross-border send with Card / Apple Pay / Bank
# transfer via Stripe. Users can also still fund from their crypto wallet
# using /remit/send unchanged. The fiat path never surfaces crypto to the
# user; under the hood the send is recorded as processed and settled via
# our off-ramp partners (executed by ops until Kotani Pay / on-chain
# disbursement lands in Phase C).
# ============================================================================
def _stripe_payment_method_config(pm: str) -> dict:
    """Return kwargs for stripe.checkout.Session.create tailored to the
    selected payment method. Card + Apple Pay share Stripe's "card" type
    (Apple Pay / Google Pay are surfaced automatically on supported
    browsers). Bank transfer omits payment_method_types entirely so
    Stripe Checkout auto-shows every method enabled in the dashboard for
    that region (cards + bank rails + wallets)."""
    if pm == "bank":
        # Omit payment_method_types → Stripe Checkout auto-selects from
        # every enabled method in the account (BACS in UK, SEPA in EU,
        # ACH in US, plus cards as fallback).
        return {}
    return {"payment_method_types": ["card"]}


@api.post("/remit/fund")
async def remit_fund(body: RemitFundIn, user=Depends(get_current_user)):
    """Create a Stripe Checkout session to fund a cross-border send with
    fiat. On completion the send is auto-executed by _apply_checkout_session.
    Front-end can call /stripe/sync to receive the tx receipt on return.

    KYC / free-tier / sanctions / corridor gates are enforced here BEFORE
    the user is charged — so we never take money for a blocked send.
    """
    if not STRIPE_API_KEY:
        raise HTTPException(status_code=503, detail="Stripe not configured")

    # 1) Corridor block (same as /remit/send)
    block_reason = is_country_blocked(body.destination_code)
    if block_reason:
        await audit_write(db, EventType.CORRIDOR_BLOCKED, user=user, data={
            "destination_code": body.destination_code, "reason": block_reason,
            "attempted_amount": body.amount, "source_fiat": body.source_fiat,
            "funding_method": "stripe",
        })
        raise HTTPException(status_code=403, detail={
            "error": "corridor_blocked",
            "message": f"We cannot send to that destination. {block_reason}",
        })

    # 2) Free-tier gate — Pro bypasses
    is_pro = is_user_pro(user)
    remit_used = await _remit_send_count_this_month(user["id"])
    if (not is_pro) and remit_used >= FREE_TIER_REMIT_LIMIT:
        raise HTTPException(status_code=402, detail={
            "error": "free_tier_exhausted",
            "message": f"You've used your {FREE_TIER_REMIT_LIMIT} free cross-border sends this month.",
            "cta": "upgrade_to_pro",
        })

    # 3) Re-quote server-side (same as /remit/send). We build our own quote
    #    request here since we don't need on-chain balance to be sufficient
    #    for the fiat path.
    quote = await remit_quote(
        RemitQuoteIn(
            source_fiat=body.source_fiat,
            amount=body.amount,
            destination_code=body.destination_code,
        ),
        user=user,
    )

    # 4) KYC tier — HARD block
    kyc = quote.get("kyc") or {}
    if not kyc.get("allowed"):
        raise HTTPException(status_code=403, detail={
            "error": "kyc_required",
            "reason": kyc.get("reason"),
            "current_tier": kyc.get("current_tier"),
            "current_tier_label": kyc.get("current_tier_label"),
            "limit": kyc.get("limit"),
            "usage": kyc.get("usage"),
            "upgrade": kyc.get("upgrade"),
            "message": (
                f"This send exceeds your {kyc.get('current_tier_label')} tier limit. "
                f"Verify your identity to unlock up to £{(kyc.get('upgrade') or {}).get('target_per_send_gbp', 0):,.0f} per send."
            ),
        })

    # 5) Build the Stripe Checkout session. We charge the user the SOURCE
    #    fiat (GBP / USD / EUR) — no crypto conversion visible.
    src_fiat = body.source_fiat.upper()
    if src_fiat not in ("GBP", "USD", "EUR"):
        raise HTTPException(status_code=400, detail="Unsupported source currency for fiat funding")
    # Charge the source amount + total fees converted to source fiat.
    total_fees_usd = float(quote["fees"]["total_fee_usd"])
    fees_in_src = total_fees_usd * (float(quote["source"]["amount"]) / max(float(quote["source"]["amount_usd"]), 0.01))
    charge_amount_src = round(float(quote["source"]["amount"]) + fees_in_src, 2)
    amount_cents = int(round(charge_amount_src * 100))

    dst = quote["destination"]
    line_item_name = f"Send to {dst['country']} · {dst['flag']}"
    line_item_desc = (
        f"{quote['source']['currency']} {quote['source']['amount']:.2f} → "
        f"{dst['currency']} {dst['amount']:,.2f} · fees included · arrives {dst['eta']}"
    )
    success, cancel = _success_cancel_urls("remit_fund")
    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            **_stripe_payment_method_config(body.payment_method),
            line_items=[{
                "price_data": {
                    "currency": src_fiat.lower(),
                    "product_data": {"name": line_item_name, "description": line_item_desc},
                    "unit_amount": amount_cents,
                },
                "quantity": 1,
            }],
            success_url=success,
            cancel_url=cancel,
            metadata={
                "user_id": user["id"],
                "flow": "remit_fund",
                "source_fiat": src_fiat,
                "source_amount": str(quote["source"]["amount"]),
                "destination_code": body.destination_code.upper(),
                "destination_currency": dst["currency"],
                "destination_amount": str(dst["amount"]),
                "destination_country": dst["country"],
                "destination_flag": dst["flag"],
                "recipient_address": body.recipient_address.strip(),
                "recipient_name": (body.recipient_name or "").strip()[:80],
                "memo": (body.memo or "")[:120],
                "payment_method": body.payment_method,
                "vaulted_service_usd": str(quote["fees"]["vaulted_service_usd"]),
                "fx_rate": str(quote["fx_rate"]),
                "receive_via": dst["receive_via"],
            },
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Stripe error: {e}") from e

    return {
        "checkout_url": session.url,
        "session_id": session.id,
        "charge_amount": charge_amount_src,
        "charge_currency": src_fiat,
        "destination": dst,
        "payment_method": body.payment_method,
    }


# ============================================================================
# OFF-RAMP / KOTANI PAY — USDC → M-Pesa (KES) direct payout to a phone number
# ============================================================================
# Automatically kicks in when a fiat-funded remit lands with destination
# Kenya (KE). The Stripe payment is booked first (funds land in Vaulted's
# balance); then Kotani Pay disburses KES directly to the recipient's
# M-Pesa wallet. Runs in MOCK mode until KOTANI_API_KEY is set in .env —
# flips to LIVE automatically on backend restart with a real key.
# Docs: https://documentation.kotanipay.com/v3/flows/offramp-flow


class OfframpQuoteIn(BaseModel):
    """Ask Kotani for a live USDC→KES rate before initiating a payout.
    Front-end calls this to show the recipient KES amount alongside our
    own remit-quote number so we can flag divergence > 3%."""
    amount_usd: float = Field(gt=0)
    to_currency: str = Field(default="KES", min_length=3, max_length=3)


class OfframpInitiateIn(BaseModel):
    """Auth'd, non-Stripe path: user has already deposited USDC and wants
    to push it straight to an M-Pesa recipient. Rare path — most sends go
    through /remit/fund → automated off-ramp on Stripe callback."""
    phone_number: str = Field(min_length=10, max_length=18)
    recipient_name: str = Field(min_length=1, max_length=80)
    amount_usd: float = Field(gt=0)
    country: str = Field(default="KE", min_length=2, max_length=2)


def _offramp_callback_url() -> str:
    base = (APP_PUBLIC_URL or "https://vaulted-app.onrender.com").rstrip("/")
    return f"{base}/api/offramp/callback"


async def _trigger_kotani_offramp_for_remit(remit_tx: dict) -> dict:
    """Called from _apply_checkout_session for KE-destined fiat-funded
    remits. Books the Kotani off-ramp, updates the transaction row with
    the Kotani reference id, and audits every terminal state.

    Returns a summary dict for the /stripe/sync response. Failures are
    non-fatal — the user still sees a successful send (money charged);
    ops can retry the off-ramp from admin dashboard.
    """
    remit_ctx = (remit_tx.get("remit") or {})
    if remit_ctx.get("destination_country_code") != "KE" and remit_ctx.get("destination_currency") != "KES":
        return {"kotani": {"skipped": True, "reason": "destination not KES/M-Pesa"}}
    phone = (remit_tx.get("counterparty") or "").strip()
    recipient_name = (remit_tx.get("recipient_name") or "").strip() or "Vaulted Recipient"
    src_amount_usd = float(remit_tx.get("fiat_value") or 0.0)
    # Rough USD conversion from source fiat — we already have the tx's
    # source in USD via the remit_quote earlier so this is a passable
    # approximation for the off-ramp instruction.
    kotani_res = await kotani.create_offramp(
        phone_number=phone,
        recipient_name=recipient_name,
        amount_usdc=src_amount_usd,
        estimated_kes=float(remit_ctx.get("destination_amount") or 0.0),
        callback_url=_offramp_callback_url(),
        country="KE",
        currency="KES",
        mobile_money_network="MPESA",
    )
    data = (kotani_res or {}).get("data") or {}
    ref_id = data.get("referenceId")
    kotani_status = data.get("status", "UNKNOWN")

    # Persist the Kotani ref on the transaction so status polls + webhook
    # correlation both work.
    await db.transactions.update_one(
        {"id": remit_tx["id"]},
        {"$set": {
            "kotani": {
                "reference_id": ref_id,
                "status": kotani_status,
                "mode": "live" if kotani.live_mode() else "mock",
                "initiated_at": iso(now_utc()),
                "callback_url": _offramp_callback_url(),
            },
            # Success-status transactions: flip receipt status to "settled"
            # for mock (deterministic) — live mode waits for webhook.
            **({"status": "settled"} if (kotani_status == "SUCCESS" and not kotani.live_mode()) else {}),
        }},
    )

    audit_event = EventType.OFFRAMP_MPESA_INITIATED
    if not kotani_res.get("success"):
        audit_event = EventType.OFFRAMP_MPESA_FAILED
    try:
        user_doc = await db.users.find_one({"id": remit_tx["user_id"]}, {"_id": 0})
        await audit_write(db, audit_event, user=user_doc, data={
            "tx_id": remit_tx["id"],
            "kotani_reference_id": ref_id,
            "kotani_status": kotani_status,
            "kotani_mode": "live" if kotani.live_mode() else "mock",
            "phone_masked": kotani.mask_phone(phone),
            "amount_kes": remit_ctx.get("destination_amount"),
            "amount_usd": src_amount_usd,
        })
    except Exception as e:  # noqa: BLE001
        logger.warning("kotani audit_write failed: %s", e)

    return {"kotani": {"reference_id": ref_id, "status": kotani_status, "mode": "live" if kotani.live_mode() else "mock"}}


@api.get("/offramp/health")
async def offramp_health(_admin=Depends(require_admin)):
    """Admin-only sanity check — confirms Kotani auth works (or that we're
    intentionally in mock mode). Not for end users."""
    res = await kotani.health()
    return {"kotani": res, "config": kotani.diagnostic_info()}


@api.post("/offramp/mpesa/quote")
async def offramp_mpesa_quote(body: OfframpQuoteIn, user=Depends(get_current_user)):
    """Show the user what KES they'll get for a given USD amount. Used
    by the frontend as a secondary rate check next to our own remit quote —
    if Kotani's rate diverges > 3%, we warn the user."""
    res = await kotani.offramp_rate(
        from_token="USDC",
        to_currency=body.to_currency,
        amount_usd=body.amount_usd,
    )
    return {
        "kotani": res,
        "mode": "live" if kotani.live_mode() else "mock",
    }


@api.get("/offramp/mpesa/status/{reference_id}")
async def offramp_mpesa_status(reference_id: str, user=Depends(get_current_user)):
    """Poll a single off-ramp. Also cross-checks the tx belongs to the
    caller (or is admin) to prevent enumeration."""
    tx = await db.transactions.find_one(
        {"$or": [
            {"id": reference_id},
            {"kotani.reference_id": reference_id},
        ]},
        {"_id": 0},
    )
    if not tx:
        raise HTTPException(status_code=404, detail="No such off-ramp reference")
    if tx.get("user_id") != user["id"]:
        # Allow admins through
        if not user.get("is_admin"):
            raise HTTPException(status_code=403, detail="Not your transaction")
    kotani_ref = (tx.get("kotani") or {}).get("reference_id") or reference_id
    res = await kotani.offramp_status(kotani_ref)
    return {"kotani": res, "tx": tx}


@api.post("/offramp/callback")
async def offramp_callback(request: Request):
    """Webhook endpoint — Kotani Pay POSTs terminal state here after fiat
    disbursement. Signature verification is enforced when
    KOTANI_WEBHOOK_SECRET is configured.

    Terminal states we handle:
    - SUCCESS: mark tx settled, record M-Pesa receipt
    - FAILED: mark tx failed, ops will follow up
    - REFUNDED / REFUND_FAILED: informational only for the tx timeline
    """
    payload = await request.body()
    signature = request.headers.get("X-Kotani-Signature")
    event_type = request.headers.get("X-Kotani-Event", "callback")

    if not kotani.verify_webhook_signature(payload, signature):
        await audit_write(db, EventType.OFFRAMP_WEBHOOK_INVALID_SIGNATURE, user=None, data={
            "event_type": event_type,
            "sig_present": bool(signature),
        })
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        event = json.loads(payload.decode())
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}") from e

    # Kotani sends either the raw tx object (unsigned mode) or a
    # {event, data} envelope (signed mode). Handle both.
    if isinstance(event, dict) and isinstance(event.get("data"), dict):
        data = event["data"]
    elif isinstance(event, dict):
        # Unsigned mode — the whole payload is the tx object
        data = event
    else:
        raise HTTPException(status_code=400, detail="Payload must be a JSON object")

    ref_id = data.get("referenceId") or data.get("reference_id")
    kotani_status = (data.get("status") or "").upper()
    if not ref_id or not kotani_status:
        raise HTTPException(status_code=400, detail="Payload missing referenceId or status")

    tx = await db.transactions.find_one({"kotani.reference_id": ref_id}, {"_id": 0})
    if not tx:
        # Kotani retries webhooks; a stray one is not fatal — log + 200.
        logger.warning("[kotani-webhook] no local tx for referenceId=%s", ref_id)
        return {"ok": True, "matched": False}

    updates: dict = {"kotani.status": kotani_status, "kotani.updated_at": iso(now_utc())}
    audit_event = None
    if kotani_status == "SUCCESS":
        updates["status"] = "settled"
        updates["kotani.mpesa_receipt"] = (data.get("receipt") or {}).get("mpesaReceipt")
        updates["kotani.settled_at"] = data.get("settledAt") or iso(now_utc())
        audit_event = EventType.OFFRAMP_MPESA_SUCCESS
    elif kotani_status == "FAILED":
        updates["status"] = "failed"
        updates["kotani.failure_reason"] = data.get("failureReason") or data.get("message")
        audit_event = EventType.OFFRAMP_MPESA_FAILED
    elif kotani_status in ("REFUNDED", "REFUND_PENDING"):
        updates["status"] = "refunded" if kotani_status == "REFUNDED" else "processing"
        audit_event = EventType.OFFRAMP_MPESA_REFUNDED

    await db.transactions.update_one({"id": tx["id"]}, {"$set": updates})

    if audit_event:
        user_doc = await db.users.find_one({"id": tx["user_id"]}, {"_id": 0})
        try:
            await audit_write(db, audit_event, user=user_doc, data={
                "tx_id": tx["id"],
                "kotani_reference_id": ref_id,
                "kotani_status": kotani_status,
                "mpesa_receipt": (data.get("receipt") or {}).get("mpesaReceipt"),
            })
        except Exception as e:  # noqa: BLE001
            logger.warning("kotani webhook audit_write failed: %s", e)

    return {"ok": True, "matched": True, "status": kotani_status}

# ============================================================================
# KYC / IDENTITY — Stripe Identity + OpenSanctions integration
# ============================================================================
KYC_RETURN_URL = os.environ.get("KYC_RETURN_URL") or (
    (APP_PUBLIC_URL.rstrip("/") + "/kyc-return") if APP_PUBLIC_URL else "https://app.phoenix-atlas.com/kyc-return"
)


@api.get("/kyc/status")
async def kyc_status(user=Depends(get_current_user)):
    """Snapshot of the caller's current tier, limits, and month-to-date usage.
    The frontend polls this to render the KYC banner and after Stripe Identity
    submissions to show a 'Processing' state until the webhook flips the tier."""
    tier = get_user_tier(user)
    limits = tier_limits(tier)
    used = await sum_this_month_gbp(db, user["id"])
    kyc = user.get("kyc") or {}
    return {
        "tier": tier,
        "tier_label": limits["label"],
        "limits": {
            "per_send_gbp": limits["per_send_gbp"],
            "monthly_gbp": limits["monthly_gbp"],
        },
        "usage": {
            "this_month_gbp": used,
            "monthly_remaining_gbp": max(0.0, limits["monthly_gbp"] - used),
            "monthly_used_pct": round((used / limits["monthly_gbp"]) * 100, 1) if limits["monthly_gbp"] else 0,
        },
        "next_tier": limits.get("next_tier"),
        "next_tier_details": TIER_LIMITS[limits["next_tier"]] if limits.get("next_tier") else None,
        # Stripe Identity + sanctions state
        "identity_verification_status": kyc.get("identity_verification_status") or "not_started",
        "identity_last_error": kyc.get("identity_last_error"),
        "sanctions_check": {
            "matched": (kyc.get("sanctions") or {}).get("matched", False),
            "checked_at": (kyc.get("sanctions") or {}).get("checked_at"),
            "degraded": (kyc.get("sanctions") or {}).get("degraded", False),
            "degraded_reason": (kyc.get("sanctions") or {}).get("degraded_reason"),
        },
    }


@api.get("/kyc/debug")
async def kyc_debug(user=Depends(get_current_user)):
    """Diagnostic endpoint — pulls the RAW Stripe Identity verification
    report(s) for the current user's most recent verification session so
    we can see the exact document / selfie / id_number rejection codes.

    Only exposes what Stripe already surfaces to the account owner —
    never leaks other users' data. Safe to call from the client.
    """
    if not STRIPE_API_KEY:
        raise HTTPException(status_code=503, detail="Stripe not configured")

    kyc = user.get("kyc") or {}
    session_id = kyc.get("identity_verification_id") or kyc.get("identity_session_id")
    if not session_id:
        return {
            "ok": False,
            "reason": "no_active_session",
            "hint": "Start a verification session via /kyc/session first.",
        }

    try:
        session = stripe.identity.VerificationSession.retrieve(
            session_id,
            expand=["last_verification_report"],
        )
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reason": "stripe_retrieve_failed", "detail": str(e)[:400]}

    # Build a minimal, safe summary — no raw doc images or full personal
    # data, just the codes / reasons we need for triage.
    summary: dict = {
        "ok": True,
        "session_id": session.get("id"),
        "session_status": session.get("status"),
        "session_type": session.get("type"),
        "session_options": (session.get("options") or {}),
        "session_last_error": session.get("last_error"),
        "created": session.get("created"),
        "attempt_count": session.get("client_reference_id") is not None,
    }

    report = session.get("last_verification_report") or {}
    if isinstance(report, dict):
        doc = report.get("document") or {}
        selfie = report.get("selfie") or {}
        id_number = report.get("id_number") or {}
        summary["last_report"] = {
            "id": report.get("id"),
            "type": report.get("type"),
            "created": report.get("created"),
            "document": {
                "status": doc.get("status"),
                "error": doc.get("error"),
                "type": doc.get("type"),
                "issuing_country": doc.get("issuing_country"),
                "expiration_date": doc.get("expiration_date"),
                # Deliberately NOT returning: files (raw doc images),
                # first_name / last_name / dob / address / number
            },
            "selfie": {
                "status": selfie.get("status"),
                "error": selfie.get("error"),
                # Not returning file ids
            },
            "id_number": {
                "status": id_number.get("status"),
                "error": id_number.get("error"),
            },
        }
    return summary


class KycSessionIn(BaseModel):
    """Optional body for /kyc/session.
    - force_new: cancels any existing session and creates a fresh one. Used by
      the frontend's "Start over" escape hatch when a user is stuck retrying
      the same failed document scan.
    """
    force_new: bool = False


@api.post("/kyc/session")
async def kyc_session(body: KycSessionIn | None = None, user=Depends(get_current_user)):
    """Create a Stripe Identity VerificationSession and return the hosted URL
    that the frontend redirects the user to. Idempotent per user — if there's
    already an active session that hasn't been canceled, we reuse its URL
    (unless the caller passed `force_new: true`)."""
    if not STRIPE_API_KEY:
        raise HTTPException(status_code=503, detail="Stripe not configured")

    force_new = bool(body and body.force_new)
    kyc = user.get("kyc") or {}
    existing_id = kyc.get("identity_verification_session_id")
    existing_status = kyc.get("identity_verification_status")

    # Reuse the existing active session UNLESS the caller explicitly asked for
    # a brand-new one (prevents Dashboard clutter + Stripe session costs).
    if not force_new and existing_id and existing_status in ("requires_input", "processing"):
        try:
            existing = stripe.identity.VerificationSession.retrieve(existing_id)
            if existing.get("status") in ("requires_input",) and existing.get("url"):
                return {"session_id": existing_id, "url": existing["url"], "reused": True}
        except Exception as e:
            logger.warning(f"kyc: existing session retrieve failed ({existing_id}): {e}")

    # force_new: cancel the existing Stripe session so we don't accumulate
    # zombie sessions on the Dashboard. Best-effort — a failure to cancel is
    # not fatal (the new session will still work).
    if force_new and existing_id:
        try:
            stripe.identity.VerificationSession.cancel(existing_id)
            logger.info(f"kyc: canceled stale session {existing_id} for user {user['id']}")
        except Exception as e:
            logger.warning(f"kyc: cancel stale session failed ({existing_id}): {e}")

    # Bump a per-user attempt counter so the Stripe idempotency key is unique
    # across cancellations. Without this, canceling a session and retrying
    # within 24h would hit Stripe's cached response (the canceled session)
    # and never mint a fresh URL.
    attempt_num = int(kyc.get("session_attempt", 0)) + 1

    try:
        session = stripe.identity.VerificationSession.create(
            type="document",
            return_url=KYC_RETURN_URL,
            options={
                "document": {
                    "allowed_types": ["driving_license", "passport", "id_card"],
                    "require_matching_selfie": True,
                    "require_live_capture": True,
                },
            },
            metadata={
                "user_id": user["id"],
                "target_tier": "kyc_lite",
                "email": user.get("email") or "",
                "attempt": str(attempt_num),
            },
            idempotency_key=f"vaulted-kyc-lite-{user['id']}-{attempt_num}",
        )
    except stripe.error.StripeError as e:  # type: ignore[attr-defined]
        # Detect the "Identity product not enabled" state and surface it as a
        # friendly configuration error rather than a scary raw Stripe message.
        msg = str(e)
        if "not set up to use Identity" in msg or "identity/application" in msg:
            raise HTTPException(status_code=503, detail={
                "error": "stripe_identity_not_activated",
                "message": (
                    "Identity verification is temporarily unavailable — we're finalising "
                    "our Stripe Identity onboarding. Please try again shortly, or "
                    "contact support@phoenix-atlas.com for immediate help."
                ),
            }) from e
        raise HTTPException(status_code=502, detail=f"Stripe Identity error: {e}") from e

    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {
            "kyc.identity_verification_session_id": session["id"],
            "kyc.identity_verification_status": "requires_input",
            "kyc.identity_started_at": iso(now_utc()),
            "kyc.session_attempt": attempt_num,
            # Clear any stale error from the previous session so the UI
            # doesn't confusingly show an old failure alongside the new attempt.
            "kyc.identity_last_error": None,
        }},
    )
    await audit_write(
        db,
        EventType.KYC_SESSION_FORCE_NEW if force_new else EventType.KYC_SESSION_CREATED,
        user=user,
        data={
            "session_id": session["id"],
            "attempt_num": attempt_num,
            "force_new": force_new,
            "previous_session_id": existing_id if force_new else None,
        },
    )
    return {"session_id": session["id"], "url": session["url"], "reused": False}


async def _apply_identity_verified(session_obj: dict):
    """Webhook handler for identity.verification_session.verified — bumps the
    user to kyc_lite tier and enqueues an OpenSanctions screen against the
    verified name from the session."""
    user_id = (session_obj.get("metadata") or {}).get("user_id")
    if not user_id:
        logger.warning(f"identity webhook missing user_id metadata: {session_obj.get('id')}")
        return

    # Pull the verified outputs (name + address; DOB requires a restricted key
    # which we can add later). Falls back gracefully if expansion fails.
    verified_name = None
    verified_country = None
    verified_dob = None
    try:
        full = stripe.identity.VerificationSession.retrieve(
            session_obj["id"],
            expand=["verified_outputs"],
        )
        vo = full.get("verified_outputs") or {}
        first = (vo.get("first_name") or "").strip()
        last = (vo.get("last_name") or "").strip()
        verified_name = f"{first} {last}".strip() or None
        addr = vo.get("address") or {}
        verified_country = addr.get("country")
        dob = vo.get("dob") or {}
        if dob.get("year") and dob.get("month") and dob.get("day"):
            verified_dob = f"{dob['year']:04d}-{dob['month']:02d}-{dob['day']:02d}"
    except Exception as e:
        logger.warning(f"identity verified_outputs fetch failed: {e}")

    # Sanctions screening against the verified identity
    sanctions_result = {
        "matched": False,
        "checked_at": iso(now_utc()),
        "degraded": True,
        "degraded_reason": "no_name",
    }
    if verified_name:
        try:
            sanctions_result = await screen_sanctions(verified_name, dob=verified_dob, country=verified_country)
        except Exception as e:
            logger.warning(f"sanctions screen failed for user {user_id}: {e}")
            sanctions_result = {
                "matched": False,
                "checked_at": iso(now_utc()),
                "degraded": True,
                "degraded_reason": f"exception: {type(e).__name__}",
            }

    # If the sanctions check produced a HIGH-confidence match on a sanctions
    # dataset, we do NOT auto-tier the user up — we flag for manual review.
    is_flagged = bool(sanctions_result.get("matched")) and sanctions_result.get("scope") == "sanctions"

    update = {
        "kyc.identity_verification_status": "verified",
        "kyc.identity_verified_at": iso(now_utc()),
        "kyc.verified_name": verified_name,
        "kyc.verified_country": verified_country,
        "kyc.verified_dob": verified_dob,
        "kyc.sanctions": sanctions_result,
    }
    if is_flagged:
        update["kyc.tier"] = "flagged"
        update["kyc.flagged_at"] = iso(now_utc())
    else:
        update["kyc.tier"] = "kyc_lite"

    await db.users.update_one({"id": user_id}, {"$set": update})
    logger.info(f"KYC-lite {'FLAGGED' if is_flagged else 'GRANTED'} for user={user_id}")

    # Audit trail — separate events for verified vs flagged so log filters
    # can trivially count each outcome.
    await audit_write(
        db,
        EventType.KYC_FLAGGED if is_flagged else EventType.KYC_VERIFIED,
        user_id=user_id,
        user_email=(await db.users.find_one({"id": user_id}, {"email": 1}) or {}).get("email"),
        data={
            "session_id": session_obj.get("id"),
            "verified_name_hash": hashlib.sha256((verified_name or "").strip().lower().encode()).hexdigest()[:12] if verified_name else None,
            "verified_country": verified_country,
            "has_dob": bool(verified_dob),
            "tier_before": "unverified",
            "tier_after": "flagged" if is_flagged else "kyc_lite",
            "sanctions": {
                "matched": sanctions_result.get("matched"),
                "highest_score": sanctions_result.get("highest_score"),
                "scope": sanctions_result.get("scope"),
                "degraded": sanctions_result.get("degraded", False),
                "degraded_reason": sanctions_result.get("degraded_reason"),
            },
        },
    )
    # Also record the sanctions screen as its own event so
    # /audit-log?event_type=sanctions.screened counts include the KYC-time
    # screen (not just admin manual ones).
    await audit_write(
        db,
        EventType.SANCTIONS_SCREENED,
        user_id=user_id,
        data={
            "context": "kyc_verified",
            "matched": sanctions_result.get("matched"),
            "highest_score": sanctions_result.get("highest_score"),
            "scope": sanctions_result.get("scope"),
            "degraded": sanctions_result.get("degraded", False),
            "degraded_reason": sanctions_result.get("degraded_reason"),
        },
    )

    # Referral credit — only if the user was NOT flagged. Flagged users
    # (sanctions match) are under manual review; we don't want to hand out
    # credit for a potentially fraudulent signup.
    if not is_flagged:
        try:
            credit_result = await credit_referral_on_kyc(db, user_id)
        except Exception as e:  # noqa: BLE001 — never break the KYC flow
            logger.warning(f"referral: credit_referral_on_kyc failed for {user_id}: {e}")
            credit_result = None
        if credit_result:
            await audit_write(db, EventType.REFERRAL_CREDITED, user_id=user_id, data={
                "referral_id": credit_result["referral_id"],
                "referrer_user_id": credit_result["referrer_user_id"],
                "referred_credit_gbp": REFERRAL_SIGNUP_BONUS_GBP,
                "referrer_credit_gbp": REFERRAL_REWARD_GBP,
            })
            # Emit credit.granted events for both sides so the ledger has
            # a searchable trail per user
            await audit_write(db, EventType.CREDIT_GRANTED,
                              user_id=credit_result["referrer_user_id"],
                              data={
                                  "amount_gbp": REFERRAL_REWARD_GBP,
                                  "source": "referral_reward",
                                  "ledger_id": credit_result["referrer_credit_row"]["id"],
                                  "balance_after_gbp": credit_result["referrer_credit_row"]["balance_after_gbp"],
                              })
            await audit_write(db, EventType.CREDIT_GRANTED,
                              user_id=user_id,
                              data={
                                  "amount_gbp": REFERRAL_SIGNUP_BONUS_GBP,
                                  "source": "referral_signup_bonus",
                                  "ledger_id": credit_result["referred_credit_row"]["id"],
                                  "balance_after_gbp": credit_result["referred_credit_row"]["balance_after_gbp"],
                              })


async def _apply_identity_requires_input(session_obj: dict):
    """Webhook handler for identity.verification_session.requires_input —
    a check failed and the user needs to retry with a better photo/document.

    The session-level `last_error` is only a summary. The real per-step
    reason (document / selfie / id_number) lives in the last verification
    report, which we fetch here so the frontend can show step-specific
    guidance instead of a generic "retake in bright light" message.
    """
    user_id = (session_obj.get("metadata") or {}).get("user_id")
    if not user_id:
        return
    last_error = session_obj.get("last_error") or {}

    # Fetch the detailed report so we can distinguish document vs selfie
    # failures. Falls back gracefully — if this fails we still store the
    # summary error so the flow isn't blocked.
    document_error: dict | None = None
    selfie_error: dict | None = None
    id_number_error: dict | None = None
    report_id = session_obj.get("last_verification_report")
    if report_id and STRIPE_API_KEY:
        try:
            report = stripe.identity.VerificationReport.retrieve(report_id)
            document_error = (report.get("document") or {}).get("error") or None
            selfie_error = (report.get("selfie") or {}).get("error") or None
            id_number_error = (report.get("id_number") or {}).get("error") or None
        except Exception as e:  # noqa: BLE001
            logger.warning("VerificationReport retrieve failed: %s", e)

    # Prefer the most specific error we found. Selfie failures are the most
    # commonly misdiagnosed as "document quality" issues in the wild — check
    # them first so the frontend gets the right step-specific code.
    resolved_code = last_error.get("code")
    resolved_reason = last_error.get("reason")
    if selfie_error and selfie_error.get("code"):
        resolved_code = selfie_error.get("code")
        resolved_reason = selfie_error.get("reason")
    elif document_error and document_error.get("code"):
        resolved_code = document_error.get("code")
        resolved_reason = document_error.get("reason")
    elif id_number_error and id_number_error.get("code"):
        resolved_code = id_number_error.get("code")
        resolved_reason = id_number_error.get("reason")

    await db.users.update_one(
        {"id": user_id},
        {"$set": {
            "kyc.identity_verification_status": "requires_input",
            "kyc.identity_last_error": {
                "code": resolved_code,
                "reason": resolved_reason,
                "at": iso(now_utc()),
                # Also persist the raw sub-step errors for admin diagnostics
                "step_errors": {
                    "document": document_error,
                    "selfie": selfie_error,
                    "id_number": id_number_error,
                    "session": last_error or None,
                },
            },
        }},
    )
    await audit_write(
        db,
        EventType.KYC_REQUIRES_INPUT,
        user_id=user_id,
        data={
            "session_id": session_obj.get("id"),
            "error_code": resolved_code,
            "error_reason": resolved_reason,
            "selfie_error_code": (selfie_error or {}).get("code"),
            "document_error_code": (document_error or {}).get("code"),
            "id_number_error_code": (id_number_error or {}).get("code"),
        },
    )


# ============================================================================
# ADMIN — Compliance health & manual screening tools
# ============================================================================
@api.get("/admin/compliance/health")
async def admin_compliance_health(_admin=Depends(require_admin)):
    """Ping OpenSanctions with a canary query so operators can verify at a
    glance whether sanctions screening is actually live. Also returns the
    current integration config (key present, strict mode, URL, scopes)."""
    health = await opensanctions_health()
    return {
        "opensanctions": {
            "config": opensanctions_config_status(),
            "health": health,
        },
        "corridor_blocklist": {
            "count": len(COUNTRY_BLOCKLIST),
            "codes": sorted(COUNTRY_BLOCKLIST.keys()),
        },
        "checked_at": iso(now_utc()),
    }


class AdminScreenIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    dob: Optional[str] = None       # ISO YYYY-MM-DD
    country: Optional[str] = None    # ISO alpha-2


@api.post("/admin/compliance/screen")
async def admin_compliance_screen(body: AdminScreenIn, admin=Depends(require_admin)):
    """Manually screen a name/DOB/country against OpenSanctions. Useful for
    testing after enabling a new API key, and for ad-hoc SAR investigations.
    Returns the full raw screen result (including degraded/reason flags)."""
    result = await screen_sanctions(body.name, dob=body.dob, country=body.country)
    await audit_write(db, EventType.ADMIN_MANUAL_SCREEN, user=admin, data={
        "screened_name_hash": hashlib.sha256((body.name or "").strip().lower().encode()).hexdigest()[:12],
        "screened_country": body.country,
        "has_dob": bool(body.dob),
        "matched": result.get("matched"),
        "degraded": result.get("degraded", False),
        "highest_score": result.get("highest_score"),
    })
    return {"input": body.model_dump(), "result": result}


# ============================================================================
# ADMIN — Audit-log endpoint (FCA / MLR 2017 record-keeping)
# ============================================================================
@api.get("/admin/audit-log")
async def admin_audit_log(
    _admin=Depends(require_admin),
    event_type: Optional[str] = None,
    user_id: Optional[str] = None,
    from_iso: Optional[str] = None,
    to_iso: Optional[str] = None,
    limit: int = 50,
    cursor: Optional[str] = None,
):
    """Cursor-paginated audit event feed. Supports filtering by event_type,
    user_id, and timestamp range (ISO 8601). Newest first. Meant to be
    consumed by ops dashboards, compliance officers, and (eventually) a
    scheduled export job that ships events to a WORM (write-once-read-many)
    archival store for the 5-year MLR 2017 retention requirement."""
    if event_type and event_type not in ALL_EVENT_TYPES:
        raise HTTPException(status_code=400, detail={
            "error": "unknown_event_type",
            "provided": event_type,
            "allowed": sorted(ALL_EVENT_TYPES),
        })
    return await audit_query(
        db,
        event_type=event_type,
        user_id=user_id,
        from_iso=from_iso,
        to_iso=to_iso,
        limit=limit,
        cursor=cursor,
    )


@api.get("/admin/audit-log/event-types")
async def admin_audit_event_types(_admin=Depends(require_admin)):
    """Enumerate every event_type the audit system knows how to write. Useful
    for populating filter dropdowns in an ops UI without hardcoding."""
    return {"event_types": sorted(ALL_EVENT_TYPES)}


@api.get("/admin/audit-log/user/{user_id}")
async def admin_audit_log_for_user(user_id: str, _admin=Depends(require_admin)):
    """Compliance-file view for a single user. Returns every event we've
    recorded for that user, ordered chronologically, plus counts by
    event_type. Consumed by SAR (Suspicious Activity Report) filings and
    ad-hoc regulator requests."""
    return await audit_summarize_user(db, user_id)


# ============================================================================
# REFERRAL LOOP — invite-link viral growth + £5 GBP credit
# ============================================================================
REFERRAL_LINK_BASE = os.environ.get("REFERRAL_LINK_BASE") or (
    APP_PUBLIC_URL.rstrip("/") if APP_PUBLIC_URL else "https://app.phoenix-atlas.com"
)


@api.get("/referrals/me")
async def referrals_me(user=Depends(get_current_user)):
    """Everything the /referral screen needs in one call: my code, my
    shareable link, my credit balance, and my referral history."""
    code = await ensure_referral_code(db, user)
    balance = await get_balance_gbp(db, user["id"])
    summary = await referral_summary(db, user["id"])
    share_link = f"{REFERRAL_LINK_BASE}/?ref={code}"
    return {
        "referral_code": code,
        "share_link": share_link,
        "share_message": (
            f"Send money home for less on Vaulted. Sign up with my code {code} "
            f"and we both get £{REFERRAL_REWARD_GBP:.0f} credit."
        ),
        "credit_balance_gbp": balance,
        "reward_per_side_gbp": REFERRAL_REWARD_GBP,
        "signup_bonus_gbp": REFERRAL_SIGNUP_BONUS_GBP,
        **summary,
    }


@api.get("/referrals/validate/{code}")
async def referrals_validate(code: str):
    """Public endpoint used by the signup form to preview who invited them —
    returns just enough to build trust without leaking full PII."""
    from referrals import user_by_referral_code
    referrer = await user_by_referral_code(db, code)
    if not referrer:
        return {"valid": False}
    name = (referrer.get("name") or "").strip()
    # Show first name + last initial (Sarah B.) at most
    parts = name.split()
    display = (parts[0] if parts else "A friend") + (
        f" {parts[1][:1]}." if len(parts) > 1 and parts[1] else ""
    )
    return {
        "valid": True,
        "referrer_name_masked": display,
        "reward_per_side_gbp": REFERRAL_REWARD_GBP,
    }


@api.get("/credit/balance")
async def credit_balance(user=Depends(get_current_user)):
    """Current GBP credit balance for the caller."""
    balance = await get_balance_gbp(db, user["id"])
    return {"balance_gbp": balance}


@api.get("/credit/ledger")
async def credit_ledger(user=Depends(get_current_user), limit: int = 50):
    """Paginated credit ledger — newest first. Includes source labels the
    frontend can render (referral_reward, referral_signup_bonus,
    remit_fee_offset, admin_grant)."""
    limit = max(1, min(200, int(limit)))
    rows = await db.credit_ledger.find(
        {"user_id": user["id"]}, {"_id": 0},
    ).sort("created_at", -1).limit(limit).to_list(length=limit)
    return {"entries": rows, "count": len(rows)}


class SendEthIn(BaseModel):
    to_address: str
    amount_eth: float = Field(gt=0)


@api.post("/wallet/eth/send")
async def eth_send(body: SendEthIn, user=Depends(get_current_user)):
    pk = user.get("eth_private_key")
    addr = user.get("wallet_address")
    if not pk or not addr:
        raise HTTPException(status_code=400, detail="No ETH key on file")
    to = body.to_address.strip()
    if not (to.startswith("0x") and len(to) == 42):
        raise HTTPException(status_code=400, detail="Invalid recipient address")

    # ---- Multi-sig gate ----
    multisig_on = bool(user.get("multisig_enabled"))
    cosigner = await db.cosigners.find_one(
        {"user_id": user["id"], "status": "active"}, {"_id": 0}
    )
    needs_approval = (
        multisig_on
        and cosigner is not None
        and body.amount_eth >= MULTISIG_THRESHOLD_ETH
    )
    if needs_approval:
        approval_id = str(uuid.uuid4())
        token = secrets.token_urlsafe(32)
        expires = now_utc() + timedelta(hours=APPROVAL_TTL_HOURS)
        pending = {
            "id": approval_id,
            "user_id": user["id"],
            "user_name": user.get("name"),
            "user_email": user.get("email"),
            "from_address": addr,
            "to_address": to,
            "amount_eth": body.amount_eth,
            "cosigner_id": cosigner["id"],
            "cosigner_email": cosigner["email"],
            "approver_token": token,
            "status": "pending",
            "created_at": iso(now_utc()),
            "expires_at": iso(expires),
        }
        await db.eth_approvals.insert_one(pending)
        await _send_approval_email(pending)
        pending.pop("_id", None)
        return {
            "approval_required": True,
            "approval_id": approval_id,
            "cosigner_email": cosigner["email"],
            "amount_eth": body.amount_eth,
            "to_address": to,
            "expires_at": pending["expires_at"],
            "message": f"Awaiting approval from {cosigner['email']}",
        }

    return await _broadcast_eth_send(user, addr, pk, to, body.amount_eth)


async def _broadcast_eth_send(user: dict, addr: str, pk: str, to: str, amount_eth: float) -> dict:
    value_wei = int(round(amount_eth * 1e18))
    try:
        nonce_resp = await _eth_rpc("eth_getTransactionCount", [addr, "pending"])
        nonce = int(nonce_resp["result"], 16)
        gas_resp = await _eth_rpc("eth_gasPrice", [])
        gas_price = int(gas_resp["result"], 16)
        bal_wei = await _fetch_eth_balance_wei(addr)
        gas_limit = 21000
        total_cost = value_wei + gas_price * gas_limit
        if total_cost > bal_wei:
            raise HTTPException(status_code=400, detail=f"Insufficient ETH (need {total_cost/1e18:.6f}, have {bal_wei/1e18:.6f})")

        tx = {
            "nonce": nonce,
            "to": to,
            "value": value_wei,
            "gas": gas_limit,
            "gasPrice": gas_price,
            "chainId": SEPOLIA_CHAIN_ID,
        }
        signed = Account.sign_transaction(tx, pk)
        send_resp = await _eth_rpc("eth_sendRawTransaction", [signed.raw_transaction.hex()])
        if "error" in send_resp:
            raise HTTPException(status_code=502, detail=f"RPC error: {send_resp['error']}")
        tx_hash = send_resp["result"]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Sepolia send failed: {e}")

    is_pro = is_user_pro(user)
    service_fee_usd = 0.05 if is_pro else 0.10

    price = next((a["price_usd"] for a in DEFAULT_ASSETS if a["symbol"] == "ETH"), 0)
    tx_record = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "type": "send",
        "category": "crypto",
        "asset": "ETH",
        "amount": amount_eth,
        "fiat_value": round(amount_eth * price, 2),
        "counterparty": to,
        "tx_hash": tx_hash,
        "network": "Sepolia",
        "service_fee_usd": service_fee_usd,
        "pro_discount_applied": is_pro,
        "explorer_url": f"https://sepolia.etherscan.io/tx/{tx_hash}",
        "status": "pending",
        "created_at": iso(now_utc()),
    }
    await db.transactions.insert_one(tx_record)
    tx_record.pop("_id", None)
    return tx_record


# --------------------------- Multi-sig: co-signers & approvals ---------------------------
async def _send_approval_email(pending: dict) -> None:
    if not RESEND_API_KEY:
        logger.warning("RESEND_API_KEY not set; skipping approval email")
        return
    base = APP_PUBLIC_URL.rstrip("/")
    approve_url = f"{base}/approve?token={pending['approver_token']}&decision=approve"
    reject_url = f"{base}/approve?token={pending['approver_token']}&decision=reject"
    short_to = pending["to_address"][:10] + "..." + pending["to_address"][-6:]
    html = f"""
    <div style="font-family:-apple-system,Helvetica,Arial,sans-serif;max-width:520px;margin:auto;padding:24px;background:#fcfcfc;color:#1a1d1a">
      <div style="font-size:22px;font-weight:700;color:#3F6156;margin-bottom:4px">Vaulted</div>
      <div style="font-size:13px;color:#6d7a73;margin-bottom:24px">Multi-signature approval request</div>
      <div style="background:#f3f4f3;padding:16px;border-radius:12px">
        <div style="font-size:13px;color:#6d7a73">{pending['user_name']} ({pending['user_email']}) wants to send</div>
        <div style="font-size:28px;font-weight:700;margin-top:6px">{pending['amount_eth']} ETH</div>
        <div style="font-size:12px;color:#6d7a73;margin-top:6px">to <code>{short_to}</code> on Sepolia</div>
      </div>
      <p style="font-size:13px;color:#4a524d;margin-top:18px">As their designated co-signer, your approval is required for sends ≥ {MULTISIG_THRESHOLD_ETH} ETH. This request expires in {APPROVAL_TTL_HOURS}h.</p>
      <div style="margin-top:24px">
        <a href="{approve_url}" style="display:inline-block;background:#3F6156;color:#fff;padding:12px 20px;border-radius:10px;text-decoration:none;font-weight:600;margin-right:8px">Approve</a>
        <a href="{reject_url}" style="display:inline-block;background:#fff;color:#b83a3a;padding:12px 20px;border-radius:10px;text-decoration:none;font-weight:600;border:1px solid #b83a3a">Reject</a>
      </div>
      <div style="font-size:11px;color:#6d7a73;margin-top:24px">If you didn't expect this, reject and let {pending['user_email']} know — their account may be compromised.</div>
    </div>
    """
    try:
        async with httpx.AsyncClient(timeout=12) as cx:
            r = await cx.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
                json={
                    "from": get_resend_from(),
                    "to": [pending["cosigner_email"]],
                    "subject": f"Approve {pending['amount_eth']} ETH from Vaulted?",
                    "html": html,
                },
            )
            if r.status_code >= 400:
                logger.warning(f"resend send failed {r.status_code}: {r.text[:200]}")
    except Exception as e:
        logger.warning(f"resend send exception: {e}")


@api.get("/cosigners")
async def list_cosigners(user=Depends(get_current_user)):
    cur = db.cosigners.find({"user_id": user["id"]}, {"_id": 0})
    return await cur.to_list(50)


@api.post("/cosigners")
async def add_cosigner(body: CosignerInviteIn, user=Depends(get_current_user)):
    if (user.get("subscription") or {}).get("status") not in ("active", "trialing"):
        raise HTTPException(status_code=402, detail="Vault Pro required to add co-signers")
    existing = await db.cosigners.find_one({"user_id": user["id"], "email": body.email.lower()}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=400, detail="Co-signer already added")
    doc = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "email": body.email.lower(),
        "label": body.label or body.email.split("@")[0],
        "status": "active",
        "added_at": iso(now_utc()),
    }
    await db.cosigners.insert_one(doc)
    # Send a welcome / "you are now a co-signer" email so the recipient knows
    if RESEND_API_KEY:
        try:
            async with httpx.AsyncClient(timeout=10) as cx:
                await cx.post(
                    "https://api.resend.com/emails",
                    headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
                    json={
                        "from": get_resend_from(),
                        "to": [body.email],
                        "subject": f"You're now a Vaulted co-signer for {user.get('name')}",
                        "html": f"<p>{user.get('name')} ({user.get('email')}) added you as a co-signer on their Vaulted wallet. You'll receive an email any time they try to send ≥ {MULTISIG_THRESHOLD_ETH} ETH; tap Approve or Reject in those emails.</p>",
                    },
                )
        except Exception as e:
            logger.warning(f"welcome email failed: {e}")
    doc.pop("_id", None)
    return doc


@api.delete("/cosigners/{cosigner_id}")
async def remove_cosigner(cosigner_id: str, user=Depends(get_current_user)):
    r = await db.cosigners.delete_one({"id": cosigner_id, "user_id": user["id"]})
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Co-signer not found")
    return {"removed": True}


@api.get("/approvals/pending")
async def list_pending_approvals(user=Depends(get_current_user)):
    cur = db.eth_approvals.find(
        {"user_id": user["id"], "status": "pending"}, {"_id": 0, "approver_token": 0}
    ).sort("created_at", -1)
    return await cur.to_list(50)


@api.post("/approvals/decide")
async def decide_approval(body: ApprovalActionIn):
    """Public endpoint hit from email link (no auth — the token is the credential)."""
    approval = await db.eth_approvals.find_one({"approver_token": body.token}, {"_id": 0})
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found or already used")
    if approval["status"] != "pending":
        return {"status": approval["status"], "already": True, "approval": approval}

    try:
        expires = datetime.fromisoformat(approval["expires_at"])
        if now_utc() > expires:
            await db.eth_approvals.update_one(
                {"id": approval["id"]}, {"$set": {"status": "expired", "decided_at": iso(now_utc())}}
            )
            raise HTTPException(status_code=410, detail="Approval expired")
    except HTTPException:
        raise
    except Exception:
        pass

    if body.decision == "reject":
        await db.eth_approvals.update_one(
            {"id": approval["id"]}, {"$set": {"status": "rejected", "decided_at": iso(now_utc())}}
        )
        try:
            await send_push(
                recipients=[approval["user_id"]],
                data={
                    "title": f"⛔ Co-signer rejected {approval['amount_eth']} ETH",
                    "message": "Your multi-sig transaction was not broadcast.",
                    "action_url": "/approvals",
                },
                idempotency_key=f"approval-{approval['id']}-rejected",
            )
        except Exception as e:
            logger.warning("push approval-rejected failed: %s", e)
        return {"status": "rejected", "approval_id": approval["id"]}

    # Approve → broadcast the tx now using the sender's key
    user = await db.users.find_one({"id": approval["user_id"]}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="Original sender not found")
    try:
        tx_record = await _broadcast_eth_send(
            user, user["wallet_address"], user["eth_private_key"],
            approval["to_address"], approval["amount_eth"],
        )
    except HTTPException as e:
        await db.eth_approvals.update_one(
            {"id": approval["id"]},
            {"$set": {"status": "failed", "decided_at": iso(now_utc()), "failure_reason": e.detail}},
        )
        raise
    await db.eth_approvals.update_one(
        {"id": approval["id"]},
        {"$set": {
            "status": "approved",
            "decided_at": iso(now_utc()),
            "tx_hash": tx_record.get("tx_hash"),
            "explorer_url": tx_record.get("explorer_url"),
        }},
    )
    # Notify the wallet owner that their cosigner approved & the broadcast is live
    try:
        await send_push(
            recipients=[approval["user_id"]],
            data={
                "title": f"✅ Co-signer approved {approval['amount_eth']} ETH",
                "message": "Your multi-sig transaction is now on Sepolia.",
                "action_url": "/approvals",
            },
            idempotency_key=f"approval-{approval['id']}-approved",
        )
    except Exception as e:
        logger.warning("push approval-approved failed: %s", e)
    return {"status": "approved", "approval_id": approval["id"], "tx_hash": tx_record.get("tx_hash"), "explorer_url": tx_record.get("explorer_url")}


@api.get("/wallet/eth/export")
async def eth_export_key(user=Depends(get_current_user)):
    """Reveals the private key so the user can take true self-custody.
    For Sepolia testnet only; never expose live keys this way in production."""
    pk = user.get("eth_private_key")
    if not pk:
        raise HTTPException(status_code=404, detail="No private key on file")
    return {
        "address": user.get("wallet_address"),
        "private_key": pk,
        "network": "Sepolia (chain id 11155111)",
        "warning": "Never share this key. Anyone with it controls your wallet.",
    }


@api.get("/wallet/eth/mnemonic")
async def eth_mnemonic(user=Depends(get_current_user)):
    """Reveals the 12-word BIP-39 recovery phrase. For Sepolia testnet only."""
    mnemonic_phrase = user.get("eth_mnemonic")
    if not mnemonic_phrase:
        raise HTTPException(status_code=404, detail="No recovery phrase on file. Re-register to get one.")

    # Self-heal: if mnemonic_origin isn't set yet, derive + compare against the
    # stored ETH address. Mismatch → tag as multichain_only and persist; match
    # → tag as eth_native. This closes the iter10 backfill gap for any user
    # who was backfilled before iter11 started tagging at write-time.
    origin = user.get("mnemonic_origin")
    if not origin:
        try:
            Account.enable_unaudited_hdwallet_features()
            derived_addr = Account.from_mnemonic(mnemonic_phrase).address
        except Exception:
            derived_addr = None
        stored_addr = user.get("wallet_address")
        if derived_addr and stored_addr and derived_addr.lower() == stored_addr.lower():
            origin = "eth_native"
        else:
            origin = "multichain_only"
        await db.users.update_one({"id": user["id"]}, {"$set": {"mnemonic_origin": origin}})
        user["mnemonic_origin"] = origin

    # Legacy users had their ETH key generated via Account.create() — the mnemonic
    # we have on file derives BTC/SOL but NOT their ETH key. Refuse to misrepresent.
    if origin == "multichain_only":
        raise HTTPException(
            status_code=409,
            detail=(
                "This account was created before BIP-39 onboarding, so we can't show a "
                "recovery phrase for your existing ETH key. Use Export Private Key instead."
            ),
        )
    return {
        "address": user.get("wallet_address"),
        "mnemonic": mnemonic_phrase,
        "word_count": len(mnemonic_phrase.split()),
        "network": "Sepolia (chain id 11155111)",
        "warning": "Anyone with these 12 words controls your wallet.",
    }


@api.post("/auth/onboarding-complete")
async def complete_onboarding(user=Depends(get_current_user)):
    await db.users.update_one({"id": user["id"]}, {"$set": {"onboarding_seed_acknowledged": True}})
    u = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    return public_user(u)


# --------------------------- Live market prices (CoinGecko, cached) ---------------------------
COINGECKO_IDS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "USDC": "usd-coin",
    "SOL": "solana",
    "XLM": "stellar",
    "XRP": "ripple",
}
PRICE_CACHE_TTL_SECONDS = 300


async def _refresh_market_prices() -> dict:
    """Fetch latest prices + 24h change + 7d sparkline. Cache in DB with TTL."""
    cached = await db.market_cache.find_one({"_id": "prices"}, {"_id": 0})
    if cached and cached.get("fetched_at"):
        try:
            t = datetime.fromisoformat(cached["fetched_at"])
            age = (now_utc() - t).total_seconds()
            if age < PRICE_CACHE_TTL_SECONDS:
                return cached
        except Exception:
            pass

    ids = ",".join(COINGECKO_IDS.values())
    url = f"https://api.coingecko.com/api/v3/coins/markets?ids={ids}&vs_currency=usd&sparkline=true&price_change_percentage=24h"
    out_assets: dict[str, dict] = {}
    try:
        async with httpx.AsyncClient(timeout=10) as cx:
            r = await cx.get(url)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list):
                    cg_to_sym = {v: k for k, v in COINGECKO_IDS.items()}
                    for coin in data:
                        sym = cg_to_sym.get(coin.get("id"))
                        if not sym:
                            continue
                        sparkline = coin.get("sparkline_in_7d", {}).get("price", [])
                        out_assets[sym] = {
                            "symbol": sym,
                            "price_usd": float(coin.get("current_price") or 0),
                            "change_24h_pct": float(coin.get("price_change_percentage_24h") or 0),
                            "sparkline_7d": [float(x) for x in sparkline[-48:]],  # last 48 hourly points
                            "market_cap": coin.get("market_cap"),
                        }
    except Exception as e:
        logger.warning(f"coingecko fetch failed: {e}")

    if not out_assets:
        # Fall back to whatever cached value we have, even if stale
        if cached and cached.get("assets"):
            return cached
        # Last-resort defaults so the app keeps working
        out_assets = {
            sym: {"symbol": sym, "price_usd": p, "change_24h_pct": 0.0, "sparkline_7d": []}
            for sym, p in [("BTC", 67000), ("ETH", 3500), ("USDC", 1.0), ("SOL", 150), ("XLM", 0.12), ("XRP", 0.52)]
        }

    record = {
        "assets": out_assets,
        "fetched_at": iso(now_utc()),
        "stale": False,
    }
    await db.market_cache.update_one({"_id": "prices"}, {"$set": record}, upsert=True)
    return record


@api.get("/market/prices")
async def market_prices(_=Depends(get_current_user)):
    rec = await _refresh_market_prices()
    return {"assets": rec["assets"], "fetched_at": rec.get("fetched_at"), "ttl_seconds": PRICE_CACHE_TTL_SECONDS}


# Existing simulated send for non-ETH assets
@api.post("/wallet/send")
async def wallet_send(body: SendCryptoIn, user=Depends(get_current_user)):
    if body.asset.upper() == "ETH":
        raise HTTPException(status_code=400, detail="Use /wallet/eth/send for ETH (on-chain)")
    bal = await db.balances.find_one({"user_id": user["id"], "symbol": body.asset.upper()}, {"_id": 0})
    if not bal:
        raise HTTPException(status_code=400, detail="Asset not found")
    if bal["amount"] < body.amount:
        raise HTTPException(status_code=400, detail="Insufficient balance")
    new_amt = round(bal["amount"] - body.amount, 8)
    await db.balances.update_one(
        {"user_id": user["id"], "symbol": body.asset.upper()},
        {"$set": {"amount": new_amt, "updated_at": iso(now_utc())}},
    )
    price = next((a["price_usd"] for a in DEFAULT_ASSETS if a["symbol"] == body.asset.upper()), 0)
    tx = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "type": "send",
        "category": "crypto",
        "asset": body.asset.upper(),
        "amount": body.amount,
        "fiat_value": round(body.amount * price, 2),
        "counterparty": body.to_address,
        "memo": body.memo,
        "status": "completed",
        "tx_hash": "0x" + secrets.token_hex(32),
        "created_at": iso(now_utc()),
    }
    await db.transactions.insert_one(tx)
    tx.pop("_id", None)
    return tx


@api.post("/fiat/deposit")
async def fiat_deposit(body: FiatTxIn, user=Depends(get_current_user)):
    # Credit user's USDC 1:1
    await db.balances.update_one(
        {"user_id": user["id"], "symbol": "USDC"},
        {"$inc": {"amount": body.amount}, "$set": {"updated_at": iso(now_utc())}},
    )
    tx = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "type": "deposit",
        "category": "fiat",
        "asset": body.currency,
        "amount": body.amount,
        "fiat_value": body.amount,
        "counterparty": f"{body.method.upper()} Top-up",
        "method": body.method,
        "status": "completed",
        "receipt_id": "VLT-" + secrets.token_hex(4).upper(),
        "created_at": iso(now_utc()),
    }
    await db.transactions.insert_one(tx)
    tx.pop("_id", None)
    return tx


@api.post("/fiat/withdraw")
async def fiat_withdraw(body: FiatTxIn, user=Depends(get_current_user)):
    bal = await db.balances.find_one({"user_id": user["id"], "symbol": "USDC"}, {"_id": 0})
    if not bal or bal["amount"] < body.amount:
        raise HTTPException(status_code=400, detail="Insufficient USDC balance")
    await db.balances.update_one(
        {"user_id": user["id"], "symbol": "USDC"},
        {"$inc": {"amount": -body.amount}, "$set": {"updated_at": iso(now_utc())}},
    )
    tx = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "type": "withdraw",
        "category": "fiat",
        "asset": body.currency,
        "amount": body.amount,
        "fiat_value": body.amount,
        "counterparty": f"{body.method.upper()} Withdrawal",
        "method": body.method,
        "status": "completed",
        "receipt_id": "VLT-" + secrets.token_hex(4).upper(),
        "created_at": iso(now_utc()),
    }
    await db.transactions.insert_one(tx)
    tx.pop("_id", None)
    return tx


@api.get("/transactions")
async def list_transactions(user=Depends(get_current_user), limit: int = 100):
    cur = db.transactions.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).limit(limit)
    return await cur.to_list(limit)


# ---------- CSV / tax export -------------------------------------------------
@api.get("/transactions/export")
async def export_transactions_csv(
    user=Depends(get_current_user),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    assets: Optional[str] = None,   # comma-separated symbols, e.g. "ETH,USDC"
    types: Optional[str] = None,    # comma-separated, e.g. "send,receive"
):
    """Return a tax-ready CSV of the user's transactions, filterable by
    date range / asset / type. Compatible with most accounting tools
    (Koinly, CoinTracker, Excel, Google Sheets)."""
    from io import StringIO
    import csv
    from fastapi.responses import StreamingResponse

    q: dict = {"user_id": user["id"]}
    if date_from:
        q.setdefault("created_at", {})["$gte"] = date_from
    if date_to:
        # treat date_to as inclusive end-of-day
        q.setdefault("created_at", {})["$lte"] = f"{date_to}T23:59:59.999Z"
    if assets:
        wanted = [a.strip().upper() for a in assets.split(",") if a.strip()]
        if wanted:
            q["asset"] = {"$in": wanted}
    if types:
        wanted_t = [t.strip().lower() for t in types.split(",") if t.strip()]
        if wanted_t:
            q["type"] = {"$in": wanted_t}

    cur = db.transactions.find(q, {"_id": 0}).sort("created_at", 1)
    rows = await cur.to_list(10000)

    buf = StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "Date (UTC)", "Type", "Category", "Asset", "Amount",
        "USD Value", "Cost Basis USD", "Service Fee USD", "Net USD",
        "Counterparty", "Network", "Tx Hash", "Status", "Explorer URL",
    ])
    for r in rows:
        fiat = float(r.get("fiat_value") or 0)
        fee = float(r.get("service_fee_usd") or 0)
        t = r.get("type")
        # Net = USD value the user actually exchanged hands with (after fees)
        sign = -1 if t in ("send", "withdraw") else 1
        net = round(sign * fiat - fee, 2)
        writer.writerow([
            r.get("created_at", ""),
            t or "",
            r.get("category", ""),
            r.get("asset", ""),
            r.get("amount", ""),
            f"{fiat:.2f}",
            f"{fiat:.2f}",   # cost basis = fiat value at time of tx (snapshot)
            f"{fee:.2f}",
            f"{net:.2f}",
            r.get("counterparty", ""),
            r.get("network", ""),
            r.get("tx_hash", ""),
            r.get("status", ""),
            r.get("explorer_url", ""),
        ])

    name = "vaulted-transactions"
    if date_from or date_to:
        name += f"-{(date_from or 'all')}_to_{(date_to or 'now')}"
    name += ".csv"
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


# Chat
@api.get("/chat/contacts")
async def contacts(user=Depends(get_current_user)):
    cur = db.contacts.find({"user_id": user["id"]}, {"_id": 0}).sort("name", 1)
    return await cur.to_list(200)


@api.get("/chat/conversations")
async def conversations(user=Depends(get_current_user)):
    is_pro = is_user_pro(user)
    cur = db.conversations.find({"user_id": user["id"]}, {"_id": 0}).sort("last_message_at", -1)
    items = await cur.to_list(200)
    if is_pro:
        # Pin priority conversations (Vault Support) to the top while preserving
        # last_message_at ordering within each group (Python sort is stable).
        items.sort(key=lambda c: 0 if c.get("priority") else 1)
    return items


@api.get("/chat/messages/{conversation_id}")
async def get_messages(conversation_id: str, user=Depends(get_current_user)):
    conv = await db.conversations.find_one({"id": conversation_id, "user_id": user["id"]}, {"_id": 0})
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    # Mark read
    await db.conversations.update_one({"id": conversation_id}, {"$set": {"unread": 0}})
    cur = db.messages.find({"conversation_id": conversation_id}, {"_id": 0}).sort("created_at", 1)
    msgs = await cur.to_list(1000)
    return {"conversation": conv, "messages": msgs}


@api.post("/chat/messages")
async def send_message(body: SendMessageIn, user=Depends(get_current_user)):
    conv = await db.conversations.find_one({"id": body.conversation_id, "user_id": user["id"]}, {"_id": 0})
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    msg = {
        "id": str(uuid.uuid4()),
        "conversation_id": body.conversation_id,
        "user_id": user["id"],
        "sender": "me",
        "text": body.text,
        "nonce": body.nonce,
        "encrypted": bool(body.encrypted),
        "created_at": iso(now_utc()),
    }
    await db.messages.insert_one(msg)
    preview = "🔒 Encrypted message" if body.encrypted else body.text
    await db.conversations.update_one(
        {"id": body.conversation_id},
        {"$set": {"last_message": preview, "last_message_at": msg["created_at"], "unread": 0}},
    )
    # Auto echo response from contact (server-generated, always plaintext system message)
    auto = {
        "id": str(uuid.uuid4()),
        "conversation_id": body.conversation_id,
        "user_id": user["id"],
        "sender": "contact",
        "text": "Got it — secure message received.",
        "nonce": None,
        "encrypted": False,
        "created_at": iso(now_utc()),
    }
    await db.messages.insert_one(auto)
    await db.conversations.update_one(
        {"id": body.conversation_id},
        {"$set": {"last_message": auto["text"], "last_message_at": auto["created_at"]}},
    )
    msg.pop("_id", None)
    # Push the encrypted-message notification to the other party
    try:
        if conv.get("is_group"):
            recipients = [m.get("contact_id") for m in (conv.get("members") or []) if m.get("contact_id")]
            title = f"💬 New message in {conv.get('group_name') or 'group'}"
        else:
            cid = conv.get("contact_id")
            recipients = [cid] if cid else []
            title = f"💬 {user.get('name') or 'A friend'} sent you a message"
        if recipients:
            await send_push(
                recipients=recipients,
                data={
                    "title": title,
                    "message": "🔒 Encrypted message · tap to read",
                    "action_url": f"/chat/{body.conversation_id}",
                },
                idempotency_key=f"chat-msg-{msg['id']}",
            )
    except Exception as e:
        logger.warning("push chat-msg failed: %s", e)
    return msg
async def _get_or_create_contact_eth_address(contact_id: str) -> str:
    """Lazily derive a deterministic Sepolia address for a seeded contact.
    Stored once on the contact doc so subsequent sends are idempotent."""
    c = await db.contacts.find_one({"id": contact_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Contact not found")
    addr = c.get("eth_address")
    if addr and addr.startswith("0x") and len(addr) == 42:
        return addr
    # derive deterministically from email so the same contact always maps to the same address
    import hashlib
    seed = hashlib.sha256(f"vaulted-contact::{c.get('email','')}".encode()).digest()
    acct = Account.from_key(seed)
    addr = acct.address
    await db.contacts.update_one({"id": contact_id}, {"$set": {"eth_address": addr}})
    return addr


@api.post("/chat/send_crypto")
async def chat_send_crypto(body: SendChatCryptoIn, user=Depends(get_current_user)):
    """Send ETH inside a chat and post a tx_card receipt.

    For 1-on-1 chats the recipient is the conversation's contact. For groups,
    `to_contact_id` MUST identify a member of the group. UX guard caps
    in-chat sends below MULTISIG_THRESHOLD_ETH to avoid email-approval gating.
    """
    if body.amount_eth >= MULTISIG_THRESHOLD_ETH:
        raise HTTPException(
            status_code=400,
            detail=f"In-chat sends are capped under {MULTISIG_THRESHOLD_ETH} ETH. Use the Send screen for larger amounts.",
        )
    conv = await db.conversations.find_one(
        {"id": body.conversation_id, "user_id": user["id"]}, {"_id": 0}
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    is_group = bool(conv.get("is_group"))
    if is_group:
        if not body.to_contact_id:
            raise HTTPException(status_code=400, detail="Pick a recipient from the group")
        members = conv.get("members") or []
        if not any(m.get("contact_id") == body.to_contact_id for m in members):
            raise HTTPException(status_code=400, detail="Recipient is not in this group")
        contact_id = body.to_contact_id
    else:
        contact_id = conv.get("contact_id")
        if not contact_id:
            raise HTTPException(status_code=400, detail="Conversation has no recipient")

    pk = user.get("eth_private_key")
    addr = user.get("wallet_address")
    if not pk or not addr:
        raise HTTPException(status_code=400, detail="No ETH key on file")

    to_addr = await _get_or_create_contact_eth_address(contact_id)
    result = await _broadcast_eth_send(user, addr, pk, to_addr, body.amount_eth)
    tx_hash = result.get("tx_hash")
    explorer = result.get("explorer_url")

    # Find recipient display name for the tx_card label
    recipient_name = None
    if is_group:
        recipient_name = next(
            (m.get("name") for m in (conv.get("members") or []) if m.get("contact_id") == contact_id),
            None,
        )
    else:
        recipient_name = conv.get("contact_name")

    msg = {
        "id": str(uuid.uuid4()),
        "conversation_id": body.conversation_id,
        "user_id": user["id"],
        "sender": "me",
        "kind": "tx_card",
        "text": f"Sent {body.amount_eth} ETH" + (f" to {recipient_name}" if recipient_name else ""),
        "tx_hash": tx_hash,
        "explorer_url": explorer,
        "amount_eth": body.amount_eth,
        "asset": "ETH",
        "to_address": to_addr,
        "to_contact_id": contact_id,
        "to_name": recipient_name,
        "tx_status": result.get("status", "pending"),
        "encrypted": False,
        "created_at": iso(now_utc()),
    }
    await db.messages.insert_one(msg)

    preview = f"💸 Sent {body.amount_eth} ETH" + (f" to {recipient_name}" if recipient_name else "")
    await db.conversations.update_one(
        {"id": body.conversation_id},
        {"$set": {"last_message": preview, "last_message_at": msg["created_at"], "unread": 0}},
    )
    # Auto-ack only for 1-on-1 chats (groups would feel chatty)
    if not is_group:
        ack = {
            "id": str(uuid.uuid4()),
            "conversation_id": body.conversation_id,
            "user_id": user["id"],
            "sender": "contact",
            "kind": "text",
            "text": f"Received {body.amount_eth} ETH — thank you! ✨",
            "encrypted": False,
            "created_at": iso(now_utc()),
        }
        await db.messages.insert_one(ack)
        await db.conversations.update_one(
            {"id": body.conversation_id},
            {"$set": {"last_message": ack["text"], "last_message_at": ack["created_at"]}},
        )
    msg.pop("_id", None)
    # Fire-and-forget push to the recipient — never blocks the broadcast
    if contact_id:
        try:
            await send_push(
                recipients=[contact_id],
                data={
                    "title": f"💸 {user.get('name') or 'A friend'} sent you {body.amount_eth} ETH",
                    "message": "Tap to view the transaction in your chat.",
                    "action_url": f"/chat/{body.conversation_id}",
                },
                idempotency_key=f"chat-crypto-{msg['id']}",
            )
        except Exception as e:
            logger.warning("push send_crypto failed: %s", e)
    return msg


# ---------- Contacts & Groups -------------------------------------------------
@api.post("/chat/groups")
async def create_group(body: CreateGroupIn, user=Depends(get_current_user)):
    """Spin up an encrypted group conversation with the given contact ids."""
    if not body.contact_ids:
        raise HTTPException(status_code=400, detail="Pick at least one member")
    cur = db.contacts.find({"user_id": user["id"], "id": {"$in": body.contact_ids}}, {"_id": 0})
    contacts = await cur.to_list(50)
    if len(contacts) != len(set(body.contact_ids)):
        raise HTTPException(status_code=400, detail="Some contacts not found")
    members = [
        {"contact_id": c["id"], "name": c.get("name"), "avatar": c.get("avatar")}
        for c in contacts
    ]
    conv_id = str(uuid.uuid4())
    conv = {
        "id": conv_id,
        "user_id": user["id"],
        "is_group": True,
        "group_name": body.name.strip(),
        "contact_name": body.name.strip(),  # used by list rows
        "contact_avatar": (contacts[0].get("avatar") if contacts else None),
        "members": members,
        "last_message": f"Group created with {len(members)} member{'s' if len(members)!=1 else ''}.",
        "last_message_at": iso(now_utc()),
        "encrypted": True,
        "priority": False,
        "unread": 0,
    }
    await db.conversations.insert_one(conv)
    # Seed a system message inside the group so it isn't empty.
    sys_msg = {
        "id": str(uuid.uuid4()),
        "conversation_id": conv_id,
        "user_id": user["id"],
        "sender": "contact",
        "kind": "text",
        "text": f"🔒 {body.name.strip()} created. Messages here are end-to-end encrypted.",
        "encrypted": False,
        "created_at": iso(now_utc()),
    }
    await db.messages.insert_one(sys_msg)
    conv.pop("_id", None)
    return conv


# --------------------------- E2E Crypto Keys ---------------------------
@api.post("/keys/register")
async def register_public_key(body: RegisterKeyIn, user=Depends(get_current_user)):
    if len(body.public_key) > 512:
        raise HTTPException(status_code=400, detail="Public key too long")
    await db.users.update_one({"id": user["id"]}, {"$set": {"public_key": body.public_key}})
    return {"public_key": body.public_key}


@api.get("/keys/{user_id}")
async def get_public_key(user_id: str, _=Depends(get_current_user)):
    u = await db.users.find_one({"id": user_id}, {"_id": 0, "public_key": 1, "id": 1, "name": 1})
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    return {"id": u["id"], "public_key": u.get("public_key")}


# --------------------------- Stripe payments ---------------------------
async def _get_or_create_vault_pro_price() -> str:
    """Lazy-create a recurring Stripe Price for Vault Pro, cache id in DB."""
    if not STRIPE_API_KEY:
        raise HTTPException(status_code=503, detail="Stripe not configured")
    cfg = await db.config.find_one({"_id": "stripe"})
    if cfg and cfg.get("vault_pro_price_id"):
        return cfg["vault_pro_price_id"]
    try:
        product = stripe.Product.create(name="Vault Pro", description="Premium tier: multi-sig, lower fees, priority support")
        price = stripe.Price.create(
            unit_amount=int(VAULT_PRO_PRICE_USD * 100),  # env var name is legacy; value is now in GBP
            currency="gbp",
            recurring={"interval": "month"},
            product=product.id,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Stripe error: {e}")
    await db.config.update_one(
        {"_id": "stripe"},
        {"$set": {"vault_pro_product_id": product.id, "vault_pro_price_id": price.id}},
        upsert=True,
    )
    return price.id


def _success_cancel_urls(flow: str) -> tuple[str, str]:
    base = APP_PUBLIC_URL.rstrip("/") if APP_PUBLIC_URL else "https://example.com"
    success = f"{base}/stripe-return?flow={flow}&status=success&session_id={{CHECKOUT_SESSION_ID}}"
    cancel = f"{base}/stripe-return?flow={flow}&status=cancel"
    return success, cancel


@api.post("/stripe/checkout/deposit")
async def stripe_checkout_deposit(body: StripeDepositIn, user=Depends(get_current_user)):
    if not STRIPE_API_KEY:
        raise HTTPException(status_code=503, detail="Stripe not configured")
    amount_cents = int(round(body.amount_usd * 100))
    success, cancel = _success_cancel_urls("deposit")
    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": "USDC Wallet Top-up", "description": "Vaulted fiat deposit"},
                    "unit_amount": amount_cents,
                },
                "quantity": 1,
            }],
            success_url=success,
            cancel_url=cancel,
            metadata={"user_id": user["id"], "flow": "deposit", "amount_usd": str(body.amount_usd)},
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Stripe error: {e}")
    return {"checkout_url": session.url, "session_id": session.id}


@api.post("/stripe/checkout/subscription")
async def stripe_checkout_subscription(user=Depends(get_current_user)):
    if not STRIPE_API_KEY:
        raise HTTPException(status_code=503, detail="Stripe not configured")
    price_id = await _get_or_create_vault_pro_price()
    success, cancel = _success_cancel_urls("subscription")

    customer_id = (user.get("stripe") or {}).get("customer_id")
    if not customer_id:
        try:
            cust = stripe.Customer.create(email=user["email"], metadata={"user_id": user["id"]})
            customer_id = cust.id
            await db.users.update_one(
                {"id": user["id"]},
                {"$set": {"stripe.customer_id": customer_id}},
            )
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Stripe error: {e}")
    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            customer=customer_id,
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=success,
            cancel_url=cancel,
            metadata={"user_id": user["id"], "flow": "subscription", "tier": "vault_pro"},
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Stripe error: {e}")
    return {"checkout_url": session.url, "session_id": session.id, "price_id": price_id}


async def _apply_checkout_session(session_obj: dict) -> dict:
    """Idempotently apply a completed Stripe session to user state. Returns summary."""
    mode = session_obj.get("mode")
    metadata = session_obj.get("metadata") or {}
    user_id = metadata.get("user_id")
    if not user_id:
        return {"applied": False, "reason": "no user_id"}
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user:
        return {"applied": False, "reason": "user not found"}

    # Idempotency: check if already processed
    existing = await db.stripe_events.find_one({"session_id": session_obj.get("id")})
    if existing:
        return {"applied": False, "already": True}

    if mode == "payment" and metadata.get("flow") == "deposit":
        if session_obj.get("payment_status") != "paid":
            return {"applied": False, "reason": "not paid"}
        amount_usd = (session_obj.get("amount_total") or 0) / 100.0
        await db.balances.update_one(
            {"user_id": user_id, "symbol": "USDC"},
            {"$inc": {"amount": amount_usd}, "$set": {"updated_at": iso(now_utc())}},
        )
        tx = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "type": "deposit",
            "category": "fiat",
            "asset": (session_obj.get("currency") or "usd").upper(),
            "amount": amount_usd,
            "fiat_value": amount_usd,
            "counterparty": "Stripe Card Top-up",
            "method": "card",
            "status": "completed",
            "receipt_id": "VLT-" + (session_obj.get("id") or "")[-8:].upper(),
            "stripe_session_id": session_obj.get("id"),
            "created_at": iso(now_utc()),
        }
        await db.transactions.insert_one(tx)
        await db.stripe_events.insert_one({"session_id": session_obj.get("id"), "kind": "deposit", "at": iso(now_utc())})
        return {"applied": True, "kind": "deposit", "amount_usd": amount_usd}

    if mode == "payment" and metadata.get("flow") == "remit_fund":
        # Fiat-funded cross-border send. We already charged the user — now
        # book the send as processing. Actual settlement to the recipient
        # happens via our off-ramp partners (executed by ops until Kotani
        # Pay direct integration lands in Phase C). The tx is created with
        # `funding_method: stripe` so the receipt/UX can hide crypto rails.
        if session_obj.get("payment_status") != "paid":
            return {"applied": False, "reason": "not paid"}
        try:
            src_amount = float(metadata.get("source_amount") or 0)
            dst_amount = float(metadata.get("destination_amount") or 0)
            fx_rate = float(metadata.get("fx_rate") or 0)
            svc_fee_usd = float(metadata.get("vaulted_service_usd") or 0)
        except ValueError:
            return {"applied": False, "reason": "bad metadata"}

        # What the user paid (already charged by Stripe, all-in)
        total_paid_src = (session_obj.get("amount_total") or 0) / 100.0

        tx_id = str(uuid.uuid4())
        record = {
            "id": tx_id,
            "user_id": user_id,
            "type": "send",
            "category": f"Remit · {metadata.get('destination_country')}",
            "asset": (metadata.get("source_fiat") or "GBP").upper(),  # user-facing fiat asset
            "amount": src_amount,
            "fiat_value": total_paid_src,
            "counterparty": metadata.get("recipient_address") or "",
            "recipient_name": metadata.get("recipient_name") or None,
            "memo": metadata.get("memo") or None,
            "network": "Stripe",
            "tx_hash": f"stripe:{session_obj.get('id')}",  # placeholder ref
            "explorer_url": None,
            "status": "processing",  # fiat rails: settled by ops / off-ramp partners
            "service_fee_usd": svc_fee_usd,
            "gross_service_fee_usd": svc_fee_usd,
            "credit_applied_gbp": 0.0,
            "credit_balance_after_gbp": 0.0,
            "funding_method": "stripe",
            "payment_method": metadata.get("payment_method") or "card",
            "stripe_session_id": session_obj.get("id"),
            "receipt_id": "VLT-" + (session_obj.get("id") or "")[-8:].upper(),
            "created_at": iso(now_utc()),
            "remit": {
                "source_currency": (metadata.get("source_fiat") or "GBP").upper(),
                "source_amount": src_amount,
                "destination_currency": metadata.get("destination_currency"),
                "destination_amount": dst_amount,
                "destination_country": metadata.get("destination_country"),
                "destination_country_code": (metadata.get("destination_code") or "").upper(),
                "destination_flag": metadata.get("destination_flag"),
                "chain": None,  # hidden from user — fiat rails
                "fx_rate": fx_rate,
                "receive_via": metadata.get("receive_via"),
            },
        }
        await db.transactions.insert_one(record)
        record.pop("_id", None)
        await db.stripe_events.insert_one({
            "session_id": session_obj.get("id"), "kind": "remit_fund", "at": iso(now_utc()),
        })

        # Audit as a remit success — same event type as crypto path so
        # analytics + compliance reports treat both funding methods uniformly.
        user_doc = await db.users.find_one({"id": user_id}, {"_id": 0})
        user_kyc = (user_doc or {}).get("kyc") or {}
        user_sanctions = user_kyc.get("sanctions") or {}
        try:
            await audit_write(db, EventType.REMIT_SEND_SUCCESS, user=user_doc, data={
                "tx_id": tx_id,
                "tx_hash": record["tx_hash"],
                "chain": None,
                "funding_method": "stripe",
                "payment_method": record["payment_method"],
                "source_currency": record["remit"]["source_currency"],
                "source_amount": record["remit"]["source_amount"],
                "destination_country": record["remit"]["destination_country"],
                "destination_currency": record["remit"]["destination_currency"],
                "destination_amount": record["remit"]["destination_amount"],
                "recipient_address_hash": hashlib.sha256((record["counterparty"] or "").lower().encode()).hexdigest()[:12],
                "recipient_name_hash": hashlib.sha256((record.get("recipient_name") or "").strip().lower().encode()).hexdigest()[:12] if record.get("recipient_name") else None,
                "service_fee_usd": record["service_fee_usd"],
                "fiat_value_src": total_paid_src,
                "tier_at_send": user_kyc.get("tier"),
                "sanctions_state_at_send": {
                    "matched": user_sanctions.get("matched", False),
                    "degraded": user_sanctions.get("degraded", True),
                    "degraded_reason": user_sanctions.get("degraded_reason"),
                },
            })
        except Exception as e:  # noqa: BLE001
            logger.warning("remit_fund audit_write failed: %s", e)

        # === Auto-trigger Kotani Pay M-Pesa off-ramp for Kenya sends ===
        # Non-fatal: any Kotani failure leaves the Stripe charge in place
        # and the tx in "processing" so ops can retry. Mock mode returns
        # SUCCESS immediately, so mock-mode receipts render "settled".
        kotani_result: dict = {}
        try:
            if (metadata.get("destination_code") or "").upper() == "KE":
                kotani_result = await _trigger_kotani_offramp_for_remit(record)
                # Reload the record so the returned tx has the fresh kotani state
                fresh = await db.transactions.find_one({"id": record["id"]}, {"_id": 0})
                if fresh:
                    record = fresh
        except Exception as e:  # noqa: BLE001
            logger.warning("kotani offramp trigger failed for tx %s: %s", tx_id, e)
            kotani_result = {"error": str(e)[:200]}

        return {"applied": True, "kind": "remit_fund", "tx": record, **kotani_result}

    if mode == "subscription":
        sub_id = session_obj.get("subscription")
        cust_id = session_obj.get("customer")
        # Fetch subscription for accurate status
        status_val = "active"
        period_end = None
        if sub_id and STRIPE_API_KEY:
            try:
                sub = stripe.Subscription.retrieve(sub_id)
                status_val = sub.get("status", "active")
                period_end = sub.get("current_period_end")
            except Exception:
                pass
        await db.users.update_one(
            {"id": user_id},
            {"$set": {
                "stripe.customer_id": cust_id,
                "subscription": {
                    "tier": "vault_pro",
                    "stripe_subscription_id": sub_id,
                    "status": status_val,
                    "current_period_end": period_end,
                },
            }},
        )
        await db.stripe_events.insert_one({"session_id": session_obj.get("id"), "kind": "subscription", "at": iso(now_utc())})
        return {"applied": True, "kind": "subscription", "status": status_val}

    return {"applied": False, "reason": "unhandled mode"}


@api.post("/stripe/sync")
async def stripe_sync(body: StripeSyncIn, user=Depends(get_current_user)):
    """Client polls this after returning from Stripe Checkout to settle state."""
    if not STRIPE_API_KEY:
        raise HTTPException(status_code=503, detail="Stripe not configured")
    try:
        session = stripe.checkout.Session.retrieve(body.session_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Session not found: {e}")
    if (session.get("metadata") or {}).get("user_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Session not for this user")
    result = await _apply_checkout_session(dict(session))
    u = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    return {"session_status": session.get("status"), "payment_status": session.get("payment_status"), "applied": result, "user": public_user(u)}


@api.post("/stripe/webhook")
async def stripe_webhook(request: Request, stripe_signature: Optional[str] = Header(None, alias="Stripe-Signature")):
    payload = await request.body()
    if STRIPE_WEBHOOK_SECRET and stripe_signature:
        try:
            event = stripe.Webhook.construct_event(payload, stripe_signature, STRIPE_WEBHOOK_SECRET)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid webhook: {e}")
    else:
        try:
            event = json.loads(payload.decode())
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid payload")
    if event["type"] == "checkout.session.completed":
        await _apply_checkout_session(event["data"]["object"])
    elif event["type"] in ("customer.subscription.updated", "customer.subscription.deleted"):
        sub = event["data"]["object"]
        await db.users.update_one(
            {"subscription.stripe_subscription_id": sub.get("id")},
            {"$set": {"subscription.status": sub.get("status"), "subscription.current_period_end": sub.get("current_period_end")}},
        )
    elif event["type"] == "identity.verification_session.verified":
        await _apply_identity_verified(event["data"]["object"])
    elif event["type"] == "identity.verification_session.requires_input":
        await _apply_identity_requires_input(event["data"]["object"])
    elif event["type"] == "identity.verification_session.canceled":
        # User canceled mid-flow — leave the tier alone, just clear the pending state
        user_id = ((event["data"]["object"].get("metadata") or {}).get("user_id"))
        if user_id:
            await db.users.update_one(
                {"id": user_id},
                {"$set": {"kyc.identity_verification_status": "canceled"}},
            )
            await audit_write(
                db,
                EventType.KYC_CANCELED,
                user_id=user_id,
                data={"session_id": event["data"]["object"].get("id")},
            )
    return {"status": "ok"}


@api.post("/stripe/portal")
async def stripe_portal(user=Depends(get_current_user)):
    """Returns a Stripe Billing Portal URL so the user can manage their subscription."""
    if not STRIPE_API_KEY:
        raise HTTPException(status_code=503, detail="Stripe not configured")
    customer_id = (user.get("stripe") or {}).get("customer_id")
    if not customer_id:
        raise HTTPException(status_code=400, detail="No billing customer; subscribe first.")
    base = APP_PUBLIC_URL.rstrip("/") if APP_PUBLIC_URL else "https://example.com"
    try:
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=f"{base}/vault-pro",
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Stripe portal error: {e}")
    return {"url": session.url}


@api.post("/stripe/cancel")
async def stripe_cancel_subscription(user=Depends(get_current_user)):
    if not STRIPE_API_KEY:
        raise HTTPException(status_code=503, detail="Stripe not configured")
    sub_id = (user.get("subscription") or {}).get("stripe_subscription_id")
    if not sub_id:
        raise HTTPException(status_code=400, detail="No active subscription")
    try:
        stripe.Subscription.modify(sub_id, cancel_at_period_end=True)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Stripe error: {e}")
    await db.users.update_one({"id": user["id"]}, {"$set": {"subscription.status": "canceled"}})
    return {"status": "canceled"}


# --------------------------- Daily.co video calls ---------------------------
@api.post("/calls/room")
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
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Daily.co error: {e}")
    return {"configured": True, "room_url": room["url"], "token": token, "name": room_name}


app.include_router(api)


# Lightweight liveness probe for Railway/Render/Fly health checks.
@app.api_route("/api/health", methods=["GET", "HEAD"])
async def health() -> dict:
    return {"status": "ok"}


# CORS — env-driven for prod, falls back to '*' for local dev.
# Set CORS_ALLOW_ORIGINS in Railway/Vercel as a comma-separated list, e.g.:
#   CORS_ALLOW_ORIGINS=https://vaulted.vercel.app,https://app.vaulted.io
_origins_env = os.environ.get("CORS_ALLOW_ORIGINS", "").strip()
_allow_origins = (
    [o.strip() for o in _origins_env.split(",") if o.strip()] if _origins_env else ["*"]
)
# Browsers reject `allow_credentials=True` with `allow_origins=*`, so flip credentials
# off when we're in the wildcard fallback.
_allow_credentials = _allow_origins != ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_credentials=_allow_credentials,
    allow_origins=_allow_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()


# ---------- Resend domain auto-poller -----------------------------------------
# Periodically checks Resend for the target domain (e.g. phoenix-atlas.com).
# As soon as it flips to "verified", we promote the sender by populating
# `_resolved_resend_from`. No env-file rewriting required.
async def _resend_domain_poller():
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
                                    "[resend-poller] %s verified — sender promoted to %s",
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
        except Exception as e:  # pragma: no cover — best-effort
            logger.warning("[resend-poller] iteration failed: %s", e)
        await asyncio.sleep(interval)


@app.on_event("startup")
async def _start_resend_poller():
    # Fire-and-forget; FastAPI will keep this task alive for the process lifetime.
    asyncio.create_task(_resend_domain_poller())


@app.on_event("startup")
async def _ensure_audit_indexes():
    """Ensure the query patterns on the audit-log endpoint stay fast even as
    the collection grows to 100k+ events. Idempotent — safe to run on every
    startup."""
    try:
        await db.audit_events.create_index([("timestamp", -1)])
        await db.audit_events.create_index([("user_id", 1), ("timestamp", -1)])
        await db.audit_events.create_index([("event_type", 1), ("timestamp", -1)])
        # Referrals + credit-ledger indexes
        await db.users.create_index("referral_code", unique=True, sparse=True)
        await db.referrals.create_index("referrer_user_id")
        await db.referrals.create_index("referred_user_id", unique=True, sparse=True)
        await db.credit_ledger.create_index([("user_id", 1), ("created_at", -1)])
    except Exception as e:
        logger.warning(f"audit_events index creation failed: {e}")


# ---------- Emergent push notifications --------------------------------------
PUSH_BASE_URL = "https://integrations.emergentagent.com"
EMERGENT_PUSH_KEY = os.environ.get("EMERGENT_PUSH_KEY", "placeholder")

_push_client = httpx.AsyncClient(
    base_url=PUSH_BASE_URL,
    headers={"X-Push-Key": EMERGENT_PUSH_KEY},
    timeout=10.0,
)


class RegisterPushBody(BaseModel):
    user_id: str
    platform: str
    device_token: str


@app.post("/api/register-push", status_code=201)
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
    except Exception as e:  # pragma: no cover — best-effort
        logger.warning("send_push failed (non-blocking): %s", e)
