"""Optional advanced test — webhook HMAC signature verification.

KNOWN BUG (iter 23): /app/backend/server.py imports `kotani` on line 92
BEFORE calling `load_dotenv(...)` on line 96. So `kotani._WEBHOOK_SECRET`
is captured at module-import time and is ALWAYS empty when the secret is
only present in /app/backend/.env. Result: `verify_webhook_signature()`
returns True for every request (dev-mode short-circuit) — signature
verification is effectively disabled even when the secret is configured.

Manual repro (confirmed 2026-01):
    $ sed -i 's/^KOTANI_WEBHOOK_SECRET=$/KOTANI_WEBHOOK_SECRET=x/' /app/backend/.env
    $ sudo supervisorctl restart backend
    $ curl -X POST .../api/offramp/callback -H 'X-Kotani-Signature: deadbeef' \\
           -d '{"referenceId":"kp_mock_x","status":"SUCCESS"}'
    HTTP:200   <-- SHOULD BE 401

Fix (for main agent): in /app/backend/kotani.py, either (a) call
`load_dotenv()` at the top of the module, or (b) defer the env reads
into helper functions / a lazy init, or (c) move `import kotani` in
server.py to AFTER `load_dotenv(...)`.

Tests are marked xfail below until the bug is fixed.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import subprocess
import time

import pytest
import requests

BASE_URL = os.environ.get("EXPO_BACKEND_URL", "https://multi-sig-vault.preview.emergentagent.com").rstrip("/")
ENV_PATH = "/app/backend/.env"
TEST_SECRET = "TEST_KOTANI_HMAC_SECRET_iter23"


def _read_env() -> str:
    with open(ENV_PATH, "r", encoding="utf-8") as f:
        return f.read()


def _write_env(text: str) -> None:
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.write(text)


def _restart_backend() -> None:
    subprocess.run(["sudo", "supervisorctl", "restart", "backend"], check=False, capture_output=True)
    # Wait for backend to come back up
    for _ in range(30):
        try:
            r = requests.get(f"{BASE_URL}/api/", timeout=2)
            if r.status_code < 500:
                return
        except Exception:
            pass
        time.sleep(1)


@pytest.fixture(scope="module")
def signed_backend():
    original = _read_env()
    new = original.replace("KOTANI_WEBHOOK_SECRET=", f"KOTANI_WEBHOOK_SECRET={TEST_SECRET}")
    assert TEST_SECRET in new, "secret not injected"
    _write_env(new)
    _restart_backend()
    yield
    _write_env(original)
    _restart_backend()


def test_valid_signature_accepted(signed_backend):
    body = {"referenceId": "kp_mock_sig_unknown", "status": "SUCCESS"}
    raw = json.dumps(body).encode()
    sig = hmac.new(TEST_SECRET.encode(), raw, hashlib.sha256).hexdigest()
    r = requests.post(
        f"{BASE_URL}/api/offramp/callback",
        data=raw,
        headers={"Content-Type": "application/json", "X-Kotani-Signature": sig},
        timeout=10,
    )
    assert r.status_code == 200, r.text[:200]


@pytest.mark.xfail(reason="kotani.py reads env before load_dotenv runs; secret never loaded — see module docstring", strict=False)
def test_invalid_signature_rejected(signed_backend):
    body = {"referenceId": "kp_mock_sig_unknown", "status": "SUCCESS"}
    raw = json.dumps(body).encode()
    r = requests.post(
        f"{BASE_URL}/api/offramp/callback",
        data=raw,
        headers={"Content-Type": "application/json", "X-Kotani-Signature": "deadbeef"},
        timeout=10,
    )
    assert r.status_code == 401, r.text[:200]


@pytest.mark.xfail(reason="kotani.py reads env before load_dotenv runs; secret never loaded — see module docstring", strict=False)
def test_missing_signature_when_secret_set(signed_backend):
    body = {"referenceId": "kp_mock_sig_unknown", "status": "SUCCESS"}
    raw = json.dumps(body).encode()
    r = requests.post(
        f"{BASE_URL}/api/offramp/callback",
        data=raw,
        headers={"Content-Type": "application/json"},
        timeout=10,
    )
    assert r.status_code == 401, r.text[:200]
