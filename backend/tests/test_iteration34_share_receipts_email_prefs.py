# Iteration 34: delivery email preference + shareable receipt links
import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
TX_ID = os.environ.get("ITER34_TX_ID")


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    r = sess.post(f"{BASE_URL}/api/auth/login", json={"email": "smoketest@vaulted.app", "password": "test1234"})
    if r.status_code != 200:
        pytest.skip("login failed")
    d = r.json()
    tok = d.get("token") or d.get("access_token")
    sess.headers.update({"Authorization": f"Bearer {tok}"})
    return sess


# Email preferences
def test_delivery_emails_toggle(s):
    r = s.patch(f"{BASE_URL}/api/auth/security", json={"delivery_emails": False})
    assert r.status_code == 200 and r.json()["delivery_emails"] is False
    assert s.get(f"{BASE_URL}/api/auth/me").json()["delivery_emails"] is False
    r = s.patch(f"{BASE_URL}/api/auth/security", json={"delivery_emails": True})
    assert r.json()["delivery_emails"] is True
    assert s.get(f"{BASE_URL}/api/auth/me").json()["delivery_emails"] is True


# Share link
def test_share_stable_and_public_page(s):
    if not TX_ID:
        pytest.skip("no seeded tx")
    a = s.post(f"{BASE_URL}/api/transactions/{TX_ID}/share").json()
    b = s.post(f"{BASE_URL}/api/transactions/{TX_ID}/share").json()
    assert a["token"] == b["token"] and a["path"] == f"/api/r/{a['token']}"
    r = requests.get(f"{BASE_URL}{a['path']}")
    assert r.status_code == 200
    h = r.text
    assert "8,123.45 KES" in h and "Delivered" in h and "Grace" in h
    assert "Wanjiru" not in h and "Otieno" not in h and "712345678" not in h
    assert "Beta test payout" in h
    assert "smoketest@vaulted.app" not in h


def test_share_unknown_tx_404(s):
    assert s.post(f"{BASE_URL}/api/transactions/does-not-exist/share").status_code == 404


def test_share_requires_auth():
    if not TX_ID:
        pytest.skip("no seeded tx")
    assert requests.post(f"{BASE_URL}/api/transactions/{TX_ID}/share").status_code in (401, 403)


def test_bad_token_404():
    assert requests.get(f"{BASE_URL}/api/r/badtoken123").status_code == 404
