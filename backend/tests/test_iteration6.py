"""Iteration 6 backend tests: biometric_enabled toggle + regression.

Focus:
  - PATCH /api/auth/security accepts biometric_enabled (true/false) and
    returns updated user with the flag reflected.
  - GET /api/auth/me includes biometric_enabled.
  - Existing critical endpoints still work (regression):
    /auth/login, /wallet/assets, /cosigners, /approvals/pending.
  - RESEND_FROM env-driven sender path: backend doesn't crash on cosigner
    add (which triggers email send). Resend 403 is tolerated.
"""
import os
import uuid
import pytest
import requests
from pathlib import Path

# Read public URL from frontend/.env
BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    env_path = Path("/app/frontend/.env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("EXPO_PUBLIC_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().strip('"').rstrip("/")
                break
assert BASE_URL, "BASE_URL must be configured"
API = f"{BASE_URL}/api"

# Mongo (for promoting test user to Pro for the cosigner+resend check)
try:
    from pymongo import MongoClient
    MONGO_URL = os.environ.get("MONGO_URL", "")
    DB_NAME = os.environ.get("DB_NAME", "")
    benv = Path("/app/backend/.env")
    if benv.exists():
        for line in benv.read_text().splitlines():
            if line.startswith("MONGO_URL=") and not MONGO_URL:
                MONGO_URL = line.split("=", 1)[1].strip().strip('"')
            if line.startswith("DB_NAME=") and not DB_NAME:
                DB_NAME = line.split("=", 1)[1].strip().strip('"')
    mongo = MongoClient(MONGO_URL) if MONGO_URL else None
    db = mongo[DB_NAME] if mongo and DB_NAME else None
except Exception:
    db = None


def H(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _register():
    email = f"it6_{uuid.uuid4().hex[:8]}@vaulted.app"
    r = requests.post(
        f"{API}/auth/register",
        json={"email": email, "password": "test1234", "name": "Iter6 Tester"},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    j = r.json()
    return j["access_token"], j["user"], email


@pytest.fixture(scope="module")
def user_ctx():
    tok, u, em = _register()
    return {"token": tok, "user": u, "email": em}


# ----- biometric_enabled toggle -----
class TestBiometricFlag:
    def test_me_returns_biometric_enabled_field(self, user_ctx):
        r = requests.get(f"{API}/auth/me", headers=H(user_ctx["token"]))
        assert r.status_code == 200, r.text
        d = r.json()
        assert "biometric_enabled" in d, f"missing biometric_enabled in /auth/me: {d}"
        # Default for a fresh user should be False
        assert d["biometric_enabled"] is False

    def test_patch_security_enable_biometric(self, user_ctx):
        r = requests.patch(
            f"{API}/auth/security",
            headers=H(user_ctx["token"]),
            json={"biometric_enabled": True},
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("biometric_enabled") is True, d
        # Verify persistence via /auth/me
        me = requests.get(f"{API}/auth/me", headers=H(user_ctx["token"])).json()
        assert me["biometric_enabled"] is True

    def test_patch_security_disable_biometric(self, user_ctx):
        r = requests.patch(
            f"{API}/auth/security",
            headers=H(user_ctx["token"]),
            json={"biometric_enabled": False},
        )
        assert r.status_code == 200, r.text
        assert r.json().get("biometric_enabled") is False
        me = requests.get(f"{API}/auth/me", headers=H(user_ctx["token"])).json()
        assert me["biometric_enabled"] is False

    def test_patch_security_requires_auth(self):
        r = requests.patch(f"{API}/auth/security", json={"biometric_enabled": True})
        assert r.status_code == 401

    def test_patch_security_coerces_truthy_values(self, user_ctx):
        # Backend uses bool(body[...]) so non-bool truthy still works
        r = requests.patch(
            f"{API}/auth/security",
            headers=H(user_ctx["token"]),
            json={"biometric_enabled": 1},
        )
        assert r.status_code == 200
        assert r.json()["biometric_enabled"] is True
        # cleanup
        requests.patch(
            f"{API}/auth/security",
            headers=H(user_ctx["token"]),
            json={"biometric_enabled": False},
        )


# ----- Regression on critical flows -----
class TestRegression:
    def test_login_smoketest_account(self):
        r = requests.post(
            f"{API}/auth/login",
            json={"email": "smoketest@vaulted.app", "password": "test1234"},
            timeout=30,
        )
        # Account may not exist in this environment (it's seeded at build time).
        # If it 401s, fall back to verifying the fresh-register account login.
        if r.status_code == 200:
            j = r.json()
            assert "access_token" in j and "user" in j
            assert "biometric_enabled" in j["user"]
        else:
            pytest.skip(
                f"smoketest@vaulted.app login returned {r.status_code} — likely not seeded. "
                "Register-path login is tested implicitly elsewhere."
            )

    def test_login_with_freshly_registered_user(self, user_ctx):
        # Use the user_ctx email; password test1234
        r = requests.post(
            f"{API}/auth/login",
            json={"email": user_ctx["email"], "password": "test1234"},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        j = r.json()
        assert "access_token" in j
        assert j["user"]["email"] == user_ctx["email"]
        assert "biometric_enabled" in j["user"]

    def test_wallet_assets(self, user_ctx):
        r = requests.get(f"{API}/wallet/assets", headers=H(user_ctx["token"]))
        assert r.status_code == 200, r.text
        d = r.json()
        # tolerate either shape
        assets = d.get("assets") if isinstance(d, dict) else d
        assert assets is not None
        assert isinstance(assets, list) and len(assets) > 0

    def test_cosigners_empty_for_fresh_user(self, user_ctx):
        r = requests.get(f"{API}/cosigners", headers=H(user_ctx["token"]))
        assert r.status_code == 200
        assert r.json() == []

    def test_approvals_pending_empty(self, user_ctx):
        r = requests.get(f"{API}/approvals/pending", headers=H(user_ctx["token"]))
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ----- RESEND_FROM env-driven sender (cosigner add triggers Resend) -----
class TestResendFromEnv:
    def test_cosigner_add_does_not_crash_backend(self, user_ctx):
        """Add a cosigner as a Pro user — backend uses RESEND_FROM. Should
        return 200 (cosigner persisted) even if Resend 403s the email."""
        if db is None:
            pytest.skip("mongo not reachable")

        # Promote the existing user to Pro
        db.users.update_one(
            {"id": user_ctx["user"]["id"]},
            {"$set": {
                "subscription": {"status": "active", "plan": "vault_pro"},
                "multisig_enabled": True,
            }},
        )
        r = requests.post(
            f"{API}/cosigners",
            headers=H(user_ctx["token"]),
            json={"email": f"resendtest_{uuid.uuid4().hex[:6]}@example.com",
                  "label": "ResendFrom"},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        # core shape sanity
        for k in ("id", "email", "label", "status"):
            assert k in d
        assert d["status"] == "active"
        # cleanup
        try:
            requests.delete(
                f"{API}/cosigners/{d['id']}", headers=H(user_ctx["token"])
            )
        except Exception:
            pass
