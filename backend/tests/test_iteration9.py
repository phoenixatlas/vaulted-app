"""Iteration 9 backend tests — Multichain: BTC testnet3 + SOL devnet + USDC Sepolia.

Focus areas:
- /wallet/assets returns multichain addresses (eth/btc/sol) deterministically
- /wallet/btc/info, /wallet/sol/info, /wallet/usdc/info shape + network/explorer/faucet
- /wallet/usdc/send validation (invalid addr -> 400, zero-balance -> 400)
- Regression: health (GET+HEAD), login, contacts alpha sort, eth info, csv export
"""
import os
import re
import uuid
import pytest
import requests

BASE_URL = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/")


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def fresh_user(api):
    """Register a fresh account so a BIP-39 mnemonic is on file."""
    email = f"TEST_iter9_{uuid.uuid4().hex[:8]}@vaulted.app"
    r = api.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": email, "password": "test1234", "name": "Iter9 Tester"},
    )
    assert r.status_code == 200, f"register failed: {r.status_code} {r.text[:200]}"
    data = r.json()
    return {"email": email, "token": data["access_token"], "user": data["user"]}


@pytest.fixture(scope="module")
def auth_headers(fresh_user):
    return {"Authorization": f"Bearer {fresh_user['token']}", "Content-Type": "application/json"}


# ---------------- Multichain address derivation ----------------
BTC_TESTNET_RE = re.compile(r"^[mn][1-9A-HJ-NP-Za-km-z]{25,40}$")
SOL_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")


class TestMultichainDerivation:
    def test_assets_returns_three_addresses(self, api, auth_headers):
        r = api.get(f"{BASE_URL}/api/wallet/assets", headers=auth_headers)
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        # Must include all three address fields
        eth = body.get("wallet_address")
        btc = body.get("btc_address")
        sol = body.get("sol_address")
        assert eth and eth.startswith("0x") and len(eth) == 42, f"bad eth: {eth}"
        assert btc and BTC_TESTNET_RE.match(btc), f"bad btc testnet addr: {btc}"
        assert sol and SOL_RE.match(sol), f"bad sol addr: {sol}"

    def test_addresses_deterministic_across_endpoints(self, api, auth_headers):
        a = api.get(f"{BASE_URL}/api/wallet/assets", headers=auth_headers).json()
        b = api.get(f"{BASE_URL}/api/wallet/btc/info", headers=auth_headers).json()
        s = api.get(f"{BASE_URL}/api/wallet/sol/info", headers=auth_headers).json()
        assert a["btc_address"] == b["address"], f"btc mismatch: {a['btc_address']} vs {b['address']}"
        assert a["sol_address"] == s["address"], f"sol mismatch: {a['sol_address']} vs {s['address']}"

    def test_assets_zero_balances_for_fresh_wallet(self, api, auth_headers):
        r = api.get(f"{BASE_URL}/api/wallet/assets", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        by_sym = {a["symbol"]: a for a in body["assets"]}
        for sym in ("BTC", "ETH", "USDC", "SOL"):
            assert sym in by_sym, f"missing {sym}"
            assert by_sym[sym]["amount"] == 0, f"{sym} not zero: {by_sym[sym]['amount']}"
            assert by_sym[sym]["on_chain"] is True, f"{sym} on_chain not true"

    def test_assets_networks_correct(self, api, auth_headers):
        body = api.get(f"{BASE_URL}/api/wallet/assets", headers=auth_headers).json()
        by_sym = {a["symbol"]: a for a in body["assets"]}
        assert by_sym["ETH"]["network"] == "Sepolia"
        assert by_sym["USDC"]["network"] == "Sepolia"
        assert by_sym["BTC"]["network"] == "Testnet"
        assert by_sym["SOL"]["network"] == "Devnet"


# ---------------- Asset info endpoints ----------------
class TestBtcInfo:
    def test_btc_info_shape(self, api, auth_headers):
        r = api.get(f"{BASE_URL}/api/wallet/btc/info", headers=auth_headers)
        assert r.status_code == 200, r.text[:300]
        b = r.json()
        assert "balance_sats" in b and isinstance(b["balance_sats"], int)
        assert "balance_btc" in b
        assert b["network"] == "Testnet"
        assert "mempool.space/testnet" in (b.get("explorer") or ""), f"bad explorer: {b.get('explorer')}"
        assert b.get("faucet"), "expected faucet url for testnet"
        assert b["send_supported"] is False


class TestSolInfo:
    def test_sol_info_shape(self, api, auth_headers):
        r = api.get(f"{BASE_URL}/api/wallet/sol/info", headers=auth_headers)
        assert r.status_code == 200, r.text[:300]
        b = r.json()
        assert "balance_lamports" in b and isinstance(b["balance_lamports"], int)
        assert "balance_sol" in b
        assert b["network"] == "Devnet"
        assert "cluster=devnet" in (b.get("explorer") or ""), f"bad explorer: {b.get('explorer')}"
        assert b.get("faucet"), "expected faucet for devnet"
        assert b["send_supported"] is False


class TestUsdcInfo:
    def test_usdc_info_shape(self, api, auth_headers):
        r = api.get(f"{BASE_URL}/api/wallet/usdc/info", headers=auth_headers)
        assert r.status_code == 200, r.text[:300]
        b = r.json()
        assert "balance_micro" in b and isinstance(b["balance_micro"], int)
        assert "balance_usdc" in b
        assert b["network"] == "Sepolia"
        assert b["send_supported"] is True
        # USDC contract must be the Sepolia Circle deployment
        assert b.get("contract", "").lower() == "0x1c7d4b196cb0c7b01d743fbc6116a902379c7238"


# ---------------- USDC send validation ----------------
class TestUsdcSendValidation:
    def test_invalid_address_returns_400(self, api, auth_headers):
        r = api.post(
            f"{BASE_URL}/api/wallet/usdc/send",
            headers=auth_headers,
            json={"to_address": "not-an-address", "amount_usdc": 1.0},
        )
        assert r.status_code == 400, f"expected 400 got {r.status_code}: {r.text[:200]}"
        assert "invalid" in r.text.lower() or "address" in r.text.lower()

    def test_short_hex_address_returns_400(self, api, auth_headers):
        r = api.post(
            f"{BASE_URL}/api/wallet/usdc/send",
            headers=auth_headers,
            json={"to_address": "0x1234", "amount_usdc": 1.0},
        )
        assert r.status_code == 400

    def test_valid_address_zero_balance_returns_400_insufficient(self, api, auth_headers):
        # Fresh wallet has zero USDC on Sepolia -> Insufficient
        valid_to = "0x" + ("a" * 40)
        r = api.post(
            f"{BASE_URL}/api/wallet/usdc/send",
            headers=auth_headers,
            json={"to_address": valid_to, "amount_usdc": 1.0},
        )
        # Could be 400 (Insufficient USDC) or 502 (USDC balance error from RPC). 400 expected.
        assert r.status_code == 400, f"expected 400 (Insufficient) got {r.status_code}: {r.text[:300]}"
        assert "insufficient" in r.text.lower() or "usdc" in r.text.lower()

    def test_endpoint_exists_not_404(self, api, auth_headers):
        r = api.post(
            f"{BASE_URL}/api/wallet/usdc/send",
            headers=auth_headers,
            json={"to_address": "not-an-address", "amount_usdc": 1.0},
        )
        assert r.status_code != 404, "USDC send endpoint must exist"


# ---------------- Regression ----------------
class TestRegression:
    def test_health_get(self, api):
        r = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}

    def test_health_head(self, api):
        r = requests.head(f"{BASE_URL}/api/health", timeout=10)
        assert r.status_code == 200

    def test_login_smoketest(self, api):
        r = api.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "smoketest@vaulted.app", "password": "test1234"},
        )
        assert r.status_code == 200, r.text[:200]
        body = r.json()
        assert "access_token" in body and "user" in body

    def test_chat_contacts_alphabetical(self, api, auth_headers):
        r = api.get(f"{BASE_URL}/api/chat/contacts", headers=auth_headers)
        assert r.status_code == 200
        names = [c.get("name") for c in r.json()]
        assert names == sorted(names, key=lambda n: n.lower()), f"not alphabetical: {names}"

    def test_eth_info_still_works(self, api, auth_headers):
        r = api.get(f"{BASE_URL}/api/wallet/eth/info", headers=auth_headers)
        assert r.status_code == 200, r.text[:200]
        b = r.json()
        assert b.get("network") == "Sepolia"
        assert b.get("address", "").startswith("0x")

    def test_transactions_export_streams_csv(self, api, auth_headers):
        r = api.get(f"{BASE_URL}/api/transactions/export", headers=auth_headers)
        assert r.status_code == 200
        ct = r.headers.get("content-type", "")
        assert "text/csv" in ct, f"expected text/csv got {ct}"
        # First line should be the header row
        first = r.text.split("\n", 1)[0]
        assert "Date" in first and "Asset" in first, f"unexpected csv header: {first}"
