# Iteration 40 helper: print an admin JWT for UI testing (no data changes).
import asyncio, os, sys
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")
from motor.motor_asyncio import AsyncIOMotorClient
from deps import make_token


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    u = await db.users.find_one({"email": "umar.sani@phoenix-atlas.com"}, {"_id": 0, "id": 1})
    print(make_token(u["id"]))

asyncio.run(main())
