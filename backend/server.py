from fastapi import FastAPI, APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import uuid
import secrets
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
    text: str = Field(min_length=1, max_length=4000)


class StartConversationIn(BaseModel):
    contact_id: str


class UpdateLanguageIn(BaseModel):
    language: str


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
    return {
        "id": u["id"],
        "email": u["email"],
        "name": u["name"],
        "language": u.get("language", "en"),
        "avatar": u.get("avatar"),
        "wallet_address": u.get("wallet_address"),
        "biometric_enabled": u.get("biometric_enabled", False),
        "multisig_enabled": u.get("multisig_enabled", False),
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
    {"name": "Maya Chen", "email": "maya@vaulted.app",
     "avatar": "https://images.pexels.com/photos/8384889/pexels-photo-8384889.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=200&w=200"},
    {"name": "Daniel Park", "email": "daniel@vaulted.app",
     "avatar": "https://images.pexels.com/photos/35334114/pexels-photo-35334114.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=200&w=200"},
    {"name": "Vault Support", "email": "support@vaulted.app",
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
    user_doc = {
        "id": uid,
        "email": body.email.lower(),
        "name": body.name.strip(),
        "password_hash": pwd_ctx.hash(body.password),
        "language": "en",
        "wallet_address": "0x" + secrets.token_hex(20),
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
@api.get("/wallet/assets")
async def wallet_assets(user=Depends(get_current_user)):
    cursor = db.balances.find({"user_id": user["id"]}, {"_id": 0})
    items = await cursor.to_list(100)
    price_map = {a["symbol"]: a["price_usd"] for a in DEFAULT_ASSETS}
    total_usd = 0.0
    out = []
    for b in items:
        p = price_map.get(b["symbol"], 0)
        fiat = round(b["amount"] * p, 2)
        total_usd += fiat
        out.append({**b, "price_usd": p, "fiat_value": fiat})
    out.sort(key=lambda x: x["fiat_value"], reverse=True)
    return {
        "total_usd": round(total_usd, 2),
        "wallet_address": user.get("wallet_address"),
        "assets": out,
    }


@api.post("/wallet/send")
async def wallet_send(body: SendCryptoIn, user=Depends(get_current_user)):
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
    cur = db.conversations.find({"user_id": user["id"]}, {"_id": 0}).sort("last_message_at", -1)
    return await cur.to_list(200)


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
        "created_at": iso(now_utc()),
    }
    await db.messages.insert_one(msg)
    await db.conversations.update_one(
        {"id": body.conversation_id},
        {"$set": {"last_message": body.text, "last_message_at": msg["created_at"], "unread": 0}},
    )
    # Auto echo response from contact for the demo (only for first reply)
    auto = {
        "id": str(uuid.uuid4()),
        "conversation_id": body.conversation_id,
        "user_id": user["id"],
        "sender": "contact",
        "text": "Got it — message received securely.",
        "created_at": iso(now_utc()),
    }
    await db.messages.insert_one(auto)
    await db.conversations.update_one(
        {"id": body.conversation_id},
        {"$set": {"last_message": auto["text"], "last_message_at": auto["created_at"]}},
    )
    msg.pop("_id", None)
    return msg


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
