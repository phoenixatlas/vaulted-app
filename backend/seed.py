"""Seed data + user bootstrapping. Extracted from server.py so routers can
invoke seed_user_data() without pulling in every other server-level import.
"""
from __future__ import annotations

import uuid

from deps import db, iso, now_utc


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
            "text": f"Hi! I'm {c['name']}. Welcome to Vaulted \u2014 your messages here are end-to-end encrypted.",
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
