# Iteration 36: Chat Report & Block (Apple 1.2) endpoints
import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")


@pytest.fixture(scope="module")
def s():
    return requests.Session()


@pytest.fixture(scope="module")
def h(s):
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": "smoketest@vaulted.app", "password": "test1234"})
    if r.status_code != 200:
        pytest.skip("login failed")
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="module")
def conv(s, h):
    r = s.get(f"{BASE_URL}/api/chat/conversations", headers=h)
    assert r.status_code == 200
    one = [c for c in r.json() if not c.get("is_group") and c.get("contact_id")]
    if not one:
        pytest.skip("no 1:1 conversation")
    c = one[0]
    yield c
    # teardown: always leave the contact unblocked
    s.post(f"{BASE_URL}/api/chat/block", json={"contact_id": c["contact_id"], "block": False}, headers=h)


# Auth guards
class TestAuthGuards:
    def test_block_requires_auth(self, s):
        assert s.post(f"{BASE_URL}/api/chat/block", json={"contact_id": "x"}).status_code in (401, 403)

    def test_blocked_requires_auth(self, s):
        assert s.get(f"{BASE_URL}/api/chat/blocked").status_code in (401, 403)

    def test_report_requires_auth(self, s):
        assert s.post(f"{BASE_URL}/api/chat/report", json={"conversation_id": "x", "reason": "spam"}).status_code in (401, 403)


# Block / unblock flow
class TestBlockFlow:
    def test_block_then_send_403_then_unblock_200(self, s, h, conv):
        cid, conv_id = conv["contact_id"], conv["id"]
        r = s.post(f"{BASE_URL}/api/chat/block", json={"contact_id": cid, "block": True}, headers=h)
        assert r.status_code == 200 and r.json() == {"contact_id": cid, "blocked": True}
        r = s.get(f"{BASE_URL}/api/chat/blocked", headers=h)
        assert cid in r.json()["blocked_contacts"]
        # idempotent ($addToSet)
        s.post(f"{BASE_URL}/api/chat/block", json={"contact_id": cid, "block": True}, headers=h)
        assert s.get(f"{BASE_URL}/api/chat/blocked", headers=h).json()["blocked_contacts"].count(cid) == 1
        r = s.get(f"{BASE_URL}/api/chat/messages/{conv_id}", headers=h)
        assert r.status_code == 200 and r.json()["blocked"] is True
        r = s.post(f"{BASE_URL}/api/chat/messages", json={"conversation_id": conv_id, "text": "TEST_blocked"}, headers=h)
        assert r.status_code == 403
        assert "block" in r.json()["detail"].lower()
        # unblock
        r = s.post(f"{BASE_URL}/api/chat/block", json={"contact_id": cid, "block": False}, headers=h)
        assert r.status_code == 200 and r.json()["blocked"] is False
        assert cid not in s.get(f"{BASE_URL}/api/chat/blocked", headers=h).json()["blocked_contacts"]
        assert s.get(f"{BASE_URL}/api/chat/messages/{conv_id}", headers=h).json()["blocked"] is False
        r = s.post(f"{BASE_URL}/api/chat/messages", json={"conversation_id": conv_id, "text": "TEST_unblocked"}, headers=h)
        assert r.status_code == 200 and r.json()["text"] == "TEST_unblocked"

    def test_block_missing_contact_id_422(self, s, h):
        assert s.post(f"{BASE_URL}/api/chat/block", json={}, headers=h).status_code == 422


# Report flow
class TestReport:
    def test_report_autoblocks(self, s, h, conv):
        r = s.post(f"{BASE_URL}/api/chat/report", json={"conversation_id": conv["id"], "reason": "TEST_Spam or scam", "block": True}, headers=h)
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True and isinstance(d["id"], str)
        assert conv["contact_id"] in s.get(f"{BASE_URL}/api/chat/blocked", headers=h).json()["blocked_contacts"]
        s.post(f"{BASE_URL}/api/chat/block", json={"contact_id": conv["contact_id"], "block": False}, headers=h)

    def test_report_without_block(self, s, h, conv):
        r = s.post(f"{BASE_URL}/api/chat/report", json={"conversation_id": conv["id"], "reason": "TEST_other", "block": False}, headers=h)
        assert r.status_code == 200
        assert conv["contact_id"] not in s.get(f"{BASE_URL}/api/chat/blocked", headers=h).json()["blocked_contacts"]

    def test_report_unknown_conversation_404(self, s, h):
        r = s.post(f"{BASE_URL}/api/chat/report", json={"conversation_id": "not-mine-xyz", "reason": "spam"}, headers=h)
        assert r.status_code == 404

    def test_report_empty_reason_422(self, s, h, conv):
        r = s.post(f"{BASE_URL}/api/chat/report", json={"conversation_id": conv["id"], "reason": ""}, headers=h)
        assert r.status_code == 422

    def test_report_long_reason_422(self, s, h, conv):
        r = s.post(f"{BASE_URL}/api/chat/report", json={"conversation_id": conv["id"], "reason": "x" * 201}, headers=h)
        assert r.status_code == 422
