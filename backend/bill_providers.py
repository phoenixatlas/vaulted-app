"""International Bill Payments — partner routing.

Each regulated partner declares which payer countries, payout currencies and
purposes it supports, plus its (illustrative, test-mode) pricing and
settlement time. `select_provider` filters by the request and picks the
cheapest eligible partner. Add a partner by appending to PROVIDERS.
Beta: every partner runs in TEST MODE — no real money moves.
"""
from typing import Optional

PAYER_COUNTRIES = {
    "NG": {"name": "Nigeria", "currency": "NGN"},
    "KE": {"name": "Kenya", "currency": "KES"},
    "GH": {"name": "Ghana", "currency": "GHS"},
    "ZA": {"name": "South Africa", "currency": "ZAR"},
}
PAYOUT_CURRENCIES = {
    "GBP": {"country": "United Kingdom", "rail": "Faster Payments / SWIFT", "routing_label": "Sort code"},
    "EUR": {"country": "Eurozone", "rail": "SEPA / SWIFT", "routing_label": "BIC / SWIFT"},
    "USD": {"country": "United States", "rail": "ACH / Fedwire / SWIFT", "routing_label": "ABA routing number"},
    "CAD": {"country": "Canada", "rail": "EFT / SWIFT", "routing_label": "Transit + institution number"},
}
CATEGORIES = {
    "education": {"label": "Education", "tagline": "Tuition and school fees",
                  "subtypes": ["Tuition fees", "Accommodation", "Application / exam fees", "Other education costs"],
                  "fields": [("beneficiary_name", "Student full name"), ("beneficiary_ref", "Student ID / reference"),
                             ("institution", "University or school")]},
    "healthcare": {"label": "Healthcare", "tagline": "Hospital and medical bills",
                   "subtypes": ["Hospital invoice", "Treatment deposit", "Consultation", "Other medical costs"],
                   "fields": [("beneficiary_name", "Patient full name"), ("beneficiary_ref", "Patient / invoice reference"),
                              ("institution", "Hospital or clinic")]},
    "business": {"label": "Business", "tagline": "Qualifying international invoices",
                 "subtypes": ["Goods", "Services", "Software / subscriptions", "Other business costs"],
                 "fields": [("beneficiary_name", "Supplier legal name"), ("beneficiary_ref", "Invoice number"),
                            ("institution", "What the invoice is for")]},
}

PROVIDERS = [
    {"id": "flutterwave", "label": "Flutterwave", "mode": "test",
     "payer_countries": {"NG", "KE", "GH", "ZA"}, "payout_currencies": {"GBP", "EUR", "USD"},
     "categories": {"education", "healthcare", "business"},
     "fee_pct": 0.010, "fee_fixed_usd": 5.0, "fx_margin": 0.006, "settlement": "1–2 business days"},
    {"id": "simulated_fx", "label": "Simulated FX partner", "mode": "test",
     "payer_countries": {"NG", "KE", "GH", "ZA"}, "payout_currencies": {"GBP", "EUR", "USD", "CAD"},
     "categories": {"education", "healthcare", "business"},
     "fee_pct": 0.012, "fee_fixed_usd": 4.0, "fx_margin": 0.008, "settlement": "2–3 business days"},
]


def _cost_usd(p: dict, amount_usd: float) -> float:
    return amount_usd * (p["fee_pct"] + p["fx_margin"]) + p["fee_fixed_usd"]


def select_provider(payer_country: str, payout_currency: str, category: str, amount_usd: float) -> Optional[dict]:
    eligible = [p for p in PROVIDERS if payer_country in p["payer_countries"]
                and payout_currency in p["payout_currencies"] and category in p["categories"]]
    return min(eligible, key=lambda p: _cost_usd(p, amount_usd)) if eligible else None
