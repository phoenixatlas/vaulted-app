# Iteration 43: Bill Payments — Saved Institutions (save on submit, list, delete, pay-again, route ordering)
import os
import uuid

import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
PDF_BYTES = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
TAG = uuid.uuid4().hex[:6]
INST = f"TEST_ University of Leeds {TAG}"
ACCT = f"GB29NWBK6016{TAG}"


def _login(email, pw):
    return requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=30)


@pytest.fixture(scope="module")
def user_h():
    r = _login("smoketest@vaulted.app", "test1234")
    if r.status_code != 200:
        pytest.skip(f"smoke login failed {r.status_code}")
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="module")
def other_h():
    email = f"test_saved_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": "test1234", "name": "TEST_ Saved",
                                                     "invite_code": "VAULTED-BETA"}, timeout=30)
    if r.status_code not in (200, 201):
        pytest.skip(f"register failed {r.status_code} {r.text[:200]}")
    tok = r.json().get("access_token") or _login(email, "test1234").json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _upload(h):
    r = requests.post(f"{API}/bills/invoice", headers=h, files={"file": ("TEST_inv.pdf", PDF_BYTES, "application/pdf")}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["invoice_path"]


def _quote(h, amount=1500, cur="GBP"):
    r = requests.post(f"{API}/bills/quote", headers=h, json={"category": "education", "payer_country": "NG",
                                                            "payout_currency": cur, "amount": amount}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _submit(h, inst=INST, acct=ACCT, ref="INV-1", save=True, amount=1500):
    body = {"category": "education", "subtype": "Tuition fees", "beneficiary_name": "TEST_ Student",
            "beneficiary_ref": "STU-123", "institution": inst,
            "payee": {"name": "TEST_ Univ Leeds", "bank_name": "Barclays", "account_number": acct,
                      "routing": "60-16-13", "swift": "BARCGB22", "address": "Leeds", "reference": ref},
            "invoice_path": _upload(h), "invoice_name": "TEST_inv.pdf", "declaration": True,
            "payer_country": "NG", "payout_currency": "GBP", "amount": amount, "quote_id": _quote(h, amount),
            "save_institution": save}
    return requests.post(f"{API}/bills", headers=h, json=body, timeout=30)


def _saved(h):
    r = requests.get(f"{API}/bills/saved", headers=h, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["saved"]


class TestSavedInstitutions:
    def test_saved_requires_auth(self):
        assert requests.get(f"{API}/bills/saved", timeout=30).status_code in (401, 403)

    def test_saved_route_not_swallowed(self, user_h):
        d = requests.get(f"{API}/bills/saved", headers=user_h, timeout=30).json()
        assert "saved" in d and isinstance(d["saved"], list)

    def test_no_save_when_false(self, user_h):
        inst = f"TEST_ NoSave {TAG}"
        r = _submit(user_h, inst=inst, save=False)
        assert r.status_code == 200, r.text
        assert not [s for s in _saved(user_h) if s["institution"] == inst]

    def test_save_upsert_dedup_and_delete(self, user_h, other_h):
        r = _submit(user_h, ref="INV-A")
        assert r.status_code == 200, r.text
        rows = [s for s in _saved(user_h) if s["institution"] == INST]
        assert len(rows) == 1
        s = rows[0]
        assert "_id" not in s and "user_id" not in s
        assert s["payee"]["reference"] == ""
        assert s["payee"]["account_number"] == ACCT and s["payee"]["swift"] == "BARCGB22"
        assert s["category"] == "education" and s["subtype"] == "Tuition fees"
        assert s["payer_country"] == "NG" and s["payout_currency"] == "GBP"
        assert s["beneficiary_name"] == "TEST_ Student" and s["beneficiary_ref"] == "STU-123"
        sid = s["id"]
        # dedup: same institution different case + whitespace
        r = _submit(user_h, inst="  " + INST.upper() + " ", ref="INV-B")
        assert r.status_code == 200, r.text
        rows = [x for x in _saved(user_h) if x["institution"].lower() == INST.lower()]
        assert len(rows) == 1 and rows[0]["id"] == sid
        # different account -> new row
        r = _submit(user_h, acct=ACCT + "X", ref="INV-C")
        assert r.status_code == 200
        rows2 = [x for x in _saved(user_h) if x["institution"].lower() == INST.lower()]
        assert len(rows2) == 2
        # other user can't see/delete
        assert sid not in [x["id"] for x in _saved(other_h)]
        assert requests.delete(f"{API}/bills/saved/{sid}", headers=other_h, timeout=30).status_code == 404
        assert requests.delete(f"{API}/bills/saved/nope-{TAG}", headers=user_h, timeout=30).status_code == 404
        # owner deletes both
        for x in rows2:
            d = requests.delete(f"{API}/bills/saved/{x['id']}", headers=user_h, timeout=30)
            assert d.status_code == 200 and d.json() == {"ok": True}
        assert not [x for x in _saved(user_h) if x["institution"].lower() == INST.lower()]
        assert requests.delete(f"{API}/bills/saved/{sid}", headers=user_h, timeout=30).status_code == 404

    def test_empty_reference_still_rejected(self, user_h):
        r = _submit(user_h, inst=f"TEST_ EmptyRef {TAG}", ref="", save=True)
        assert r.status_code == 422
