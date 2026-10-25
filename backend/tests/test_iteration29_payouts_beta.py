"""Iteration 29 — payout orchestrator (Kotani/Yellow Card), beta test mode,
live-FX estimate fallback, delete-account. Runs against public URL."""
import os
import uuid

import pytest
import requests
from dotenv import dotenv_values

_FE_ENV = dotenv_values("/app/frontend/.env")
BASE_URL = (os.environ.get("EXPO_BACKEND_URL") or os.environ.get("EXPO_PUBLIC_BACKEND_URL")
            or _FE_ENV.get("EXPO_BACKEND_URL") or _FE_ENV.get("EXPO_PUBLIC_BACKEND_URL")).rstrip("/")
API = f"{BASE_URL}/api"
SMOKE = {"email": "smoketest@vaulted.app", "password": "test1234"}


def _token(resp):
    d = resp.json()
    return d.get("access_token") or d.get("token")


@pytest.fixture(scope="module")
def smoke_headers():
    r = requests.post(f"{API}/auth/login", json=SMOKE, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"smoketest login failed {r.status_code}")
    return {"Authorization": f"Bearer {_token(r)}"}


# ---- App config (public) ----
def test_app_config():
    r = requests.get(f"{API}/app/config", timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert d["beta_test_mode"] is True
    assert d["payout_provider"] in ("kotani", "yellowcard")
    assert d["payout_provider_label"] in ("Kotani Pay", "Yellow Card")
    assert d["stripe_mode"] == "test"


# ---- Reverse remit quote (public) — bug fix: was 502 ----
@pytest.mark.parametrize("country,amount", [("NG", 100000), ("KE", 10000), ("GH", 1000), ("ZA", 2000)])
@pytest.mark.parametrize("dst", ["GBP", "EUR"])
def test_reverse_quote_estimated(country, amount, dst):
    r = requests.post(f"{API}/remit/reverse/quote",
                      json={"source_country": country, "source_amount": amount, "destination_currency": dst}, timeout=45)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["kotani"]["mode"] in ("estimated", "live")
    amt = d["destination"]["amount"]
    assert isinstance(amt, (int, float)) and amt > 0
    print(country, dst, amount, "->", amt, d["kotani"]["mode"])


def test_reverse_quote_sanity_ng_gbp():
    # 100k NGN ≈ £45-55 at ~2000 NGN/GBP. Allow wide range for FX drift.
    r = requests.post(f"{API}/remit/reverse/quote",
                      json={"source_country": "NG", "source_amount": 100000, "destination_currency": "GBP"}, timeout=45)
    amt = r.json()["destination"]["amount"]
    assert 25 < amt < 80, amt


def test_reverse_quote_unsupported():
    r = requests.post(f"{API}/remit/reverse/quote", json={"source_country": "IN", "source_amount": 100}, timeout=30)
    assert r.status_code == 400


# ---- Offramp quote (auth) ----
@pytest.mark.parametrize("cur", ["KES", "GHS", "TZS", "ZMW", "UGX", "NGN"])
def test_offramp_quote(smoke_headers, cur):
    r = requests.post(f"{API}/offramp/mpesa/quote", json={"amount_usd": 100, "to_currency": cur},
                      headers=smoke_headers, timeout=45)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["kotani"]["success"] is True
    assert float(d["kotani"]["data"]["fiatAmount"]) > 0
    assert d["mode"] in ("estimated", "live")
    assert d["provider"] in ("kotani", "yellowcard")
    print(cur, d["kotani"]["data"]["fiatAmount"], d["mode"], d["provider"])


def test_offramp_quote_unauth():
    r = requests.post(f"{API}/offramp/mpesa/quote", json={"amount_usd": 100, "to_currency": "KES"}, timeout=30)
    assert r.status_code == 401


# ---- Remit quote regression ----
@pytest.mark.parametrize("dest", ["KE", "NG"])
def test_remit_quote_regression(smoke_headers, dest):
    r = requests.post(f"{API}/remit/quote", json={"source_fiat": "GBP", "amount": 100, "destination_code": dest},
                      headers=smoke_headers, timeout=45)
    assert r.status_code == 200, r.text
    d = r.json()
    print(dest, {k: d.get(k) for k in list(d)[:12]})


# ---- Admin payouts gate ----
def test_admin_payouts_forbidden(smoke_headers):
    assert requests.get(f"{API}/admin/payouts", headers=smoke_headers, timeout=30).status_code == 403
    assert requests.put(f"{API}/admin/payouts", json={"provider": "yellowcard"},
                        headers=smoke_headers, timeout=30).status_code == 403


# ---- Yellow Card webhook signature ----
def test_yc_webhook_no_sig():
    r = requests.post(f"{API}/payouts/yellowcard/webhook", json={"sequenceId": "x", "status": "COMPLETE"}, timeout=30)
    assert r.status_code == 401


def test_yc_webhook_bad_sig():
    r = requests.post(f"{API}/payouts/yellowcard/webhook", json={"sequenceId": "x", "status": "COMPLETE"},
                      headers={"X-YC-Signature": "bogus"}, timeout=30)
    assert r.status_code == 401


# ---- Delete account ----
def test_delete_account_flow():
    email = f"test_del_{uuid.uuid4().hex[:8]}@vaulted.app"
    pw = "DelPass123!"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": pw, "name": "TEST Del"}, timeout=30)
    assert r.status_code in (200, 201), r.text
    h = {"Authorization": f"Bearer {_token(r)}"}
    bad = requests.post(f"{API}/auth/delete-account", json={"password": "wrong"}, headers=h, timeout=30)
    assert bad.status_code == 403, bad.text
    assert requests.get(f"{API}/auth/me", headers=h, timeout=30).status_code == 200
    ok = requests.post(f"{API}/auth/delete-account", json={"password": pw}, headers=h, timeout=30)
    assert ok.status_code == 200 and ok.json() == {"ok": True}, ok.text
    login = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=30)
    assert login.status_code == 401
    assert requests.get(f"{API}/auth/me", headers=h, timeout=30).status_code == 401
