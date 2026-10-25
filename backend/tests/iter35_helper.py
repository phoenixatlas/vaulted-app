# Seed / cleanup helper for iteration 35 (tell-recipient). Usage: python iter35_helper.py seed|clean
import asyncio, json, os, sys, uuid
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _remit(cur, amt, country, via):
    return {"source_currency": "GBP", "source_amount": 50, "destination_currency": cur,
            "destination_amount": amt, "destination_country": country, "receive_via": via}


async def seed():
    u = await db.users.find_one({"email": "smoketest@vaulted.app"}, {"_id": 0, "id": 1})
    now = datetime.now(timezone.utc).isoformat()
    base = {"user_id": u["id"], "type": "send", "asset": "USDC", "amount": 50.0, "created_at": now,
            "payout": {"mode": "simulated"}, "_iter35": True}
    ids = {"ke": str(uuid.uuid4()), "ng": str(uuid.uuid4()), "proc": str(uuid.uuid4())}
    await db.transactions.insert_many([
        {**base, "id": ids["ke"], "status": "settled", "recipient_name": "Grace Wanjiru",
         "counterparty": "+254712345678", "receipt_id": "VLT-IT35KE",
         "remit": _remit("KES", 8123.45, "Kenya", "M-Pesa")},
        {**base, "id": ids["ng"], "status": "settled", "recipient_name": "Chidi Okafor",
         "counterparty": "0123456789", "receipt_id": "VLT-IT35NG",
         "recipient_bank": {"id": "ng_058", "name": "GTBank"},
         "remit": _remit("NGN", 95000, "Nigeria", "Bank transfer")},
        {**base, "id": ids["proc"], "status": "processing", "recipient_name": "Grace Wanjiru",
         "counterparty": "+254712345678", "receipt_id": "VLT-IT35PR",
         "remit": _remit("KES", 1000, "Kenya", "M-Pesa")},
    ])
    print(json.dumps(ids))


async def clean():
    r = await db.transactions.delete_many({"_iter35": True})
    r2 = await db.users.delete_many({"email": {"$regex": "^test_iter35"}})
    print("deleted tx", r.deleted_count, "users", r2.deleted_count)


asyncio.run(seed() if sys.argv[1] == "seed" else clean())
