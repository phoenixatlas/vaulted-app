# Iteration 40: International Bill Payments (config, quote, invoice upload, submit, admin review)
import os
import sys
import uuid

import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")
from deps import make_token  # noqa: E402

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
ADMIN_EMAIL = "umar.sani@phoenix-atlas.com"
PDF_BYTES = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
CREATED_IDS = []


def _login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=30)
    return r


@pytest.fixture(scope="module")
def user_h():
    r = _login("smoketest@vaulted.app", "test1234")
    if r.status_code != 200:
        pytest.skip(f"smoke login failed {r.status_code}")
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="module")
def other_h():
    email = f"test_bills_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": "test1234", "name": "TEST_ Bills",
                                                     "invite_code": "VAULTED-BETA"}, timeout=30)
    if r.status_code not in (200, 201):
        pytest.skip(f"register failed {r.status_code} {r.text[:200]}")
    tok = r.json().get("access_token") or _login(email, "test1234").json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def admin_h():
    from motor.motor_asyncio import AsyncIOMotorClient
    import asyncio

    async def get():
        db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        return await db.users.find_one({"email": ADMIN_EMAIL}, {"_id": 0, "id": 1})
    u = asyncio.new_event_loop().run_until_complete(get())
    if not u:
        pytest.skip("admin user not found")
    return {"Authorization": f"Bearer {make_token(u['id'])}"}


def _upload(h, content=PDF_BYTES, name="TEST_invoice.pdf", ctype="application/pdf"):
    return requests.post(f"{API}/bills/invoice", headers=h, files={"file": (name, content, ctype)}, timeout=30)


def _bill_body(invoice_path, **over):
    b = {"category": "education", "subtype": "Tuition fees", "beneficiary_name": "TEST_ Student",
         "beneficiary_ref": "STU-123", "institution": "TEST_ University of Leeds",
         "payee": {"name": "TEST_ Univ Leeds", "bank_name": "Barclays", "account_number": "GB29NWBK60161331926819",
                   "routing": "60-16-13", "swift": "BARCGB22", "address": "Leeds", "reference": "INV-1"},
         "invoice_path": invoice_path, "invoice_name": "TEST_invoice.pdf", "declaration": True,
         "payer_country": "NG", "payout_currency": "GBP", "amount": 1500}
    b.update(over)
    return b


# Config
class TestConfig:
    def test_config_public(self):
        r = requests.get(f"{API}/bills/config", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert [c["id"] for c in d["categories"]] == ["education", "healthcare", "business"]
        assert all(c["subtypes"] and len(c["fields"]) == 3 for c in d["categories"])
        assert {c["code"] for c in d["payer_countries"]} == {"NG", "KE", "GH", "ZA"}
        assert {c["code"] for c in d["payout_currencies"]} == {"GBP", "EUR", "USD", "CAD"}


# Quote
class TestQuote:
    def test_quote_requires_auth(self):
        r = requests.post(f"{API}/bills/quote", json={"category": "education", "payer_country": "NG",
                                                     "payout_currency": "GBP", "amount": 100}, timeout=30)
        assert r.status_code in (401, 403)

    @pytest.mark.parametrize("cur,prov", [("GBP", "Flutterwave"), ("EUR", "Flutterwave"), ("USD", "Flutterwave"),
                                          ("CAD", "Simulated FX partner")])
    def test_quote_values(self, user_h, cur, prov):
        r = requests.post(f"{API}/bills/quote", headers=user_h, json={"category": "healthcare", "payer_country": "KE",
                                                                     "payout_currency": cur, "amount": 1000}, timeout=30)
        assert r.status_code == 200, r.text
        q = r.json()
        assert q["provider"]["label"] == prov
        assert q["rate"] > q["mid_market_rate"] > 0
        assert abs(q["total"] - (q["principal"] + q["fee"])) < 0.02
        assert q["fee"] > 0 and q["expires_at"] and q["payer_currency"] == "KES"

    @pytest.mark.parametrize("body", [
        {"category": "travel", "payer_country": "NG", "payout_currency": "GBP", "amount": 100},
        {"category": "education", "payer_country": "US", "payout_currency": "GBP", "amount": 100},
        {"category": "education", "payer_country": "NG", "payout_currency": "JPY", "amount": 100},
        {"category": "education", "payer_country": "NG", "payout_currency": "USD", "amount": 10},
        {"category": "education", "payer_country": "NG", "payout_currency": "USD", "amount": 60000},
    ])
    def test_quote_rejects(self, user_h, body):
        r = requests.post(f"{API}/bills/quote", headers=user_h, json=body, timeout=30)
        assert r.status_code == 400, r.text


# Invoice upload
class TestInvoice:
    def test_upload_pdf(self, user_h):
        r = _upload(user_h)
        assert r.status_code == 200, r.text
        assert r.json()["invoice_path"].startswith("bills/") or "/bills/" in r.json()["invoice_path"]

    def test_upload_png(self, user_h):
        r = _upload(user_h, b"\x89PNG\r\n\x1a\n" + b"0" * 100, "TEST_inv.png", "image/png")
        assert r.status_code == 200, r.text

    def test_upload_rejects_txt(self, user_h):
        r = _upload(user_h, b"hello", "TEST.txt", "text/plain")
        assert r.status_code == 400

    def test_upload_rejects_oversize(self, user_h):
        r = _upload(user_h, b"0" * (10 * 1024 * 1024 + 10))
        assert r.status_code in (400, 413)


# Submit + ownership + admin review
class TestBillFlow:
    def test_full_flow(self, user_h, other_h, admin_h):
        inv = _upload(user_h).json()["invoice_path"]
        qid = requests.post(f"{API}/bills/quote", headers=user_h, json={"category": "education", "payer_country": "NG",
                            "payout_currency": "GBP", "amount": 1500}, timeout=30).json()["id"]
        _b = globals()["_bill_body"]
        def _bill_body(p, **o):  # noqa: E306 — quote_id now required (iteration 41+)
            o.setdefault("quote_id", qid)
            return _b(p, **o)
        # declaration false
        r = requests.post(f"{API}/bills", headers=user_h, json=_bill_body(inv, declaration=False), timeout=30)
        assert r.status_code == 400
        # bad subtype
        r = requests.post(f"{API}/bills", headers=user_h, json=_bill_body(inv, subtype="Holiday"), timeout=30)
        assert r.status_code == 400
        # other user's invoice path
        r = requests.post(f"{API}/bills", headers=other_h, json=_bill_body(inv), timeout=30)
        assert r.status_code == 400
        # success x2 (approve + reject)
        ids = []
        for _ in range(2):
            r = requests.post(f"{API}/bills", headers=user_h, json=_bill_body(inv), timeout=30)
            assert r.status_code == 200, r.text
            b = r.json()
            assert b["status"] == "under_review" and len(b["timeline"]) == 2 and b["reference"].startswith("IBP-")
            assert "_id" not in b
            ids.append(b["id"]); CREATED_IDS.append(b["id"])
        # list/get own
        lst = requests.get(f"{API}/bills", headers=user_h, timeout=30).json()["bills"]
        assert ids[0] in [x["id"] for x in lst]
        g = requests.get(f"{API}/bills/{ids[0]}", headers=user_h, timeout=30)
        assert g.status_code == 200 and g.json()["institution"] == "TEST_ University of Leeds"
        assert requests.get(f"{API}/bills/{ids[0]}", headers=other_h, timeout=30).status_code == 404
        assert ids[0] not in [x["id"] for x in requests.get(f"{API}/bills", headers=other_h, timeout=30).json()["bills"]]
        # non-admin 403
        assert requests.get(f"{API}/admin/bills", headers=user_h, timeout=30).status_code == 403
        assert requests.post(f"{API}/admin/bills/{ids[0]}/decision", headers=user_h, json={"approve": True}, timeout=30).status_code == 403
        # admin list + invoice
        a = requests.get(f"{API}/admin/bills", headers=admin_h, timeout=30)
        assert a.status_code == 200 and ids[0] in [x["id"] for x in a.json()["bills"]]
        assert a.json()["pending"] >= 2
        f = requests.get(f"{API}/admin/bills/{ids[0]}/invoice", headers=admin_h, timeout=30)
        assert f.status_code == 200 and f.content.startswith(b"%PDF")
        # approve
        d = requests.post(f"{API}/admin/bills/{ids[0]}/decision", headers=admin_h, json={"approve": True}, timeout=30)
        assert d.status_code == 200 and d.json()["status"] == "paid"
        g = requests.get(f"{API}/bills/{ids[0]}", headers=user_h, timeout=30).json()
        assert g["status"] == "paid"
        assert [e["status"] for e in g["timeline"]][-3:] == ["approved", "processing", "paid"]
        # second decision 400
        assert requests.post(f"{API}/admin/bills/{ids[0]}/decision", headers=admin_h, json={"approve": False}, timeout=30).status_code == 400
        # reject
        d = requests.post(f"{API}/admin/bills/{ids[1]}/decision", headers=admin_h, json={"approve": False, "note": "TEST_"}, timeout=30)
        assert d.status_code == 200 and d.json()["status"] == "rejected"
        g = requests.get(f"{API}/bills/{ids[1]}", headers=user_h, timeout=30).json()
        assert g["status"] == "rejected" and g["timeline"][-1]["status"] == "rejected"
        # 404 on unknown
        assert requests.post(f"{API}/admin/bills/nope/decision", headers=admin_h, json={"approve": True}, timeout=30).status_code == 404
