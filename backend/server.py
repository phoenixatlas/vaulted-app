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
import httpx
import stripe
from eth_account import Account
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Literal

from pydantic import BaseModel, EmailStr, Field
from passlib.context import CryptContext
import jwt


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
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
        "subscription": {
            "tier": sub.get("tier", "free"),
            "status": sub.get("status", "inactive"),
            "current_period_end": sub.get("current_period_end"),
        },
        "is_pro": (sub.get("status") in ("active", "trialing")),
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


DEFAULT_ASSETS = [
    {"symbol": "BTC", "name": "Bitcoin", "price_usd": 67234.12, "icon": "bitcoin"},
    {"symbol": "ETH", "name": "Ethereum", "price_usd": 3582.40, "icon": "ethereum"},
    {"symbol": "USDC", "name": "USD Coin", "price_usd": 1.00, "icon": "usdc"},
    {"symbol": "SOL", "name": "Solana", "price_usd": 158.22, "icon": "solana"},
]

SEED_BALANCES = {"BTC": 0.0421, "ETH": 1.842, "USDC": 1250.00, "SOL": 12.55}

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
    user_doc = {
        "id": uid,
        "email": body.email.lower(),
        "name": body.name.strip(),
        "password_hash": pwd_ctx.hash(body.password),
        "language": "en",
        "wallet_address": acct.address,
        "eth_private_key": "0x" + acct.key.hex(),
        "eth_mnemonic": mnemonic_phrase,
        "onboarding_seed_acknowledged": False,
        "biometric_enabled": False,
        "multisig_enabled": False,
        "created_at": iso(now_utc()),
    }
    await db.users.insert_one(user_doc)
    await seed_user_data(uid)
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

    total_usd = 0.0
    out = []
    for b in items:
        p = price_map.get(b["symbol"], 0)
        amt = b["amount"]
        on_chain = False
        if b["symbol"] == "ETH":
            amt = eth_amount
            on_chain = True
            await db.balances.update_one(
                {"user_id": user["id"], "symbol": "ETH"},
                {"$set": {"amount": amt, "updated_at": iso(now_utc())}},
            )
        fiat = round(amt * p, 2)
        total_usd += fiat
        ma = market_assets.get(b["symbol"], {})
        out.append({
            **b,
            "amount": amt,
            "price_usd": p,
            "fiat_value": fiat,
            "on_chain": on_chain,
            "network": "Sepolia" if on_chain else None,
            "change_24h_pct": ma.get("change_24h_pct", 0.0),
            "sparkline_7d": ma.get("sparkline_7d", []),
        })
    out.sort(key=lambda x: x["fiat_value"], reverse=True)
    return {
        "total_usd": round(total_usd, 2),
        "wallet_address": addr,
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

    is_pro = (user.get("subscription") or {}).get("status") in ("active", "trialing")
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
    if not (user.get("subscription") or {}).get("status") in ("active", "trialing"):
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
        # Backfill for users created before BIP-39 support
        raise HTTPException(status_code=404, detail="No recovery phrase on file. Re-register to get one.")
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
            for sym, p in [("BTC", 67000), ("ETH", 3500), ("USDC", 1.0), ("SOL", 150)]
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
    is_pro = (user.get("subscription") or {}).get("status") in ("active", "trialing")
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
            unit_amount=int(VAULT_PRO_PRICE_USD * 100),
            currency="usd",
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
