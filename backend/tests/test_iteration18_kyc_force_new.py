"""Iteration 18 backend tests — /api/kyc/session `force_new` flag.

Regression tests for the "user stuck retrying the same failed session" fix.

Verifies:
  1. Without `force_new`, a `requires_input` session is REUSED (existing url).
  2. With `force_new=true`, the existing session is CANCELED and a fresh one
     is created with a new idempotency key (attempt counter incremented).
  3. Stale `identity_last_error` is cleared when a new session is minted.
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


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

load_dotenv(BACKEND_DIR / ".env", override=True)

import server  # noqa: E402


SMOKE_EMAIL = "smoketest@vaulted.app"
SMOKE_PASSWORD = "test1234"


# client & smoke_auth are provided session-scoped by conftest.py
def _set_kyc_state(session_id: str | None, status: str | None, last_error_code: str | None = None):
    async def _run():
        cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = cli[os.environ["DB_NAME"]]
        set_doc: dict = {"kyc.session_attempt": 3}
        unset_doc: dict = {}
        if session_id is None:
            unset_doc["kyc.identity_verification_session_id"] = ""
        else:
            set_doc["kyc.identity_verification_session_id"] = session_id
        if status is None:
            unset_doc["kyc.identity_verification_status"] = ""
        else:
            set_doc["kyc.identity_verification_status"] = status
        if last_error_code is not None:
            set_doc["kyc.identity_last_error"] = {"code": last_error_code, "reason": "test error"}
        update: dict = {}
        if set_doc:
            update["$set"] = set_doc
        if unset_doc:
            update["$unset"] = unset_doc
        await db.users.update_one({"email": SMOKE_EMAIL}, update)
        cli.close()
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_run())
    finally:
        loop.close()


def _get_kyc_state() -> dict:
    async def _run():
        cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = cli[os.environ["DB_NAME"]]
        doc = await db.users.find_one({"email": SMOKE_EMAIL}, {"kyc": 1})
        cli.close()
        return (doc or {}).get("kyc") or {}
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_run())
    finally:
        loop.close()


@pytest.fixture(autouse=True)
def _reset():
    _set_kyc_state(None, None)
    yield
    _set_kyc_state(None, None)


class TestForceNewReuses:
    """Default (no force_new) — reuse the existing requires_input session."""

    def test_reuses_existing_session(self, client, smoke_auth, monkeypatch):
        _set_kyc_state("vs_existing_abc", "requires_input", last_error_code="document_expired")

        def _retrieve(_id, **_kwargs):
            return {"id": _id, "status": "requires_input", "url": "https://verify.stripe.com/existing"}

        create_called = {"count": 0}
        def _create(**_kwargs):
            create_called["count"] += 1
            return {"id": "vs_new_should_not_be_called", "status": "requires_input", "url": "https://x"}

        monkeypatch.setattr(stripe.identity.VerificationSession, "retrieve", _retrieve)
        monkeypatch.setattr(stripe.identity.VerificationSession, "create", _create)

        r = client.post("/api/kyc/session", headers=smoke_auth, json={})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["session_id"] == "vs_existing_abc"
        assert body["url"] == "https://verify.stripe.com/existing"
        assert body["reused"] is True
        assert create_called["count"] == 0, "create should NOT be called when reusing"


class TestForceNewCreatesFresh:
    """force_new=true — cancel the existing session and mint a brand-new one."""

    def test_force_new_cancels_and_creates(self, client, smoke_auth, monkeypatch):
        _set_kyc_state("vs_stale_xyz", "requires_input", last_error_code="document_unverified_other")

        cancel_calls = []
        def _cancel(_id, **_kwargs):
            cancel_calls.append(_id)
            return {"id": _id, "status": "canceled"}

        retrieve_calls = []
        def _retrieve(_id, **_kwargs):
            retrieve_calls.append(_id)
            return {"id": _id, "status": "requires_input", "url": "https://x"}

        captured_kwargs = {}
        def _create(**kwargs):
            captured_kwargs.update(kwargs)
            return {"id": "vs_fresh_new", "status": "requires_input", "url": "https://verify.stripe.com/fresh"}

        monkeypatch.setattr(stripe.identity.VerificationSession, "cancel", _cancel)
        monkeypatch.setattr(stripe.identity.VerificationSession, "retrieve", _retrieve)
        monkeypatch.setattr(stripe.identity.VerificationSession, "create", _create)

        r = client.post("/api/kyc/session", headers=smoke_auth, json={"force_new": True})
        assert r.status_code == 200, r.text
        body = r.json()

        # Fresh session returned
        assert body["session_id"] == "vs_fresh_new"
        assert body["url"] == "https://verify.stripe.com/fresh"
        assert body["reused"] is False

        # Stale session cancelled
        assert cancel_calls == ["vs_stale_xyz"], f"expected cancel of vs_stale_xyz, got: {cancel_calls}"

        # Retrieve should NOT be called on force_new path
        assert retrieve_calls == [], f"retrieve should NOT be called: {retrieve_calls}"

        # Idempotency key incremented (previous attempt was 3, so new should be 4)
        idem_key = captured_kwargs.get("idempotency_key")
        assert idem_key and idem_key.endswith("-4"), f"unexpected idempotency_key: {idem_key}"

        # DB state: stale last_error should have been cleared, new session persisted
        state = _get_kyc_state()
        assert state.get("identity_verification_session_id") == "vs_fresh_new"
        assert state.get("session_attempt") == 4
        assert state.get("identity_last_error") in (None, {}, {"code": None, "reason": None, "at": None})


class TestForceNewToleratesCancelFailure:
    """If cancelling the old session fails (e.g. already canceled), the new
    session should still be created — cancel is best-effort."""

    def test_cancel_failure_is_swallowed(self, client, smoke_auth, monkeypatch):
        _set_kyc_state("vs_already_canceled", "requires_input")

        def _cancel(_id, **_kwargs):
            raise stripe.error.StripeError("Session already canceled")

        def _create(**_kwargs):
            return {"id": "vs_fresh_2", "status": "requires_input", "url": "https://verify.stripe.com/fresh2"}

        monkeypatch.setattr(stripe.identity.VerificationSession, "cancel", _cancel)
        monkeypatch.setattr(stripe.identity.VerificationSession, "create", _create)

        r = client.post("/api/kyc/session", headers=smoke_auth, json={"force_new": True})
        assert r.status_code == 200, r.text
        assert r.json()["session_id"] == "vs_fresh_2"


class TestBackwardCompat:
    """No body (legacy client) still works — should default to force_new=False."""

    def test_empty_body_defaults_to_reuse(self, client, smoke_auth, monkeypatch):
        _set_kyc_state(None, None)  # no existing session

        def _create(**_kwargs):
            return {"id": "vs_from_empty_body", "status": "requires_input", "url": "https://verify.stripe.com/e"}

        monkeypatch.setattr(stripe.identity.VerificationSession, "create", _create)

        # Send with no body at all (legacy behavior)
        r = client.post("/api/kyc/session", headers=smoke_auth)
        assert r.status_code == 200, r.text
        assert r.json()["session_id"] == "vs_from_empty_body"
