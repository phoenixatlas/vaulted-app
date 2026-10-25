"""Iteration 31 — retest of iteration 30 backend fixes:
NG fund server-side name re-check, screenshot short-lived token, account deletion cleanup.
No feedback submissions (they email admins)."""
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
HELPER = "/app/backend/tests/iter31_helper.py"


def _token(resp):
    d = resp.json()
    return d.get("access_token") or d.get("token")


def _helper(*args):
    out = subprocess.run(["python", HELPER, *args], capture_output=True, text=True, cwd="/app/backend", timeout=90)
    assert out.returncode == 0, out.stderr[-2000:]
    return json.loads(out.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def smoke_headers():
    r = requests.post(f"{API}/auth/login", json=SMOKE, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"smoketest login failed {r.status_code}")
    return {"Authorization": f"Bearer {_token(r)}"}


# ---- Remit fund NG: server re-checks account name ----
class TestFundNgRecheck:
    def test_unresolvable_account_400(self, smoke_headers):
        r = requests.post(f"{API}/remit/fund", json={
            "source_fiat": "GBP", "amount": 20, "destination_code": "NG",
            "recipient_address": "0000123456", "recipient_name": "TEST", "payment_method": "card",
            "recipient_bank_id": "ng_058", "recipient_verified": True},
            headers=smoke_headers, timeout=30)
        assert r.status_code == 400, r.text
        assert "couldn't confirm that Nigerian bank account" in r.text


# ---- Admin screenshot: short-lived per-screenshot token only ----
class TestScreenshotToken:
    def test_no_token_401(self):
        r = requests.get(f"{API}/admin/feedback/nonexistent/screenshot", timeout=30)
        assert r.status_code == 401

    def test_login_token_403(self, smoke_headers):
        tok = smoke_headers["Authorization"].split(" ", 1)[1]
        r = requests.get(f"{API}/admin/feedback/nonexistent/screenshot", params={"t": tok}, timeout=30)
        assert r.status_code == 403

    def test_garbage_token_401(self):
        r = requests.get(f"{API}/admin/feedback/nonexistent/screenshot", params={"t": "abc.def.ghi"}, timeout=30)
        assert r.status_code == 401

    def test_token_for_other_id_403(self):
        t = _helper("shot_token", "other-id")["t"]
        r = requests.get(f"{API}/admin/feedback/nonexistent/screenshot", params={"t": t}, timeout=30)
        assert r.status_code == 403

    def test_valid_scoped_token_passes_auth(self):
        t = _helper("shot_token", "nonexistent")["t"]
        r = requests.get(f"{API}/admin/feedback/nonexistent/screenshot", params={"t": t}, timeout=30)
        assert r.status_code == 404  # auth passed, no such feedback


# ---- Account deletion also removes recipients + feedback ----
class TestDeleteAccountCleanup:
    def test_delete_removes_recipients_and_feedback(self):
        email = f"test_iter31_{uuid.uuid4().hex[:8]}@example.com"
        pw = "Test12345!"
        r = requests.post(f"{API}/auth/register", json={"email": email, "password": pw, "name": "TEST Iter31"}, timeout=30)
        assert r.status_code in (200, 201), r.text
        h = {"Authorization": f"Bearer {_token(r)}"}
        me = requests.get(f"{API}/auth/me", headers=h, timeout=30).json()
        uid = (me.get("user") or me)["id"]
        _helper("seed_rec_fb", uid)
        before = _helper("count", uid)
        assert before["recipients"] == 1 and before["feedback"] == 1
        lr = requests.get(f"{API}/recipients?country=KE", headers=h, timeout=30)
        assert lr.status_code == 200 and len(lr.json()["recipients"]) == 1
        d = requests.post(f"{API}/auth/delete-account", json={"password": pw}, headers=h, timeout=30)
        assert d.status_code == 200, d.text
        after = _helper("count", uid)
        assert after == {"recipients": 0, "feedback": 0}
        lg = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=30)
        assert lg.status_code in (400, 401, 404)
