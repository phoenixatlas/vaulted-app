"""Iteration 28 — Verify Stripe router extraction has no regressions.

Refactor: /app/backend/routers/stripe_router.py extracted from server.py.
Cross-touchpoint: /api/remit/fund (still in server.py) imports
`_success_cancel_urls` from the new stripe_router module.
"""
import os
import json
import pytest
import requests

BASE_URL = os.environ.get("EXPO_BACKEND_URL", "http://localhost:8001").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def sess():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# --- Basic module-load smoke ------------------------------------------------
class TestServerLoaded:
    def test_health_ok(self, sess):
        r = sess.get(f"{API}/health", timeout=10)
        assert r.status_code == 200, r.text
        assert r.json().get("status") == "ok"

    def test_openapi_has_exactly_six_stripe_endpoints(self, sess):
        r = sess.get(f"{BASE_URL}/openapi.json", timeout=10)
        assert r.status_code == 200
        paths = r.json().get("paths", {})
        stripe_paths = sorted(p for p in paths if "/stripe/" in p)
        expected = sorted([
            "/api/stripe/checkout/deposit",
            "/api/stripe/checkout/subscription",
            "/api/stripe/sync",
            "/api/stripe/webhook",
            "/api/stripe/portal",
            "/api/stripe/cancel",
        ])
        assert stripe_paths == expected, f"Got: {stripe_paths}"


# --- Stripe endpoint auth guards -------------------------------------------
class TestStripeAuthGuards:
    def test_checkout_deposit_unauth(self, sess):
        r = sess.post(f"{API}/stripe/checkout/deposit", json={"amount_usd": 10})
        assert r.status_code == 401, f"Got {r.status_code}: {r.text}"

    def test_checkout_subscription_unauth(self, sess):
        r = sess.post(f"{API}/stripe/checkout/subscription", json={})
        assert r.status_code == 401, f"Got {r.status_code}: {r.text}"

    def test_sync_unauth(self, sess):
        r = sess.post(f"{API}/stripe/sync", json={"session_id": "cs_test_xxx"})
        assert r.status_code == 401, f"Got {r.status_code}: {r.text}"

    def test_portal_unauth(self, sess):
        r = sess.post(f"{API}/stripe/portal", json={})
        assert r.status_code == 401, f"Got {r.status_code}: {r.text}"

    def test_cancel_unauth(self, sess):
        r = sess.post(f"{API}/stripe/cancel", json={})
        assert r.status_code == 401, f"Got {r.status_code}: {r.text}"


# --- Stripe webhook signature validation -----------------------------------
class TestStripeWebhook:
    def test_webhook_invalid_signature(self, sess):
        """With STRIPE_WEBHOOK_SECRET set, invalid signature → 400.
        NOTE: If STRIPE_WEBHOOK_SECRET is empty in .env, code falls into
        else branch and this returns 200. Test accordingly.
        """
        # send with dummy sig header
        r = requests.post(
            f"{API}/stripe/webhook",
            data=b'{"type":"noop"}',
            headers={"Stripe-Signature": "t=1,v1=bad", "Content-Type": "application/json"},
            timeout=10,
        )
        # We check the code path: if secret is set, expect 400; else expect
        # the else branch to parse and short-circuit. Assert one of the two
        # documented behaviours and record which one for the report.
        assert r.status_code in (200, 400), f"Unexpected {r.status_code}: {r.text}"
        if r.status_code == 400:
            assert "Invalid webhook" in r.text or "invalid" in r.text.lower()

    def test_webhook_no_signature_valid_body(self, sess):
        """Without any Stripe-Signature header and valid JSON body → 200."""
        body = {
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "id": "sub_test_none",
                    "status": "active",
                    "current_period_end": 9999999999,
                }
            },
        }
        r = requests.post(
            f"{API}/stripe/webhook",
            data=json.dumps(body),
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        assert r.status_code == 200, f"Got {r.status_code}: {r.text}"
        assert r.json().get("status") == "ok"


# --- Cross-router regressions ----------------------------------------------
class TestCrossRouterRegressions:
    def test_remit_fund_unauth_still_401(self, sess):
        """CRITICAL: /api/remit/fund lives in server.py but imports
        _success_cancel_urls from stripe_router. If the import broke,
        this would 500 or the module wouldn't load."""
        r = sess.post(
            f"{API}/remit/fund",
            json={
                "source_amount": 100.0,
                "source_fiat": "GBP",
                "destination_country_code": "NG",
                "recipient_address": "test",
                "receive_via": "bank",
            },
        )
        assert r.status_code == 401, f"Got {r.status_code}: {r.text}"

    def test_waitlist_join(self, sess):
        import uuid as _u
        import time as _t
        _t.sleep(6)  # per-IP rate limit is ~5s
        email = f"TEST_iter28_{_u.uuid4().hex[:8]}@example.com"
        r = sess.post(f"{API}/waitlist/join", json={"email": email})
        assert r.status_code == 200, f"Got {r.status_code}: {r.text}"
        data = r.json()
        assert "position" in data
        assert "referral_code" in data
        assert isinstance(data["referral_code"], str) and len(data["referral_code"]) > 0

    def test_remit_reverse_quote(self, sess):
        r = sess.post(f"{API}/remit/reverse/quote", json={
            "source_country": "NG",
            "source_amount": 100000,
            "destination_currency": "GBP",
        })
        assert r.status_code == 200, f"Got {r.status_code}: {r.text}"
        data = r.json()
        assert "destination" in data
        assert data["destination"].get("amount", 0) > 0

    def test_investor_onepager_request(self, sess):
        import uuid as _u
        r = sess.post(f"{API}/investor/onepager/request", json={
            "email": f"TEST_iter28_{_u.uuid4().hex[:8]}@example.com",
            "name": "Test Investor",
            "firm": "TestVC",
        })
        assert r.status_code == 200, f"Got {r.status_code}: {r.text}"
        data = r.json()
        assert "download_url" in data

    def test_investor_deck_request(self, sess):
        import uuid as _u
        r = sess.post(f"{API}/investor/deck/request", json={
            "email": f"TEST_iter28_{_u.uuid4().hex[:8]}@example.com",
            "name": "Test Investor",
            "firm": "TestVC",
        })
        assert r.status_code == 200, f"Got {r.status_code}: {r.text}"
        data = r.json()
        assert "download_url" in data
