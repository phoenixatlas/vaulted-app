"""Shared session-scoped fixtures for KYC iteration tests.

Both `test_iteration17_kyc_error.py` and `test_iteration18_kyc_force_new.py`
instantiate a FastAPI TestClient against the same `server.app`. `server.py`
holds a module-level `motor.AsyncIOMotorClient` that is bound to the event
loop of whichever TestClient started up first. If each test module owns its
own TestClient, the first module's teardown closes that event loop, and the
second module then tries to reuse the same motor client on a closed loop —
resulting in `RuntimeError: Event loop is closed`.

Making the TestClient session-scoped and shared via conftest keeps a single
event loop alive across both files.
"""

from __future__ import annotations

import pathlib
import sys

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Override sk_test_emergent placeholder inherited from the shell before
# server.py is imported so its startup-time STRIPE_API_KEY is the real key.
load_dotenv(BACKEND_DIR / ".env", override=True)

import server  # noqa: E402


SMOKE_EMAIL = "smoketest@vaulted.app"
SMOKE_PASSWORD = "test1234"


@pytest.fixture(scope="session")
def client():
    with TestClient(server.app) as c:
        yield c


@pytest.fixture(scope="session")
def smoke_auth(client):
    assert server.STRIPE_API_KEY, (
        "STRIPE_API_KEY is empty on the backend — /api/kyc/session would return "
        "503 'Stripe not configured' before ever reaching the code path under test."
    )
    r = client.post("/api/auth/login", json={"email": SMOKE_EMAIL, "password": SMOKE_PASSWORD})
    assert r.status_code == 200, f"smoke login failed: {r.status_code} {r.text}"
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
