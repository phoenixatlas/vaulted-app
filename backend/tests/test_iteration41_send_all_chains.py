"""Iteration 41: All-coin send endpoints (ETH/BTC/SOL/XLM/XRP/USDC-EVM) must return
sensible 4xx (never 500) for invalid address / insufficient funds. Testnet only, tiny/huge
amounts so nothing ever broadcasts from the smoke account."""
import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", os.environ.get("EXPO_BACKEND_URL", "")).rstrip("/")
EMAIL = "smoketest@vaulted.app"
PASSWORD = "test1234"
HUGE = 999999.0  # guarantees insufficient funds -> never broadcasts


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"login failed {r.status_code} {r.text[:200]}")
    tok = r.json().get("token") or r.json().get("access_token")
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def own_addrs(client):
    r = client.get(f"{BASE_URL}/api/wallet/assets", timeout=60)
    assert r.status_code == 200
    return {a["symbol"]: a.get("wallet_address") for a in r.json()["assets"]}


# Wallet assets contain all 6 chips
def test_assets_has_six_symbols(own_addrs):
    for sym in ["BTC", "ETH", "USDC", "SOL", "XLM", "XRP"]:
        assert sym in own_addrs, f"{sym} missing from /wallet/assets"


# Invalid address -> 400 for each chain
@pytest.mark.parametrize("path,body", [
    ("/api/wallet/eth/send", {"to_address": "bogus", "amount_eth": 0.0001}),
    ("/api/wallet/btc/send", {"to_address": "bogus", "amount": 0.00001}),
    ("/api/wallet/sol/send", {"to_address": "bogus", "amount": 0.0001}),
    ("/api/wallet/xlm/send", {"to_address": "bogus", "amount": 0.1}),
    ("/api/wallet/xrp/send", {"to_address": "bogus", "amount": 0.1}),
    ("/api/wallet/evm/usdc/send", {"chain": "sepolia", "to_address": "bogus", "amount_usdc": 0.01}),
])
def test_invalid_address_4xx(client, path, body):
    r = client.post(f"{BASE_URL}{path}", json=body, timeout=60)
    print(path, r.status_code, r.text[:200])
    assert r.status_code == 400
    assert "invalid" in r.json()["detail"].lower()


# Valid-format address + huge amount -> insufficient (400), never 500
@pytest.mark.parametrize("sym,path,body_fn", [
    ("ETH", "/api/wallet/eth/send", lambda a: {"to_address": "0x000000000000000000000000000000000000dEaD", "amount_eth": HUGE}),
    ("BTC", "/api/wallet/btc/send", lambda a: {"to_address": a, "amount": HUGE}),
    ("SOL", "/api/wallet/sol/send", lambda a: {"to_address": a, "amount": HUGE}),
    ("XLM", "/api/wallet/xlm/send", lambda a: {"to_address": a, "amount": HUGE}),
    ("XRP", "/api/wallet/xrp/send", lambda a: {"to_address": a, "amount": HUGE}),
    ("USDC", "/api/wallet/evm/usdc/send", lambda a: {"chain": "sepolia", "to_address": "0x000000000000000000000000000000000000dEaD", "amount_usdc": HUGE}),
])
def test_insufficient_funds_4xx(client, own_addrs, sym, path, body_fn):
    addr = own_addrs.get(sym)
    if sym in ("BTC", "SOL", "XLM", "XRP") and not addr:
        pytest.skip(f"no own {sym} address to use as valid-format recipient")
    r = client.post(f"{BASE_URL}{path}", json=body_fn(addr), timeout=90)
    print(sym, r.status_code, r.text[:300])
    assert r.status_code < 500, f"{sym} returned {r.status_code}"
    assert r.status_code in (400, 402, 422)
    assert "insufficient" in r.json()["detail"].lower() or "fail" in r.json()["detail"].lower()


# Other USDC L2 chains + invalid chain
@pytest.mark.parametrize("chain", ["polygon", "base", "arbitrum"])
def test_usdc_l2_insufficient(client, chain):
    r = client.post(f"{BASE_URL}/api/wallet/evm/usdc/send", json={"chain": chain, "to_address": "0x000000000000000000000000000000000000dEaD", "amount_usdc": HUGE}, timeout=90)
    print(chain, r.status_code, r.text[:200])
    assert r.status_code < 500


def test_usdc_bad_chain(client):
    r = client.post(f"{BASE_URL}/api/wallet/evm/usdc/send", json={"chain": "doge", "to_address": "0x000000000000000000000000000000000000dEaD", "amount_usdc": 1}, timeout=30)
    assert r.status_code == 400


# Zero / negative amount -> 422 validation
@pytest.mark.parametrize("path,body", [
    ("/api/wallet/eth/send", {"to_address": "0x000000000000000000000000000000000000dEaD", "amount_eth": 0}),
    ("/api/wallet/xrp/send", {"to_address": "rXXXXXXXXXXXXXXXXXXXXXXXXXX", "amount": -1}),
])
def test_zero_amount_422(client, path, body):
    r = client.post(f"{BASE_URL}{path}", json=body, timeout=30)
    assert r.status_code == 422


# Unauthenticated -> 401/403
def test_unauth_send():
    r = requests.post(f"{BASE_URL}/api/wallet/xrp/send", json={"to_address": "r" * 30, "amount": 1}, timeout=30)
    assert r.status_code in (401, 403)
