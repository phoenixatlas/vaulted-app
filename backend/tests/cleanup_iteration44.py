# Cleanup for iteration 44: delete only tx records this run created (looked up by exact unique names + time window, deleted by id)
import asyncio, os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
NAMES = ["TEST_Uni Of London", "TEST_Klinik Berlin", "TEST University London", "TEST Klinik Berlin", "TEST Smith & Co Ltd",
         "TEST King's College", "TEST Zoë Müller", "TEST2 Clinic 24", "TESTMadonna", "TEST Imperial College", "TEST Charite Klinik"]


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    rows = await db.transactions.find({"recipient_name": {"$in": NAMES}, "created_at": {"$gte": "2026-11-16T12:09"}},
                                      {"_id": 0, "id": 1, "recipient_name": 1, "status": 1, "payout.mode": 1, "created_at": 1}).to_list(50)
    for r in rows:
        print(r)
    ids = [r["id"] for r in rows]
    if os.environ.get("DO_DELETE") == "1" and ids:
        res = await db.transactions.delete_many({"id": {"$in": ids}})
        print("deleted", res.deleted_count)

asyncio.run(main())
