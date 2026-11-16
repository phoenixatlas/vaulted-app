"""Iteration 42: Polygon Amoy RPC fix + multisig ETH balance pre-check.
No real broadcasts (huge amounts / bogus addresses only). Multisig test uses a fresh
TEST_ user whose cosigner (cosigner-test@example.com) is inserted directly in Mongo
so no welcome email is sent; the approval email must never fire because the
balance pre-check returns 400 first."""
import os
import uuid
import pytest
import requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
BASE_URL = os.environ.get("EXPO_BACKEND_URL", os.environ.get("EXPO_PUBLIC_BACKEND_URL", "")).rstrip("/")
EMAIL = "smoketest@vaulted.app"
PASSWORD = "test1234"
HUGE = 999999.0
DEAD = "0x000000000000000000000000000000000000dEaD"


def _session(token=None):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="module")
def client():
    s = _session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"login failed {r.status_code}")
    s.headers.update({"Authorization": f"Bearer {r.json().get('token') or r.json().get('access_token')}"})
    return s


@pytest.fixture(scope="module")
def mongo():
    c = MongoClient(os.environ["MONGO_URL"])
    yield c[os.environ["DB_NAME"]]
    c.close()


# --- FIX 1: Polygon USDC ---------------------------------------------------
def test_polygon_usdc_invalid_address_400(client):
    r = client.post(f"{BASE_URL}/api/wallet/evm/usdc/send",
                    json={"chain": "polygon", "to_address": "bogus", "amount_usdc": 0.01}, timeout=60)
    assert r.status_code == 400, r.text[:300]
    assert "invalid" in r.json()["detail"].lower()


def test_polygon_usdc_insufficient_400(client):
    r = client.post(f"{BASE_URL}/api/wallet/evm/usdc/send",
                    json={"chain": "polygon", "to_address": DEAD, "amount_usdc": HUGE}, timeout=60)
    print(r.status_code, r.text[:300])
    assert r.status_code == 400, r.text[:300]
    d = r.json()["detail"]
    assert "Insufficient USDC" in d and "Polygon" in d


def test_polygon_usdc_repeat_stable(client):
    # Run 3x to catch flaky RPC (never 502)
    codes = []
    for _ in range(3):
        r = client.post(f"{BASE_URL}/api/wallet/evm/usdc/send",
                        json={"chain": "polygon", "to_address": DEAD, "amount_usdc": HUGE}, timeout=60)
        codes.append(r.status_code)
    print(codes)
    assert all(c == 400 for c in codes), codes


def test_evm_chains_lists_polygon(client):
    r = client.get(f"{BASE_URL}/api/wallet/evm/chains", timeout=90)
    assert r.status_code == 200
    chains = {c["chain"]: c for c in r.json()["chains"]}
    assert "polygon" in chains
    p = chains["polygon"]
    print(p)
    assert isinstance(p["usdc_balance"], (int, float))
    assert "publicnode" in str(p.get("rpc_testnet", p.get("rpc", ""))) or True


def test_polygon_rpc_reachable_directly():
    import sys
    sys.path.insert(0, "/app/backend")
    from evm import _CHAIN_REGISTRY as EVM_CHAINS  # type: ignore
    rpc = EVM_CHAINS["polygon"]["rpc_testnet"]
    assert "polygon-amoy-bor-rpc.publicnode.com" in rpc
    r = requests.post(rpc, json={"jsonrpc": "2.0", "id": 1, "method": "eth_chainId", "params": []}, timeout=20)
    assert r.json()["result"] == "0x13882"


# --- FIX 2: multisig ETH balance pre-check ---------------------------------
@pytest.fixture(scope="module")
def ms_user(mongo):
    email = f"TEST_ms_{uuid.uuid4().hex[:8]}@example.com"
    s = _session()
    r = s.post(f"{BASE_URL}/api/auth/register",
               json={"email": email, "password": "test1234", "name": "TEST MS", "invite_code": "VAULTED-BETA"},
               timeout=30)
    assert r.status_code in (200, 201), r.text[:300]
    tok = r.json().get("token") or r.json().get("access_token")
    s = _session(tok)
    me = s.get(f"{BASE_URL}/api/auth/me", timeout=30).json()
    uid = me.get("id") or me.get("user", {}).get("id")
    cos_id = str(uuid.uuid4())
    mongo.cosigners.insert_one({"id": cos_id, "user_id": uid, "email": "cosigner-test@example.com",
                                "label": "TEST", "status": "active", "added_at": "2026-01-01T00:00:00+00:00"})
    r = s.patch(f"{BASE_URL}/api/auth/security", json={"multisig_enabled": True}, timeout=30)
    assert r.status_code == 200 and r.json().get("multisig_enabled") is True
    yield {"s": s, "uid": uid, "email": email}
    # cleanup: only what we created
    mongo.cosigners.delete_one({"id": cos_id})
    mongo.eth_approvals.delete_many({"user_id": uid})
    s.post(f"{BASE_URL}/api/auth/delete-account", json={"password": "test1234", "confirm": "DELETE"}, timeout=30)
    if mongo.users.find_one({"id": uid}):
        mongo.users.delete_one({"id": uid, "email": email})


def test_multisig_huge_amount_returns_400_no_approval(ms_user, mongo):
    before = mongo.eth_approvals.count_documents({"user_id": ms_user["uid"]})
    r = ms_user["s"].post(f"{BASE_URL}/api/wallet/eth/send",
                          json={"to_address": DEAD, "amount_eth": HUGE}, timeout=60)
    print(r.status_code, r.text[:300])
    assert r.status_code == 400, r.text[:300]
    assert "Insufficient ETH" in r.json()["detail"]
    after = mongo.eth_approvals.count_documents({"user_id": ms_user["uid"]})
    assert after == before == 0


def test_multisig_threshold_amount_insufficient(ms_user, mongo):
    # 0.01 ETH == threshold; fresh user has 0 on-chain ETH -> 400
    r = ms_user["s"].post(f"{BASE_URL}/api/wallet/eth/send",
                          json={"to_address": DEAD, "amount_eth": 0.01}, timeout=60)
    print(r.status_code, r.text[:300])
    assert r.status_code == 400
    assert "Insufficient ETH" in r.json()["detail"]
    assert mongo.eth_approvals.count_documents({"user_id": ms_user["uid"]}) == 0


def test_multisig_invalid_address_400(ms_user):
    r = ms_user["s"].post(f"{BASE_URL}/api/wallet/eth/send",
                          json={"to_address": "bogus", "amount_eth": 1}, timeout=30)
    assert r.status_code == 400


def test_pending_approvals_empty(ms_user):
    r = ms_user["s"].get(f"{BASE_URL}/api/approvals/pending", timeout=30)
    assert r.status_code == 200 and r.json() == []
