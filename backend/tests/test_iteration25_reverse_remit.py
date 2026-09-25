"""Iteration 25 — Bi-directional remittance (Africa → UK/EU) Phase 1 MVP.

Tests:
  - GET  /api/remit/reverse/corridors  — public catalog
  - POST /api/remit/reverse/quote      — happy path (8 combos) + validation
  - POST /api/waitlist/join            — direction segmentation + backward-compat
  - GET  /api/admin/waitlist/stats     — admin/403
  - Regression: /api/remit/corridors + /api/remit/quote for KE outbound
"""
from __future__ import annotations

import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get(
    "EXPO_PUBLIC_BACKEND_URL",
    "https://multi-sig-vault.preview.emergentagent.com",
).rstrip("/")

# waitlist route rate-limits 5s per IP; be generous.
WAITLIST_SLEEP = 6


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ---------- Reverse corridors catalog ------------------------------------
class TestReverseCorridors:
    def test_catalog_shape(self, api):
        r = api.get(f"{BASE_URL}/api/remit/reverse/corridors")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["status"] == "quote_only"
        # 4 source corridors: NG, KE, GH, ZA
        codes = {s["code"] for s in data["sources"]}
        assert codes == {"NG", "KE", "GH", "ZA"}, f"got {codes}"
        # 2 destinations: GBP, EUR
        dst = {d["code"] for d in data["destinations"]}
        assert dst == {"GBP", "EUR"}, f"got {dst}"
        # Every source has the promised fields
        for s in data["sources"]:
            for k in ("min_amount", "max_amount", "use_cases", "flag", "fund_via"):
                assert k in s, f"missing {k} in source {s['code']}"
            assert isinstance(s["use_cases"], list) and s["use_cases"]
        assert data["bridge"]["token"] == "USDC"
        assert data["bridge"]["chain"] == "POLYGON"


# ---------- Reverse quote — happy path (8 combos) -------------------------
CORRIDOR_TEST_AMOUNTS = {
    "NG": 100000,   # NGN
    "KE": 25000,    # KES
    "GH": 3000,     # GHS
    "ZA": 5000,     # ZAR
}


class TestReverseQuoteHappy:
    @pytest.mark.parametrize("src", ["NG", "KE", "GH", "ZA"])
    @pytest.mark.parametrize("dst", ["GBP", "EUR"])
    def test_quote(self, api, src, dst):
        payload = {
            "source_country": src,
            "source_amount": CORRIDOR_TEST_AMOUNTS[src],
            "destination_currency": dst,
        }
        r = api.post(f"{BASE_URL}/api/remit/reverse/quote", json=payload)
        assert r.status_code == 200, f"{src}->{dst}: {r.status_code} {r.text}"
        data = r.json()
        # Populated amounts
        assert data["destination"]["amount"] > 0, f"destination amount <= 0 for {src}->{dst}"
        assert data["destination"]["currency"] == dst
        assert data["bridge"]["amount"] > 0, f"bridge amount <= 0 for {src}->{dst}"
        assert data["bridge"]["token"] == "USDC"
        assert data["fees"]["total_fee_usd"] > 0
        assert data["kotani"]["mode"] in {"live", "estimated", "mock"}
        assert data["status"] == "quote_only"
        assert data["source"]["country_code"] == src


# ---------- Reverse quote — validation -----------------------------------
class TestReverseQuoteValidation:
    def test_below_min(self, api):
        # NG min is 5000 NGN
        r = api.post(f"{BASE_URL}/api/remit/reverse/quote", json={
            "source_country": "NG", "source_amount": 100, "destination_currency": "GBP",
        })
        assert r.status_code == 400, r.text
        assert "minimum" in r.json()["detail"].lower()

    def test_above_max(self, api):
        # NG max is 5,000,000 NGN
        r = api.post(f"{BASE_URL}/api/remit/reverse/quote", json={
            "source_country": "NG", "source_amount": 10_000_000, "destination_currency": "GBP",
        })
        assert r.status_code == 400, r.text
        assert "maximum" in r.json()["detail"].lower()

    def test_unsupported_source(self, api):
        r = api.post(f"{BASE_URL}/api/remit/reverse/quote", json={
            "source_country": "XX", "source_amount": 1000, "destination_currency": "GBP",
        })
        assert r.status_code == 400, r.text
        assert "unsupported" in r.json()["detail"].lower()

    def test_unsupported_destination(self, api):
        r = api.post(f"{BASE_URL}/api/remit/reverse/quote", json={
            "source_country": "NG", "source_amount": 100000, "destination_currency": "USD",
        })
        assert r.status_code == 400, r.text
        assert "unsupported" in r.json()["detail"].lower()


# ---------- Waitlist direction segmentation ------------------------------
def _rand_email(tag: str) -> str:
    return f"testing-agent-{tag}-{uuid.uuid4().hex[:8]}@example.com"


class TestWaitlistDirection:
    def test_inbound_ng(self, api):
        time.sleep(WAITLIST_SLEEP)
        r = api.post(f"{BASE_URL}/api/waitlist/join", json={
            "email": _rand_email("in"), "corridor": "NG", "direction": "inbound",
            "source": "iter25-test",
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["direction"] == "inbound"
        assert body["corridor"] == "NG"

    def test_outbound_explicit(self, api):
        time.sleep(WAITLIST_SLEEP)
        r = api.post(f"{BASE_URL}/api/waitlist/join", json={
            "email": _rand_email("out"), "corridor": "KE", "direction": "outbound",
            "source": "iter25-test",
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["direction"] == "outbound"

    def test_missing_direction_defaults_outbound(self, api):
        time.sleep(WAITLIST_SLEEP)
        r = api.post(f"{BASE_URL}/api/waitlist/join", json={
            "email": _rand_email("nod"), "corridor": "GH",
            "source": "iter25-test",
        })
        assert r.status_code == 200, r.text
        assert r.json()["direction"] == "outbound"

    def test_invalid_direction_defaults_outbound(self, api):
        time.sleep(WAITLIST_SLEEP)
        r = api.post(f"{BASE_URL}/api/waitlist/join", json={
            "email": _rand_email("bad"), "corridor": "ZA", "direction": "sideways",
            "source": "iter25-test",
        })
        assert r.status_code == 200, r.text
        assert r.json()["direction"] == "outbound"


# ---------- Admin waitlist stats -----------------------------------------
class TestWaitlistStatsAdmin:
    """Admin endpoint. If ADMIN_EMAILS env is not set OR the smoke user is
    not in it, we expect 403 (per review-request expected-behaviour note)."""

    def _login_smoke(self, api):
        r = api.post(f"{BASE_URL}/api/auth/login", json={
            "email": "smoketest@vaulted.app", "password": "test1234",
        })
        if r.status_code != 200:
            pytest.skip(f"smoke login unavailable: {r.status_code} {r.text}")
        return r.json()["access_token"]

    def test_admin_or_403(self, api):
        token = self._login_smoke(api)
        r = api.get(
            f"{BASE_URL}/api/admin/waitlist/stats",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code in (200, 403), r.text
        if r.status_code == 200:
            body = r.json()
            for k in ("total", "by_corridor", "by_direction", "matrix"):
                assert k in body, f"missing {k}"
            assert "outbound" in body["by_direction"]
            assert "inbound" in body["by_direction"]
            assert isinstance(body["matrix"], list)
            if body["matrix"]:
                row = body["matrix"][0]
                for k in ("corridor", "direction", "count"):
                    assert k in row
        else:
            # 403: smoke user not on ADMIN_EMAILS — documented expected behaviour
            print("Admin endpoint returned 403 as expected (smoke user not on ADMIN_EMAILS)")

    def test_unauthenticated_forbidden(self, api):
        r = api.get(f"{BASE_URL}/api/admin/waitlist/stats")
        # Either 401 (unauthenticated) or 403 (not admin) is acceptable
        assert r.status_code in (401, 403), r.text


# ---------- Regression: outbound corridors + quote -----------------------
class TestOutboundRegression:
    def test_outbound_corridors(self, api):
        r = api.get(f"{BASE_URL}/api/remit/corridors")
        assert r.status_code == 200, r.text
        data = r.json()
        # Handle either list or wrapped dict shape defensively
        if isinstance(data, dict) and "corridors" in data:
            corridors = data["corridors"]
        else:
            corridors = data
        assert isinstance(corridors, list)
        assert len(corridors) == 11, f"expected 11 outbound corridors, got {len(corridors)}"

    def test_outbound_quote_ke(self, api):
        payload = {"source_fiat": "GBP", "amount": 100, "destination_code": "KE"}
        r = api.post(f"{BASE_URL}/api/remit/quote", json=payload)
        if r.status_code == 401:
            login = api.post(f"{BASE_URL}/api/auth/login", json={
                "email": "smoketest@vaulted.app", "password": "test1234",
            })
            if login.status_code == 200:
                tok = login.json()["access_token"]
                r = api.post(
                    f"{BASE_URL}/api/remit/quote",
                    json=payload,
                    headers={"Authorization": f"Bearer {tok}"},
                )
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        body = r.json()
        assert isinstance(body, dict)
