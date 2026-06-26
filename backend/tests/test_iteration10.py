"""Iteration 10 — Bug fix verification: legacy user (pre-BIP39) multichain backfill.

Bug repro: smoketest@vaulted.app was created BEFORE BIP-39 mnemonic was stored on the user
doc, so calling /api/wallet/btc/info and /api/wallet/sol/info used to 400 ('mnemonic missing').

Expected after fix:
- /api/wallet/btc/info and /api/wallet/sol/info return 200 with derived testnet3/devnet
  addresses for the legacy smoketest account.
- The existing ETH wallet_address is preserved unchanged (eth_info before == after).
- Subsequent calls return the same addresses (idempotent).
- Plus all iteration_9 regression flows still work.
"""
import os
import re
import uuid
import pytest
import requests

BASE_URL = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/")

BTC_TESTNET_RE = re.compile(r"^[mn][1-9A-HJ-NP-Za-km-z]{25,40}$")
SOL_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
ETH_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ---------------- Legacy smoketest account ----------------
@pytest.fixture(scope="module")
def smoketest_headers(api):
    r = api.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "smoketest@vaulted.app", "password": "test1234"},
    )
    assert r.status_code == 200, f"smoketest login failed: {r.status_code} {r.text[:200]}"
    tok = r.json()["access_token"]
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


class TestLegacyBackfill:
    """The critical bug fix: legacy smoketest user must get BTC + SOL addresses on demand."""

    def test_eth_info_works_before_backfill(self, api, smoketest_headers):
        """Record ETH address BEFORE any multichain backfill happens."""
        r = api.get(f"{BASE_URL}/api/wallet/eth/info", headers=smoketest_headers)
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert ETH_RE.match(body.get("address", "")), f"bad eth addr: {body.get('address')}"
        # stash for the post-backfill comparison test
        pytest.eth_addr_before = body["address"]

    def test_btc_info_returns_200_for_legacy_user(self, api, smoketest_headers):
        """Was 400 'mnemonic missing' before fix; must now succeed with a testnet addr."""
        r = api.get(f"{BASE_URL}/api/wallet/btc/info", headers=smoketest_headers)
        assert r.status_code == 200, f"BTC info still failing: {r.status_code} {r.text[:300]}"
        body = r.json()
        addr = body.get("address")
        assert addr and BTC_TESTNET_RE.match(addr), f"bad btc testnet addr: {addr!r}"
        assert body.get("network") == "Testnet"
        pytest.btc_addr_first = addr

    def test_sol_info_returns_200_for_legacy_user(self, api, smoketest_headers):
        """Was 400 'mnemonic missing' before fix; must now succeed with a devnet addr."""
        r = api.get(f"{BASE_URL}/api/wallet/sol/info", headers=smoketest_headers)
        assert r.status_code == 200, f"SOL info still failing: {r.status_code} {r.text[:300]}"
        body = r.json()
        addr = body.get("address")
        assert addr and SOL_RE.match(addr), f"bad sol addr: {addr!r}"
        assert body.get("network") == "Devnet"
        pytest.sol_addr_first = addr

    def test_eth_address_unchanged_after_backfill(self, api, smoketest_headers):
        """Critical guarantee: the legacy ETH wallet_address must NOT mutate."""
        r = api.get(f"{BASE_URL}/api/wallet/eth/info", headers=smoketest_headers)
        assert r.status_code == 200, r.text[:300]
        after = r.json()["address"]
        assert after == pytest.eth_addr_before, (
            f"ETH address mutated by backfill! before={pytest.eth_addr_before} after={after}"
        )

    def test_btc_idempotent_second_call(self, api, smoketest_headers):
        r = api.get(f"{BASE_URL}/api/wallet/btc/info", headers=smoketest_headers)
        assert r.status_code == 200
        assert r.json()["address"] == pytest.btc_addr_first, "BTC address changed between calls!"

    def test_sol_idempotent_second_call(self, api, smoketest_headers):
        r = api.get(f"{BASE_URL}/api/wallet/sol/info", headers=smoketest_headers)
        assert r.status_code == 200
        assert r.json()["address"] == pytest.sol_addr_first, "SOL address changed between calls!"

    def test_assets_endpoint_returns_all_three_addresses_for_legacy(self, api, smoketest_headers):
        r = api.get(f"{BASE_URL}/api/wallet/assets", headers=smoketest_headers)
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert body.get("wallet_address") == pytest.eth_addr_before
        assert body.get("btc_address") == pytest.btc_addr_first
        assert body.get("sol_address") == pytest.sol_addr_first


# ---------------- Fresh user — regression that backfill doesn't regress new flows ----------------
@pytest.fixture(scope="module")
def fresh_user(api):
    email = f"TEST_iter10_{uuid.uuid4().hex[:8]}@vaulted.app"
    r = api.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": email, "password": "test1234", "name": "Iter10 Tester"},
    )
    assert r.status_code == 200, f"register failed: {r.status_code} {r.text[:200]}"
    return {"email": email, "token": r.json()["access_token"]}


@pytest.fixture(scope="module")
def fresh_headers(fresh_user):
    return {"Authorization": f"Bearer {fresh_user['token']}", "Content-Type": "application/json"}


class TestFreshUserStillWorks:
    def test_fresh_btc_info(self, api, fresh_headers):
        r = api.get(f"{BASE_URL}/api/wallet/btc/info", headers=fresh_headers)
        assert r.status_code == 200
        assert BTC_TESTNET_RE.match(r.json()["address"])

    def test_fresh_sol_info(self, api, fresh_headers):
        r = api.get(f"{BASE_URL}/api/wallet/sol/info", headers=fresh_headers)
        assert r.status_code == 200
        assert SOL_RE.match(r.json()["address"])

    def test_fresh_assets_three_addresses(self, api, fresh_headers):
        body = api.get(f"{BASE_URL}/api/wallet/assets", headers=fresh_headers).json()
        assert ETH_RE.match(body["wallet_address"])
        assert BTC_TESTNET_RE.match(body["btc_address"])
        assert SOL_RE.match(body["sol_address"])

    def test_fresh_usdc_info(self, api, fresh_headers):
        b = api.get(f"{BASE_URL}/api/wallet/usdc/info", headers=fresh_headers).json()
        assert b["network"] == "Sepolia"
        assert b.get("contract", "").lower() == "0x1c7d4b196cb0c7b01d743fbc6116a902379c7238"
        assert b["send_supported"] is True


# ---------------- Iteration 9 regression ----------------
class TestIter9Regression:
    def test_health_get(self):
        r = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}

    def test_health_head(self):
        r = requests.head(f"{BASE_URL}/api/health", timeout=10)
        assert r.status_code == 200

    def test_contacts_alphabetical(self, api, smoketest_headers):
        r = api.get(f"{BASE_URL}/api/chat/contacts", headers=smoketest_headers)
        assert r.status_code == 200
        names = [c.get("name") for c in r.json()]
        assert names == sorted(names, key=lambda n: n.lower()), f"not alphabetical: {names}"

    def test_usdc_send_invalid_address(self, api, fresh_headers):
        r = api.post(
            f"{BASE_URL}/api/wallet/usdc/send",
            headers=fresh_headers,
            json={"to_address": "not-an-address", "amount_usdc": 1.0},
        )
        assert r.status_code == 400

    def test_usdc_send_short_hex(self, api, fresh_headers):
        r = api.post(
            f"{BASE_URL}/api/wallet/usdc/send",
            headers=fresh_headers,
            json={"to_address": "0x1234", "amount_usdc": 1.0},
        )
        assert r.status_code == 400

    def test_usdc_send_valid_zero_balance(self, api, fresh_headers):
        valid = "0x" + ("a" * 40)
        r = api.post(
            f"{BASE_URL}/api/wallet/usdc/send",
            headers=fresh_headers,
            json={"to_address": valid, "amount_usdc": 1.0},
        )
        assert r.status_code == 400
        assert "insufficient" in r.text.lower() or "usdc" in r.text.lower()

    def test_chat_send_crypto_one_on_one(self, api, smoketest_headers):
        # find a contact to send to
        contacts = api.get(f"{BASE_URL}/api/chat/contacts", headers=smoketest_headers).json()
        assert len(contacts) > 0
        target = contacts[0]
        recipient_id = target.get("id") or target.get("user_id") or target.get("contact_id")
        if not recipient_id:
            pytest.skip(f"contact has no id-like field: {target}")
        r = api.post(
            f"{BASE_URL}/api/chat/send_crypto",
            headers=smoketest_headers,
            json={"to_user_id": recipient_id, "asset": "USDC", "amount": 1.0, "memo": "iter10 test"},
        )
        # acceptable: 200 (sent) or 400 (validation) or 404 (group only) — must NOT 500
        assert r.status_code < 500, f"5xx on chat send_crypto: {r.status_code} {r.text[:200]}"

    def test_transactions_export_csv(self, api, smoketest_headers):
        r = api.get(f"{BASE_URL}/api/transactions/export", headers=smoketest_headers)
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "")
        first = r.text.split("\n", 1)[0]
        assert "Date" in first and "Asset" in first
