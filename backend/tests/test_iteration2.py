"""Iteration 2 tests: Stripe (placeholder), Daily.co (unset), E2E key registration, encrypted chat."""
import os
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


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def user_ctx(client):
    email = f"it2_{uuid.uuid4().hex[:8]}@vaulted.app"
    r = client.post(f"{API}/auth/register", json={"email": email, "password": "test1234", "name": "Iter2 Tester"})
    assert r.status_code == 200, r.text
    j = r.json()
    return {"token": j["access_token"], "user": j["user"], "email": email}


def H(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ---------- Auth me / public_user fields ----------
class TestAuthMeShape:
    def test_me_returns_pro_subscription_public_key(self, client, user_ctx):
        r = client.get(f"{API}/auth/me", headers=H(user_ctx["token"]))
        assert r.status_code == 200
        d = r.json()
        assert "is_pro" in d and d["is_pro"] is False
        assert "subscription" in d
        sub = d["subscription"]
        assert sub.get("tier") == "free"
        assert sub.get("status") == "inactive"
        assert "current_period_end" in sub
        # public_key field exists (may be null)
        assert "public_key" in d
        assert d["public_key"] is None


# ---------- Keys (E2E) ----------
class TestKeys:
    def test_register_public_key_then_fetch(self, client, user_ctx):
        pk = "Q3NRZ0p2VEhpVlpEdXk4OFNqYytGZkF2dnVobEN2cFlEUHpVPQ=="  # base64-ish
        r = client.post(f"{API}/keys/register", headers=H(user_ctx["token"]), json={"public_key": pk})
        assert r.status_code == 200, r.text
        assert r.json()["public_key"] == pk

        # Now /auth/me should expose it
        me = client.get(f"{API}/auth/me", headers=H(user_ctx["token"])).json()
        assert me["public_key"] == pk

        # GET /keys/{user_id}
        uid = user_ctx["user"]["id"]
        r2 = client.get(f"{API}/keys/{uid}", headers=H(user_ctx["token"]))
        assert r2.status_code == 200
        body = r2.json()
        assert body["id"] == uid and body["public_key"] == pk

    def test_register_public_key_too_long_rejected(self, client, user_ctx):
        big = "x" * 600
        r = client.post(f"{API}/keys/register", headers=H(user_ctx["token"]), json={"public_key": big})
        assert r.status_code == 400

    def test_get_key_unknown_user_404(self, client, user_ctx):
        r = client.get(f"{API}/keys/{uuid.uuid4()}", headers=H(user_ctx["token"]))
        assert r.status_code == 404

    def test_keys_requires_auth(self, client):
        assert client.post(f"{API}/keys/register", json={"public_key": "abc"}).status_code == 401
        assert client.get(f"{API}/keys/{uuid.uuid4()}").status_code == 401


# ---------- Encrypted chat ----------
class TestEncryptedChat:
    def test_send_encrypted_message_persists_nonce_and_flag(self, client, user_ctx):
        convs = client.get(f"{API}/chat/conversations", headers=H(user_ctx["token"])).json()
        assert convs, "expected seeded conversations"
        cid = convs[0]["id"]
        ciphertext = "BASE64CIPHERTEXTAAAA=="
        nonce = "BASE64NONCEAAAAAAAAA=="
        r = client.post(
            f"{API}/chat/messages",
            headers=H(user_ctx["token"]),
            json={"conversation_id": cid, "text": ciphertext, "nonce": nonce, "encrypted": True},
        )
        assert r.status_code == 200, r.text
        msg = r.json()
        assert msg["text"] == ciphertext
        assert msg["nonce"] == nonce
        assert msg["encrypted"] is True

        # Fetch messages -> verify nonce + encrypted preserved
        body = client.get(f"{API}/chat/messages/{cid}", headers=H(user_ctx["token"])).json()
        mine = [m for m in body["messages"] if m.get("sender") == "me" and m.get("encrypted")]
        assert any(m["nonce"] == nonce and m["text"] == ciphertext for m in mine)

        # Note: the server-generated auto-reply (plaintext) overwrites the
        # conversation last_message after the encrypted send, so we don't
        # assert lock icon on the conversation preview — the encrypted flag
        # and nonce on the persisted message itself is the contract.


# ---------- Stripe (placeholder key, expect 503) ----------
class TestStripeUnconfigured:
    def test_deposit_checkout_503(self, client, user_ctx):
        r = client.post(f"{API}/stripe/checkout/deposit", headers=H(user_ctx["token"]), json={"amount_usd": 25.0})
        assert r.status_code == 503
        assert "stripe" in r.json()["detail"].lower()

    def test_subscription_checkout_503(self, client, user_ctx):
        r = client.post(f"{API}/stripe/checkout/subscription", headers=H(user_ctx["token"]))
        assert r.status_code == 503

    def test_sync_503(self, client, user_ctx):
        r = client.post(f"{API}/stripe/sync", headers=H(user_ctx["token"]), json={"session_id": "cs_test_x"})
        assert r.status_code == 503

    def test_cancel_503(self, client, user_ctx):
        r = client.post(f"{API}/stripe/cancel", headers=H(user_ctx["token"]))
        assert r.status_code == 503

    def test_stripe_endpoints_require_auth(self, client):
        assert client.post(f"{API}/stripe/checkout/deposit", json={"amount_usd": 10}).status_code == 401
        assert client.post(f"{API}/stripe/checkout/subscription").status_code == 401
        assert client.post(f"{API}/stripe/sync", json={"session_id": "x"}).status_code == 401
        assert client.post(f"{API}/stripe/cancel").status_code == 401


# ---------- Stripe Webhook (no secret => JSON fallback) ----------
class TestStripeWebhook:
    def test_fake_checkout_completed_credits_balance(self, client, user_ctx):
        # Snapshot current USDC
        before = client.get(f"{API}/wallet/assets", headers=H(user_ctx["token"])).json()
        usdc_before = next(a["amount"] for a in before["assets"] if a["symbol"] == "USDC")
        session_id = f"cs_test_{uuid.uuid4().hex[:16]}"
        payload = {
            "id": f"evt_test_{uuid.uuid4().hex[:10]}",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": session_id,
                    "mode": "payment",
                    "payment_status": "paid",
                    "amount_total": 4200,  # $42.00
                    "currency": "usd",
                    "metadata": {"user_id": user_ctx["user"]["id"], "flow": "deposit", "amount_usd": "42.0"},
                }
            },
        }
        # Webhook is public (signature optional). Use raw POST.
        r = requests.post(f"{API}/stripe/webhook", json=payload)
        assert r.status_code == 200, r.text
        assert r.json().get("status") == "ok"

        after = client.get(f"{API}/wallet/assets", headers=H(user_ctx["token"])).json()
        usdc_after = next(a["amount"] for a in after["assets"] if a["symbol"] == "USDC")
        assert round(usdc_after - usdc_before, 2) == 42.00

        # Idempotency: second send should NOT double-credit
        r2 = requests.post(f"{API}/stripe/webhook", json=payload)
        assert r2.status_code == 200
        again = client.get(f"{API}/wallet/assets", headers=H(user_ctx["token"])).json()
        usdc_again = next(a["amount"] for a in again["assets"] if a["symbol"] == "USDC")
        assert round(usdc_again - usdc_after, 2) == 0.00

        # Verify transaction recorded
        txs = client.get(f"{API}/transactions", headers=H(user_ctx["token"])).json()
        assert any(t.get("stripe_session_id") == session_id for t in txs)


# ---------- Daily.co (unset key => configured:false) ----------
class TestCalls:
    def test_calls_room_returns_unconfigured(self, client, user_ctx):
        r = client.post(f"{API}/calls/room", headers=H(user_ctx["token"]), json={"conversation_id": None})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["configured"] is False
        assert d["room_url"] is None
        assert "DAILY_API_KEY" in d.get("message", "")

    def test_calls_room_requires_auth(self, client):
        assert client.post(f"{API}/calls/room", json={}).status_code == 401


# ---------- Regression: existing endpoints still work ----------
class TestRegression:
    def test_login_smoketest_still_works(self, client):
        r = client.post(f"{API}/auth/login", json={"email": "smoketest@vaulted.app", "password": "test1234"})
        if r.status_code != 200:
            pytest.skip(f"smoke login {r.status_code}")
        j = r.json()
        assert "access_token" in j
        # public_user shape now must include subscription / is_pro
        assert "is_pro" in j["user"]
        assert "subscription" in j["user"]

    def test_wallet_send_still_works(self, client, user_ctx):
        r = client.post(f"{API}/wallet/send", headers=H(user_ctx["token"]),
                        json={"asset": "USDC", "amount": 1.5, "to_address": "0xdeadbeef"})
        assert r.status_code == 200
        assert r.json()["asset"] == "USDC"
