"""Iteration 27 — Referral queue-jump, analytics, and investor deck backend tests.

Covers:
  - POST /api/waitlist/join with `ref` (valid, invalid, self-ref, missing, repeat)
  - GET  /api/waitlist/position (happy, 404, 400)
  - GET  /api/waitlist/refer/<code> (happy w/ redaction, 404)
  - GET  /api/admin/waitlist/analytics/daily-signups (unauth + shape)
  - GET  /api/admin/waitlist/analytics/referrals (unauth + shape)
  - POST /api/investor/deck/request (happy)
  - GET  /api/investor/deck/download (no-token 422, tampered 403, valid 200 pdf)
  - GET  /api/admin/investor/deck/status (unauth)
  - POST /api/admin/investor/deck/upload (unauth)
  - Regression: /api/investor/onepager/request + /api/remit/reverse/quote

Note: rate limit on /waitlist/join is 5s per IP — the test sleeps.
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

load_dotenv(Path("/app/backend/.env"))

BASE_URL = (os.environ.get("EXPO_BACKEND_URL")
            or "https://multi-sig-vault.preview.emergentagent.com").rstrip("/")

JWT_SECRET = os.environ.get("JWT_SECRET", "vaulted-dev-secret-change-me")

RL_SLEEP = 5.2  # per-IP rate limit on /waitlist/join is 5 seconds


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _mint_deck_token(email: str, expires_at: int) -> str:
    payload = json.dumps({"e": email.lower(), "x": expires_at}, separators=(",", ":")).encode()
    mac = hmac.new(JWT_SECRET.encode(), payload, hashlib.sha256).digest()
    return f"{_b64url(payload)}.{_b64url(mac)}"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


def _join(s, email, ref=None, corridor="KE", source="test-i27"):
    body = {"email": email, "corridor": corridor, "source": source}
    if ref is not None:
        body["ref"] = ref
    return s.post(f"{BASE_URL}/api/waitlist/join", json=body)


# ------------------------------------------------------------------
# Referral queue-jump — /waitlist/join with `ref`
# ------------------------------------------------------------------
class TestReferralJoin:
    """
    Uses one referrer + several unique referees. Because /waitlist/join
    rate-limits per IP at 5s, we sleep RL_SLEEP between calls.
    """

    @pytest.fixture(scope="class")
    def referrer(self, s):
        email = f"TEST_ref_owner_{uuid.uuid4().hex[:8]}@example.com"
        r = _join(s, email)
        assert r.status_code == 200, r.text
        code = r.json().get("referral_code")
        assert code, r.json()
        return {"email": email, "code": code}

    def test_valid_ref_increments_counter(self, s, referrer):
        time.sleep(RL_SLEEP)
        # Get baseline referral_count via public /position endpoint
        r0 = s.get(f"{BASE_URL}/api/waitlist/position", params={"email": referrer["email"]})
        assert r0.status_code == 200, r0.text
        before = int(r0.json().get("referral_count") or 0)

        time.sleep(RL_SLEEP)
        referee = f"TEST_referee_{uuid.uuid4().hex[:8]}@example.com"
        r = _join(s, referee, ref=referrer["code"])
        assert r.status_code == 200, r.text
        b = r.json()
        for k in ("referral_code", "position", "total"):
            assert k in b, b
        assert isinstance(b["position"], int)
        assert isinstance(b["total"], int)

        time.sleep(RL_SLEEP)
        r1 = s.get(f"{BASE_URL}/api/waitlist/position", params={"email": referrer["email"]})
        assert r1.status_code == 200, r1.text
        after = int(r1.json().get("referral_count") or 0)
        assert after == before + 1, f"expected +1, got {before}->{after}"

    def test_idempotent_repeat_same_email_no_increment(self, s, referrer):
        time.sleep(RL_SLEEP)
        r0 = s.get(f"{BASE_URL}/api/waitlist/position", params={"email": referrer["email"]})
        before = int(r0.json().get("referral_count") or 0)

        time.sleep(RL_SLEEP)
        repeat_email = f"TEST_repeat_{uuid.uuid4().hex[:8]}@example.com"
        # First join with ref
        r1 = _join(s, repeat_email, ref=referrer["code"])
        assert r1.status_code == 200, r1.text
        time.sleep(RL_SLEEP)
        # Second join same email + same ref -> already_joined, no increment
        r2 = _join(s, repeat_email, ref=referrer["code"])
        assert r2.status_code == 200, r2.text
        assert r2.json().get("already_joined") is True, r2.json()

        time.sleep(RL_SLEEP)
        r_after = s.get(f"{BASE_URL}/api/waitlist/position", params={"email": referrer["email"]})
        after = int(r_after.json().get("referral_count") or 0)
        # Should be +1 only (from the first join), not +2
        assert after == before + 1, f"expected +1 (first join only), got {before}->{after}"

    def test_invalid_ref_no_increment_no_error(self, s):
        time.sleep(RL_SLEEP)
        email = f"TEST_badref_{uuid.uuid4().hex[:8]}@example.com"
        r = _join(s, email, ref="ZZZZZZZZ")
        assert r.status_code == 200, r.text
        b = r.json()
        assert "referral_code" in b and "position" in b and "total" in b
        # referred_by must be null for unknown code
        assert b.get("referred_by") in (None, ""), b

    def test_self_referral_no_increment(self, s):
        time.sleep(RL_SLEEP)
        email = f"TEST_self_{uuid.uuid4().hex[:8]}@example.com"
        r1 = _join(s, email)
        assert r1.status_code == 200, r1.text
        own_code = r1.json()["referral_code"]

        time.sleep(RL_SLEEP)
        r0 = s.get(f"{BASE_URL}/api/waitlist/position", params={"email": email})
        before = int(r0.json().get("referral_count") or 0)

        time.sleep(RL_SLEEP)
        # Same email tries to self-refer — no change (already_joined, and code==own)
        r2 = _join(s, email, ref=own_code)
        assert r2.status_code == 200, r2.text

        time.sleep(RL_SLEEP)
        r_after = s.get(f"{BASE_URL}/api/waitlist/position", params={"email": email})
        after = int(r_after.json().get("referral_count") or 0)
        assert after == before, f"self-ref should not bump; {before}->{after}"

    def test_no_ref_regression(self, s):
        time.sleep(RL_SLEEP)
        email = f"TEST_noref_{uuid.uuid4().hex[:8]}@example.com"
        r = _join(s, email)
        assert r.status_code == 200, r.text
        b = r.json()
        for k in ("referral_code", "position", "total"):
            assert k in b, b


# ------------------------------------------------------------------
# Position / refer lookup
# ------------------------------------------------------------------
class TestPositionLookup:
    def test_position_happy(self, s):
        time.sleep(RL_SLEEP)
        email = f"TEST_pos_{uuid.uuid4().hex[:8]}@example.com"
        r = _join(s, email)
        assert r.status_code == 200
        time.sleep(0.3)
        r2 = s.get(f"{BASE_URL}/api/waitlist/position", params={"email": email})
        assert r2.status_code == 200, r2.text
        b = r2.json()
        for k in ("email", "position", "total", "referral_code",
                  "referral_count", "founding_member", "next_boost_at",
                  "corridor", "direction"):
            assert k in b, f"missing key {k} in {b}"
        assert isinstance(b["founding_member"], bool)
        assert isinstance(b["next_boost_at"], int)

    def test_position_not_found(self, s):
        r = s.get(f"{BASE_URL}/api/waitlist/position",
                  params={"email": f"nonexistent_{uuid.uuid4().hex[:6]}@example.com"})
        assert r.status_code == 404, r.text

    def test_position_bad_email(self, s):
        r = s.get(f"{BASE_URL}/api/waitlist/position",
                  params={"email": "not-an-email"})
        assert r.status_code == 400, r.text


class TestReferLookup:
    def test_refer_happy_redacted(self, s):
        time.sleep(RL_SLEEP)
        email = f"TEST_refluk_{uuid.uuid4().hex[:8]}@example.com"
        r = _join(s, email)
        assert r.status_code == 200
        code = r.json()["referral_code"]

        r2 = s.get(f"{BASE_URL}/api/waitlist/refer/{code}")
        assert r2.status_code == 200, r2.text
        b = r2.json()
        assert b.get("ok") is True
        assert b.get("code") == code
        assert "referrer" in b and "*" in b["referrer"], b
        assert "@" in b["referrer"], b

    def test_refer_not_found(self, s):
        r = s.get(f"{BASE_URL}/api/waitlist/refer/ZZZZZZZZ")
        assert r.status_code == 404, r.text


# ------------------------------------------------------------------
# Admin analytics endpoints
# ------------------------------------------------------------------
class TestAdminAnalytics:
    def test_daily_signups_no_auth(self, s):
        r = s.get(f"{BASE_URL}/api/admin/waitlist/analytics/daily-signups")
        assert r.status_code in (401, 403), r.text

    def test_referrals_no_auth(self, s):
        r = s.get(f"{BASE_URL}/api/admin/waitlist/analytics/referrals")
        assert r.status_code in (401, 403), r.text

    def _login_admin(self, s):
        r = s.post(f"{BASE_URL}/api/auth/login",
                   json={"email": "smoketest@vaulted.app", "password": "test1234"})
        if r.status_code != 200:
            return None
        return r.json().get("access_token")

    def test_daily_signups_with_admin(self, s):
        token = self._login_admin(s)
        if not token:
            pytest.skip("admin login failed")
        r = s.get(f"{BASE_URL}/api/admin/waitlist/analytics/daily-signups",
                  params={"days": 7},
                  headers={"Authorization": f"Bearer {token}"})
        if r.status_code in (401, 403):
            # ADMIN_EMAILS unset → acceptable per spec
            pytest.skip("smoketest is not in ADMIN_EMAILS")
        assert r.status_code == 200, r.text
        b = r.json()
        assert b.get("days") == 7
        series = b.get("series") or []
        assert len(series) == 7, f"expected dense series len=7, got {len(series)}"
        totals = b.get("totals") or {}
        for k in ("signups", "outbound", "inbound", "peak_day",
                  "peak_count", "average_per_day"):
            assert k in totals, f"missing totals.{k}"

    def test_referrals_with_admin(self, s):
        token = self._login_admin(s)
        if not token:
            pytest.skip("admin login failed")
        r = s.get(f"{BASE_URL}/api/admin/waitlist/analytics/referrals",
                  headers={"Authorization": f"Bearer {token}"})
        if r.status_code in (401, 403):
            pytest.skip("smoketest is not in ADMIN_EMAILS")
        assert r.status_code == 200, r.text
        b = r.json()
        assert "leaders" in b and isinstance(b["leaders"], list)
        totals = b.get("totals") or {}
        for k in ("total_referred_signups", "founding_members",
                  "boost_interval", "boost_spots", "founding_threshold"):
            assert k in totals, f"missing totals.{k}"
        assert totals["boost_interval"] == 3
        assert totals["boost_spots"] == 25
        assert totals["founding_threshold"] == 5
        # If we have any leaders, each must be redacted
        for L in b["leaders"]:
            assert "email_redacted" in L and "*" in L["email_redacted"], L
            assert "referral_count" in L
            assert "founding_member" in L


# ------------------------------------------------------------------
# Investor deck endpoints
# ------------------------------------------------------------------
class TestInvestorDeck:
    def test_request_happy(self, s):
        email = f"TEST_deck_{uuid.uuid4().hex[:8]}@example.com"
        r = s.post(f"{BASE_URL}/api/investor/deck/request",
                   json={"email": email, "name": "Deck Reader",
                         "company": "Fund Alpha"})
        assert r.status_code == 200, r.text
        b = r.json()
        assert b.get("ok") is True
        assert "download_url" in b and b["download_url"].startswith(
            "/api/investor/deck/download?token=")
        assert "expires_at" in b
        assert "is_official_deck" in b

    def test_download_missing_token_422(self, s):
        r = s.get(f"{BASE_URL}/api/investor/deck/download")
        assert r.status_code == 422, r.text

    def test_download_tampered_403(self, s):
        email = f"TEST_dtamp_{uuid.uuid4().hex[:8]}@example.com"
        req = s.post(f"{BASE_URL}/api/investor/deck/request",
                     json={"email": email, "name": "Tamper Deck"})
        assert req.status_code == 200
        token = req.json()["download_url"].split("token=", 1)[1]
        payload_b, _ = token.split(".", 1)
        garbage_mac = _b64url(b"totally-invalid-mac-signature-xyz")
        tampered = f"{payload_b}.{garbage_mac}"
        r = s.get(f"{BASE_URL}/api/investor/deck/download",
                  params={"token": tampered})
        assert r.status_code == 403, r.text

    def test_download_valid_streams_pdf(self, s):
        email = f"TEST_dpdf_{uuid.uuid4().hex[:8]}@example.com"
        req = s.post(f"{BASE_URL}/api/investor/deck/request",
                     json={"email": email, "name": "PDF Deck"})
        assert req.status_code == 200
        token = req.json()["download_url"].split("token=", 1)[1]
        r = s.get(f"{BASE_URL}/api/investor/deck/download",
                  params={"token": token})
        assert r.status_code == 200, r.text
        assert "application/pdf" in r.headers.get("content-type", "")
        body = r.content
        assert body[:4] == b"%PDF", body[:8]
        assert len(body) > 5000, f"deck PDF too small: {len(body)}"

    def test_admin_status_no_auth(self, s):
        r = s.get(f"{BASE_URL}/api/admin/investor/deck/status")
        assert r.status_code in (401, 403), r.text

    def test_admin_upload_no_auth(self, s):
        # Attempt without auth — must be blocked
        files = {"file": ("x.pdf", b"%PDF-1.4\n%dummy", "application/pdf")}
        r = requests.post(f"{BASE_URL}/api/admin/investor/deck/upload",
                          files=files)
        assert r.status_code in (401, 403), r.text


# ------------------------------------------------------------------
# Regressions
# ------------------------------------------------------------------
class TestRegressions:
    def test_onepager_request_regression(self, s):
        email = f"TEST_op_reg_{uuid.uuid4().hex[:8]}@example.com"
        r = s.post(f"{BASE_URL}/api/investor/onepager/request",
                   json={"email": email, "name": "Regression One-Pager"})
        assert r.status_code == 200, r.text
        b = r.json()
        assert b.get("ok") is True
        assert b.get("download_url", "").startswith(
            "/api/investor/onepager/download?token=")
        assert "expires_at" in b

    def test_reverse_remit_ng_100000(self, s):
        r = s.post(f"{BASE_URL}/api/remit/reverse/quote",
                   json={"source_country": "NG",
                         "source_amount": 100000,
                         "destination_currency": "GBP"})
        assert r.status_code == 200, r.text
        dest = (r.json() or {}).get("destination") or {}
        assert dest.get("amount", 0) > 0, dest
