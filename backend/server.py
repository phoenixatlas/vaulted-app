from fastapi import FastAPI, APIRouter, Depends, HTTPException, status, Request, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
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

    value_wei = int(round(body.amount_eth * 1e18))
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

    # Vault Pro fee discount: simulated 50% off the dust fee we charge
    is_pro = (user.get("subscription") or {}).get("status") in ("active", "trialing")
    service_fee_usd = 0.10 if not is_pro else 0.05

    price = next((a["price_usd"] for a in DEFAULT_ASSETS if a["symbol"] == "ETH"), 0)
    tx_record = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "type": "send",
        "category": "crypto",
        "asset": "ETH",
        "amount": body.amount_eth,
        "fiat_value": round(body.amount_eth * price, 2),
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


# Chat
@api.get("/chat/contacts")
async def contacts(user=Depends(get_current_user)):
    cur = db.contacts.find({"user_id": user["id"]}, {"_id": 0})
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
    return msg


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

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
