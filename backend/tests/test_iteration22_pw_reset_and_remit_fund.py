"""Iteration 22 — Password reset flow + /remit/fund (Stripe fiat funding).

Covers:
- POST /api/auth/forgot-password (known + unknown email + rate limit)
- POST /api/auth/reset-password (bogus token + happy path + reuse)
- POST /api/remit/fund (happy path + sanctioned corridor + all 3 payment methods)
- /api/remit/send unchanged crypto path still callable (contract smoke)

Uses TestClient via conftest so we can also poke MongoDB directly to
verify nonce insertion / burning (Resend email is fire-and-forget and
not actually delivered).
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient

import server  # loaded via conftest sys.path fix


# ---------- helpers ---------------------------------------------------------
# Use a SYNCHRONOUS pymongo client for direct DB inspection — the async
# motor client inside server.py is bound to the TestClient's event loop
# and cannot be reused from pytest's main thread.
_sync_mongo = MongoClient(os.environ["MONGO_URL"])
_sync_db = _sync_mongo[os.environ["DB_NAME"]]


def _new_user(client: TestClient) -> dict:
    """Register a fresh throwaway user and return {email, password, token, id}."""
    email = f"TEST_pw_{uuid.uuid4().hex[:10]}@vaulted.app"
    password = "OldPass123!"
    r = client.post("/api/auth/register", json={
        "email": email,
        "password": password,
        "name": "TEST PW Reset User",
    })
    assert r.status_code == 200, r.text
    data = r.json()
    return {
        "email": email,
        "password": password,
        "token": data["access_token"],
        "id": data["user"]["id"],
    }


# ============================================================================
# 1. /auth/forgot-password contract
# ============================================================================
class TestForgotPassword:
    def test_known_email_returns_generic_and_writes_nonce(self, client):
        u = _new_user(client)
        email = u["email"]

        r = client.post("/api/auth/forgot-password", json={"email": email})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is True
        assert "reset link has been sent" in body.get("message", "").lower()

        # Verify a nonce was persisted in Mongo for this user
        row = _sync_db.password_resets.find_one({"email": email.lower(), "user_id": u["id"]})
        assert row is not None, "expected password_resets row for known email"
        assert row.get("nonce"), "expected nonce to be minted for known email"
        assert row.get("used_at") is None
        assert row.get("no_user") is not True

    def test_unknown_email_returns_same_generic_message(self, client):
        unknown = f"TEST_ghost_{uuid.uuid4().hex[:8]}@nowhere.example"
        r = client.post("/api/auth/forgot-password", json={"email": unknown})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is True
        assert "reset link has been sent" in body.get("message", "").lower()

        # Verify a "no_user" audit row was written (idempotent enumeration probe log)
        row = _sync_db.password_resets.find_one({"email": unknown.lower()})
        assert row is not None
        assert row.get("no_user") is True
        assert row.get("nonce") is None

    def test_rate_limit_caps_nonce_creation_to_3_per_hour(self, client):
        u = _new_user(client)
        email = u["email"]

        # Fire 5 requests in a row. All must return 200 with same body.
        for i in range(5):
            r = client.post("/api/auth/forgot-password", json={"email": email})
            assert r.status_code == 200, f"attempt #{i+1}: {r.status_code} {r.text}"
            assert r.json().get("ok") is True

        # Only 3 nonce rows should have been minted for this user.
        nonce_count = _sync_db.password_resets.count_documents({
            "user_id": u["id"],
            "nonce": {"$ne": None},
        })
        assert nonce_count <= server.PASSWORD_RESET_MAX_PER_HOUR, (
            f"expected ≤{server.PASSWORD_RESET_MAX_PER_HOUR} nonces after rate-limit, got {nonce_count}"
        )


# ============================================================================
# 2. /auth/reset-password contract
# ============================================================================
class TestResetPassword:
    def test_bogus_token_returns_400(self, client):
        r = client.post("/api/auth/reset-password", json={
            "token": "not-a-real-jwt.at.all",
            "new_password": "NewPass123!",
        })
        assert r.status_code == 400
        detail = r.json().get("detail", "").lower()
        assert "invalid" in detail

    def test_valid_token_resets_password_and_burns_nonce(self, client):
        u = _new_user(client)
        email = u["email"]
        new_password = "BrandNewPass456!"

        # Trigger forgot-password to create a nonce row
        r = client.post("/api/auth/forgot-password", json={"email": email})
        assert r.status_code == 200

        # Read the nonce from Mongo and mint the JWT ourselves (matches server behaviour)
        row = _sync_db.password_resets.find_one({"user_id": u["id"], "used_at": None})
        assert row is not None and row.get("nonce"), "expected active nonce"
        nonce = row["nonce"]

        payload = {
            "sub": u["id"],
            "purpose": "password_reset",
            "nonce": nonce,
            "exp": datetime.now(tz=timezone.utc) + timedelta(minutes=25),
        }
        token = jwt.encode(payload, server.JWT_SECRET, algorithm=server.JWT_ALG)

        # Reset succeeds
        r2 = client.post("/api/auth/reset-password", json={
            "token": token,
            "new_password": new_password,
        })
        assert r2.status_code == 200, r2.text
        assert r2.json().get("ok") is True

        # Old password no longer works
        r3 = client.post("/api/auth/login", json={"email": email, "password": u["password"]})
        assert r3.status_code == 401

        # New password works
        r4 = client.post("/api/auth/login", json={"email": email, "password": new_password})
        assert r4.status_code == 200, r4.text
        assert r4.json().get("access_token")

        # Nonce is burned in Mongo
        burned = _sync_db.password_resets.find_one({"user_id": u["id"], "nonce": nonce})
        assert burned is not None
        assert burned.get("used_at") is not None, "expected used_at to be set after reset"

        # Reusing the same token → 400
        r5 = client.post("/api/auth/reset-password", json={
            "token": token,
            "new_password": "YetAnotherPass789!",
        })
        assert r5.status_code == 400
        detail = r5.json().get("detail", "").lower()
        assert "already been used" in detail or "invalid" in detail

    def test_wrong_purpose_token_rejected(self, client):
        """Ordinary auth token (no purpose=password_reset claim) must be rejected."""
        u = _new_user(client)
        # Use the normal login token (no purpose claim)
        r = client.post("/api/auth/reset-password", json={
            "token": u["token"],
            "new_password": "SomeNewPass1!",
        })
        assert r.status_code == 400


# ============================================================================
# 3. /remit/fund — Stripe checkout for fiat funding
# ============================================================================
class TestRemitFund:
    def _auth(self, client):
        u = _new_user(client)
        return u, {"Authorization": f"Bearer {u['token']}"}

    def test_fund_happy_path_card(self, client):
        u, headers = self._auth(client)
        payload = {
            "source_fiat": "GBP",
            "amount": 50,
            "destination_code": "KE",
            "recipient_address": "GA7QYNF7SOWQ3GLR2BGMZEHXAVIRZA4KVWLTJJFC7MGXUA74P7UJUWDA",
            "recipient_name": "TEST Kenya Recipient",
            "payment_method": "card",
        }
        r = client.post("/api/remit/fund", json=payload, headers=headers)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("checkout_url", "").startswith("https://checkout.stripe.com/"), data
        assert data.get("session_id", "").startswith("cs_")
        assert data.get("charge_amount") is not None and float(data["charge_amount"]) > 0
        assert data.get("charge_currency") == "GBP"

    def test_fund_sanctioned_corridor_blocked_403(self, client):
        _u, headers = self._auth(client)
        payload = {
            "source_fiat": "GBP",
            "amount": 50,
            "destination_code": "KP",  # North Korea → sanctioned
            "recipient_address": "any-address-string",
            "payment_method": "card",
        }
        r = client.post("/api/remit/fund", json=payload, headers=headers)
        assert r.status_code == 403, r.text
        detail = r.json().get("detail")
        # Detail can be a dict or a plain string depending on FastAPI handling
        if isinstance(detail, dict):
            assert detail.get("error") == "corridor_blocked"
        else:
            assert "corridor" in str(detail).lower() or "cannot send" in str(detail).lower()

    @pytest.mark.parametrize("pm", [
        "apple_pay",
        pytest.param("bank", marks=pytest.mark.xfail(
            reason="BUG: Stripe returns 400 'A value is required for payment_method_options[customer_balance][funding_type]'. "
                   "_payment_method_types_for('bank') returns ['card','customer_balance'] but the Session.create call "
                   "does not set payment_method_options.customer_balance.funding_type (e.g. 'bank_transfer') nor "
                   "payment_method_types constraints for bank_transfer type. See /app/backend/server.py:1977 and 2073.",
            strict=True,
        )),
    ])
    def test_fund_apple_pay_and_bank_succeed(self, client, pm):
        _u, headers = self._auth(client)
        payload = {
            "source_fiat": "GBP",
            "amount": 40,
            "destination_code": "KE",
            "recipient_address": "GA7QYNF7SOWQ3GLR2BGMZEHXAVIRZA4KVWLTJJFC7MGXUA74P7UJUWDA",
            "payment_method": pm,
        }
        r = client.post("/api/remit/fund", json=payload, headers=headers)
        assert r.status_code == 200, f"pm={pm}: {r.text}"
        data = r.json()
        assert data.get("checkout_url", "").startswith("https://checkout.stripe.com/")
        assert data.get("payment_method") == pm

    def test_fund_requires_auth(self, client):
        r = client.post("/api/remit/fund", json={
            "source_fiat": "GBP", "amount": 50, "destination_code": "KE",
            "recipient_address": "x", "payment_method": "card",
        })
        assert r.status_code in (401, 403)


# ============================================================================
# 4. /remit/send crypto path — regression contract only
# ============================================================================
class TestRemitSendUnchanged:
    def test_remit_send_endpoint_still_exists(self, client):
        """Fresh users have no XLM balance, so we expect either a
        pre-flight balance error (400) or KYC gate (403) — never a 404 /
        500. This ensures the endpoint contract is unchanged."""
        u = _new_user(client)
        headers = {"Authorization": f"Bearer {u['token']}"}
        r = client.post("/api/remit/send", json={
            "source_fiat": "GBP",
            "amount": 50,
            "destination_code": "KE",
            "recipient_address": "GA7QYNF7SOWQ3GLR2BGMZEHXAVIRZA4KVWLTJJFC7MGXUA74P7UJUWDA",
        }, headers=headers)
        assert r.status_code not in (404, 500), r.text
