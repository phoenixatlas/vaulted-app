"""Iteration 19 backend tests — Compliance / OpenSanctions health & admin flows.

Verifies:
 1. screen_sanctions() returns degraded=True with reason "no_api_key" when
    OPENSANCTIONS_API_KEY is not set (fallback path).
 2. screen_sanctions() returns degraded=True with reason "no_name" for empty
    input.
 3. /api/admin/compliance/health is admin-gated (403 for non-admin, 200 for
    ADMIN_EMAILS listed user).
 4. /api/admin/compliance/screen returns full result shape.
 5. /api/kyc/status now surfaces `degraded` + `degraded_reason` in
    sanctions_check.
 6. COMPLIANCE_STRICT_MODE gate on /api/remit/send returns 503 when the
    user's last screen was degraded.
"""

from __future__ import annotations

import pytest

# NOTE: pathlib/dotenv/server already set up by /app/backend/tests/conftest.py
import server  # noqa: E402
import deps  # noqa: E402
import compliance  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
import asyncio
import os


SMOKE_EMAIL = "smoketest@vaulted.app"


# --------------------------------------------------------------------------
# Unit tests on compliance.py directly (no HTTP)
# --------------------------------------------------------------------------
class TestScreenSanctionsFallback:
    def test_no_api_key_returns_degraded(self, monkeypatch):
        """When no OPENSANCTIONS_API_KEY, we short-circuit rather than 401."""
        monkeypatch.setattr(compliance, "OPENSANCTIONS_API_KEY", None)
        result = asyncio.get_event_loop().run_until_complete(
            compliance.screen_sanctions("John Doe", country="GB")
        )
        assert result["matched"] is False
        assert result["degraded"] is True
        assert result["degraded_reason"] == "no_api_key"
        assert result["highest_score"] == 0.0
        assert result["top_matches"] == []

    def test_empty_name_returns_degraded(self):
        result = asyncio.get_event_loop().run_until_complete(
            compliance.screen_sanctions("")
        )
        assert result["matched"] is False
        assert result["degraded"] is True
        assert result["degraded_reason"] == "no_name"

    def test_whitespace_name_returns_degraded(self):
        result = asyncio.get_event_loop().run_until_complete(
            compliance.screen_sanctions("   \t\n  ")
        )
        assert result["degraded"] is True
        assert result["degraded_reason"] == "no_name"


class TestConfigSnapshot:
    def test_config_status_shape(self):
        cfg = compliance.opensanctions_config_status()
        assert "url" in cfg
        assert "api_key_configured" in cfg
        assert "strict_mode" in cfg
        assert cfg["scopes"] == ["sanctions", "peps"]


class TestHealthNoKey:
    def test_health_without_key(self, monkeypatch):
        monkeypatch.setattr(compliance, "OPENSANCTIONS_API_KEY", None)
        h = asyncio.get_event_loop().run_until_complete(compliance.opensanctions_health())
        assert h["ok"] is False
        assert h["status"] == "degraded"
        assert h["reason"] == "no_api_key"


# --------------------------------------------------------------------------
# Admin endpoint tests (HTTP via TestClient from conftest)
# --------------------------------------------------------------------------
class TestAdminGate:
    def test_health_without_admin_returns_403(self, client, smoke_auth, monkeypatch):
        """A regular authed user is not on ADMIN_EMAILS → 403."""
        monkeypatch.setattr(deps, "ADMIN_EMAILS", {"root@example.com"})
        r = client.get("/api/admin/compliance/health", headers=smoke_auth)
        assert r.status_code == 403, r.text

    def test_health_no_admin_configured_returns_403(self, client, smoke_auth, monkeypatch):
        """Empty ADMIN_EMAILS locks the endpoints down entirely."""
        monkeypatch.setattr(deps, "ADMIN_EMAILS", set())
        r = client.get("/api/admin/compliance/health", headers=smoke_auth)
        assert r.status_code == 403, r.text

    def test_health_with_admin_returns_200(self, client, smoke_auth, monkeypatch):
        """When smoketest is on ADMIN_EMAILS and no API key set, returns
        200 with degraded status."""
        monkeypatch.setattr(deps, "ADMIN_EMAILS", {SMOKE_EMAIL})
        monkeypatch.setattr(compliance, "OPENSANCTIONS_API_KEY", None)
        r = client.get("/api/admin/compliance/health", headers=smoke_auth)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "opensanctions" in body
        assert body["opensanctions"]["health"]["status"] == "degraded"
        assert body["opensanctions"]["health"]["reason"] == "no_api_key"
        assert body["opensanctions"]["config"]["api_key_configured"] is False
        assert body["corridor_blocklist"]["count"] > 0

    def test_screen_endpoint_returns_full_shape(self, client, smoke_auth, monkeypatch):
        monkeypatch.setattr(deps, "ADMIN_EMAILS", {SMOKE_EMAIL})
        monkeypatch.setattr(compliance, "OPENSANCTIONS_API_KEY", None)
        r = client.post(
            "/api/admin/compliance/screen",
            headers=smoke_auth,
            json={"name": "Test Person", "country": "GB"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["input"]["name"] == "Test Person"
        assert body["result"]["degraded"] is True
        assert body["result"]["degraded_reason"] == "no_api_key"


# --------------------------------------------------------------------------
# /api/kyc/status now surfaces degraded state
# --------------------------------------------------------------------------
class TestKycStatusSurfacesDegraded:
    def test_kyc_status_shape_includes_degraded_fields(self, client, smoke_auth):
        r = client.get("/api/kyc/status", headers=smoke_auth)
        assert r.status_code == 200, r.text
        sc = r.json().get("sanctions_check")
        assert sc is not None
        # New fields present (even if user has no sanctions data yet, they must exist)
        assert "matched" in sc
        assert "degraded" in sc
        assert "degraded_reason" in sc


# --------------------------------------------------------------------------
# COMPLIANCE_STRICT_MODE gate on /api/remit/send
# --------------------------------------------------------------------------
def _set_user_sanctions(email: str, degraded: bool, degraded_reason: str | None) -> None:
    async def _run():
        cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = cli[os.environ["DB_NAME"]]
        await db.users.update_one(
            {"email": email},
            {"$set": {
                "kyc.sanctions": {
                    "matched": False,
                    "degraded": degraded,
                    "degraded_reason": degraded_reason,
                    "checked_at": "2026-07-08T20:00:00Z",
                },
                # Also bump tier so we get past the KYC gate and hit the strict-mode gate
                "kyc.tier": "kyc_lite",
            }},
        )
        cli.close()
    asyncio.new_event_loop().run_until_complete(_run())


def _reset_user_sanctions(email: str) -> None:
    async def _run():
        cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = cli[os.environ["DB_NAME"]]
        await db.users.update_one(
            {"email": email},
            {"$unset": {"kyc.sanctions": "", "kyc.tier": ""}},
        )
        cli.close()
    asyncio.new_event_loop().run_until_complete(_run())


class TestStrictModeGate:
    """When COMPLIANCE_STRICT_MODE is on, a degraded sanctions state blocks
    /api/remit/send with a friendly 503. When off (default), sends proceed."""

    def test_strict_off_allows_degraded_user(self, client, smoke_auth, monkeypatch):
        """Default behavior: degraded user is NOT blocked at the strict gate.
        (They may still be blocked by other gates like insufficient balance —
        we assert the strict-mode error is NOT the one returned.)"""
        _set_user_sanctions(SMOKE_EMAIL, degraded=True, degraded_reason="no_api_key")
        try:
            monkeypatch.setattr(server, "COMPLIANCE_STRICT_MODE", False)
            r = client.post(
                "/api/remit/send",
                headers=smoke_auth,
                json={
                    "source_fiat": "GBP",
                    "amount": 50,
                    "destination_code": "NG",
                    "recipient_address": "GABC1234567890",  # invalid — will fail later
                },
            )
            # Whatever the outcome, it must NOT be sanctions_screening_unavailable
            body_text = r.text
            assert "sanctions_screening_unavailable" not in body_text, (
                f"strict-off should not trigger strict gate: {body_text}"
            )
        finally:
            _reset_user_sanctions(SMOKE_EMAIL)

    def test_strict_on_blocks_degraded_user(self, client, smoke_auth, monkeypatch):
        _set_user_sanctions(SMOKE_EMAIL, degraded=True, degraded_reason="no_api_key")
        try:
            monkeypatch.setattr(server, "COMPLIANCE_STRICT_MODE", True)
            r = client.post(
                "/api/remit/send",
                headers=smoke_auth,
                json={
                    "source_fiat": "GBP",
                    "amount": 50,
                    "destination_code": "NG",
                    "recipient_address": "GABC1234567890",
                },
            )
            assert r.status_code == 503, f"expected 503, got {r.status_code}: {r.text}"
            detail = r.json().get("detail", {})
            assert isinstance(detail, dict)
            assert detail.get("error") == "sanctions_screening_unavailable"
            assert detail.get("degraded_reason") == "no_api_key"
        finally:
            _reset_user_sanctions(SMOKE_EMAIL)

    def test_strict_on_allows_healthy_user(self, client, smoke_auth, monkeypatch):
        """User whose last screen was clean (degraded=False) should not be
        blocked by strict mode."""
        _set_user_sanctions(SMOKE_EMAIL, degraded=False, degraded_reason=None)
        try:
            monkeypatch.setattr(server, "COMPLIANCE_STRICT_MODE", True)
            r = client.post(
                "/api/remit/send",
                headers=smoke_auth,
                json={
                    "source_fiat": "GBP",
                    "amount": 50,
                    "destination_code": "NG",
                    "recipient_address": "GABC1234567890",
                },
            )
            body_text = r.text
            assert "sanctions_screening_unavailable" not in body_text, (
                f"clean screen should not trigger strict gate: {body_text}"
            )
        finally:
            _reset_user_sanctions(SMOKE_EMAIL)
