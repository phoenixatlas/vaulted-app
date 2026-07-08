"""Iteration 5 tests: Real 2-of-2 ETH multi-sig with Resend email approvals."""
import os
import re
import uuid
import pytest
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path
from pymongo import MongoClient

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

# --- Mongo for DB-fixture steps (promote-to-Pro, expire approval) ---
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")
# Read backend/.env in case the test process didn't inherit
benv = Path("/app/backend/.env")
if benv.exists():
    for line in benv.read_text().splitlines():
        if line.startswith("MONGO_URL="):
            MONGO_URL = line.split("=", 1)[1].strip().strip('"')
        if line.startswith("DB_NAME="):
            DB_NAME = line.split("=", 1)[1].strip().strip('"')
mongo = MongoClient(MONGO_URL)
db = mongo[DB_NAME]


def H(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _register():
    email = f"it5_{uuid.uuid4().hex[:8]}@vaulted.app"
    r = requests.post(f"{API}/auth/register",
                      json={"email": email, "password": "test1234", "name": "Iter5 Tester"})
    assert r.status_code == 200, r.text
    j = r.json()
    return j["access_token"], j["user"], email


@pytest.fixture(scope="module")
def free_user():
    tok, u, em = _register()
    return {"token": tok, "user": u, "email": em}


@pytest.fixture(scope="module")
def pro_user():
    """Fresh user, promoted to Pro via direct DB write, multisig_enabled=True."""
    tok, u, em = _register()
    db.users.update_one(
        {"id": u["id"]},
        {"$set": {
            "subscription": {"status": "active", "plan": "vault_pro"},
            "multisig_enabled": True,
        }},
    )
    # Re-fetch /auth/me to refresh client view
    me = requests.get(f"{API}/auth/me", headers=H(tok)).json()
    return {"token": tok, "user": me, "email": em}


# ===================== Co-signers =====================
class TestCosigners:
    def test_get_cosigners_empty_for_fresh_user(self, free_user):
        r = requests.get(f"{API}/cosigners", headers=H(free_user["token"]))
        assert r.status_code == 200
        assert r.json() == []

    def test_get_cosigners_requires_auth(self):
        assert requests.get(f"{API}/cosigners").status_code == 401

    def test_add_cosigner_402_for_non_pro(self, free_user):
        r = requests.post(f"{API}/cosigners", headers=H(free_user["token"]),
                          json={"email": "x@y.com", "label": "x"})
        assert r.status_code == 402, r.text
        assert "Vault Pro" in r.json().get("detail", "")

    def test_add_cosigner_pro_success_and_shape(self, pro_user):
        email = f"cosigner_{uuid.uuid4().hex[:6]}@example.com"
        r = requests.post(f"{API}/cosigners", headers=H(pro_user["token"]),
                          json={"email": email, "label": "Test Cosigner"})
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("id", "email", "label", "status", "added_at"):
            assert k in d, f"missing {k}"
        assert d["status"] == "active"
        assert d["email"] == email.lower()
        # save id to module scope via class attr
        TestCosigners._cosigner_id = d["id"]
        # GET should now list it
        lst = requests.get(f"{API}/cosigners", headers=H(pro_user["token"])).json()
        assert any(c["id"] == d["id"] for c in lst)

    def test_delete_cosigner(self, pro_user):
        cid = getattr(TestCosigners, "_cosigner_id", None)
        assert cid, "depends on previous test"
        r = requests.delete(f"{API}/cosigners/{cid}", headers=H(pro_user["token"]))
        assert r.status_code == 200
        assert r.json()["removed"] is True
        lst = requests.get(f"{API}/cosigners", headers=H(pro_user["token"])).json()
        assert not any(c["id"] == cid for c in lst)


# ===================== Multi-sig gate on /wallet/eth/send =====================
class TestMultisigGate:
    @classmethod
    def _ensure_cosigner(cls, pro_user):
        # ensure exactly one active cosigner
        existing = requests.get(f"{API}/cosigners", headers=H(pro_user["token"])).json()
        if existing:
            return existing[0]
        r = requests.post(f"{API}/cosigners", headers=H(pro_user["token"]),
                          json={"email": f"gate_{uuid.uuid4().hex[:6]}@example.com",
                                "label": "Gate"})
        assert r.status_code == 200, r.text
        return r.json()

    def test_send_above_threshold_requires_approval(self, pro_user):
        cs = self._ensure_cosigner(pro_user)
        r = requests.post(f"{API}/wallet/eth/send", headers=H(pro_user["token"]),
                          json={"to_address": "0x000000000000000000000000000000000000dEaD",
                                "amount_eth": 0.05})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("approval_required") is True
        assert "approval_id" in d and d["approval_id"]
        assert d["cosigner_email"] == cs["email"]
        assert "expires_at" in d and d["expires_at"]
        # Save for later tests
        TestMultisigGate._approval_id = d["approval_id"]
        # Confirm not broadcast (no tx_hash returned)
        assert "tx_hash" not in d

    def test_below_threshold_skips_gate(self, pro_user):
        self._ensure_cosigner(pro_user)
        # 0.005 < 0.01 threshold — should bypass and try to broadcast (Insufficient ETH expected)
        r = requests.post(f"{API}/wallet/eth/send", headers=H(pro_user["token"]),
                          json={"to_address": "0x000000000000000000000000000000000000dEaD",
                                "amount_eth": 0.005})
        # Either status_code != 200 (broadcast failed) or no approval_required
        d = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        assert not d.get("approval_required"), f"below-threshold incorrectly gated: {d}"

    def test_non_pro_no_cosigner_no_gate(self, free_user):
        # non-pro can't even add cosigner, so multisig_enabled doesn't matter
        # Set multisig_enabled=True via DB to be sure
        db.users.update_one({"id": free_user["user"]["id"]},
                            {"$set": {"multisig_enabled": True}})
        r = requests.post(f"{API}/wallet/eth/send", headers=H(free_user["token"]),
                          json={"to_address": "0x000000000000000000000000000000000000dEaD",
                                "amount_eth": 0.05})
        d = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        # Should NOT be gated; either 200 broadcast result or 400 Insufficient ETH
        assert not d.get("approval_required"), f"non-pro user gated by mistake: {d}"


# ===================== Approvals list & decide =====================
class TestApprovals:
    def test_pending_lists_for_user_and_excludes_token(self, pro_user):
        r = requests.get(f"{API}/approvals/pending", headers=H(pro_user["token"]))
        assert r.status_code == 200
        lst = r.json()
        assert isinstance(lst, list) and len(lst) >= 1
        # newest first by created_at
        if len(lst) >= 2:
            assert lst[0]["created_at"] >= lst[1]["created_at"]
        for a in lst:
            assert "approver_token" not in a, "approver_token must be hidden"
            assert "id" in a and "amount_eth" in a and "to_address" in a

    def test_pending_requires_auth(self):
        assert requests.get(f"{API}/approvals/pending").status_code == 401

    def test_decide_reject_no_auth_succeeds(self, pro_user):
        # Create a fresh approval to reject
        # Need a cosigner present
        existing = requests.get(f"{API}/cosigners", headers=H(pro_user["token"])).json()
        if not existing:
            requests.post(f"{API}/cosigners", headers=H(pro_user["token"]),
                          json={"email": f"rej_{uuid.uuid4().hex[:6]}@example.com",
                                "label": "Rej"})
        rs = requests.post(f"{API}/wallet/eth/send", headers=H(pro_user["token"]),
                           json={"to_address": "0x000000000000000000000000000000000000dEaD",
                                 "amount_eth": 0.02})
        assert rs.status_code == 200 and rs.json().get("approval_required")
        aid = rs.json()["approval_id"]
        # Fetch token from DB (production-only path uses email link)
        approval_doc = db.eth_approvals.find_one({"id": aid})
        token = approval_doc["approver_token"]

        # Reject WITHOUT auth headers
        r = requests.post(f"{API}/approvals/decide",
                          json={"token": token, "decision": "reject"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "rejected"
        assert d["approval_id"] == aid

        # Idempotency — same token again returns already:true
        r2 = requests.post(f"{API}/approvals/decide",
                          json={"token": token, "decision": "reject"})
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2.get("already") is True
        assert d2["status"] == "rejected"

    def test_decide_approve_attempts_broadcast(self, pro_user):
        existing = requests.get(f"{API}/cosigners", headers=H(pro_user["token"])).json()
        if not existing:
            requests.post(f"{API}/cosigners", headers=H(pro_user["token"]),
                          json={"email": f"app_{uuid.uuid4().hex[:6]}@example.com",
                                "label": "App"})
        rs = requests.post(f"{API}/wallet/eth/send", headers=H(pro_user["token"]),
                           json={"to_address": "0x000000000000000000000000000000000000dEaD",
                                 "amount_eth": 0.02})
        assert rs.status_code == 200 and rs.json().get("approval_required")
        aid = rs.json()["approval_id"]
        token = db.eth_approvals.find_one({"id": aid})["approver_token"]

        r = requests.post(f"{API}/approvals/decide",
                          json={"token": token, "decision": "approve"})
        # Fresh user has 0 ETH so broadcast fails — backend returns 4xx with detail "Insufficient ETH"
        # (or possibly 200 if RPC quirks; either is acceptable for this test)
        if r.status_code == 200:
            d = r.json()
            assert d["status"] in ("approved",)
        else:
            # Expected path: broadcast fails because of zero balance
            assert r.status_code in (400, 402, 502), r.text
            detail = r.json().get("detail", "")
            assert any(s in detail.lower() for s in ("insufficient", "balance", "fund")), detail

    def test_decide_expired_returns_410(self, pro_user):
        existing = requests.get(f"{API}/cosigners", headers=H(pro_user["token"])).json()
        if not existing:
            requests.post(f"{API}/cosigners", headers=H(pro_user["token"]),
                          json={"email": f"exp_{uuid.uuid4().hex[:6]}@example.com",
                                "label": "Exp"})
        rs = requests.post(f"{API}/wallet/eth/send", headers=H(pro_user["token"]),
                           json={"to_address": "0x000000000000000000000000000000000000dEaD",
                                 "amount_eth": 0.03})
        assert rs.status_code == 200 and rs.json().get("approval_required")
        aid = rs.json()["approval_id"]
        token = db.eth_approvals.find_one({"id": aid})["approver_token"]

        # Manually set expires_at to the past
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        db.eth_approvals.update_one({"id": aid}, {"$set": {"expires_at": past}})

        r = requests.post(f"{API}/approvals/decide",
                          json={"token": token, "decision": "approve"})
        assert r.status_code == 410, f"expected 410 Gone, got {r.status_code}: {r.text}"

    def test_decide_invalid_token(self):
        r = requests.post(f"{API}/approvals/decide",
                          json={"token": "definitely-not-a-real-token", "decision": "reject"})
        assert r.status_code == 404


# ===================== Regression on earlier endpoints =====================
class TestRegression:
    def test_auth_me(self, pro_user):
        r = requests.get(f"{API}/auth/me", headers=H(pro_user["token"]))
        assert r.status_code == 200
        assert r.json()["email"] == pro_user["email"]

    def test_wallet_assets_has_prices_and_sparklines(self, pro_user):
        r = requests.get(f"{API}/wallet/assets", headers=H(pro_user["token"]))
        assert r.status_code == 200
        d = r.json()
        assert "prices_fetched_at" in d
        assets = d.get("assets") or d  # tolerate either shape
        # locate BTC
        btc = None
        if isinstance(assets, list):
            for a in assets:
                if a.get("symbol") == "BTC":
                    btc = a
                    break
        else:
            btc = assets.get("BTC")
        assert btc, "BTC asset missing"
        assert "sparkline_7d" in btc and isinstance(btc["sparkline_7d"], list) and len(btc["sparkline_7d"]) > 0
        assert "change_24h_pct" in btc

    def test_wallet_eth_info(self, pro_user):
        r = requests.get(f"{API}/wallet/eth/info", headers=H(pro_user["token"]))
        assert r.status_code == 200
        assert re.match(r"^0x[0-9a-fA-F]{40}$", r.json()["address"])

    def test_wallet_eth_mnemonic(self, pro_user):
        r = requests.get(f"{API}/wallet/eth/mnemonic", headers=H(pro_user["token"]))
        assert r.status_code == 200
        d = r.json()
        assert d["word_count"] == 12
        assert len(d["mnemonic"].split()) == 12

    def test_market_prices_still_works(self, pro_user):
        r = requests.get(f"{API}/market/prices", headers=H(pro_user["token"]))
        assert r.status_code == 200
        assert r.json()["ttl_seconds"] == 300
