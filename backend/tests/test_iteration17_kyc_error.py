"""Iteration 17 backend tests — Stripe Identity error-handling fix.

Verifies that when Stripe raises the "Your account is not set up to use Identity"
error, the /api/kyc/session endpoint traps it and returns a structured, friendly
503 payload (error=`stripe_identity_not_activated`) instead of leaking the raw
Stripe error to the frontend. Also regression-checks generic Stripe errors and
the happy path.

Uses FastAPI's TestClient so we can `monkeypatch.setattr` on
`stripe.identity.VerificationSession.create` — this would not be possible if
we hit the running supervisor backend over HTTP.
"""

from __future__ import annotations

import os
import sys
import asyncio
import pathlib

import pytest
import stripe
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from motor.motor_asyncio import AsyncIOMotorClient


# Make /app/backend importable
BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# The pytest process inherits STRIPE_API_KEY=sk_test_emergent from the shell,
# which server.py treats as a placeholder and coerces to "". Force-override
# from backend/.env so we get the real live key that the supervisor backend
# uses.
load_dotenv(BACKEND_DIR / ".env", override=True)

import server  # noqa: E402  — imports FastAPI `app`, `stripe`, config


SMOKE_EMAIL = "smoketest@vaulted.app"
SMOKE_PASSWORD = "test1234"


# --------------------------------------------------------------------------
# Fixtures — client & smoke_auth now provided session-scoped by conftest.py
# --------------------------------------------------------------------------
def _reset_kyc_session_state():
    """Wipe any existing identity_verification_session_id on the smoke user so
    the endpoint takes the create-new-session path (not the reuse path)."""
    async def _run():
        cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = cli[os.environ["DB_NAME"]]
        await db.users.update_one(
            {"email": SMOKE_EMAIL},
            {"$unset": {
                "kyc.identity_verification_session_id": "",
                "kyc.identity_verification_status": "",
                "kyc.identity_started_at": "",
            }},
        )
        cli.close()

    # Use a fresh event loop each time so cross-module test runs (where a
    # previous TestClient has already closed the default loop) don't error.
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_run())
    finally:
        loop.close()


@pytest.fixture(autouse=True)
def _reset_kyc():
    _reset_kyc_session_state()
    yield
    _reset_kyc_session_state()


# --------------------------------------------------------------------------
# Test 1 — "not set up" Stripe error is trapped into friendly 503
# --------------------------------------------------------------------------
class TestStripeIdentityNotActivated:
    def test_not_set_up_error_becomes_friendly_503(self, client, smoke_auth, monkeypatch):
        def _raise_not_set_up(**kwargs):
            raise stripe.error.StripeError(
                "Request req_TEST: Your account is not set up to use Identity. "
                "Please have an account admin visit "
                "https://dashboard.stripe.com/identity/application to get started."
            )

        monkeypatch.setattr(
            stripe.identity.VerificationSession, "create", _raise_not_set_up
        )

        r = client.post("/api/kyc/session", headers=smoke_auth)

        # Status
        assert r.status_code == 503, f"expected 503, got {r.status_code}: {r.text}"

        # Structured detail payload
        body = r.json()
        detail = body.get("detail")
        assert isinstance(detail, dict), f"detail should be a dict, got: {detail!r}"
        assert detail.get("error") == "stripe_identity_not_activated", detail
        msg = detail.get("message") or ""
        assert "temporarily unavailable" in msg, f"message missing 'temporarily unavailable': {msg!r}"
        assert "support@phoenix-atlas.com" in msg, f"message missing support email: {msg!r}"

        # Raw Stripe phrase must NOT leak through anywhere in the response
        raw_body_text = r.text
        assert "not set up to use Identity" not in raw_body_text, (
            f"raw Stripe phrase leaked into response body: {raw_body_text}"
        )


# --------------------------------------------------------------------------
# Test 2 — Generic Stripe errors still bubble as 502 (regression)
# --------------------------------------------------------------------------
class TestStripeGenericError:
    def test_generic_stripe_error_returns_502(self, client, smoke_auth, monkeypatch):
        def _raise_rate_limit(**kwargs):
            raise stripe.error.StripeError("Rate limit exceeded")

        monkeypatch.setattr(
            stripe.identity.VerificationSession, "create", _raise_rate_limit
        )

        r = client.post("/api/kyc/session", headers=smoke_auth)
        assert r.status_code == 502, f"expected 502, got {r.status_code}: {r.text}"
        assert "Stripe Identity error" in r.text, r.text

        detail = r.json().get("detail")
        # detail is a string in this branch, but be tolerant of dict form too
        if isinstance(detail, dict):
            assert detail.get("error") != "stripe_identity_not_activated", detail
        else:
            assert detail != "stripe_identity_not_activated"
            assert "stripe_identity_not_activated" not in r.text


# --------------------------------------------------------------------------
# Test 3 — Happy path is unaffected (regression)
# --------------------------------------------------------------------------
class TestStripeHappyPath:
    def test_successful_session_creation(self, client, smoke_auth, monkeypatch):
        def _ok(**kwargs):
            return {
                "id": "vs_test_123",
                "url": "https://verify.stripe.com/test",
                "status": "requires_input",
            }

        monkeypatch.setattr(
            stripe.identity.VerificationSession, "create", _ok
        )

        r = client.post("/api/kyc/session", headers=smoke_auth)
        assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text}"
        body = r.json()
        assert body.get("session_id"), body
        assert body.get("url"), body
        assert body["session_id"] == "vs_test_123"
        assert body["url"] == "https://verify.stripe.com/test"
