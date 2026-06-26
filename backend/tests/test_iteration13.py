"""Iteration 13 — BTC/SOL send route tests.

Verifies the new POST /api/wallet/btc/send and /api/wallet/sol/send routes:
- require JWT (401 without)
- validate address shape (400)
- surface insufficient-balance / broadcast errors as clean 400/502 (NEVER 500)
- existing /eth/send and /usdc/send still work (no regression)
- /wallet/assets reports BTC/SOL with on_chain:true and correct network labels
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "EXPO_PUBLIC_BACKEND_URL must be set"

SMOKE_EMAIL = "smoketest@vaulted.app"
SMOKE_PASSWORD = "test1234"

VALID_BTC_TESTNET_ADDR = "tb1qexampleaddressstring0000000000000000000"  # syntactically valid length, will fail UTXO
VALID_SOL_DEVNET_ADDR = "GdkBBkdaJ3qvw7nQ75JhTwjFvDqzy1cmqRPNwk5kkqV6"


# ---------- fixtures ----------
@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def smoke_token(session):
    r = session.post(f"{BASE_URL}/api/auth/login", json={"email": SMOKE_EMAIL, "password": SMOKE_PASSWORD})
    if r.status_code != 200:
        # fall back to register
        r = session.post(f"{BASE_URL}/api/auth/register",
                         json={"email": SMOKE_EMAIL, "password": SMOKE_PASSWORD, "name": "Smoke"})
    assert r.status_code == 200, f"login/register failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def fresh_token(session):
    email = f"TEST_iter13_{uuid.uuid4().hex[:8]}@vaulted.app"
    r = session.post(f"{BASE_URL}/api/auth/register",
                     json={"email": email, "password": "test1234", "name": "Iter13 Fresh"})
    assert r.status_code == 200, f"register failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# ---------- BTC send ----------
class TestBtcSend:
    def test_requires_auth(self, session):
        r = session.post(f"{BASE_URL}/api/wallet/btc/send",
                         json={"to_address": VALID_BTC_TESTNET_ADDR, "amount": 0.0001})
        assert r.status_code == 401, f"expected 401, got {r.status_code} {r.text[:200]}"

    def test_rejects_short_address(self, session, fresh_token):
        r = session.post(f"{BASE_URL}/api/wallet/btc/send",
                         headers=_auth(fresh_token),
                         json={"to_address": "tb1qshort", "amount": 0.0001})
        assert r.status_code == 400, f"expected 400 for short addr, got {r.status_code} {r.text[:200]}"
        body = r.json()
        assert "address" in body.get("detail", "").lower()

    def test_rejects_zero_amount(self, session, fresh_token):
        # pydantic gt=0 → 422
        r = session.post(f"{BASE_URL}/api/wallet/btc/send",
                         headers=_auth(fresh_token),
                         json={"to_address": VALID_BTC_TESTNET_ADDR, "amount": 0})
        assert r.status_code in (400, 422), f"expected 400/422, got {r.status_code}"

    def test_insufficient_btc_returns_400_or_502_not_500(self, session, fresh_token):
        """Fresh user has zero testnet BTC → bit.send() will raise. Must surface
        as a clean 400 (insufficient) or 502 (broadcast failure), NEVER 500."""
        r = session.post(f"{BASE_URL}/api/wallet/btc/send",
                         headers=_auth(fresh_token),
                         json={"to_address": VALID_BTC_TESTNET_ADDR, "amount": 0.0001})
        assert r.status_code != 500, f"500 traceback leaked: {r.text[:400]}"
        assert r.status_code in (400, 502), f"expected 400 or 502, got {r.status_code} {r.text[:300]}"
        # When ingress wraps a 502 in an HTML page, body won't be JSON — that's fine,
        # the important thing is no 500 and a clean 4xx/502 status code.
        ctype = r.headers.get("content-type", "")
        if "application/json" in ctype:
            detail = r.json().get("detail", "")
            assert isinstance(detail, str) and len(detail) > 0
            low = detail.lower()
            assert any(w in low for w in ("btc", "insufficient", "broadcast", "address")), \
                f"detail missing BTC context: {detail}"


# ---------- SOL send ----------
class TestSolSend:
    def test_requires_auth(self, session):
        r = session.post(f"{BASE_URL}/api/wallet/sol/send",
                         json={"to_address": VALID_SOL_DEVNET_ADDR, "amount": 0.001})
        assert r.status_code == 401

    def test_rejects_short_address(self, session, fresh_token):
        r = session.post(f"{BASE_URL}/api/wallet/sol/send",
                         headers=_auth(fresh_token),
                         json={"to_address": "tooShort", "amount": 0.001})
        assert r.status_code == 400, f"expected 400, got {r.status_code} {r.text[:200]}"
        assert "solana" in r.json().get("detail", "").lower() or "address" in r.json().get("detail", "").lower()

    def test_rejects_zero_amount(self, session, fresh_token):
        r = session.post(f"{BASE_URL}/api/wallet/sol/send",
                         headers=_auth(fresh_token),
                         json={"to_address": VALID_SOL_DEVNET_ADDR, "amount": 0})
        assert r.status_code in (400, 422)

    def test_insufficient_sol_returns_400_not_500(self, session, fresh_token):
        """Fresh user has zero devnet SOL — pre-flight balance check should
        return 400 'Insufficient SOL', not 500."""
        r = session.post(f"{BASE_URL}/api/wallet/sol/send",
                         headers=_auth(fresh_token),
                         json={"to_address": VALID_SOL_DEVNET_ADDR, "amount": 0.001})
        assert r.status_code != 500, f"500 traceback leaked: {r.text[:400]}"
        # Could be 400 (insufficient) or 502 (RPC issue) or 200 (if account had airdrop)
        assert r.status_code in (200, 400, 502), f"unexpected status {r.status_code}: {r.text[:300]}"
        if r.status_code == 400:
            detail = r.json().get("detail", "").lower()
            assert "insufficient" in detail and "sol" in detail, f"unexpected 400 detail: {detail}"
        elif r.status_code == 200:
            body = r.json()
            assert "tx_hash" in body and body["tx_hash"]


# ---------- regression: ETH and USDC sends ----------
class TestExistingSendsRegression:
    def test_eth_send_insufficient_funds_400(self, session, fresh_token):
        # Fresh user has 0 ETH — should hit insufficient guard with 400.
        r = session.post(f"{BASE_URL}/api/wallet/eth/send",
                         headers=_auth(fresh_token),
                         json={"to_address": "0x000000000000000000000000000000000000dEaD", "amount_eth": 0.001})
        assert r.status_code != 500, f"500 leaked: {r.text[:300]}"
        assert r.status_code in (400, 502), f"got {r.status_code} {r.text[:200]}"

    def test_eth_send_invalid_address_400(self, session, fresh_token):
        r = session.post(f"{BASE_URL}/api/wallet/eth/send",
                         headers=_auth(fresh_token),
                         json={"to_address": "0xshort", "amount_eth": 0.001})
        assert r.status_code == 400

    def test_usdc_send_invalid_address_400(self, session, fresh_token):
        r = session.post(f"{BASE_URL}/api/wallet/usdc/send",
                         headers=_auth(fresh_token),
                         json={"to_address": "0xshort", "amount_usdc": 1.0})
        assert r.status_code == 400

    def test_usdc_send_insufficient_400(self, session, fresh_token):
        r = session.post(f"{BASE_URL}/api/wallet/usdc/send",
                         headers=_auth(fresh_token),
                         json={"to_address": "0x000000000000000000000000000000000000dEaD",
                               "amount_usdc": 100.0})
        assert r.status_code != 500
        assert r.status_code in (400, 502)


# ---------- /wallet/assets reports BTC + SOL on-chain ----------
class TestWalletAssetsBtcSol:
    def test_btc_sol_appear_on_chain(self, session, fresh_token):
        r = session.get(f"{BASE_URL}/api/wallet/assets", headers=_auth(fresh_token))
        assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
        body = r.json()
        assets = body.get("assets", [])
        sym_map = {a["symbol"]: a for a in assets}
        assert "BTC" in sym_map, "BTC missing from /wallet/assets"
        assert "SOL" in sym_map, "SOL missing from /wallet/assets"
        btc = sym_map["BTC"]
        sol = sym_map["SOL"]
        assert btc.get("on_chain") is True, f"BTC on_chain expected True, got {btc.get('on_chain')}"
        assert sol.get("on_chain") is True, f"SOL on_chain expected True, got {sol.get('on_chain')}"
        # Network labels — accept either expected form
        assert btc.get("network") in ("Testnet", "Testnet3"), f"BTC network unexpected: {btc.get('network')}"
        assert sol.get("network") == "Devnet", f"SOL network unexpected: {sol.get('network')}"
        # addresses present on the top-level
        assert body.get("btc_address"), "btc_address missing"
        assert body.get("sol_address"), "sol_address missing"


# ---------- root ----------
class TestRoot:
    def test_api_root(self, session):
        r = session.get(f"{BASE_URL}/api/")
        assert r.status_code == 200
        assert r.json().get("status") == "ok"
