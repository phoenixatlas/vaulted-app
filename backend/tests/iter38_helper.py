# Iteration 38 helper: seed partner lead + print admin token, or clean. Usage: python iter38_helper.py seed|clean
import asyncio, os, sys, uuid
from datetime import datetime, timezone
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")
from motor.motor_asyncio import AsyncIOMotorClient
from deps import make_token
db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

async def main(cmd):
    if cmd == "seed":
        lid = str(uuid.uuid4())
        await db.partner_enquiries.insert_one({"id": lid, "name": "TEST_ UI Lead", "email": "ui_iter38@example.com",
            "company": "TEST_UI_Co", "corridor": "UK → Ghana", "partner_type": "mobile_money", "message": "TEST_ msg",
            "status": "new", "created_at": datetime.now(timezone.utc).isoformat()})
        u = await db.users.find_one({"email": "umar.sani@phoenix-atlas.com"}, {"_id": 0, "id": 1})
        print(lid); print(make_token(u["id"]))
    else:
        r = await db.partner_enquiries.delete_many({"email": {"$regex": r"(example\.com|resend\.dev)$"}})
        print("deleted", r.deleted_count)
asyncio.run(main(sys.argv[1]))
