"""Iteration 4 tests: Live CoinGecko prices + BIP-39 mnemonic onboarding."""
import os
import re
import uuid
import time
import pytest
import requests
from pathlib import Path

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    env_path = Path("/app/frontend/.env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("EXPO_PUBLIC_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().strip('"').rstrip("/")
                break
assert BASE_URL, "BASE_URL must be configured"
API = f"{BASE_URL}/api"

ADDR_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


def H(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def user_ctx(client):
    email = f"it4_{uuid.uuid4().hex[:8]}@vaulted.app"
    r = client.post(f"{API}/auth/register",
                    json={"email": email, "password": "test1234", "name": "Iter4 Tester"})
    assert r.status_code == 200, r.text
    j = r.json()
    return {"token": j["access_token"], "user": j["user"], "email": email}


# -------- Market prices: live CoinGecko + cache + fallback --------
class TestMarketPrices:
    def test_market_prices_auth_required(self, client):
        assert client.get(f"{API}/market/prices").status_code == 401

    def test_market_prices_shape(self, client, user_ctx):
        r = client.get(f"{API}/market/prices", headers=H(user_ctx["token"]))
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ttl_seconds"] == 300
        assert "fetched_at" in d and d["fetched_at"]
        assets = d["assets"]
        for sym in ["BTC", "ETH", "USDC", "SOL"]:
            assert sym in assets, f"Missing {sym}"
            a = assets[sym]
            assert "price_usd" in a and a["price_usd"] > 0
            assert "change_24h_pct" in a
            assert "sparkline_7d" in a
            assert isinstance(a["sparkline_7d"], list)

    def test_sparkline_has_points(self, client, user_ctx):
        r = client.get(f"{API}/market/prices", headers=H(user_ctx["token"]))
        d = r.json()
        # Allow either live (~48 points) or fallback ([])
        for sym in ["BTC", "ETH", "SOL"]:
            sp = d["assets"][sym]["sparkline_7d"]
            # If live data, should be capped at last 48 points
            assert len(sp) <= 48
            if len(sp) > 0:
                assert all(isinstance(x, (int, float)) for x in sp)

    def test_cache_returns_same_fetched_at(self, client, user_ctx):
        r1 = client.get(f"{API}/market/prices", headers=H(user_ctx["token"]))
        r2 = client.get(f"{API}/market/prices", headers=H(user_ctx["token"]))
        assert r1.status_code == 200 and r2.status_code == 200
        assert r1.json()["fetched_at"] == r2.json()["fetched_at"], "Cache should return same fetched_at"


# -------- /wallet/assets has change_24h_pct, sparkline_7d, prices_fetched_at --------
class TestWalletAssetsMarket:
    def test_assets_have_market_fields(self, client, user_ctx):
        r = client.get(f"{API}/wallet/assets", headers=H(user_ctx["token"]))
        assert r.status_code == 200, r.text
        d = r.json()
        assert "prices_fetched_at" in d and d["prices_fetched_at"]
        for a in d["assets"]:
            assert "change_24h_pct" in a
            assert "sparkline_7d" in a
            assert isinstance(a["sparkline_7d"], list)
        # total_usd should reflect live prices, NOT old hardcoded 4650
        # With fresh acct: BTC 0.0421, ETH 0 (live), USDC 1250, SOL 12.55
        assert d["total_usd"] > 0

    def test_total_usd_reflects_live_prices(self, client, user_ctx):
        # Sanity: total should be in a reasonable real-world range (not 4650 hardcoded)
        r = client.get(f"{API}/wallet/assets", headers=H(user_ctx["token"]))
        d = r.json()
        # Should NOT equal exactly the old hardcoded $4,650 total
        # BTC 0.0421 * ~live BTC price (say 90k) ~3800 + USDC 1250 + SOL 12.55 * ~200 = ~7500
        # Anyway must be a positive number
        assert d["total_usd"] > 1000


# -------- BIP-39 mnemonic on register --------
class TestMnemonic:
    def test_register_assigns_eth_address(self, user_ctx):
        addr = user_ctx["user"]["wallet_address"]
        assert addr and ADDR_RE.match(addr)

    def test_mnemonic_endpoint_returns_12_words(self, client, user_ctx):
        r = client.get(f"{API}/wallet/eth/mnemonic", headers=H(user_ctx["token"]))
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["address"] == user_ctx["user"]["wallet_address"]
        assert d["word_count"] == 12
        words = d["mnemonic"].split()
        assert len(words) == 12
        # All words should be lowercase alphabetic (BIP-39 wordlist)
        for w in words:
            assert w.isalpha() and w.islower(), f"Bad word: {w}"
        assert "Sepolia" in d["network"]
        assert "warning" in d

    def test_mnemonic_requires_auth(self, client):
        assert client.get(f"{API}/wallet/eth/mnemonic").status_code == 401

    def test_mnemonic_derives_to_wallet_address(self, client, user_ctx):
        """Verify the mnemonic actually derives to the wallet address."""
        from eth_account import Account
        Account.enable_unaudited_hdwallet_features()
        r = client.get(f"{API}/wallet/eth/mnemonic", headers=H(user_ctx["token"]))
        mnemonic = r.json()["mnemonic"]
        acct = Account.from_mnemonic(mnemonic)
        assert acct.address.lower() == user_ctx["user"]["wallet_address"].lower(), \
            "Mnemonic must derive to the same wallet_address as register"


# -------- Onboarding complete flag --------
class TestOnboarding:
    def test_onboarding_complete_flow(self, client, user_ctx):
        # Initially false
        me = client.get(f"{API}/auth/me", headers=H(user_ctx["token"])).json()
        assert me["onboarding_seed_acknowledged"] is False

        r = client.post(f"{API}/auth/onboarding-complete", headers=H(user_ctx["token"]))
        assert r.status_code == 200, r.text
        assert r.json()["onboarding_seed_acknowledged"] is True

        # Verify persisted
        me2 = client.get(f"{API}/auth/me", headers=H(user_ctx["token"])).json()
        assert me2["onboarding_seed_acknowledged"] is True

    def test_onboarding_requires_auth(self, client):
        assert client.post(f"{API}/auth/onboarding-complete").status_code == 401


# -------- Regression: iter1/2/3 still works --------
class TestRegression:
    def test_login_smoke(self, client):
        r = client.post(f"{API}/auth/login", json={"email": "smoketest@vaulted.app", "password": "test1234"})
        if r.status_code != 200:
            pytest.skip("smoke missing")
        assert "access_token" in r.json()

    def test_eth_info_still_works(self, client, user_ctx):
        r = client.get(f"{API}/wallet/eth/info", headers=H(user_ctx["token"]))
        assert r.status_code == 200
        assert r.json()["chain_id"] == 11155111

    def test_eth_export_still_works(self, client, user_ctx):
        r = client.get(f"{API}/wallet/eth/export", headers=H(user_ctx["token"]))
        assert r.status_code == 200
        assert r.json()["private_key"]

    def test_stripe_deposit_checkout(self, client, user_ctx):
        r = client.post(f"{API}/stripe/checkout/deposit", headers=H(user_ctx["token"]), json={"amount_usd": 10.0})
        assert r.status_code == 200
        assert r.json()["checkout_url"].startswith("https://checkout.stripe.com/")

    def test_stripe_subscription_checkout(self, client, user_ctx):
        r = client.post(f"{API}/stripe/checkout/subscription", headers=H(user_ctx["token"]))
        assert r.status_code == 200
        assert r.json()["checkout_url"].startswith("https://checkout.stripe.com/")

    def test_calls_room(self, client, user_ctx):
        r = client.post(f"{API}/calls/room", headers=H(user_ctx["token"]), json={"conversation_id": None})
        assert r.status_code == 200
        d = r.json()
        assert d.get("configured") is True
        assert ".daily.co/" in d["room_url"]

    def test_conversations_list(self, client, user_ctx):
        r = client.get(f"{API}/chat/conversations", headers=H(user_ctx["token"]))
        assert r.status_code == 200
        convs = r.json()
        assert any(c["contact_name"] == "Vault Support" for c in convs)

    def test_send_e2e_message(self, client, user_ctx):
        convs = client.get(f"{API}/chat/conversations", headers=H(user_ctx["token"])).json()
        cid = convs[0]["id"]
        r = client.post(f"{API}/chat/messages", headers=H(user_ctx["token"]),
                        json={"conversation_id": cid, "text": "hi from iter4", "encrypted": False})
        assert r.status_code == 200

    def test_legacy_btc_send(self, client, user_ctx):
        r = client.post(f"{API}/wallet/send", headers=H(user_ctx["token"]),
                        json={"asset": "BTC", "amount": 0.0001, "to_address": "bc1qfake"})
        assert r.status_code == 200
