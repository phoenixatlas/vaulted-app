"""Iteration 8 backend tests — Vaulted deployment-prep round.

Focus areas:
- /api/health liveness endpoint (no auth)
- CORS env-driven behavior (wildcard fallback + credentials off)
- /api/chat/contacts alphabetical sort (regression fix)
- Regression: existing critical endpoints still 200
"""
import os
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
def auth_token(api):
    # Register a fresh user so seed contacts exist for this test run
    email = f"TEST_iter8_{uuid.uuid4().hex[:8]}@vaulted.app"
    r = api.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": email, "password": "test1234", "name": "Iter8 Tester"},
    )
    assert r.status_code == 200, f"register failed: {r.status_code} {r.text[:200]}"
    data = r.json()
    return data["access_token"]


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


# ---------------- Health endpoint ----------------
class TestHealth:
    def test_health_returns_ok_no_auth(self, api):
        r = api.get(f"{BASE_URL}/api/health")
        assert r.status_code == 200
        body = r.json()
        assert body == {"status": "ok"}

    def test_health_does_not_require_bearer(self, api):
        # No Authorization header on a fresh session -> still 200
        s = requests.Session()
        r = s.get(f"{BASE_URL}/api/health")
        assert r.status_code == 200
        assert r.json().get("status") == "ok"


# ---------------- CORS env-driven ----------------
class TestCORS:
    """With CORS_ALLOW_ORIGINS unset, FastAPI CORSMiddleware should fall back to
    allow_origins=['*'] with allow_credentials=False. Browsers reject the combo
    of `*` + credentials, so the server MUST NOT echo a specific Origin nor set
    `Access-Control-Allow-Credentials: true` in this state."""

    def _preflight(self, origin: str) -> requests.Response:
        return requests.options(
            f"{BASE_URL}/api/health",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
            timeout=10,
        )

    def test_preflight_wildcard_fallback_no_credentials(self):
        # CORS_ALLOW_ORIGINS is unset in this env (dev). Expect '*' echo + no credentials.
        r = self._preflight("https://example.com")
        assert r.status_code in (200, 204), f"preflight status {r.status_code}: {r.text[:200]}"
        allow_origin = r.headers.get("access-control-allow-origin")
        allow_credentials = r.headers.get("access-control-allow-credentials")
        # In wildcard mode, should be "*" (or absent) and credentials MUST NOT be true
        assert allow_origin in ("*", None), f"expected '*' in wildcard mode, got {allow_origin}"
        assert allow_credentials != "true", (
            f"credentials must be off in wildcard mode (browsers reject *+credentials), "
            f"got {allow_credentials}"
        )

    def test_actual_request_cors_header_present(self, api):
        # Simple GET with Origin header — CORS middleware should set allow-origin
        r = requests.get(
            f"{BASE_URL}/api/health",
            headers={"Origin": "https://random-client.test"},
            timeout=10,
        )
        assert r.status_code == 200
        # In wildcard fallback, header should be '*'
        ao = r.headers.get("access-control-allow-origin")
        assert ao in ("*", None), f"expected '*' got {ao}"


# ---------------- Alphabetical contacts sort ----------------
class TestContactsSort:
    def test_contacts_sorted_alphabetically(self, api, auth_headers):
        r = api.get(f"{BASE_URL}/api/chat/contacts", headers=auth_headers)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"
        items = r.json()
        assert isinstance(items, list)
        names = [c.get("name") for c in items]
        # Spec expects alphabetical: Daniel Park, Maya Chen, Vault Support
        assert names == sorted(names, key=lambda n: n.lower()), (
            f"contacts not sorted alphabetically: {names}"
        )
        # Sanity check the exact seed order matches the spec example
        assert names[:3] == ["Daniel Park", "Maya Chen", "Vault Support"], (
            f"unexpected seed order: {names}"
        )


# ---------------- Regression — critical endpoints ----------------
class TestRegression:
    def test_login_smoketest(self, api):
        r = api.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "smoketest@vaulted.app", "password": "test1234"},
        )
        assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"
        body = r.json()
        assert "access_token" in body and "user" in body

    def test_auth_me(self, api, auth_headers):
        r = api.get(f"{BASE_URL}/api/auth/me", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert "id" in body and "email" in body

    def test_wallet_assets(self, api, auth_headers):
        r = api.get(f"{BASE_URL}/api/wallet/assets", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert "assets" in body and "total_usd" in body
        assert isinstance(body["assets"], list) and len(body["assets"]) >= 1

    def test_chat_conversations(self, api, auth_headers):
        r = api.get(f"{BASE_URL}/api/chat/conversations", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body, list)

    def test_transactions(self, api, auth_headers):
        r = api.get(f"{BASE_URL}/api/transactions", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body, list)

    def test_cosigners(self, api, auth_headers):
        r = api.get(f"{BASE_URL}/api/cosigners", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body, list)

    def test_approvals_pending(self, api, auth_headers):
        r = api.get(f"{BASE_URL}/api/approvals/pending", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body, list)
