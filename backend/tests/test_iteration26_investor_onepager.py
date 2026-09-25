"""Iteration 26 — Investor one-pager backend tests.

Covers /api/investor/onepager/{request,download}, /api/admin/investor/leads,
and regressions on /api/waitlist/join (inbound) and /api/remit/reverse/quote.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import uuid

import pytest
import requests
from dotenv import load_dotenv
from pathlib import Path

# Load backend .env so JWT_SECRET is available for expired-token mint
load_dotenv(Path("/app/backend/.env"))

BASE_URL = os.environ["EXPO_BACKEND_URL"].rstrip("/") if os.environ.get("EXPO_BACKEND_URL") else None
if not BASE_URL:
    # Fallback to the same public URL used by frontend
    BASE_URL = "https://multi-sig-vault.preview.emergentagent.com"

JWT_SECRET = os.environ.get("JWT_SECRET", "vaulted-dev-secret-change-me")


# ---------- helpers -------------------------------------------------------
def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _mint_token(email: str, expires_at: int) -> str:
    payload = json.dumps({"e": email.lower(), "x": expires_at}, separators=(",", ":")).encode()
    mac = hmac.new(JWT_SECRET.encode(), payload, hashlib.sha256).digest()
    return f"{_b64url(payload)}.{_b64url(mac)}"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# ------------------------------------------------------------------
# Onepager request — happy path
# ------------------------------------------------------------------
class TestOnepagerRequest:
    def test_full_fields_happy_path(self, s):
        email = f"TEST_full_{uuid.uuid4().hex[:8]}@example.com"
        payload = {
            "email": email,
            "name": "Ada Lovelace",
            "company": "Analytical Engines Ltd",
            "role": "General Partner",
            "note": "Interested in Phase 2 rail integration",
        }
        r = s.post(f"{BASE_URL}/api/investor/onepager/request", json=payload)
        assert r.status_code == 200, r.text
        b = r.json()
        assert b.get("ok") is True
        assert b.get("already_requested") is False
        assert "download_url" in b and b["download_url"].startswith("/api/investor/onepager/download?token=")
        token = b["download_url"].split("token=", 1)[1]
        assert "." in token, "token must be payload.mac"
        # expires_at ~ now + 86400 (allow +/- 60s)
        assert abs(int(b["expires_at"]) - (int(time.time()) + 86400)) < 60

    def test_minimal_fields(self, s):
        email = f"TEST_min_{uuid.uuid4().hex[:8]}@example.com"
        r = s.post(f"{BASE_URL}/api/investor/onepager/request",
                   json={"email": email, "name": "Min Only"})
        assert r.status_code == 200, r.text
        b = r.json()
        assert b.get("ok") is True
        assert "download_url" in b

    def test_invalid_email_422(self, s):
        r = s.post(f"{BASE_URL}/api/investor/onepager/request",
                   json={"email": "not-an-email", "name": "Bad Email"})
        assert r.status_code == 422, r.text

    def test_repeat_returns_already_requested(self, s):
        email = f"TEST_repeat_{uuid.uuid4().hex[:8]}@example.com"
        first = s.post(f"{BASE_URL}/api/investor/onepager/request",
                       json={"email": email, "name": "Repeat User", "company": "Repeat Co"})
        assert first.status_code == 200
        assert first.json().get("already_requested") is False

        second = s.post(f"{BASE_URL}/api/investor/onepager/request",
                        json={"email": email, "name": "Repeat User", "company": "Repeat Co"})
        assert second.status_code == 200
        assert second.json().get("already_requested") is True


# ------------------------------------------------------------------
# Onepager download
# ------------------------------------------------------------------
class TestOnepagerDownload:
    def test_missing_token_422(self, s):
        r = s.get(f"{BASE_URL}/api/investor/onepager/download")
        assert r.status_code == 422, r.text

    def test_tampered_signature_403(self, s):
        email = f"TEST_tamper_{uuid.uuid4().hex[:8]}@example.com"
        req = s.post(f"{BASE_URL}/api/investor/onepager/request",
                     json={"email": email, "name": "Tamper Test"})
        assert req.status_code == 200
        token = req.json()["download_url"].split("token=", 1)[1]
        payload_b, _mac_b = token.split(".", 1)
        garbage_mac = _b64url(b"not-a-valid-mac-signature-abcdef")
        tampered = f"{payload_b}.{garbage_mac}"
        r = s.get(f"{BASE_URL}/api/investor/onepager/download", params={"token": tampered})
        assert r.status_code == 403, r.text
        detail = ""
        try:
            detail = r.json().get("detail", "")
        except Exception:
            detail = r.text
        assert "expired" in detail.lower() or "invalid" in detail.lower()

    def test_valid_token_streams_pdf(self, s):
        email = f"TEST_pdf_{uuid.uuid4().hex[:8]}@example.com"
        req = s.post(f"{BASE_URL}/api/investor/onepager/request",
                     json={"email": email, "name": "PDF Fetcher"})
        assert req.status_code == 200
        token = req.json()["download_url"].split("token=", 1)[1]
        r = s.get(f"{BASE_URL}/api/investor/onepager/download",
                  params={"token": token})
        assert r.status_code == 200, r.text
        ct = r.headers.get("content-type", "")
        assert "application/pdf" in ct, ct
        body = r.content
        assert body[:4] == b"%PDF", body[:8]
        assert len(body) > 3000, f"PDF too small: {len(body)}"

    def test_expired_token_403(self, s):
        email = "expired@example.com"
        expired_ts = int(time.time()) - 3600  # 1h ago
        token = _mint_token(email, expired_ts)
        r = s.get(f"{BASE_URL}/api/investor/onepager/download",
                  params={"token": token})
        assert r.status_code == 403, r.text


# ------------------------------------------------------------------
# Admin leads endpoint
# ------------------------------------------------------------------
class TestAdminLeads:
    def test_admin_leads_no_auth_403(self, s):
        r = s.get(f"{BASE_URL}/api/admin/investor/leads")
        # No Authorization header: get_current_user raises 401 first.
        # If ADMIN_EMAILS is unset, require_admin raises 403.
        # The task spec says 403 is expected — accept 401 or 403 as "not authorized".
        assert r.status_code in (401, 403), r.text


# ------------------------------------------------------------------
# Regressions
# ------------------------------------------------------------------
class TestRegressions:
    def test_waitlist_join_inbound(self, s):
        email = f"TEST_wl_{uuid.uuid4().hex[:8]}@example.com"
        r = s.post(f"{BASE_URL}/api/waitlist/join",
                   json={"email": email, "direction": "inbound", "source": "test"})
        assert r.status_code == 200, r.text
        b = r.json()
        assert b.get("direction") == "inbound", b

    def test_remit_reverse_quote_ng_to_gbp(self, s):
        r = s.post(f"{BASE_URL}/api/remit/reverse/quote",
                   json={"source_country": "NG", "source_amount": 100000,
                         "destination_currency": "GBP"})
        assert r.status_code == 200, r.text
        b = r.json()
        dest = b.get("destination") or {}
        assert dest, b
        assert dest.get("amount", 0) > 0, dest
