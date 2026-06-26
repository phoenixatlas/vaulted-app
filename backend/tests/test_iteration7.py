"""Iteration 7 tests — Group chats, in-chat group crypto send, CSV export, Push registration.

Covers:
- Group chats (POST /api/chat/groups, GET /api/chat/contacts, GET /api/chat/conversations)
- In-chat send_crypto group vs 1-on-1 semantics
- CSV / tax export (GET /api/transactions/export)
- Push registration (POST /api/register-push) – existence + serialization
- Regression on critical existing endpoints
"""
import os
import csv
import io
import uuid
import requests
import pytest

BASE_URL = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"


# ---------- Fixtures ----------
@pytest.fixture(scope="module")
def fresh_user():
    """Register a fresh user with seeded data and return (token, user_obj)."""
    email = f"it7_{uuid.uuid4().hex[:10]}@vaulted.app"
    r = requests.post(
        f"{API}/auth/register",
        json={"email": email, "password": "test1234", "name": "Iter7 Tester"},
        timeout=20,
    )
    assert r.status_code == 200, f"register failed: {r.status_code} {r.text}"
    body = r.json()
    return body["access_token"], body["user"]


@pytest.fixture(scope="module")
def auth(fresh_user):
    token, _ = fresh_user
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def smoke_auth():
    r = requests.post(
        f"{API}/auth/login",
        json={"email": "smoketest@vaulted.app", "password": "test1234"},
        timeout=15,
    )
    if r.status_code != 200:
        pytest.skip(f"smoke account not available: {r.status_code}")
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ---------- Contacts ----------
class TestContacts:
    def test_contacts_returned(self, auth):
        r = requests.get(f"{API}/chat/contacts", headers=auth, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 3
        names = [c["name"] for c in data]
        # seeded names present
        for n in ("Maya Chen", "Daniel Park", "Vault Support"):
            assert n in names, f"{n} missing from contacts: {names}"

    def test_contacts_sorted_alphabetically(self, auth):
        """Spec says contacts should come back sorted alphabetically."""
        r = requests.get(f"{API}/chat/contacts", headers=auth, timeout=15)
        names = [c["name"] for c in r.json()]
        assert names == sorted(names, key=lambda s: s.lower()), (
            f"Contacts not sorted alphabetically: {names}"
        )


# ---------- Group chats ----------
class TestGroupChats:
    def test_create_group_and_appears_in_conversations(self, auth):
        contacts = requests.get(f"{API}/chat/contacts", headers=auth, timeout=15).json()
        ids = [c["id"] for c in contacts[:2]]
        r = requests.post(
            f"{API}/chat/groups",
            headers=auth,
            json={"name": "TEST_Trip Squad", "contact_ids": ids},
            timeout=15,
        )
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        g = r.json()
        assert g["is_group"] is True
        assert g["group_name"] == "TEST_Trip Squad"
        assert len(g["members"]) == 2
        member_ids = {m["contact_id"] for m in g["members"]}
        assert member_ids == set(ids)
        # store on class for later tests
        TestGroupChats.group_id = g["id"]
        TestGroupChats.member_ids = ids

        # verify in conversations list
        rc = requests.get(f"{API}/chat/conversations", headers=auth, timeout=15).json()
        found = next((c for c in rc if c["id"] == g["id"]), None)
        assert found is not None, "Group not in conversations list"
        assert found.get("is_group") is True
        assert isinstance(found.get("members"), list) and len(found["members"]) == 2

    def test_group_create_rejects_bad_contact_id(self, auth):
        r = requests.post(
            f"{API}/chat/groups",
            headers=auth,
            json={"name": "TEST_Bad", "contact_ids": [str(uuid.uuid4())]},
            timeout=15,
        )
        assert r.status_code == 400


# ---------- In-chat crypto send ----------
class TestInChatCryptoSend:
    @pytest.fixture(scope="class")
    def group_setup(self, auth):
        contacts = requests.get(f"{API}/chat/contacts", headers=auth, timeout=15).json()
        ids = [c["id"] for c in contacts[:2]]
        g = requests.post(
            f"{API}/chat/groups",
            headers=auth,
            json={"name": "TEST_CryptoGroup", "contact_ids": ids},
            timeout=15,
        ).json()
        return g, ids, contacts

    def test_group_send_requires_to_contact_id(self, auth, group_setup):
        g, _, _ = group_setup
        r = requests.post(
            f"{API}/chat/send_crypto",
            headers=auth,
            json={"conversation_id": g["id"], "amount_eth": 0.001},
            timeout=15,
        )
        assert r.status_code == 400
        assert "recipient" in r.json().get("detail", "").lower() or "pick" in r.json().get("detail", "").lower()

    def test_group_send_rejects_non_member(self, auth, group_setup):
        g, _, _ = group_setup
        r = requests.post(
            f"{API}/chat/send_crypto",
            headers=auth,
            json={"conversation_id": g["id"], "amount_eth": 0.001, "to_contact_id": str(uuid.uuid4())},
            timeout=15,
        )
        assert r.status_code == 400

    def test_group_send_balance_check_fires_last(self, auth, group_setup):
        """Sender has ~0 Sepolia ETH so balance check should trigger after passing the
        recipient validation; should NOT be 400 about recipient anymore."""
        g, ids, _ = group_setup
        r = requests.post(
            f"{API}/chat/send_crypto",
            headers=auth,
            json={"conversation_id": g["id"], "amount_eth": 0.001, "to_contact_id": ids[0]},
            timeout=25,
        )
        # Expect 400 due to insufficient ETH OR 200 if somehow seeded (we assert structure for both)
        if r.status_code == 200:
            msg = r.json()
            assert msg.get("kind") == "tx_card"
            assert msg.get("to_address", "").startswith("0x")
            assert msg.get("to_contact_id") == ids[0]
            assert msg.get("to_name")
        else:
            # Must NOT be a "Pick a recipient" error -> means validation moved past it
            detail = r.json().get("detail", "").lower()
            assert "pick a recipient" not in detail
            assert "not in this group" not in detail
            # Should be the ETH balance error
            assert "insufficient" in detail or "rpc" in detail or "sepolia" in detail, detail

    def test_one_on_one_ignores_to_contact_id(self, auth):
        """For 1-on-1 conversations the body's to_contact_id should be ignored."""
        convs = requests.get(f"{API}/chat/conversations", headers=auth, timeout=15).json()
        one_on_one = next((c for c in convs if not c.get("is_group")), None)
        assert one_on_one is not None
        # Pass a bogus to_contact_id; should NOT 400 on it for 1-on-1
        r = requests.post(
            f"{API}/chat/send_crypto",
            headers=auth,
            json={"conversation_id": one_on_one["id"], "amount_eth": 0.001, "to_contact_id": "bogus-id"},
            timeout=25,
        )
        if r.status_code == 400:
            detail = r.json().get("detail", "").lower()
            # must NOT be about the group recipient validation
            assert "pick a recipient" not in detail
            assert "not in this group" not in detail


# ---------- CSV export ----------
class TestCSVExport:
    EXPECTED_HEADERS = [
        "Date (UTC)", "Type", "Category", "Asset", "Amount",
        "USD Value", "Cost Basis USD", "Service Fee USD", "Net USD",
        "Counterparty", "Network", "Tx Hash", "Status", "Explorer URL",
    ]

    def test_export_requires_auth(self):
        r = requests.get(f"{API}/transactions/export", timeout=15)
        assert r.status_code == 401

    def test_export_csv_headers(self, auth):
        r = requests.get(f"{API}/transactions/export", headers=auth, timeout=20)
        assert r.status_code == 200
        ct = r.headers.get("content-type", "")
        assert "text/csv" in ct, f"wrong content-type: {ct}"
        cd = r.headers.get("content-disposition", "")
        assert "attachment" in cd and ".csv" in cd, f"bad cd: {cd}"
        reader = csv.reader(io.StringIO(r.text))
        rows = list(reader)
        assert rows[0] == self.EXPECTED_HEADERS, f"header mismatch: {rows[0]}"
        # body should have the seeded welcome USDC tx
        assert len(rows) >= 2

    def test_export_filter_by_asset(self, auth):
        r = requests.get(f"{API}/transactions/export?assets=ETH", headers=auth, timeout=20)
        assert r.status_code == 200
        rows = list(csv.reader(io.StringIO(r.text)))
        # Either zero rows (no ETH txs yet for fresh user) or all ETH
        for row in rows[1:]:
            assert row[3] == "ETH", f"asset filter leaked: {row}"

    def test_export_filter_by_type(self, auth):
        r = requests.get(f"{API}/transactions/export?types=receive", headers=auth, timeout=20)
        assert r.status_code == 200
        rows = list(csv.reader(io.StringIO(r.text)))
        for row in rows[1:]:
            assert row[1] == "receive", f"type filter leaked: {row}"
        # The seeded welcome USDC receive should be present
        assert any(row[1] == "receive" and row[3] == "USDC" for row in rows[1:])

    def test_export_filter_by_date(self, auth):
        # Far past range — should return only header (no body rows)
        r = requests.get(
            f"{API}/transactions/export?date_from=2000-01-01&date_to=2000-01-02",
            headers=auth,
            timeout=20,
        )
        assert r.status_code == 200
        rows = list(csv.reader(io.StringIO(r.text)))
        assert len(rows) == 1  # only header


# ---------- Push registration ----------
class TestPushRegistration:
    def test_route_exists_and_serializes(self):
        """Endpoint must exist (not 404) and accept the documented schema.
        Upstream is allowed to fail (502/500) because the key is a placeholder."""
        r = requests.post(
            f"{API}/register-push",
            json={"user_id": "test-user", "platform": "ios", "device_token": "tok-123"},
            timeout=15,
        )
        assert r.status_code != 404, "register-push route missing"
        # Acceptable: 201 (success), 502 (upstream unavailable), 500 (bad key)
        assert r.status_code in (201, 500, 502), f"unexpected status {r.status_code}: {r.text[:200]}"

    def test_route_validates_body(self):
        r = requests.post(f"{API}/register-push", json={"user_id": "x"}, timeout=10)
        assert r.status_code == 422  # Pydantic validation error


# ---------- Regression ----------
class TestRegression:
    def test_login_smoke(self):
        r = requests.post(
            f"{API}/auth/login",
            json={"email": "smoketest@vaulted.app", "password": "test1234"},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        assert "access_token" in r.json()
        assert r.json()["user"]["email"] == "smoketest@vaulted.app"

    def test_wallet_assets(self, auth):
        r = requests.get(f"{API}/wallet/assets", headers=auth, timeout=25)
        assert r.status_code == 200
        d = r.json()
        assert "total_usd" in d and "assets" in d and "wallet_address" in d
        symbols = {a["symbol"] for a in d["assets"]}
        assert {"BTC", "ETH", "USDC", "SOL"}.issubset(symbols)

    def test_conversations(self, auth):
        r = requests.get(f"{API}/chat/conversations", headers=auth, timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_cosigners(self, auth):
        r = requests.get(f"{API}/cosigners", headers=auth, timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_approvals_pending(self, auth):
        r = requests.get(f"{API}/approvals/pending", headers=auth, timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_transactions(self, auth):
        r = requests.get(f"{API}/transactions", headers=auth, timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)
