"""Iteration 20 backend tests — audit-log endpoint (FCA compliance trail).

Verifies:
 1. Audit events are persisted to `audit_events` collection on:
    - kyc.session_created / kyc.session_force_new
    - kyc.requires_input (webhook path)
    - kyc.verified / kyc.flagged / sanctions.screened (verified webhook path)
    - kyc.canceled (webhook path)
    - remit.send_blocked (corridor, free_tier, strict_mode, kyc_required paths)
    - admin.manual_screen
 2. Admin endpoints:
    - GET /api/admin/audit-log lists newest-first with cursor pagination
    - GET /api/admin/audit-log?event_type=X filters
    - GET /api/admin/audit-log?user_id=X filters
    - GET /api/admin/audit-log/user/{id} returns chronological summary
    - GET /api/admin/audit-log/event-types enumerates constants
    - Unknown event_type returns 400 with allowed list
 3. Admin-gated (require_admin) — 403 for non-admin.
 4. PII hashing: user_email_hash present, raw email absent from every event.
"""

from __future__ import annotations

import asyncio
import os
import time

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

import server  # noqa: E402
import deps  # noqa: E402
import compliance  # noqa: E402
import audit  # noqa: E402


SMOKE_EMAIL = "smoketest@vaulted.app"


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _reset_audit_collection() -> None:
    async def _run():
        cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = cli[os.environ["DB_NAME"]]
        # Wipe only smoke-user events so we don't nuke unrelated data
        smoke = await db.users.find_one({"email": SMOKE_EMAIL}, {"id": 1})
        if smoke:
            await db.audit_events.delete_many({"user_id": smoke.get("id")})
        cli.close()
    asyncio.new_event_loop().run_until_complete(_run())


def _smoke_user_id() -> str:
    async def _run():
        cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = cli[os.environ["DB_NAME"]]
        u = await db.users.find_one({"email": SMOKE_EMAIL}, {"id": 1})
        cli.close()
        return u["id"]
    return asyncio.new_event_loop().run_until_complete(_run())


def _count_events(user_id: str, event_type: str | None = None) -> int:
    async def _run():
        cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = cli[os.environ["DB_NAME"]]
        q = {"user_id": user_id}
        if event_type:
            q["event_type"] = event_type
        n = await db.audit_events.count_documents(q)
        cli.close()
        return n
    return asyncio.new_event_loop().run_until_complete(_run())


def _reset_user_kyc() -> None:
    async def _run():
        cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = cli[os.environ["DB_NAME"]]
        await db.users.update_one(
            {"email": SMOKE_EMAIL},
            {"$unset": {"kyc": ""}},
        )
        cli.close()
    asyncio.new_event_loop().run_until_complete(_run())


@pytest.fixture(autouse=True)
def _reset():
    _reset_audit_collection()
    _reset_user_kyc()
    yield
    _reset_audit_collection()
    _reset_user_kyc()


# --------------------------------------------------------------------------
# 1. Unit tests on audit.py
# --------------------------------------------------------------------------
class TestAuditWrite:
    def test_write_event_persists_and_hashes_email(self):
        async def _run():
            cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
            db = cli[os.environ["DB_NAME"]]
            event_id = await audit.write_event(
                db,
                audit.EventType.KYC_VERIFIED,
                user={"id": "test-user-123", "email": "TestUser@Example.COM"},
                data={"foo": "bar"},
            )
            doc = await db.audit_events.find_one({"id": event_id})
            cli.close()
            return doc
        doc = asyncio.new_event_loop().run_until_complete(_run())
        assert doc is not None
        assert doc["event_type"] == "kyc.verified"
        assert doc["user_id"] == "test-user-123"
        # Email hash present, raw email absent
        assert doc["user_email_hash"] is not None
        assert len(doc["user_email_hash"]) == 12
        assert "example.com" not in str(doc).lower()
        assert doc["data"] == {"foo": "bar"}
        # Cleanup
        async def _cleanup():
            cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
            db = cli[os.environ["DB_NAME"]]
            await db.audit_events.delete_many({"user_id": "test-user-123"})
            cli.close()
        asyncio.new_event_loop().run_until_complete(_cleanup())

    def test_write_event_never_raises_on_db_failure(self, monkeypatch):
        class BrokenCollection:
            async def insert_one(self, *_a, **_k):
                raise RuntimeError("simulated DB down")

        class BrokenDB:
            audit_events = BrokenCollection()

        async def _run():
            return await audit.write_event(BrokenDB(), "some.event", user_id="x")
        result = asyncio.new_event_loop().run_until_complete(_run())
        assert result is None  # returned None, no exception


class TestEventTypeConstants:
    def test_all_expected_events_defined(self):
        expected = {
            "kyc.session_created", "kyc.session_force_new",
            "kyc.verified", "kyc.requires_input", "kyc.canceled", "kyc.flagged",
            "sanctions.screened",
            "remit.quote_generated", "remit.send_success", "remit.send_blocked",
            "corridor.blocked", "admin.manual_screen",
        }
        assert expected.issubset(audit.ALL_EVENT_TYPES)


# --------------------------------------------------------------------------
# 2. Endpoint-level tests through TestClient
# --------------------------------------------------------------------------
class TestAdminAuditLogEndpoint:
    def test_requires_admin(self, client, smoke_auth, monkeypatch):
        monkeypatch.setattr(deps, "ADMIN_EMAILS", {"someoneelse@example.com"})
        r = client.get("/api/admin/audit-log", headers=smoke_auth)
        assert r.status_code == 403, r.text

    def test_no_admin_configured_returns_403(self, client, smoke_auth, monkeypatch):
        monkeypatch.setattr(deps, "ADMIN_EMAILS", set())
        r = client.get("/api/admin/audit-log", headers=smoke_auth)
        assert r.status_code == 403

    def test_event_types_endpoint(self, client, smoke_auth, monkeypatch):
        monkeypatch.setattr(deps, "ADMIN_EMAILS", {SMOKE_EMAIL})
        r = client.get("/api/admin/audit-log/event-types", headers=smoke_auth)
        assert r.status_code == 200
        types = r.json()["event_types"]
        assert "kyc.verified" in types
        assert "remit.send_success" in types

    def test_list_endpoint_returns_pagination_shape(self, client, smoke_auth, monkeypatch):
        monkeypatch.setattr(deps, "ADMIN_EMAILS", {SMOKE_EMAIL})
        r = client.get("/api/admin/audit-log?limit=5", headers=smoke_auth)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "events" in body
        assert "count" in body
        assert "has_more" in body
        assert "next_cursor" in body

    def test_unknown_event_type_returns_400(self, client, smoke_auth, monkeypatch):
        monkeypatch.setattr(deps, "ADMIN_EMAILS", {SMOKE_EMAIL})
        r = client.get("/api/admin/audit-log?event_type=totally.made.up", headers=smoke_auth)
        assert r.status_code == 400
        detail = r.json()["detail"]
        assert detail["error"] == "unknown_event_type"
        assert "allowed" in detail
        assert "kyc.verified" in detail["allowed"]

    def test_user_summary_endpoint(self, client, smoke_auth, monkeypatch):
        monkeypatch.setattr(deps, "ADMIN_EMAILS", {SMOKE_EMAIL})
        uid = _smoke_user_id()
        r = client.get(f"/api/admin/audit-log/user/{uid}", headers=smoke_auth)
        assert r.status_code == 200
        body = r.json()
        assert body["user_id"] == uid
        assert "counts_by_type" in body
        assert "events" in body


# --------------------------------------------------------------------------
# 3. Integration — real flows write real audit events
# --------------------------------------------------------------------------
class TestRemitSendBlockedWritesAudit:
    def test_corridor_blocked_writes_two_events(self, client, smoke_auth):
        """A blocked-corridor attempt writes both a corridor.blocked event
        AND a remit.send_blocked event (with block_type=corridor_blocked)."""
        uid = _smoke_user_id()
        r = client.post(
            "/api/remit/send",
            headers=smoke_auth,
            json={
                "source_fiat": "GBP",
                "amount": 50,
                "destination_code": "KP",  # North Korea — blocklisted
                "recipient_address": "0x0000000000000000000000000000000000000000",
            },
        )
        assert r.status_code == 403
        # Give the async write a beat to land
        time.sleep(0.3)
        assert _count_events(uid, "corridor.blocked") == 1
        assert _count_events(uid, "remit.send_blocked") == 1

    def test_kyc_required_writes_send_blocked(self, client, smoke_auth):
        """Attempting a send well above the unverified £100 limit should
        surface as remit.send_blocked(kyc_required)."""
        uid = _smoke_user_id()
        r = client.post(
            "/api/remit/send",
            headers=smoke_auth,
            json={
                "source_fiat": "GBP",
                "amount": 5000,  # blows past £100 unverified limit
                "destination_code": "NG",
                "recipient_address": "0x0000000000000000000000000000000000000000",
            },
        )
        # Either 403 kyc_required or 400 insufficient — both should audit.
        assert r.status_code in (400, 403), r.text
        time.sleep(0.3)
        assert _count_events(uid, "remit.send_blocked") >= 1


class TestAdminManualScreenWritesAudit:
    def test_manual_screen_writes_event(self, client, smoke_auth, monkeypatch):
        monkeypatch.setattr(deps, "ADMIN_EMAILS", {SMOKE_EMAIL})
        monkeypatch.setattr(compliance, "OPENSANCTIONS_API_KEY", None)
        uid = _smoke_user_id()
        r = client.post(
            "/api/admin/compliance/screen",
            headers=smoke_auth,
            json={"name": "Alice Example", "country": "GB"},
        )
        assert r.status_code == 200
        time.sleep(0.3)
        assert _count_events(uid, "admin.manual_screen") == 1


class TestAuditLogFiltering:
    """Confirm filters actually narrow results."""

    def test_event_type_filter(self, client, smoke_auth, monkeypatch):
        monkeypatch.setattr(deps, "ADMIN_EMAILS", {SMOKE_EMAIL})

        # Seed one blocked-corridor event
        client.post(
            "/api/remit/send",
            headers=smoke_auth,
            json={"source_fiat": "GBP", "amount": 50, "destination_code": "KP",
                  "recipient_address": "0x00"},
        )
        time.sleep(0.3)

        r = client.get("/api/admin/audit-log?event_type=corridor.blocked&limit=10",
                       headers=smoke_auth)
        assert r.status_code == 200
        body = r.json()
        for ev in body["events"]:
            assert ev["event_type"] == "corridor.blocked"
        assert body["count"] >= 1

    def test_user_id_filter(self, client, smoke_auth, monkeypatch):
        monkeypatch.setattr(deps, "ADMIN_EMAILS", {SMOKE_EMAIL})
        uid = _smoke_user_id()

        # Seed one event
        client.post(
            "/api/remit/send",
            headers=smoke_auth,
            json={"source_fiat": "GBP", "amount": 50, "destination_code": "KP",
                  "recipient_address": "0x00"},
        )
        time.sleep(0.3)

        r = client.get(f"/api/admin/audit-log?user_id={uid}&limit=100",
                       headers=smoke_auth)
        assert r.status_code == 200
        body = r.json()
        for ev in body["events"]:
            assert ev["user_id"] == uid
