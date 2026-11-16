# Iteration 40 probe: bill submit with fabricated invoice_path (no upload) + admin invoice fetch. Cleans up its bill.
import os, sys, asyncio, requests
from dotenv import load_dotenv
load_dotenv("/app/frontend/.env"); load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend"); sys.path.insert(0, "/app/backend/tests")
from motor.motor_asyncio import AsyncIOMotorClient
from deps import make_token
from test_iteration40_bill_payments import _bill_body
API = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") + "/api"
db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

async def main():
    tok = requests.post(f"{API}/auth/login", json={"email": "smoketest@vaulted.app", "password": "test1234"}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    me = requests.get(f"{API}/auth/me", headers=h).json()
    uid = me.get("id") or me.get("user", {}).get("id")
    admin = await db.users.find_one({"email": "umar.sani@phoenix-atlas.com"}, {"_id": 0, "id": 1})
    ah = {"Authorization": f"Bearer {make_token(admin['id'])}"}
    up = requests.post(f"{API}/bills/invoice", headers=h, files={"file": ("a.pdf", b"%PDF-1", "application/pdf")}).json()
    print("upload path sample:", up)
    fake = f"bills/{uid}/does-not-exist.pdf"
    r = requests.post(f"{API}/bills", headers=h, json=_bill_body(fake))
    print("fabricated path submit:", r.status_code, r.text[:120])
    if r.status_code == 200:
        bid = r.json()["id"]
        f = requests.get(f"{API}/admin/bills/{bid}/invoice", headers=ah)
        print("admin invoice for fabricated:", f.status_code, f.text[:120])
        await db.bill_payments.delete_one({"id": bid})
        print("cleaned", bid)
    # traversal-ish path
    r = requests.post(f"{API}/bills", headers=h, json=_bill_body(f"x/bills/{uid}/../../other/file.pdf"))
    print("traversal path submit:", r.status_code)
    if r.status_code == 200:
        await db.bill_payments.delete_one({"id": r.json()["id"]}); print("cleaned traversal bill")

asyncio.run(main())
