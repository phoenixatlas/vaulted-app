# Iteration 38: Partner enquiry (public) + Admin Partner Leads inbox API tests
import os
import sys
import time
import uuid
import asyncio
import pathlib

import pytest
import requests
from dotenv import load_dotenv

BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
load_dotenv(BACKEND_DIR / ".env")
load_dotenv("/app/frontend/.env")

BASE_URL = (os.environ.get("EXPO_BACKEND_URL") or os.environ.get("EXPO_PUBLIC_BACKEND_URL")).rstrip("/")
API = f"{BASE_URL}/api"

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from deps import make_token  # noqa: E402


def _db_call(coro_fn):
    async def run():
        c = AsyncIOMotorClient(os.environ["MONGO_URL"])
        try:
            return await coro_fn(c[os.environ["DB_NAME"]])
        finally:
            c.close()
    return asyncio.new_event_loop().run_until_complete(run())


def _ip():
    return f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}"


def _body(**kw):
    b = {"name": "TEST_ Partner Person", "email": f"test_iter38_{uuid.uuid4().hex[:6]}@example.com",
         "company": f"TEST_Co_{uuid.uuid4().hex[:4]}", "partner_type": "psp_emi",
         "corridor": "UK → Kenya", "message": "TEST_ hello"}
    b.update(kw)
    return b


@pytest.fixture(scope="module")
def admin_headers():
    u = _db_call(lambda db: db.users.find_one({"email": "umar.sani@phoenix-atlas.com"}, {"_id": 0, "id": 1}))
    if not u:
        pytest.skip("admin user missing")
    return {"Authorization": f"Bearer {make_token(u['id'])}"}


@pytest.fixture(scope="module")
def smoke_headers():
    r = requests.post(f"{API}/auth/login", json={"email": "smoketest@vaulted.app", "password": "test1234"})
    if r.status_code != 200:
        pytest.skip(f"smoketest login failed {r.status_code}")
    tok = r.json().get("token") or r.json().get("access_token")
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    _db_call(lambda db: db.partner_enquiries.delete_many({"email": {"$regex": r"(example\.com|resend\.dev)$"}}))


# --- Public enquiry endpoint ---
class TestEnquiry:
    created = {}

    def test_valid_enquiry_stored_new(self):
        b = _body(email="delivered+iter38@resend.dev")
        r = requests.post(f"{API}/partners/enquiry", json=b, headers={"X-Forwarded-For": _ip()}, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True and isinstance(d["id"], str)
        doc = _db_call(lambda db: db.partner_enquiries.find_one({"id": d["id"]}, {"_id": 0}))
        assert doc and doc["status"] == "new" and doc["company"] == b["company"]
        assert doc["email"] == b["email"].lower() and doc["partner_type"] == "psp_emi"
        TestEnquiry.created["id"] = d["id"]

    def test_bad_email_422(self):
        r = requests.post(f"{API}/partners/enquiry", json=_body(email="not-an-email"), headers={"X-Forwarded-For": _ip()})
        assert r.status_code == 422

    def test_missing_company_422(self):
        b = _body(); b["company"] = ""
        r = requests.post(f"{API}/partners/enquiry", json=b, headers={"X-Forwarded-For": _ip()})
        assert r.status_code == 422

    def test_honeypot_not_stored(self):
        b = _body(website="http://spam.example.com")
        r = requests.post(f"{API}/partners/enquiry", json=b, headers={"X-Forwarded-For": _ip()})
        assert r.status_code == 200 and r.json().get("ok") is True and "id" not in r.json()
        n = _db_call(lambda db: db.partner_enquiries.count_documents({"company": b["company"]}))
        assert n == 0

    def test_unknown_partner_type_coerced(self):
        b = _body(partner_type="hacker")
        r = requests.post(f"{API}/partners/enquiry", json=b, headers={"X-Forwarded-For": _ip()}, timeout=60)
        assert r.status_code == 200
        doc = _db_call(lambda db: db.partner_enquiries.find_one({"id": r.json()["id"]}, {"_id": 0}))
        assert doc["partner_type"] == "other"

    def test_throttle_429_same_ip(self):
        ip = _ip()
        r1 = requests.post(f"{API}/partners/enquiry", json=_body(), headers={"X-Forwarded-For": ip}, timeout=60)
        assert r1.status_code == 200
        r2 = requests.post(f"{API}/partners/enquiry", json=_body(), headers={"X-Forwarded-For": ip}, timeout=60)
        assert r2.status_code == 429


# --- Admin inbox endpoints ---
class TestAdmin:
    def test_unauth_401(self):
        assert requests.get(f"{API}/admin/partners").status_code in (401, 403)

    def test_non_admin_403(self, smoke_headers):
        r = requests.get(f"{API}/admin/partners", headers=smoke_headers)
        assert r.status_code == 403
        r = requests.patch(f"{API}/admin/partners/x", json={"status": "closed"}, headers=smoke_headers)
        assert r.status_code == 403

    def test_list_sorted_with_counts(self, admin_headers):
        time.sleep(1)
        b = _body(company="TEST_Newest_Co")
        r = requests.post(f"{API}/partners/enquiry", json=b, headers={"X-Forwarded-For": _ip()}, timeout=60)
        assert r.status_code == 200
        new_id = r.json()["id"]
        r = requests.get(f"{API}/admin/partners", headers=admin_headers)
        assert r.status_code == 200
        d = r.json()
        assert d["enquiries"][0]["id"] == new_id
        dates = [e["created_at"] for e in d["enquiries"]]
        assert dates == sorted(dates, reverse=True)
        assert set(d["counts"]) == {"new", "contacted", "closed"}
        assert d["total"] == len(d["enquiries"])
        assert all("_id" not in e for e in d["enquiries"])

    def test_patch_status_and_persist(self, admin_headers):
        lid = TestEnquiry.created.get("id")
        if not lid:
            pytest.skip("no lead")
        for st in ("contacted", "closed", "new"):
            r = requests.patch(f"{API}/admin/partners/{lid}", json={"status": st}, headers=admin_headers)
            assert r.status_code == 200 and r.json() == {"id": lid, "status": st}
            lst = requests.get(f"{API}/admin/partners", headers=admin_headers).json()["enquiries"]
            assert next(e for e in lst if e["id"] == lid)["status"] == st

    def test_patch_invalid_status_422(self, admin_headers):
        lid = TestEnquiry.created.get("id") or "x"
        r = requests.patch(f"{API}/admin/partners/{lid}", json={"status": "archived"}, headers=admin_headers)
        assert r.status_code == 422

    def test_patch_unknown_404(self, admin_headers):
        r = requests.patch(f"{API}/admin/partners/{uuid.uuid4()}", json={"status": "closed"}, headers=admin_headers)
        assert r.status_code == 404
