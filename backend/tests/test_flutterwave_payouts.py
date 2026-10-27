"""Flutterwave payout provider: banks, account resolve, app config, admin switch,
plus regression on remit quote."""
import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_BACKEND_URL", os.environ.get("EXPO_PUBLIC_BACKEND_URL", "")).rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("EXPO_PUBLIC_BACKEND_URL=") or line.startswith("EXPO_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().strip('"').rstrip("/")
API = f"{BASE_URL}/api"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    if r.status_code != 200:
        return None
    d = r.json()
    return d.get("token") or d.get("access_token")


@pytest.fixture(scope="module")
def user_h():
    t = _login("smoketest@vaulted.app", "test1234")
    if not t:
        pytest.skip("smoketest login failed")
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="module")
def admin_h():
    """Admin: login, or mint a session via backend helper if password unknown."""
    import asyncio, sys
    sys.path.insert(0, "/app/backend")
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    try:
        from deps import make_token as create_token  # type: ignore
    except Exception:
        create_token = None
    from motor.motor_asyncio import AsyncIOMotorClient

    async def get_admin():
        c = AsyncIOMotorClient(os.environ["MONGO_URL"])
        u = await c[os.environ["DB_NAME"]].users.find_one({"email": "umar.sani@phoenix-atlas.com"}, {"_id": 0, "id": 1})
        c.close()
        return u
    u = asyncio.get_event_loop().run_until_complete(get_admin()) if False else asyncio.run(get_admin())
    if not u or not create_token:
        pytest.skip("admin user / token helper unavailable")
    return {"Authorization": f"Bearer {create_token(u['id'])}"}


# --- Banks ---
class TestBanks:
    def test_banks_ng_live(self, user_h):
        r = requests.get(f"{API}/payouts/banks", params={"country": "NG"}, headers=user_h, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["mode"] == "live"
        assert len(d["banks"]) > 500, len(d["banks"])
        assert all(b["id"] == b["code"] for b in d["banks"])
        access = [b for b in d["banks"] if b["code"] == "044"]
        assert access and "access" in access[0]["name"].lower()
        print("banks:", len(d["banks"]), access[0])

    def test_banks_non_ng_400(self, user_h):
        r = requests.get(f"{API}/payouts/banks", params={"country": "KE"}, headers=user_h, timeout=30)
        assert r.status_code == 400

    def test_banks_requires_auth(self):
        r = requests.get(f"{API}/payouts/banks", timeout=30)
        assert r.status_code in (401, 403)


# --- Resolve account ---
class TestResolve:
    def test_resolve_valid(self, user_h):
        r = requests.post(f"{API}/payouts/resolve-account",
                          json={"account_number": "0690000031", "bank_id": "044"}, headers=user_h, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["account_name"].lower() == "ajadi jackson"
        assert d["mode"] == "live"

    def test_resolve_invalid_404(self, user_h):
        r = requests.post(f"{API}/payouts/resolve-account",
                          json={"account_number": "1234567899", "bank_id": "XYZ"}, headers=user_h, timeout=60)
        # NOTE: FLW sandbox returns 'Ajadi Jackson' for ANY numeric account/bank; only invalid codes fail
        print("invalid resolve:", r.status_code, r.text[:200])
        assert r.status_code == 404

    def test_resolve_bad_format_422(self, user_h):
        r = requests.post(f"{API}/payouts/resolve-account",
                          json={"account_number": "12ab", "bank_id": "044"}, headers=user_h, timeout=30)
        assert r.status_code == 422


# --- App config ---
def test_app_config():
    r = requests.get(f"{API}/app/config", timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert d["payout_provider"] == "flutterwave"
    assert d["payout_provider_label"] == "Flutterwave"
    assert d["beta_test_mode"] is True


# --- Admin ---
class TestAdmin:
    def test_admin_get(self, admin_h):
        r = requests.get(f"{API}/admin/payouts", headers=admin_h, timeout=90)
        assert r.status_code == 200, r.text
        fw = r.json()["providers"]["flutterwave"]
        assert fw["probe"]["ok"] is True, fw
        assert set(fw["countries"]) == {"NG", "KE", "GH", "UG", "TZ", "RW"}
        assert fw["config"]["mode"] == "live" and fw["config"]["sandbox"] is True
        print("probe:", fw["probe"])

    def test_admin_non_admin_403(self, user_h):
        r = requests.get(f"{API}/admin/payouts", headers=user_h, timeout=30)
        assert r.status_code == 403

    def test_admin_switch_and_back(self, admin_h):
        try:
            r = requests.put(f"{API}/admin/payouts", json={"provider": "kotani"}, headers=admin_h, timeout=30)
            assert r.status_code == 200 and r.json()["settings"]["provider"] == "kotani"
            c = requests.get(f"{API}/app/config", timeout=30).json()
            assert c["payout_provider"] == "kotani" and c["payout_provider_label"] == "Kotani Pay"
            bad = requests.put(f"{API}/admin/payouts", json={"provider": "bogus"}, headers=admin_h, timeout=30)
            assert bad.status_code == 400
        finally:
            r = requests.put(f"{API}/admin/payouts", json={"provider": "flutterwave", "beta_test_mode": True},
                             headers=admin_h, timeout=30)
            assert r.status_code == 200
            s = r.json()["settings"]
            assert s["provider"] == "flutterwave" and s["beta_test_mode"] is True


# --- Regression: remit quote ---
class TestRemitQuote:
    @pytest.mark.parametrize("dest", ["NG", "KE"])
    def test_quote(self, user_h, dest):
        r = requests.post(f"{API}/remit/quote", json={"source_fiat": "GBP", "amount": 50, "destination_code": dest},
                          headers=user_h, timeout=90)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["destination"]["amount"] > 0
        assert d["fees"]["total_fee_usd"] >= 0
        print(dest, d["destination"]["currency"], d["destination"]["amount"])

    def test_corridors(self, user_h):
        r = requests.get(f"{API}/remit/corridors", headers=user_h, timeout=30)
        assert r.status_code == 200
