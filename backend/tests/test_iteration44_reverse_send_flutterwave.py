# Iteration 44 — Reverse corridor (Africa → UK/EU) test-mode send via Flutterwave GBP/EUR sandbox
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("EXPO_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

GBP_RECIPIENT = {
    "name": "TEST University London", "email": "test_bursar@example.com", "phone": "07123456789",
    "account_number": "12345678", "sort_code": "20-00-00", "swift_code": "", "bank_name": "Barclays",
    "address": {"line1": "1 Test Street", "city": "London", "postal_code": "WC1E 7HU", "country": "GB"},
}
EUR_RECIPIENT = {
    "name": "TEST Klinik Berlin", "email": "test_klinik@example.com", "phone": "",
    "account_number": "DE89 3704 0044 0532 0130 00", "sort_code": "", "swift_code": "COBADEFF",
    "bank_name": "Commerzbank",
    "address": {"line1": "Hauptstr 1", "city": "Berlin", "postal_code": "10115", "country": "DE"},
}


def _body(dst="GBP", recipient=None, **kw):
    b = {"source_country": "NG", "source_amount": 200000, "destination_currency": dst,
         "purpose": "University fees", "recipient": recipient or (GBP_RECIPIENT if dst == "GBP" else EUR_RECIPIENT)}
    b.update(kw)
    return b


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{API}/auth/login", json={"email": "smoketest@vaulted.app", "password": "test1234"})
    if r.status_code != 200:
        pytest.skip(f"login failed {r.status_code} {r.text[:200]}")
    tok = r.json().get("access_token") or r.json().get("token")
    s.headers["Authorization"] = f"Bearer {tok}"
    return s


# Corridors catalogue
class TestCorridors:
    def test_corridors_send_enabled(self):
        r = requests.get(f"{API}/remit/reverse/corridors")
        assert r.status_code == 200
        d = r.json()
        assert d["send_enabled"] is True
        assert d["status"] == "test_send"
        dests = {x["code"]: x for x in d["destinations"]}
        assert dests["GBP"]["receive_via"] == "UK Faster Payments"
        assert dests["EUR"]["receive_via"] == "SEPA bank transfer"
        assert {x["code"] for x in d["sources"]} == {"NG", "KE", "GH", "ZA"}


# Public quote — unchanged
class TestQuote:
    def test_quote_public(self):
        r = requests.post(f"{API}/remit/reverse/quote", json={"source_country": "NG", "source_amount": 200000, "destination_currency": "GBP"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "quote_only" and d["waitlist_cta"] is True
        assert d["destination"]["currency"] == "GBP" and d["destination"]["amount"] > 0

    def test_quote_bad_country(self):
        r = requests.post(f"{API}/remit/reverse/quote", json={"source_country": "US", "source_amount": 200, "destination_currency": "GBP"})
        assert r.status_code == 400


# Send — auth + validation
class TestSendValidation:
    def test_requires_auth(self):
        r = requests.post(f"{API}/remit/reverse/send", json=_body())
        assert r.status_code in (401, 403)

    @pytest.mark.parametrize("patch,msg", [
        ({"account_number": "1234567"}, "8 digits"),
        ({"sort_code": "20-00"}, "Sort code"),
        ({"swift_code": "BAD"}, "SWIFT"),
    ])
    def test_gbp_invalid(self, session, patch, msg):
        r = session.post(f"{API}/remit/reverse/send", json=_body("GBP", {**GBP_RECIPIENT, **patch}))
        assert r.status_code == 400, r.text
        assert msg in r.json()["detail"]

    @pytest.mark.parametrize("patch,msg", [
        ({"account_number": "12345678"}, "IBAN"),
        ({"swift_code": ""}, "required"),
    ])
    def test_eur_invalid(self, session, patch, msg):
        r = session.post(f"{API}/remit/reverse/send", json=_body("EUR", {**EUR_RECIPIENT, **patch}))
        assert r.status_code == 400, r.text
        assert msg in r.json()["detail"]

    def test_bad_email_422(self, session):
        r = session.post(f"{API}/remit/reverse/send", json=_body("GBP", {**GBP_RECIPIENT, "email": "nope"}))
        assert r.status_code == 422

    def test_below_min_amount(self, session):
        r = session.post(f"{API}/remit/reverse/send", json=_body("GBP", source_amount=100))
        assert r.status_code == 400
        assert "Minimum" in r.json()["detail"]

    def test_unsupported_dest(self, session):
        r = session.post(f"{API}/remit/reverse/send", json=_body("USD", GBP_RECIPIENT))
        assert r.status_code == 400


# Send — happy path GBP + EUR, persistence + reconcile
class TestSendHappy:
    created: dict = {}

    @pytest.mark.parametrize("dst", ["GBP", "EUR"])
    def test_send(self, session, dst):
        r = session.post(f"{API}/remit/reverse/send", json=_body(dst))
        assert r.status_code == 200, r.text
        tx = r.json()
        assert "_id" not in tx
        assert tx["type"] == "send" and tx["direction"] == "inbound" and tx["category"] == "remit"
        assert tx["asset"] == dst and tx["amount"] > 0 and tx["test_mode"] is True
        assert tx["receipt_id"].startswith("VLT-")
        rm = tx["remit"]
        assert rm["direction"] == "inbound" and rm["source_currency"] == "NGN" and rm["destination_currency"] == dst
        assert rm["receive_via"] == ("UK Faster Payments" if dst == "GBP" else "SEPA bank transfer")
        assert rm["destination_country_code"] == ("GB" if dst == "GBP" else "DE")
        p = tx["payout"]
        assert p["provider"] == "flutterwave"
        print(f"{dst} payout: mode={p['mode']} status={p.get('status')} reason={p.get('reason')} tx_status={tx['status']}")
        assert p["mode"] == "live", f"Flutterwave rejected → simulated: {p.get('reason')}"
        assert p["sandbox"] is True
        assert p["reference_id"]
        TestSendHappy.created[dst] = tx["id"]

    def test_listed_in_transactions(self, session):
        if not TestSendHappy.created:
            pytest.skip("no tx created")
        r = session.get(f"{API}/transactions")
        assert r.status_code == 200
        data = r.json()
        rows = data if isinstance(data, list) else (data.get("transactions") or data.get("items") or [])
        ids = {x.get("id") for x in rows}
        for dst, tid in TestSendHappy.created.items():
            assert tid in ids, f"{dst} tx {tid} not in /transactions"

    def test_reconciled_to_settled(self, session):
        if not TestSendHappy.created:
            pytest.skip("no tx created")
        deadline = time.time() + 100
        pending = dict(TestSendHappy.created)
        while pending and time.time() < deadline:
            r = session.get(f"{API}/transactions")
            data = r.json()
            rows = data if isinstance(data, list) else (data.get("transactions") or data.get("items") or [])
            by_id = {x.get("id"): x for x in rows}
            for dst, tid in list(pending.items()):
                t = by_id.get(tid)
                if t and t.get("status") == "settled":
                    print(f"{dst} settled, payout.status={t.get('payout', {}).get('status')}")
                    pending.pop(dst)
            if pending:
                time.sleep(10)
        assert not pending, f"not settled within 100s: {pending}"
