"""Iteration 30 — NG bank lookup (Yellow Card mock), saved recipients,
remit/fund NG guard + stripe apply path, tester feedback. Public URL."""
import base64
import json
import os
import subprocess
import uuid

import pytest
import requests
from dotenv import dotenv_values

_FE_ENV = dotenv_values("/app/frontend/.env")
BASE_URL = (os.environ.get("EXPO_BACKEND_URL") or os.environ.get("EXPO_PUBLIC_BACKEND_URL")
            or _FE_ENV.get("EXPO_BACKEND_URL") or _FE_ENV.get("EXPO_PUBLIC_BACKEND_URL")).rstrip("/")
API = f"{BASE_URL}/api"
SMOKE = {"email": "smoketest@vaulted.app", "password": "test1234"}
HELPER = "/app/backend/tests/iter30_helper.py"
PNG_1x1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")


def _token(resp):
    d = resp.json()
    return d.get("access_token") or d.get("token")


def _helper(*args):
    out = subprocess.run(["python", HELPER, *args], capture_output=True, text=True, cwd="/app/backend", timeout=90)
    assert out.returncode == 0, out.stderr[-2000:]
    return json.loads(out.stdout.strip().splitlines()[-1])


def _me(h):
    r = requests.get(f"{API}/auth/me", headers=h, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    return (d.get("user") or d)["id"]


@pytest.fixture(scope="module")
def smoke_headers():
    r = requests.post(f"{API}/auth/login", json=SMOKE, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"smoketest login failed {r.status_code}")
    return {"Authorization": f"Bearer {_token(r)}"}


@pytest.fixture(scope="module")
def other_user():
    """Throwaway TEST_ user; deleted at teardown."""
    email = f"test_iter30_{uuid.uuid4().hex[:8]}@example.com"
    pw = "Test12345!"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": pw, "name": "TEST Iter30"}, timeout=30)
    assert r.status_code in (200, 201), r.text
    h = {"Authorization": f"Bearer {_token(r)}"}
    uid = _me(h)
    yield {"headers": h, "id": uid, "password": pw}
    _helper("cleanup", uid)
    requests.post(f"{API}/auth/delete-account", json={"password": pw}, headers=h, timeout=30)


# ---- Payout banks (NG) ----
class TestBanks:
    def test_banks_ng(self, smoke_headers):
        r = requests.get(f"{API}/payouts/banks", params={"country": "NG"}, headers=smoke_headers, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["mode"] == "mock"
        assert len(d["banks"]) == 20
        ids = [b["id"] for b in d["banks"]]
        assert "ng_058" in ids
        assert all(i.startswith("ng_") for i in ids)
        assert any("GT" in (b["name"] or "") for b in d["banks"])

    def test_banks_ke_400(self, smoke_headers):
        r = requests.get(f"{API}/payouts/banks", params={"country": "KE"}, headers=smoke_headers, timeout=30)
        assert r.status_code == 400

    def test_banks_requires_auth(self):
        r = requests.get(f"{API}/payouts/banks", params={"country": "NG"}, timeout=30)
        assert r.status_code in (401, 403)


# ---- Account name resolve ----
class TestResolve:
    def test_resolve_ok(self, smoke_headers):
        r = requests.post(f"{API}/payouts/resolve-account", json={"account_number": "0123456789", "bank_id": "ng_058"},
                          headers=smoke_headers, timeout=30)
        assert r.status_code == 200
        assert r.json() == {"account_name": "TEST ACCOUNT HOLDER", "mode": "mock"}

    def test_resolve_not_found(self, smoke_headers):
        r = requests.post(f"{API}/payouts/resolve-account", json={"account_number": "0000123456", "bank_id": "ng_058"},
                          headers=smoke_headers, timeout=30)
        assert r.status_code == 404

    @pytest.mark.parametrize("acct", ["012345678", "01234567ab", "01234567890"])
    def test_resolve_invalid_422(self, smoke_headers, acct):
        r = requests.post(f"{API}/payouts/resolve-account", json={"account_number": acct, "bank_id": "ng_058"},
                          headers=smoke_headers, timeout=30)
        assert r.status_code == 422


# ---- Saved recipients ----
class TestRecipients:
    def test_save_upsert_filter_delete(self, other_user, smoke_headers):
        h = other_user["headers"]
        rows = _helper("save_twice", other_user["id"])
        ng = [x for x in rows if x["country_code"] == "NG"]
        assert len(ng) == 1 and ng[0]["send_count"] == 2
        assert ng[0]["bank_id"] == "ng_058" and ng[0]["verified"] is True

        r = requests.get(f"{API}/recipients", headers=h, timeout=30)
        assert r.status_code == 200
        lst = r.json()["recipients"]
        assert len(lst) == 2 and all("_id" not in x and "user_id" not in x for x in lst)

        r = requests.get(f"{API}/recipients", params={"country": "ng"}, headers=h, timeout=30)
        assert [x["country_code"] for x in r.json()["recipients"]] == ["NG"]

        rid = ng[0]["id"]
        # other user's id -> 404
        r = requests.delete(f"{API}/recipients/{rid}", headers=smoke_headers, timeout=30)
        assert r.status_code == 404
        r = requests.delete(f"{API}/recipients/{rid}", headers=h, timeout=30)
        assert r.status_code == 200 and r.json() == {"ok": True}
        r = requests.get(f"{API}/recipients", params={"country": "NG"}, headers=h, timeout=30)
        assert r.json()["recipients"] == []

    def test_recipients_requires_auth(self):
        assert requests.get(f"{API}/recipients", timeout=30).status_code in (401, 403)


# ---- Remit fund NG guard + stripe apply path ----
class TestRemitFundNG:
    def test_fund_ng_without_bank_400(self, smoke_headers):
        r = requests.post(f"{API}/remit/fund", json={
            "source_fiat": "GBP", "amount": 20, "destination_code": "NG",
            "recipient_address": "0123456789", "recipient_name": "TEST", "payment_method": "card"},
            headers=smoke_headers, timeout=30)
        assert r.status_code == 400, r.text
        assert "Choose the recipient's bank" in r.text

    def test_stripe_apply_stores_bank_and_saves(self, other_user):
        res = _helper("apply_ng", other_user["id"], f"cs_test_TESTiter30_{uuid.uuid4().hex[:10]}")
        assert res["applied"] is True
        assert res["recipient_bank"] == {"id": "ng_058", "name": "GTBank"}
        rec = res["recipient"]
        assert rec and rec["rail"] == "bank" and rec["account"] == "0123456789"
        assert rec["bank_name"] == "GTBank" and rec["verified"] is True


# ---- Tester feedback ----
class TestFeedback:
    def test_feedback_with_screenshot(self, smoke_headers):
        r = requests.post(f"{API}/feedback", headers=smoke_headers, timeout=60,
                          data={"note": "TEST_iter30 automated note with screenshot", "screen": "/remit",
                                "platform": "pytest", "app_version": "test"},
                          files={"screenshot": ("shot.png", PNG_1x1, "image/png")})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True and d["screenshot_saved"] is True
        pytest.fb_id = d["id"]

    def test_feedback_note_only(self, smoke_headers):
        r = requests.post(f"{API}/feedback", headers=smoke_headers, timeout=60,
                          data={"note": "TEST_iter30 note only", "screen": "/home", "platform": "pytest"})
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True and r.json()["screenshot_saved"] is False

    def test_feedback_empty_note_422(self, smoke_headers):
        r = requests.post(f"{API}/feedback", headers=smoke_headers, data={"note": ""}, timeout=30)
        assert r.status_code == 422

    def test_feedback_requires_auth(self):
        r = requests.post(f"{API}/feedback", data={"note": "x"}, timeout=30)
        assert r.status_code in (401, 403)

    def test_admin_feedback_403(self, smoke_headers):
        r = requests.get(f"{API}/admin/feedback", headers=smoke_headers, timeout=30)
        assert r.status_code == 403

    def test_screenshot_no_token_401(self):
        fid = getattr(pytest, "fb_id", "nonexistent")
        r = requests.get(f"{API}/admin/feedback/{fid}/screenshot", timeout=30)
        assert r.status_code == 401

    def test_screenshot_login_token_rejected(self, smoke_headers):
        # Screenshot links only accept the short-lived per-screenshot token
        # issued by /admin/feedback — a normal login token must not work.
        fid = getattr(pytest, "fb_id", "nonexistent")
        tok = smoke_headers["Authorization"].split(" ", 1)[1]
        r = requests.get(f"{API}/admin/feedback/{fid}/screenshot", params={"t": tok}, timeout=30)
        assert r.status_code == 403
