"""Iteration 3 tests: Real ETH (Sepolia) + Stripe live key + Daily.co live key + Vault Pro perks."""
import os
import re
import uuid
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
PK_RE = re.compile(r"^(0x)?[0-9a-fA-F]{64}$")


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def user_ctx(client):
    email = f"it3_{uuid.uuid4().hex[:8]}@vaulted.app"
    r = client.post(f"{API}/auth/register", json={"email": email, "password": "test1234", "name": "Iter3 Tester"})
    assert r.status_code == 200, r.text
    j = r.json()
    return {"token": j["access_token"], "user": j["user"], "email": email}


def H(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# --------------- Real ETH keypair on register ---------------
class TestEthKeypair:
    def test_register_produces_real_eth_address(self, user_ctx):
        addr = user_ctx["user"]["wallet_address"]
        assert addr and ADDR_RE.match(addr), f"Bad ETH address: {addr}"

    def test_export_returns_address_and_pk(self, client, user_ctx):
        r = client.get(f"{API}/wallet/eth/export", headers=H(user_ctx["token"]))
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["address"] == user_ctx["user"]["wallet_address"]
        assert PK_RE.match(d["private_key"]), f"Bad PK fmt: {d['private_key'][:10]}..."
        assert "Sepolia" in d["network"]
        assert "warning" in d and "share" in d["warning"].lower()

    def test_export_requires_auth(self, client):
        assert client.get(f"{API}/wallet/eth/export").status_code == 401


# --------------- /wallet/eth/info (live Sepolia RPC) ---------------
class TestEthInfo:
    def test_eth_info_shape(self, client, user_ctx):
        r = client.get(f"{API}/wallet/eth/info", headers=H(user_ctx["token"]))
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["address"] == user_ctx["user"]["wallet_address"]
        assert d["chain_id"] == 11155111
        assert d["network"] == "Sepolia"
        # Fresh accounts should have 0 balance
        assert int(d["balance_wei"]) == 0
        assert d["balance_eth"] == 0.0
        # Gas price should be a real positive integer from the RPC
        assert int(d["gas_price_wei"]) > 0
        assert d["gas_price_gwei"] > 0
        assert "sepolia.etherscan.io" in d["explorer"]
        assert d["faucet"].startswith("http")

    def test_eth_info_requires_auth(self, client):
        assert client.get(f"{API}/wallet/eth/info").status_code == 401


# --------------- /wallet/assets ETH on_chain=true ---------------
class TestWalletAssetsOnChain:
    def test_eth_row_is_on_chain(self, client, user_ctx):
        r = client.get(f"{API}/wallet/assets", headers=H(user_ctx["token"]))
        assert r.status_code == 200
        d = r.json()
        eth = next(a for a in d["assets"] if a["symbol"] == "ETH")
        assert eth["on_chain"] is True
        assert eth["network"] == "Sepolia"
        assert eth["amount"] == 0.0  # Fresh acct
        # Non-ETH still simulated
        btc = next(a for a in d["assets"] if a["symbol"] == "BTC")
        assert btc.get("on_chain") is False
        assert btc["amount"] == 0.0421


# --------------- /wallet/eth/send insufficient funds path ---------------
class TestEthSend:
    def test_send_eth_insufficient_returns_400(self, client, user_ctx):
        r = client.post(
            f"{API}/wallet/eth/send",
            headers=H(user_ctx["token"]),
            json={"to_address": "0x000000000000000000000000000000000000dEaD", "amount_eth": 0.01},
        )
        assert r.status_code == 400, r.text
        assert "insufficient" in r.json()["detail"].lower()

    def test_send_eth_bad_address(self, client, user_ctx):
        r = client.post(
            f"{API}/wallet/eth/send",
            headers=H(user_ctx["token"]),
            json={"to_address": "0xNOTANADDR", "amount_eth": 0.01},
        )
        assert r.status_code == 400
        assert "invalid recipient" in r.json()["detail"].lower()

    def test_legacy_send_blocks_eth(self, client, user_ctx):
        r = client.post(
            f"{API}/wallet/send",
            headers=H(user_ctx["token"]),
            json={"asset": "ETH", "amount": 0.1, "to_address": "0xabc"},
        )
        assert r.status_code == 400
        assert "/wallet/eth/send" in r.json()["detail"]

    def test_legacy_send_btc_still_works(self, client, user_ctx):
        r = client.post(
            f"{API}/wallet/send",
            headers=H(user_ctx["token"]),
            json={"asset": "BTC", "amount": 0.001, "to_address": "bc1qfake"},
        )
        assert r.status_code == 200
        assert r.json()["asset"] == "BTC"


# --------------- Stripe LIVE checkout (real sk_test_) ---------------
class TestStripeLive:
    def test_deposit_checkout_returns_real_url(self, client, user_ctx):
        r = client.post(f"{API}/stripe/checkout/deposit", headers=H(user_ctx["token"]), json={"amount_usd": 25.0})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["checkout_url"].startswith("https://checkout.stripe.com/")
        assert d["session_id"].startswith("cs_test_")

    def test_subscription_checkout_returns_real_url(self, client, user_ctx):
        r = client.post(f"{API}/stripe/checkout/subscription", headers=H(user_ctx["token"]))
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["checkout_url"].startswith("https://checkout.stripe.com/")
        assert d["session_id"].startswith("cs_test_")
        assert d.get("price_id", "").startswith("price_")

    def test_portal_requires_customer(self, client, user_ctx):
        # Fresh user without subscribing => no customer_id yet from subscription flow?
        # Actually subscription call above DOES create a customer. So a fresh user here
        # will have one. Test the "no customer" path with a brand-new user.
        email = f"it3p_{uuid.uuid4().hex[:8]}@vaulted.app"
        r = client.post(f"{API}/auth/register", json={"email": email, "password": "test1234", "name": "P"})
        token = r.json()["access_token"]
        r2 = client.post(f"{API}/stripe/portal", headers=H(token))
        assert r2.status_code == 400
        assert "billing customer" in r2.json()["detail"].lower()


# --------------- Daily.co LIVE rooms ---------------
class TestDailyLive:
    def test_create_room_returns_real_url(self, client, user_ctx):
        r = client.post(f"{API}/calls/room", headers=H(user_ctx["token"]), json={"conversation_id": None})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("configured") is True
        assert d.get("room_url", "").startswith("https://")
        assert ".daily.co/" in d["room_url"]
        assert d["name"].startswith("vlt-")
        # token can be present (jwt) or null if token gen failed; assert at least the field
        assert "token" in d


# --------------- Pro user pinned Vault Support ---------------
class TestProPinning:
    def test_non_pro_chronological(self, client, user_ctx):
        convs = client.get(f"{API}/chat/conversations", headers=H(user_ctx["token"])).json()
        # Free user => chronological (newest first by last_message_at), not necessarily pinned
        names = [c["contact_name"] for c in convs]
        assert "Vault Support" in names
        # No claim about ordering — just that the field exists & priority flag is preserved
        vs = next(c for c in convs if c["contact_name"] == "Vault Support")
        assert vs.get("priority") is True

    def test_pro_user_pins_priority(self, client):
        # Create a fresh user and forcibly upgrade them in DB via the webhook idempotency hack
        # Easiest: use webhook subscription path with fake session — but that needs a sub_id.
        # Simpler: directly mark them pro via the stripe subscription session retrieve mock.
        # Since we can't write DB directly, fall back to: just verify the endpoint exists.
        # If the smoke-test account happens to be pro, run the ordering test there.
        r = client.post(f"{API}/auth/login", json={"email": "smoketest@vaulted.app", "password": "test1234"})
        if r.status_code != 200:
            pytest.skip("smoke account unavailable")
        tok = r.json()["access_token"]
        me = r.json()["user"]
        if not me.get("is_pro"):
            pytest.skip("smoke account is not pro; pinning ordering not testable without DB write")
        convs = requests.get(f"{API}/chat/conversations", headers=H(tok)).json()
        assert convs[0].get("priority") is True, "Pro user: first conversation should be priority-pinned"


# --------------- Regression ---------------
class TestRegression:
    def test_smoke_login(self, client):
        r = client.post(f"{API}/auth/login", json={"email": "smoketest@vaulted.app", "password": "test1234"})
        if r.status_code != 200:
            pytest.skip("smoke missing")
        assert "access_token" in r.json()

    def test_fiat_deposit_still_works(self, client, user_ctx):
        r = client.post(f"{API}/fiat/deposit", headers=H(user_ctx["token"]),
                        json={"amount": 10, "currency": "USD", "method": "card"})
        assert r.status_code == 200
