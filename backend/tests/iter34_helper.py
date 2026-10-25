# Seed / cleanup helper for iteration 34 (shareable receipts). Usage: python iter34_helper.py seed|clean
import asyncio, os, sys, uuid
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


async def seed():
    u = await db.users.find_one({"email": "smoketest@vaulted.app"}, {"_id": 0, "id": 1})
    tid = str(uuid.uuid4())
    await db.transactions.insert_one({
        "id": tid, "user_id": u["id"], "type": "send", "status": "settled",
        "asset": "USDC", "amount": 50.0,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "recipient_name": "Grace Wanjiru Otieno", "counterparty": "+254712345678",
        "receipt_id": "VLT-IT34TEST",
        "remit": {"source_currency": "GBP", "source_amount": 50, "destination_currency": "KES",
                  "destination_amount": 8123.45, "destination_country": "Kenya", "receive_via": "M-Pesa"},
        "payout": {"mode": "simulated", "provider_label": "Kotani Pay"},
        "_iter34": True,
    })
    print(tid)


async def clean():
    r = await db.transactions.delete_many({"_iter34": True})
    print("deleted", r.deleted_count)


asyncio.run(seed() if sys.argv[1] == "seed" else clean())
