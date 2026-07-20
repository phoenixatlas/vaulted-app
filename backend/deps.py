"""Shared FastAPI dependencies + module-level state (db client, JWT config,
logger, auth helpers) for the Vaulted backend.

Every router imports from this file so we have a single source of truth for
the mongo connection and auth pipeline. server.py also imports from here so
the two stay in perfect sync.
"""
from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import jwt
from dotenv import load_dotenv
from eth_account import Account
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from motor.motor_asyncio import AsyncIOMotorClient
from passlib.context import CryptContext

# ---------------------------- Env ----------------------------------------
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

# ---------------------------- Mongo client -------------------------------
_mongo_url = os.environ["MONGO_URL"]
# Pass certifi's CA bundle explicitly when connecting to Atlas (mongodb+srv://).
# Fixes "SSL handshake failed: TLSV1_ALERT_INTERNAL_ERROR" on hosted platforms
# (Render, Railway, etc.) whose default OS trust store can be stale/incomplete.
_mongo_kwargs: dict = {}
if "mongodb+srv" in _mongo_url or "mongodb.net" in _mongo_url:
    try:
        import certifi
        _mongo_kwargs["tlsCAFile"] = certifi.where()
    except Exception:
        pass
client = AsyncIOMotorClient(_mongo_url, **_mongo_kwargs)
db = client[os.environ["DB_NAME"]]

# ---------------------------- Config -------------------------------------
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

MULTISIG_THRESHOLD_ETH = float(os.environ.get("MULTISIG_THRESHOLD_ETH", "0.01"))
APPROVAL_TTL_HOURS = 24

# Enable HD wallet features
Account.enable_unaudited_hdwallet_features()

# ---------------------------- Bcrypt / bearer / logger -------------------
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer = HTTPBearer(auto_error=False)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("vaulted")


# ---------------------------- Small helpers ------------------------------
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


# ---------------------------- Auth dependencies --------------------------
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
# simple - we don't need RBAC granularity for the current admin footprint
# (health checks, manual sanctions screens). Upgrade to a role field on the
# user doc if the admin surface grows.
ADMIN_EMAILS: set[str] = {
    e.strip().lower()
    for e in (os.environ.get("ADMIN_EMAILS", "") or "").split(",")
    if e.strip()
}


async def require_admin(user=Depends(get_current_user)) -> dict:
    if not ADMIN_EMAILS:
        # No admin list configured on this deployment -> lock everything down
        # rather than accidentally open the endpoints wide.
        raise HTTPException(status_code=403, detail="Admin endpoints not configured")
    email = (user.get("email") or "").strip().lower()
    if email not in ADMIN_EMAILS:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def hash12(s: str) -> str:
    """Deterministic 12-char lowercase hash used across audit events to log
    email/name references without persisting PII."""
    return hashlib.sha256((s or "").lower().strip().encode()).hexdigest()[:12]
