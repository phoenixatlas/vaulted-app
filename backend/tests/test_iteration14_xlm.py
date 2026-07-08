"""Iteration 14 — XLM (Stellar Testnet) integration tests.

Covers /api/wallet/xlm/info + /api/wallet/xlm/send end-to-end, plus
regression on the pre-existing ETH/USDC/BTC/SOL routes and /wallet/assets.
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://multi-sig-vault.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

# A well-formed 56-char G... address (Stellar docs example — checksum-valid).
# Note: the review brief supplied a 54-char string which the backend correctly
# rejects at the length gate, so we use a real 56-char public key here to
# actually exercise the unfunded-source path.
VALID_XLM_RECIPIENT = "GDQP2KPQGKIHYJGXNUIYOMHARUARCA7DJT5FO2FFOOKY3B2WSQHG4W37"
assert len(VALID_XLM_RECIPIENT) == 56


# --------------------------- Fixtures ---------------------------
@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def fresh_user(session):
    """Register a brand-new user; return (token, user_dict)."""
    email = f"TEST_iter14_{uuid.uuid4().hex[:10]}@vaulted.app"
    r = session.post(
        f"{API}/auth/register",
        json={"email": email, "password": "test1234", "name": "XLM Tester"},
    )
    assert r.status_code == 200, f"register failed: {r.status_code} {r.text[:200]}"
    body = r.json()
    return body["access_token"], body["user"]


@pytest.fixture(scope="module")
def auth_headers(fresh_user):
    tok, _ = fresh_user
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


# --------------------------- Health ---------------------------
def test_health(session):
    r = session.get(f"{API}/")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


# --------------------------- /wallet/assets — XLM entry ---------------------------
def test_assets_includes_xlm_and_address(session, auth_headers, fresh_user):
    _, user = fresh_user
    r = session.get(f"{API}/wallet/assets", headers=auth_headers)
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    # Top-level xlm_address must be a valid G... 56-char address
    xlm_addr = body.get("xlm_address")
    assert isinstance(xlm_addr, str) and xlm_addr.startswith("G") and len(xlm_addr) == 56, (
        f"bad xlm_address: {xlm_addr!r}"
    )
    # Total USD must be a number
    assert isinstance(body.get("total_usd"), (int, float))
    # XLM entry must be present with on_chain + network + wallet_address matching
    xlm = next((a for a in body["assets"] if a["symbol"] == "XLM"), None)
    assert xlm is not None, "XLM missing from /wallet/assets"
    assert xlm["on_chain"] is True
    assert xlm["network"] == "Testnet"
    assert xlm["wallet_address"] == xlm_addr


# --------------------------- /wallet/xlm/info ---------------------------
def test_xlm_info_shape(session, auth_headers, fresh_user):
    _, user = fresh_user
    r = session.get(f"{API}/wallet/xlm/info", headers=auth_headers)
    assert r.status_code == 200, r.text[:200]
    d = r.json()
    for k in ("address", "balance_stroops", "balance_xlm", "network", "explorer", "faucet", "send_supported", "min_reserve_xlm"):
        assert k in d, f"missing key: {k}"
    assert d["address"].startswith("G") and len(d["address"]) == 56
    assert d["network"] == "Testnet"
    assert d["send_supported"] is True
    assert d["min_reserve_xlm"] == 1.0
    # Faucet URL must be Friendbot for testnet, pointing to this address
    assert d["faucet"] == f"https://friendbot.stellar.org/?addr={d['address']}"


def test_xlm_info_requires_auth(session):
    r = session.get(f"{API}/wallet/xlm/info")
    assert r.status_code == 401


# --------------------------- /wallet/xlm/send — validation ---------------------------
def test_xlm_send_invalid_address_returns_400(session, auth_headers):
    r = session.post(
        f"{API}/wallet/xlm/send",
        headers=auth_headers,
        json={"to_address": "foo", "amount": 1.0},
    )
    assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:200]}"
    detail = (r.json() or {}).get("detail", "")
    assert "Invalid Stellar" in detail or "G..." in detail, f"unexpected detail: {detail}"


def test_xlm_send_negative_amount_returns_422(session, auth_headers):
    r = session.post(
        f"{API}/wallet/xlm/send",
        headers=auth_headers,
        json={"to_address": VALID_XLM_RECIPIENT, "amount": -0.5},
    )
    assert r.status_code == 422, f"expected 422, got {r.status_code}: {r.text[:200]}"


def test_xlm_send_zero_amount_returns_422(session, auth_headers):
    r = session.post(
        f"{API}/wallet/xlm/send",
        headers=auth_headers,
        json={"to_address": VALID_XLM_RECIPIENT, "amount": 0},
    )
    assert r.status_code == 422


def test_xlm_send_unfunded_source_returns_clean_400(session, auth_headers):
    """A fresh user has 0 XLM; server must return 400 with a clear message —
    NEVER 500 with a traceback."""
    r = session.post(
        f"{API}/wallet/xlm/send",
        headers=auth_headers,
        json={"to_address": VALID_XLM_RECIPIENT, "amount": 1.0},
    )
    assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:400]}"
    detail = (r.json() or {}).get("detail", "").lower()
    assert (
        "insufficient xlm" in detail
        or "not funded" in detail
        or "reserve" in detail
    ), f"unexpected detail: {detail}"
    # Explicitly ensure no traceback / stack leaked
    assert "traceback" not in r.text.lower()


def test_xlm_send_requires_auth(session):
    r = requests.post(
        f"{API}/wallet/xlm/send",
        json={"to_address": VALID_XLM_RECIPIENT, "amount": 1.0},
    )
    assert r.status_code == 401


# --------------------------- Regression: other chains still work ---------------------------
def test_eth_send_invalid_address_400(session, auth_headers):
    r = session.post(
        f"{API}/wallet/eth/send",
        headers=auth_headers,
        json={"to_address": "0xdeadbeef", "amount_eth": 0.001},
    )
    assert r.status_code == 400


def test_usdc_send_invalid_address_400(session, auth_headers):
    r = session.post(
        f"{API}/wallet/usdc/send",
        headers=auth_headers,
        json={"to_address": "notanaddr", "amount_usdc": 1.0},
    )
    assert r.status_code == 400


def test_btc_send_short_address_400(session, auth_headers):
    r = session.post(
        f"{API}/wallet/btc/send",
        headers=auth_headers,
        json={"to_address": "abc", "amount": 0.0001},
    )
    assert r.status_code == 400


def test_sol_send_short_address_400(session, auth_headers):
    r = session.post(
        f"{API}/wallet/sol/send",
        headers=auth_headers,
        json={"to_address": "short", "amount": 0.001},
    )
    assert r.status_code == 400


# --------------------------- Auth regression ---------------------------
def test_login_smoketest_account(session):
    r = session.post(
        f"{API}/auth/login",
        json={"email": "smoketest@vaulted.app", "password": "test1234"},
    )
    # If seed missing, skip gracefully rather than hard-fail
    if r.status_code == 401:
        pytest.skip("smoketest account not seeded in this env")
    assert r.status_code == 200
    body = r.json()
    assert "access_token" in body and "user" in body


def test_register_returns_xlm_address_indirectly(session):
    """After register, /wallet/assets should immediately expose xlm_address."""
    email = f"TEST_iter14_reg_{uuid.uuid4().hex[:8]}@vaulted.app"
    r = session.post(
        f"{API}/auth/register",
        json={"email": email, "password": "test1234", "name": "Reg XLM"},
    )
    assert r.status_code == 200
    tok = r.json()["access_token"]
    r2 = session.get(f"{API}/wallet/assets", headers={"Authorization": f"Bearer {tok}"})
    assert r2.status_code == 200
    addr = r2.json().get("xlm_address")
    assert isinstance(addr, str) and addr.startswith("G") and len(addr) == 56
