"""Iteration 32 — transfer tracking timeline, send-again prefill, feedback replies.
Requires seeded docs: python tests/iter32_helper.py seed <smoketest_uid>  (ids written to /tmp/iter32_ids.json)
"""
import json
import os

import pytest
import requests

BASE_URL = (os.environ.get("EXPO_BACKEND_URL") or os.environ.get("EXPO_PUBLIC_BACKEND_URL")).rstrip("/")
IDS = json.load(open("/tmp/iter32_ids.json"))


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    r = sess.post(f"{BASE_URL}/api/auth/login", json={"email": "smoketest@vaulted.app", "password": "test1234"})
    if r.status_code != 200:
        pytest.skip(f"login failed {r.status_code}")
    sess.headers["Authorization"] = f"Bearer {r.json().get('token') or r.json().get('access_token')}"
    return sess


def _get(s, key):
    r = s.get(f"{BASE_URL}/api/transactions/{IDS[key]}")
    assert r.status_code == 200, r.text
    return r.json()


def _states(d):
    return {st["key"]: st["state"] for st in d["timeline"]}


# --- Transaction detail / timeline ---
def test_requires_auth():
    r = requests.get(f"{BASE_URL}/api/transactions/{IDS['ng_settled']}")
    assert r.status_code in (401, 403)


def test_ng_settled_all_done(s):
    d = _get(s, "ng_settled")
    assert set(d) >= {"tx", "timeline", "is_final", "repeat"}
    assert "_id" not in d["tx"]
    assert [st["key"] for st in d["timeline"]] == ["paid", "converted", "sent", "delivered"]
    assert all(v == "done" for v in _states(d).values())
    assert d["is_final"] is True
    assert all(st.get("at") for st in d["timeline"])
    assert "Yellow Card" in d["timeline"][2]["label"]


def test_ng_repeat_prefill(s):
    rep = _get(s, "ng_settled")["repeat"]
    assert rep == {"destination_code": "NG", "source_fiat": "GBP", "amount": 20, "funding": "card",
                   "recipient_address": "0123456789", "recipient_name": "TEST ACCOUNT HOLDER",
                   "bank_id": "ng_058", "bank_name": "GTBank"}


def test_ke_processing_current_and_country_fallback(s):
    d = _get(s, "ke_processing")
    assert _states(d) == {"paid": "done", "converted": "done", "sent": "current", "delivered": "pending"}
    assert d["is_final"] is False
    assert d["repeat"]["destination_code"] == "KE"  # fallback from country name
    assert d["repeat"]["recipient_address"] == "+254712345678"
    assert d["repeat"]["bank_id"] is None


def test_failed_payout(s):
    d = _get(s, "failed")
    st = {x["key"]: x for x in d["timeline"]}
    assert st["sent"]["state"] == "failed"
    assert st["sent"]["detail"] == "TEST_ partner rejected the account"
    assert st["delivered"]["state"] == "pending"
    assert d["is_final"] is True
    assert d["repeat"]["funding"] == "apple_pay"
    assert "Apple Pay" in st["paid"]["detail"]


def test_crypto_remit_three_steps(s):
    d = _get(s, "crypto")
    assert [x["key"] for x in d["timeline"]] == ["sent", "confirmed", "delivered"]
    assert all(v == "done" for v in _states(d).values())
    assert d["repeat"]["funding"] == "crypto"
    assert "base" in d["timeline"][0]["detail"]


def test_non_remit_generic(s):
    d = _get(s, "deposit")
    assert [x["key"] for x in d["timeline"]] == ["created", "done"]
    assert d["repeat"] is None


def test_other_users_tx_404(s):
    r = s.get(f"{BASE_URL}/api/transactions/{IDS['other']}")
    assert r.status_code == 404


def test_unknown_tx_404(s):
    assert s.get(f"{BASE_URL}/api/transactions/does-not-exist").status_code == 404


def test_export_route_not_shadowed(s):
    r = s.get(f"{BASE_URL}/api/transactions/export")
    assert r.status_code == 200 and "text/csv" in r.headers.get("content-type", "")


# --- Feedback replies ---
def test_admin_reply_forbidden_for_non_admin(s):
    r = s.post(f"{BASE_URL}/api/admin/feedback/{IDS['fb']}/reply", json={"message": "hi"})
    assert r.status_code == 403


def test_feedback_mine_and_read(s):
    r = s.get(f"{BASE_URL}/api/feedback/mine")
    assert r.status_code == 200
    d = r.json()
    mine = next(x for x in d["feedback"] if x["id"] == IDS["fb"])
    assert mine["replies"][0]["id"] == IDS["reply"]
    assert mine["unread_reply"] is True and d["unread"] >= 1
    assert all("email" not in x and "_id" not in x for x in d["feedback"])
    assert s.post(f"{BASE_URL}/api/feedback/mine/read").json() == {"ok": True}
    d2 = s.get(f"{BASE_URL}/api/feedback/mine").json()
    assert d2["unread"] == 0
    assert next(x for x in d2["feedback"] if x["id"] == IDS["fb"])["unread_reply"] is False


def test_feedback_mine_requires_auth():
    assert requests.get(f"{BASE_URL}/api/feedback/mine").status_code in (401, 403)
