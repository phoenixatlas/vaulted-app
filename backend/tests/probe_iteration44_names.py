# Probe: which recipient name shapes Flutterwave sandbox rejects (→ silent simulated fallback)
import os, requests
API = os.environ["EXPO_BACKEND_URL"].rstrip("/") + "/api"
s = requests.Session()
tok = s.post(f"{API}/auth/login", json={"email": "smoketest@vaulted.app", "password": "test1234"}).json()
s.headers["Authorization"] = f"Bearer {tok.get('access_token') or tok.get('token')}"
base = {"email": "test_probe@example.com", "phone": "+44 7123 456789", "account_number": "12345678", "sort_code": "200000",
        "address": {"line1": "1 Test St", "city": "London", "postal_code": "N1 1AA", "country": "GB"}}
for name in ["TEST Smith & Co Ltd", "TEST King's College", "TEST Zoë Müller", "TEST2 Clinic 24", "TESTMadonna"]:
    r = s.post(f"{API}/remit/reverse/send", json={"source_country": "KE", "source_amount": 5000, "destination_currency": "GBP",
                                                 "purpose": "Family support", "recipient": {**base, "name": name}})
    p = (r.json() or {}).get("payout") or {}
    print(f"{name!r}: http={r.status_code} mode={p.get('mode')} reason={(p.get('reason') or '')[:160]}")
