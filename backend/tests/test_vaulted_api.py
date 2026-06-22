"""Backend API tests for Vaulted Wallet."""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") if os.environ.get("EXPO_PUBLIC_BACKEND_URL") else None
if not BASE_URL:
    # Fallback to reading frontend .env
    from pathlib import Path
    env_path = Path("/app/frontend/.env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("EXPO_PUBLIC_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().strip('"').rstrip("/")
                break

assert BASE_URL, "BASE_URL must be configured"
API = f"{BASE_URL}/api"

SMOKE_EMAIL = "smoketest@vaulted.app"
SMOKE_PWD = "test1234"


@pytest.fixture(scope="session")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def fresh_user(client):
    """Register a fresh user; returns (token, user)."""
    email = f"test_{uuid.uuid4().hex[:8]}@vaulted.app"
    r = client.post(f"{API}/auth/register", json={"email": email, "password": "test1234", "name": "Fresh Tester"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert "access_token" in data and "user" in data
    return data["access_token"], data["user"], email


@pytest.fixture(scope="session")
def smoke_token(client):
    """Login the pre-seeded smoke account."""
    r = client.post(f"{API}/auth/login", json={"email": SMOKE_EMAIL, "password": SMOKE_PWD})
    if r.status_code != 200:
        pytest.skip(f"Smoke account login failed: {r.status_code} {r.text}")
    return r.json()["access_token"]


def auth(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ---------- Auth ----------
class TestAuth:
    def test_register_creates_user_and_seeds(self, client, fresh_user):
        token, user, _ = fresh_user
        assert user["wallet_address"].startswith("0x")
        # GET /me
        r = client.get(f"{API}/auth/me", headers=auth(token))
        assert r.status_code == 200
        assert r.json()["email"] == user["email"]

    def test_register_duplicate_rejected(self, client, fresh_user):
        _, _, email = fresh_user
        r = client.post(f"{API}/auth/register", json={"email": email, "password": "test1234", "name": "Dup"})
        assert r.status_code == 400

    def test_smoke_login(self, smoke_token):
        assert smoke_token

    def test_auth_required_endpoints_401(self, client):
        for path in ["/auth/me", "/wallet/assets", "/transactions", "/chat/conversations"]:
            r = client.get(f"{API}{path}")
            assert r.status_code == 401, f"{path} should require auth, got {r.status_code}"

    def test_invalid_bearer_token(self, client):
        r = client.get(f"{API}/auth/me", headers={"Authorization": "Bearer notavalidtoken"})
        assert r.status_code == 401


# ---------- Wallet ----------
class TestWallet:
    def test_wallet_assets_seeded(self, client, fresh_user):
        token, _, _ = fresh_user
        r = client.get(f"{API}/wallet/assets", headers=auth(token))
        assert r.status_code == 200
        data = r.json()
        assert "total_usd" in data and "wallet_address" in data and "assets" in data
        symbols = {a["symbol"] for a in data["assets"]}
        assert {"BTC", "ETH", "USDC", "SOL"}.issubset(symbols)
        # sorted desc by fiat_value
        fiats = [a["fiat_value"] for a in data["assets"]]
        assert fiats == sorted(fiats, reverse=True)
        assert data["total_usd"] > 0

    def test_send_debits_and_returns_tx(self, client, fresh_user):
        token, _, _ = fresh_user
        # before
        before = client.get(f"{API}/wallet/assets", headers=auth(token)).json()
        btc_before = next(a["amount"] for a in before["assets"] if a["symbol"] == "BTC")
        r = client.post(f"{API}/wallet/send", headers=auth(token), json={
            "asset": "BTC", "amount": 0.001, "to_address": "0xabc123"
        })
        assert r.status_code == 200, r.text
        tx = r.json()
        assert tx["tx_hash"].startswith("0x") and len(tx["tx_hash"]) > 10
        assert tx["asset"] == "BTC"
        # after
        after = client.get(f"{API}/wallet/assets", headers=auth(token)).json()
        btc_after = next(a["amount"] for a in after["assets"] if a["symbol"] == "BTC")
        assert round(btc_before - btc_after, 8) == 0.001

    def test_send_insufficient_balance(self, client, fresh_user):
        token, _, _ = fresh_user
        r = client.post(f"{API}/wallet/send", headers=auth(token), json={
            "asset": "BTC", "amount": 9999, "to_address": "0xabc"
        })
        assert r.status_code == 400
        assert "insufficient" in r.json()["detail"].lower()


# ---------- Fiat ----------
class TestFiat:
    def test_deposit_credits_usdc(self, client, fresh_user):
        token, _, _ = fresh_user
        before = client.get(f"{API}/wallet/assets", headers=auth(token)).json()
        usdc_before = next(a["amount"] for a in before["assets"] if a["symbol"] == "USDC")
        r = client.post(f"{API}/fiat/deposit", headers=auth(token), json={"amount": 100, "method": "card"})
        assert r.status_code == 200, r.text
        tx = r.json()
        assert tx["receipt_id"].startswith("VLT-")
        assert tx["type"] == "deposit"
        after = client.get(f"{API}/wallet/assets", headers=auth(token)).json()
        usdc_after = next(a["amount"] for a in after["assets"] if a["symbol"] == "USDC")
        assert round(usdc_after - usdc_before, 2) == 100.00

    def test_withdraw_debits_usdc(self, client, fresh_user):
        token, _, _ = fresh_user
        r = client.post(f"{API}/fiat/withdraw", headers=auth(token), json={"amount": 50, "method": "bank"})
        assert r.status_code == 200
        assert r.json()["receipt_id"].startswith("VLT-")

    def test_withdraw_insufficient(self, client, fresh_user):
        token, _, _ = fresh_user
        r = client.post(f"{API}/fiat/withdraw", headers=auth(token), json={"amount": 9_000_000, "method": "bank"})
        assert r.status_code == 400


# ---------- Transactions ----------
class TestTransactions:
    def test_list_includes_welcome_bonus(self, client, fresh_user):
        token, _, _ = fresh_user
        r = client.get(f"{API}/transactions", headers=auth(token))
        assert r.status_code == 200
        txs = r.json()
        assert isinstance(txs, list) and len(txs) >= 1
        assert any(t.get("counterparty") == "Welcome Bonus" for t in txs)
        # reverse chrono
        dates = [t["created_at"] for t in txs]
        assert dates == sorted(dates, reverse=True)


# ---------- Chat ----------
class TestChat:
    def test_seeded_conversations(self, client, fresh_user):
        token, _, _ = fresh_user
        r = client.get(f"{API}/chat/conversations", headers=auth(token))
        assert r.status_code == 200
        convs = r.json()
        assert len(convs) == 3

    def test_get_messages_marks_read_and_send(self, client, fresh_user):
        token, _, _ = fresh_user
        convs = client.get(f"{API}/chat/conversations", headers=auth(token)).json()
        cid = convs[0]["id"]
        r = client.get(f"{API}/chat/messages/{cid}", headers=auth(token))
        assert r.status_code == 200
        body = r.json()
        assert "conversation" in body and "messages" in body
        assert len(body["messages"]) >= 1
        # After get, unread should be 0
        convs2 = client.get(f"{API}/chat/conversations", headers=auth(token)).json()
        target = next(c for c in convs2 if c["id"] == cid)
        assert target["unread"] == 0

        # Send a message
        r2 = client.post(f"{API}/chat/messages", headers=auth(token), json={"conversation_id": cid, "text": "Hello secure world"})
        assert r2.status_code == 200
        msg = r2.json()
        assert msg["text"] == "Hello secure world"
        # Auto reply added; last_message updated
        convs3 = client.get(f"{API}/chat/conversations", headers=auth(token)).json()
        target3 = next(c for c in convs3 if c["id"] == cid)
        assert target3["last_message"] != "Welcome to Vaulted secure chat."

    def test_messages_unknown_conversation(self, client, fresh_user):
        token, _, _ = fresh_user
        r = client.get(f"{API}/chat/messages/{uuid.uuid4()}", headers=auth(token))
        assert r.status_code == 404


# ---------- Settings ----------
class TestSettings:
    def test_language_update(self, client, fresh_user):
        token, _, _ = fresh_user
        r = client.patch(f"{API}/auth/language", headers=auth(token), json={"language": "es"})
        assert r.status_code == 200 and r.json()["language"] == "es"
        me = client.get(f"{API}/auth/me", headers=auth(token)).json()
        assert me["language"] == "es"

    def test_security_toggles(self, client, fresh_user):
        token, _, _ = fresh_user
        r = client.patch(f"{API}/auth/security", headers=auth(token),
                         json={"biometric_enabled": True, "multisig_enabled": True})
        assert r.status_code == 200
        body = r.json()
        assert body["biometric_enabled"] is True
        assert body["multisig_enabled"] is True
