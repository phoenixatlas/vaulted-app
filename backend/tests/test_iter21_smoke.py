"""Iteration 21 smoke tests - referral system + backward-compat.

Runs against LOCAL backend at http://localhost:8001.
"""
import os
import uuid
import requests
import pytest

BASE_URL = "http://localhost:8001"
SMOKE_EMAIL = "smoketest@vaulted.app"
SMOKE_PW = "test1234"


@pytest.fixture(scope="module")
def smoke_token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": SMOKE_EMAIL, "password": SMOKE_PW
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert "user" in body
    assert body["user"].get("referral_code"), f"missing referral_code in login: {body['user']}"
    return body["access_token"], body["user"]["referral_code"]


# ---- Unrelated flows still OK ----

def test_login_returns_referral_code():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": SMOKE_EMAIL, "password": SMOKE_PW
    })
    assert r.status_code == 200
    data = r.json()
    assert "user" in data
    code = data["user"].get("referral_code")
    assert code and len(code) == 8, code


def test_register_without_ref_code_backward_compat():
    email = f"TEST_bc_{uuid.uuid4().hex[:8]}@vaulted.app"
    r = requests.post(f"{BASE_URL}/api/auth/register", json={
        "email": email, "password": "test1234", "name": "BC User"
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert "access_token" in body
    assert body["user"].get("referral_code")


def test_wallet_assets_unchanged(smoke_token):
    token, _ = smoke_token
    r = requests.get(f"{BASE_URL}/api/wallet/assets",
                     headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


def test_remit_corridors_unchanged():
    r = requests.get(f"{BASE_URL}/api/remit/corridors")
    assert r.status_code == 200


# ---- Referral endpoints ----

def test_referrals_me(smoke_token):
    token, code = smoke_token
    r = requests.get(f"{BASE_URL}/api/referrals/me",
                     headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert body.get("referral_code") == code
    share_link = body.get("share_link", "")
    assert share_link.startswith("http"), share_link
    assert share_link.endswith(code), share_link
    assert "share_message" in body
    assert "credit_balance_gbp" in body


def test_referrals_validate_valid_public(smoke_token):
    _, code = smoke_token
    r = requests.get(f"{BASE_URL}/api/referrals/validate/{code}")
    assert r.status_code == 200
    body = r.json()
    assert body.get("valid") is True
    assert "referrer_name_masked" in body


def test_referrals_validate_invalid():
    r = requests.get(f"{BASE_URL}/api/referrals/validate/ZZZZZZZZ")
    assert r.status_code == 200
    body = r.json()
    assert body.get("valid") is False


def test_credit_balance(smoke_token):
    token, _ = smoke_token
    r = requests.get(f"{BASE_URL}/api/credit/balance",
                     headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert "balance_gbp" in body
    assert isinstance(body["balance_gbp"], (int, float))


def test_credit_ledger(smoke_token):
    token, _ = smoke_token
    r = requests.get(f"{BASE_URL}/api/credit/ledger?limit=5",
                     headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert "entries" in body
    assert isinstance(body["entries"], list)
