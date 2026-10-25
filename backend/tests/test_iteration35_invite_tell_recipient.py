# Iteration 35: beta invite code gate on register + admin invite endpoints + share for tell-recipient
import os
import uuid
import pytest
import requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
mdb = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


@pytest.fixture(scope="module")
def s():
    x = requests.Session()
    x.headers.update({"Content-Type": "application/json"})
    return x


@pytest.fixture(scope="module")
def smoke_token(s):
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": "smoketest@vaulted.app", "password": "test1234"})
    if r.status_code != 200:
        pytest.skip("smoketest login failed")
    return r.json()["access_token"]


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    mdb.users.delete_many({"email": {"$regex": "^test_iter35"}})


def _email():
    return f"test_iter35_{uuid.uuid4().hex[:8]}@example.com"


# Invite gate
class TestInviteGate:
    def test_invite_required(self, s):
        r = s.get(f"{BASE_URL}/api/auth/invite-required")
        assert r.status_code == 200 and r.json() == {"required": True}

    def test_register_no_code_403(self, s):
        r = s.post(f"{BASE_URL}/api/auth/register", json={"email": _email(), "password": "test1234", "name": "T"})
        assert r.status_code == 403
        assert "invite code" in r.json()["detail"].lower()

    def test_register_wrong_code_403(self, s):
        r = s.post(f"{BASE_URL}/api/auth/register",
                   json={"email": _email(), "password": "test1234", "name": "T", "invite_code": "NOPE-123"})
        assert r.status_code == 403

    def test_register_existing_email_wrong_code_403_not_400(self, s):
        # Gate runs before email check -> no enumeration
        r = s.post(f"{BASE_URL}/api/auth/register",
                   json={"email": "smoketest@vaulted.app", "password": "x12345678", "name": "T", "invite_code": "bad"})
        assert r.status_code == 403

    def test_register_lowercase_code_ok(self, s):
        em = _email()
        r = s.post(f"{BASE_URL}/api/auth/register",
                   json={"email": em, "password": "test1234", "name": "Iter35 User", "invite_code": " vaulted-beta "})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["access_token"] and d["user"]["email"] == em
        doc = mdb.users.find_one({"email": em})
        assert doc["invited_with"] == "VAULTED-BETA"
        # new user can log in
        r2 = s.post(f"{BASE_URL}/api/auth/login", json={"email": em, "password": "test1234"})
        assert r2.status_code == 200

    def test_existing_login_unaffected(self, s):
        r = s.post(f"{BASE_URL}/api/auth/login", json={"email": "smoketest@vaulted.app", "password": "test1234"})
        assert r.status_code == 200 and r.json()["user"]["email"] == "smoketest@vaulted.app"


# Admin invite endpoints — non-admin blocked
class TestAdminInvite:
    def test_get_no_auth(self, s):
        r = requests.get(f"{BASE_URL}/api/admin/invite")
        assert r.status_code in (401, 403)

    def test_put_no_auth(self, s):
        r = requests.put(f"{BASE_URL}/api/admin/invite", json={"enabled": False})
        assert r.status_code in (401, 403)

    def test_get_non_admin_403(self, s, smoke_token):
        r = s.get(f"{BASE_URL}/api/admin/invite", headers={"Authorization": f"Bearer {smoke_token}"})
        assert r.status_code == 403

    def test_put_non_admin_403_and_unchanged(self, s, smoke_token):
        r = s.put(f"{BASE_URL}/api/admin/invite", json={"enabled": False, "code": "HACKED"},
                  headers={"Authorization": f"Bearer {smoke_token}"})
        assert r.status_code == 403
        assert s.get(f"{BASE_URL}/api/auth/invite-required").json()["required"] is True
