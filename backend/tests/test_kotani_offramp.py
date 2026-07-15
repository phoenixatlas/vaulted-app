"""Kotani Pay v3 M-Pesa off-ramp — backend acceptance tests (MOCK mode).

Covers:
- /api/offramp/mpesa/quote (auth, validation, unauth)
- /api/offramp/mpesa/status/{ref} (404 for unknown, auth)
- /api/offramp/health (admin gate)
- /api/offramp/callback (garbage body, unknown ref, SUCCESS/FAILED matched
  against seeded db.transactions)
- /api/remit/fund contract for KE destination (Stripe checkout URL only)
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ["EXPO_BACKEND_URL"].rstrip("/") if os.environ.get("EXPO_BACKEND_URL") else \
           "https://multi-sig-vault.preview.emergentagent.com"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

SMOKE_EMAIL = "smoketest@vaulted.app"
SMOKE_PW = "test1234"


# ---------- Fixtures --------------------------------------------------------
@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def smoke_token(api):
    r = api.post(f"{BASE_URL}/api/auth/login", json={"email": SMOKE_EMAIL, "password": SMOKE_PW})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    body = r.json()
    return body["access_token"], body["user"]


@pytest.fixture(scope="module")
def auth_headers(smoke_token):
    token, _ = smoke_token
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def smoke_user(smoke_token):
    _, user = smoke_token
    return user


@pytest.fixture(scope="module")
def mongo():
    client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=3000)
    db = client[DB_NAME]
    yield db
    # cleanup TEST-created tx
    db.transactions.delete_many({"id": {"$regex": "^TEST_kotani_"}})
    client.close()


def _iso(dt: datetime | None = None) -> str:
    return (dt or datetime.now(tz=timezone.utc)).isoformat()


def _seed_tx(db, user_id: str, ref: str, status: str = "processing") -> str:
    tx_id = f"TEST_kotani_{uuid.uuid4().hex[:12]}"
    db.transactions.insert_one({
        "id": tx_id,
        "user_id": user_id,
        "type": "send",
        "status": status,
        "kind": "remit_fund",
        "asset": "GBP",
        "amount": 50.0,
        "created_at": _iso(),
        "kotani": {
            "reference_id": ref,
            "status": "PENDING",
            "mode": "mock",
        },
        "remit": {
            "destination_country_code": "KE",
            "recipient_address": "+254712345678",
            "recipient_name": "Njeri Mwangi",
            "source_fiat": "GBP",
        },
    })
    return tx_id


# ---------- Quote endpoint --------------------------------------------------
class TestOfframpQuote:
    def test_quote_success(self, api, auth_headers):
        r = api.post(f"{BASE_URL}/api/offramp/mpesa/quote",
                     json={"amount_usd": 65.0, "to_currency": "KES"},
                     headers=auth_headers)
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert body.get("mode") == "mock", f"mode={body.get('mode')}"
        kot = body.get("kotani") or {}
        assert kot.get("success") is True
        data = kot.get("data") or {}
        to_amount = float(data.get("toAmount"))
        expected = 65 * 143.5
        # within ±30%
        assert 0.7 * expected <= to_amount <= 1.3 * expected, \
            f"toAmount {to_amount} outside ±30% of {expected}"

    def test_quote_unauthenticated(self, api):
        r = api.post(f"{BASE_URL}/api/offramp/mpesa/quote",
                     json={"amount_usd": 65.0, "to_currency": "KES"})
        assert r.status_code in (401, 403), r.status_code

    def test_quote_zero_amount_rejected(self, api, auth_headers):
        r = api.post(f"{BASE_URL}/api/offramp/mpesa/quote",
                     json={"amount_usd": 0, "to_currency": "KES"},
                     headers=auth_headers)
        assert r.status_code == 422, r.text[:200]

    def test_quote_negative_amount_rejected(self, api, auth_headers):
        r = api.post(f"{BASE_URL}/api/offramp/mpesa/quote",
                     json={"amount_usd": -5, "to_currency": "KES"},
                     headers=auth_headers)
        assert r.status_code == 422


# ---------- Status endpoint -------------------------------------------------
class TestOfframpStatus:
    def test_status_unknown_ref_404(self, api, auth_headers):
        r = api.get(f"{BASE_URL}/api/offramp/mpesa/status/kp_mock_does_not_exist_xyz",
                    headers=auth_headers)
        assert r.status_code == 404, r.text[:200]

    def test_status_unauth(self, api):
        r = api.get(f"{BASE_URL}/api/offramp/mpesa/status/kp_mock_whatever")
        assert r.status_code in (401, 403)

    def test_status_owner_can_read(self, api, auth_headers, smoke_user, mongo):
        ref = f"kp_mock_status_owner_{uuid.uuid4().hex[:8]}"
        tx_id = _seed_tx(mongo, smoke_user["id"], ref)
        try:
            r = api.get(f"{BASE_URL}/api/offramp/mpesa/status/{ref}", headers=auth_headers)
            assert r.status_code == 200, r.text[:300]
            body = r.json()
            assert body.get("tx", {}).get("id") == tx_id
            assert body.get("kotani", {}).get("success") is True
        finally:
            mongo.transactions.delete_one({"id": tx_id})


# ---------- Health (admin) --------------------------------------------------
class TestOfframpHealth:
    def test_health_non_admin_forbidden(self, api, auth_headers):
        r = api.get(f"{BASE_URL}/api/offramp/health", headers=auth_headers)
        assert r.status_code == 403, r.text[:200]

    def test_health_unauth(self, api):
        r = api.get(f"{BASE_URL}/api/offramp/health")
        assert r.status_code in (401, 403)


# ---------- Callback / webhook ----------------------------------------------
class TestOfframpCallback:
    def test_callback_garbage_body(self, api):
        # Send a bare JSON string — not an object
        r = api.post(f"{BASE_URL}/api/offramp/callback",
                     data='"not-an-object"',
                     headers={"Content-Type": "application/json"})
        assert r.status_code == 400, r.text[:200]

    def test_callback_invalid_json(self, api):
        r = api.post(f"{BASE_URL}/api/offramp/callback",
                     data="{not-json",
                     headers={"Content-Type": "application/json"})
        assert r.status_code == 400

    def test_callback_missing_ref(self, api):
        r = api.post(f"{BASE_URL}/api/offramp/callback",
                     json={"status": "SUCCESS"})
        assert r.status_code == 400

    def test_callback_unknown_ref_returns_matched_false(self, api):
        r = api.post(f"{BASE_URL}/api/offramp/callback",
                     json={"referenceId": "kp_mock_unknown_xyz_000", "status": "SUCCESS"})
        assert r.status_code == 200, r.text[:200]
        body = r.json()
        assert body.get("ok") is True
        assert body.get("matched") is False

    def test_callback_success_settles_tx(self, api, mongo, smoke_user):
        ref = f"kp_mock_test_A_{uuid.uuid4().hex[:6]}"
        tx_id = _seed_tx(mongo, smoke_user["id"], ref)
        try:
            payload = {
                "referenceId": ref,
                "status": "SUCCESS",
                "settledAt": _iso(),
                "receipt": {"mpesaReceipt": "MPESA-TEST-RECEIPT-001"},
            }
            r = api.post(f"{BASE_URL}/api/offramp/callback", json=payload)
            assert r.status_code == 200, r.text[:300]
            body = r.json()
            assert body.get("ok") is True
            assert body.get("matched") is True
            assert body.get("status") == "SUCCESS"

            # Verify persistence
            tx = mongo.transactions.find_one({"id": tx_id})
            assert tx is not None
            assert tx.get("status") == "settled", f"tx.status={tx.get('status')}"
            assert tx.get("kotani", {}).get("status") == "SUCCESS"
            assert tx.get("kotani", {}).get("mpesa_receipt") == "MPESA-TEST-RECEIPT-001"
        finally:
            mongo.transactions.delete_one({"id": tx_id})

    def test_callback_success_envelope_form(self, api, mongo, smoke_user):
        """Signed-mode envelope shape: {event, data: {...}}"""
        ref = f"kp_mock_test_env_{uuid.uuid4().hex[:6]}"
        tx_id = _seed_tx(mongo, smoke_user["id"], ref)
        try:
            payload = {
                "event": "offramp.status.updated",
                "data": {
                    "referenceId": ref,
                    "status": "SUCCESS",
                    "receipt": {"mpesaReceipt": "MPESA-ENV-CHECK"},
                },
            }
            r = api.post(f"{BASE_URL}/api/offramp/callback", json=payload)
            assert r.status_code == 200, r.text[:200]
            assert r.json().get("matched") is True
            tx = mongo.transactions.find_one({"id": tx_id})
            assert tx.get("status") == "settled"
            assert tx.get("kotani", {}).get("mpesa_receipt") == "MPESA-ENV-CHECK"
        finally:
            mongo.transactions.delete_one({"id": tx_id})

    def test_callback_failed_marks_failed(self, api, mongo, smoke_user):
        ref = f"kp_mock_test_F_{uuid.uuid4().hex[:6]}"
        tx_id = _seed_tx(mongo, smoke_user["id"], ref)
        try:
            payload = {
                "referenceId": ref,
                "status": "FAILED",
                "failureReason": "Recipient phone rejected the payment",
            }
            r = api.post(f"{BASE_URL}/api/offramp/callback", json=payload)
            assert r.status_code == 200
            assert r.json().get("status") == "FAILED"

            tx = mongo.transactions.find_one({"id": tx_id})
            assert tx.get("status") == "failed"
            assert tx.get("kotani", {}).get("failure_reason") == \
                "Recipient phone rejected the payment"
        finally:
            mongo.transactions.delete_one({"id": tx_id})

    def test_callback_refunded_marks_refunded(self, api, mongo, smoke_user):
        ref = f"kp_mock_test_R_{uuid.uuid4().hex[:6]}"
        tx_id = _seed_tx(mongo, smoke_user["id"], ref)
        try:
            r = api.post(f"{BASE_URL}/api/offramp/callback",
                         json={"referenceId": ref, "status": "REFUNDED"})
            assert r.status_code == 200
            tx = mongo.transactions.find_one({"id": tx_id})
            assert tx.get("status") == "refunded"
        finally:
            mongo.transactions.delete_one({"id": tx_id})


# ---------- /remit/fund contract for KE -------------------------------------
class TestRemitFundContract:
    def test_remit_fund_card_ke_returns_checkout_url(self, api, auth_headers):
        body = {
            "source_fiat": "GBP",
            "amount": 50,
            "destination_code": "KE",
            "recipient_address": "+254712345678",
            "recipient_name": "Njeri Mwangi",
            "payment_method": "card",
        }
        r = api.post(f"{BASE_URL}/api/remit/fund", json=body, headers=auth_headers)
        assert r.status_code == 200, r.text[:400]
        resp = r.json()
        # Common Stripe checkout shapes
        url = resp.get("checkout_url") or resp.get("url") or \
              (resp.get("session") or {}).get("url")
        assert url and "stripe.com" in url, f"no stripe checkout url in resp keys={list(resp.keys())}"
