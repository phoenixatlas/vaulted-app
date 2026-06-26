"""Iteration 11 — Semantic risk closed: `mnemonic_origin` tagging on the user doc.

Bug context (carried from iter10 critical_code_review_comments[3]): legacy users had an
`eth_mnemonic` written to their doc by the backfill, but that mnemonic does NOT derive
their existing ETH key. Previously /wallet/eth/mnemonic happily returned it, which would
silently mislead anyone trying to restore their ETH funds elsewhere.

Fix verified here:
- Fresh registrations: user.mnemonic_origin == 'eth_native' → /wallet/eth/mnemonic returns
  200 with the mnemonic + address.
- Legacy smoketest@vaulted.app (after backfill): mnemonic_origin == 'multichain_only'
  → /wallet/eth/mnemonic returns 409 with a clear explainer.

Plus full iter9 + iter10 regression suite.
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
USDC_CONTRACT_SEPOLIA = "0x1c7d4b196cb0c7b01d743fbc6116a902379c7238"


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ---------------- Legacy account (smoketest) ----------------
@pytest.fixture(scope="module")
def smoketest_headers(api):
    r = api.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "smoketest@vaulted.app", "password": "test1234"},
    )
    assert r.status_code == 200, f"smoketest login failed: {r.status_code} {r.text[:200]}"
    tok = r.json()["access_token"]
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


# ---------------- Freshly-registered account (eth_native) ----------------
@pytest.fixture(scope="module")
def fresh_user(api):
    email = f"TEST_iter11_{uuid.uuid4().hex[:8]}@vaulted.app"
    r = api.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": email, "password": "test1234", "name": "Iter11 Tester"},
    )
    assert r.status_code == 200, f"register failed: {r.status_code} {r.text[:200]}"
    return {"email": email, "token": r.json()["access_token"], "user": r.json()["user"]}


@pytest.fixture(scope="module")
def fresh_headers(fresh_user):
    return {"Authorization": f"Bearer {fresh_user['token']}", "Content-Type": "application/json"}


# ============================================================
# Section A: mnemonic_origin tagging on fresh registration
# ============================================================
class TestFreshUserEthNative:
    """A freshly-registered user must be tagged 'eth_native' and /wallet/eth/mnemonic
    must return 200 with a valid 12-word phrase + matching ETH address."""

    def test_eth_mnemonic_endpoint_returns_200_for_fresh(self, api, fresh_headers, fresh_user):
        r = api.get(f"{BASE_URL}/api/wallet/eth/mnemonic", headers=fresh_headers)
        assert r.status_code == 200, f"fresh user blocked from /eth/mnemonic: {r.status_code} {r.text[:300]}"
        body = r.json()
        # Shape checks
        assert "mnemonic" in body and isinstance(body["mnemonic"], str)
        assert body.get("word_count") == 12, f"expected 12 words, got {body.get('word_count')}"
        words = body["mnemonic"].split()
        assert len(words) == 12, f"mnemonic doesn't split to 12 tokens: {len(words)}"
        # Address must match the public user record
        assert ETH_RE.match(body.get("address", "")), f"bad eth address: {body.get('address')}"
        assert body["address"].lower() == fresh_user["user"]["wallet_address"].lower()
        # Network/warning sanity
        assert "Sepolia" in body.get("network", "")
        assert "warning" in body and len(body["warning"]) > 0

    def test_fresh_user_has_eth_address_derivable_from_mnemonic(self, api, fresh_headers, fresh_user):
        """The 'eth_native' tag is meaningful only if the mnemonic actually derives the
        wallet_address via BIP44 m/44'/60'/0'/0/0. Verify this end-to-end."""
        r = api.get(f"{BASE_URL}/api/wallet/eth/mnemonic", headers=fresh_headers)
        assert r.status_code == 200
        mnemonic = r.json()["mnemonic"]
        # Derive locally using eth_account (same lib used by the server)
        from eth_account import Account
        Account.enable_unaudited_hdwallet_features()
        derived = Account.from_mnemonic(mnemonic)
        assert derived.address.lower() == fresh_user["user"]["wallet_address"].lower(), (
            f"eth_native tag is a LIE: mnemonic derives {derived.address} but "
            f"user.wallet_address is {fresh_user['user']['wallet_address']}"
        )


# ============================================================
# Section B: legacy backfill tags origin = multichain_only
# ============================================================
class TestLegacyBackfillTagsOrigin:
    """Trigger the backfill for smoketest by calling /wallet/btc/info, then verify
    /wallet/eth/mnemonic now refuses with 409 + clear explainer."""

    def test_btc_info_triggers_backfill_for_legacy(self, api, smoketest_headers):
        r = api.get(f"{BASE_URL}/api/wallet/btc/info", headers=smoketest_headers)
        assert r.status_code == 200, f"BTC info failing for legacy user: {r.text[:300]}"
        addr = r.json().get("address")
        assert addr and BTC_TESTNET_RE.match(addr), f"bad btc testnet addr: {addr!r}"

    def test_eth_mnemonic_endpoint_returns_409_for_legacy(self, api, smoketest_headers):
        """The critical semantic guard: legacy users (multichain_only) must NOT be shown
        a mnemonic that doesn't derive their ETH key."""
        r = api.get(f"{BASE_URL}/api/wallet/eth/mnemonic", headers=smoketest_headers)
        assert r.status_code == 409, (
            f"expected 409 for multichain_only user, got {r.status_code}: {r.text[:300]}"
        )
        body = r.json()
        detail = body.get("detail", "")
        # Explainer must mention the recovery phrase semantic + an alternative
        assert "recovery phrase" in detail.lower(), f"explainer missing 'recovery phrase': {detail}"
        # Mnemonic value must NOT leak in the error body
        assert "mnemonic" not in body or body.get("mnemonic") is None, (
            f"sensitive mnemonic value leaked in 409 body: {body}"
        )

    def test_legacy_eth_info_still_returns_address(self, api, smoketest_headers):
        """Even though /eth/mnemonic is blocked, /eth/info still works (the ETH key
        exists, just not derivable from the on-file mnemonic)."""
        r = api.get(f"{BASE_URL}/api/wallet/eth/info", headers=smoketest_headers)
        assert r.status_code == 200, r.text[:300]
        assert ETH_RE.match(r.json().get("address", ""))


# ============================================================
# Section C: iter10 regression — backfill still works end-to-end
# ============================================================
class TestIter10Regression:
    """Re-verify the iter10 fix is still intact (legacy multichain backfill + idempotent)."""

    def test_legacy_btc_info_200(self, api, smoketest_headers):
        r = api.get(f"{BASE_URL}/api/wallet/btc/info", headers=smoketest_headers)
        assert r.status_code == 200
        assert BTC_TESTNET_RE.match(r.json()["address"])
        assert r.json().get("network") == "Testnet"

    def test_legacy_sol_info_200(self, api, smoketest_headers):
        r = api.get(f"{BASE_URL}/api/wallet/sol/info", headers=smoketest_headers)
        assert r.status_code == 200
        assert SOL_RE.match(r.json()["address"])
        assert r.json().get("network") == "Devnet"

    def test_legacy_usdc_info_200(self, api, smoketest_headers):
        r = api.get(f"{BASE_URL}/api/wallet/usdc/info", headers=smoketest_headers)
        assert r.status_code == 200
        b = r.json()
        assert b.get("network") == "Sepolia"
        assert b.get("contract", "").lower() == USDC_CONTRACT_SEPOLIA

    def test_legacy_assets_has_all_three(self, api, smoketest_headers):
        b = api.get(f"{BASE_URL}/api/wallet/assets", headers=smoketest_headers).json()
        assert ETH_RE.match(b["wallet_address"])
        assert BTC_TESTNET_RE.match(b["btc_address"])
        assert SOL_RE.match(b["sol_address"])

    def test_fresh_btc_info(self, api, fresh_headers):
        r = api.get(f"{BASE_URL}/api/wallet/btc/info", headers=fresh_headers)
        assert r.status_code == 200
        assert BTC_TESTNET_RE.match(r.json()["address"])

    def test_fresh_sol_info(self, api, fresh_headers):
        r = api.get(f"{BASE_URL}/api/wallet/sol/info", headers=fresh_headers)
        assert r.status_code == 200
        assert SOL_RE.match(r.json()["address"])

    def test_fresh_eth_info(self, api, fresh_headers):
        r = api.get(f"{BASE_URL}/api/wallet/eth/info", headers=fresh_headers)
        assert r.status_code == 200
        assert ETH_RE.match(r.json()["address"])

    def test_fresh_usdc_info(self, api, fresh_headers):
        b = api.get(f"{BASE_URL}/api/wallet/usdc/info", headers=fresh_headers).json()
        assert b["network"] == "Sepolia"
        assert b.get("contract", "").lower() == USDC_CONTRACT_SEPOLIA


# ============================================================
# Section D: iter9 regression
# ============================================================
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

    def test_transactions_export_csv(self, api, smoketest_headers):
        r = api.get(f"{BASE_URL}/api/transactions/export", headers=smoketest_headers)
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "")
        first = r.text.split("\n", 1)[0]
        assert "Date" in first and "Asset" in first

    def test_chat_send_crypto_one_on_one_no_5xx(self, api, smoketest_headers):
        contacts = api.get(f"{BASE_URL}/api/chat/contacts", headers=smoketest_headers).json()
        assert len(contacts) > 0
        target = contacts[0]
        recipient_id = target.get("id") or target.get("user_id") or target.get("contact_id")
        if not recipient_id:
            pytest.skip(f"contact has no id-like field: {target}")
        r = api.post(
            f"{BASE_URL}/api/chat/send_crypto",
            headers=smoketest_headers,
            json={"to_user_id": recipient_id, "asset": "USDC", "amount": 1.0, "memo": "iter11"},
        )
        assert r.status_code < 500, f"5xx on chat send_crypto: {r.status_code} {r.text[:200]}"
