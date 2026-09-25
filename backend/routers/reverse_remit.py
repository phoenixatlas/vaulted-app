"""Reverse-corridor remittance quotes — Africa → UK/EU.

This is the *bi-directional* half of Vaulted's remit engine. While the main
`/remit/quote` endpoint powers UK/EU-outbound sends (GBP/USD/EUR → mobile
money in Africa), this router powers the *inbound* side: a user in Nigeria
paying UK university fees, a Kenyan family paying for medical treatment
in London, a Ghanaian parent sending rent to a child studying in Dublin.

**Product model (Phase 1 — quote-only, launch-signup gated)**:
  Sender (Africa)               Bridge                 Recipient (UK/EU)
  ─────────────                 ──────                 ──────────────────
  Mobile money / bank    →   Vaulted stablecoin   →   GBP/EUR bank payout
  (Kotani onramp)             (USDC on Polygon)        (Vaulted's PSP)

We fetch a **live Kotani onramp rate** (fiat → USDC) and combine it with our
existing FX cache (USD → GBP/EUR) to give the sender a familiar all-in
GBP/EUR receive amount. Actual settlement rails on the *receive* side (UK
Faster Payments / SEPA) are Phase 2 — until then, quote-only + waitlist
capture so we can measure demand and hand hot leads to sales.

Endpoints:
  GET  /api/remit/reverse/corridors
      Public — returns the four supported source countries + destination
      fiats + typical use cases. Used by the /remit screen and landing page.

  POST /api/remit/reverse/quote
      Auth-optional (public preview allowed for landing-page demos).
      body: {"source_country": "NG", "source_amount": 50000,
             "destination_currency": "GBP"}
      Returns: {"source": {...}, "destination": {...},
                "bridge": {"stablecoin", "chain", "amount"},
                "fees": {"kotani_fee_usd", "vaulted_fee_usd", "total"},
                "kotani": {"rate_id", "mode"},
                "eta": "~2 min", "status": "quote_only",
                "waitlist_cta": true}

Docs:
  - Kotani onramp flow: https://documentation.kotanipay.com/v3/flows/onramp-flow
  - GET rate: /api/v3/rates/onramp-rate (also POST /api/v3/rate/onramp)
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import kotani
from deps import db, iso, logger, now_utc
from remit import refresh_fx_rates, convert_fiat

router = APIRouter()

# ---- Source-corridor catalogue -------------------------------------------
# Countries where a Vaulted user can *originate* a send to the UK/EU. Each
# entry lists the network(s) Kotani supports for on-ramping the fiat plus
# the copywriting we surface in the app UI.
SOURCE_CORRIDORS: dict[str, dict] = {
    "NG": {
        "country": "Nigeria",
        "currency": "NGN",
        "flag": "🇳🇬",
        "kotani_network": "MTN",           # Kotani NG uses bank rails today
        "fund_via": "Bank transfer",
        "eta": "~2 min",
        "use_cases": ["UK university fees", "Medical treatment", "Mortgage/rent"],
        "min_amount": 5000,     # NGN
        "max_amount": 5000000,  # NGN — ~£2,500 at 2000 NGN/GBP
    },
    "KE": {
        "country": "Kenya",
        "currency": "KES",
        "flag": "🇰🇪",
        "kotani_network": "MPESA",
        "fund_via": "M-Pesa",
        "eta": "~90 sec",
        "use_cases": ["School fees abroad", "Medical bills", "Property"],
        "min_amount": 500,      # KES
        "max_amount": 400000,   # KES — ~£2,000 at 200 KES/GBP
    },
    "GH": {
        "country": "Ghana",
        "currency": "GHS",
        "flag": "🇬🇭",
        "kotani_network": "MTN",
        "fund_via": "Mobile Money (MTN/Vodafone)",
        "eta": "~2 min",
        "use_cases": ["Tuition remittance", "Family support", "Travel"],
        "min_amount": 100,      # GHS
        "max_amount": 30000,    # GHS — ~£1,600 at 18 GHS/GBP
    },
    "ZA": {
        "country": "South Africa",
        "currency": "ZAR",
        "flag": "🇿🇦",
        "kotani_network": "MTN",   # Placeholder — SA uses bank rails via partner
        "fund_via": "Bank transfer / MoMo",
        "eta": "~2 min",
        "use_cases": ["Business payments", "Property", "Family support"],
        "min_amount": 200,      # ZAR
        "max_amount": 40000,    # ZAR — ~£1,700 at 24 ZAR/GBP
    },
}

# Destination fiats we can pay out on (Phase 2 rails).
DESTINATION_FIATS: dict[str, dict] = {
    "GBP": {
        "currency": "GBP",
        "symbol": "£",
        "country": "United Kingdom",
        "flag": "🇬🇧",
        "receive_via": "UK Faster Payments (Phase 2)",
        "eta": "~10 min once live",
    },
    "EUR": {
        "currency": "EUR",
        "symbol": "€",
        "country": "Eurozone",
        "flag": "🇪🇺",
        "receive_via": "SEPA Instant (Phase 2)",
        "eta": "~10 min once live",
    },
}

# The stablecoin bridge we use — cheap, near-instant L2.
BRIDGE_CHAIN = "POLYGON"
BRIDGE_TOKEN = "USDC"

# Vaulted service fee for reverse corridors (Phase 2 launch pricing):
# Flat 1.75% with £2.00 minimum and £14.99 cap. Slightly higher than
# outbound because on-ramp fees + FCA-authorized GBP payout rails cost
# more to run than off-ramp mobile-money settlement.
def _vaulted_reverse_fee_usd(amount_usd: float) -> float:
    base = max(2.0, min(14.99, amount_usd * 0.0175))
    return round(base, 2)


class ReverseQuoteIn(BaseModel):
    source_country: str = Field(..., min_length=2, max_length=2)
    source_amount: float = Field(..., gt=0)
    destination_currency: str = Field(default="GBP", min_length=3, max_length=3)


@router.get("/remit/reverse/corridors")
async def reverse_corridors():
    """Public catalog of reverse (Africa → UK/EU) corridors — powers the
    /remit screen chips and the landing page 'Send to UK/EU' section."""
    sources = [{"code": code, **info} for code, info in SOURCE_CORRIDORS.items()]
    destinations = [{"code": code, **info} for code, info in DESTINATION_FIATS.items()]
    return {
        "sources": sources,
        "destinations": destinations,
        "bridge": {"chain": BRIDGE_CHAIN, "token": BRIDGE_TOKEN},
        "status": "quote_only",
        "note": (
            "Reverse corridors are in Phase 1 — live rate quotes are available; "
            "actual GBP/EUR settlement launches with our UK PSP integration in Phase 2."
        ),
    }


@router.post("/remit/reverse/quote")
async def reverse_quote(body: ReverseQuoteIn):
    """Return a live reverse-corridor quote using Kotani onramp + FX cache.

    Fully public (no auth) so the landing page can demo real rates.
    Rate-limiting is upstream via CORS/Cloudflare; no per-user gates.
    """
    src_code = (body.source_country or "").upper()
    corridor = SOURCE_CORRIDORS.get(src_code)
    if not corridor:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported source corridor '{src_code}'. Supported: NG, KE, GH, ZA.",
        )

    dst_code = (body.destination_currency or "GBP").upper()
    dest = DESTINATION_FIATS.get(dst_code)
    if not dest:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported destination currency '{dst_code}'. Supported: GBP, EUR.",
        )

    src_amount = float(body.source_amount)
    if src_amount < corridor["min_amount"]:
        raise HTTPException(
            status_code=400,
            detail=f"Minimum send from {corridor['country']} is {corridor['min_amount']} {corridor['currency']}.",
        )
    if src_amount > corridor["max_amount"]:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum send from {corridor['country']} is {corridor['max_amount']} {corridor['currency']} (KYC required for higher).",
        )

    # 1) Kotani onramp rate: fiat → USDC on Polygon.
    kot = await kotani.onramp_rate(
        from_currency=corridor["currency"],
        to_token=BRIDGE_TOKEN,
        fiat_amount=src_amount,
        chain=BRIDGE_CHAIN,
    )

    # Kotani sandbox has ONRAMP disabled per-integrator (same permission
    # gate that blocked the offramp customer_create call). Fall back to
    # our internal FX-cache mock quote so the UI still delivers a usable
    # rate — we flag it as `estimated` so the sender knows.
    kotani_service_disabled = (
        not kot.get("success")
        and "not available" in (kot.get("data") or {}).get("message", "").lower()
    )
    mode = "live" if kotani.live_mode() else "mock"
    if kotani_service_disabled:
        logger.info(
            "[reverse-remit] Kotani ONRAMP not yet enabled for %s — using estimated rate",
            src_code,
        )
        kot = kotani._mock_onramp_rate(corridor["currency"], BRIDGE_TOKEN, src_amount)
        mode = "estimated"

    if not kot.get("success"):
        logger.warning("[reverse-remit] kotani onramp rate failed: %s", kot)
        raise HTTPException(status_code=502, detail="Live rate unavailable — please try again shortly.")

    k_data = kot.get("data") or {}
    usdc_amount = kotani.extract_crypto_amount(kot) or 0.0
    kotani_fee_fiat = float(k_data.get("fee") or 0.0)
    kotani_effective_rate = float(k_data.get("value") or 0.0)  # source_fiat per 1 USDC

    if usdc_amount <= 0 or kotani_effective_rate <= 0:
        raise HTTPException(status_code=502, detail="Kotani returned an invalid quote — please try again.")

    # Convert Kotani fee (source fiat) → USD for consistent fee accounting
    # (1 USDC ≈ 1 USD, so kotani_fee_fiat / rate gives the USD equivalent).
    kotani_fee_usd = round(kotani_fee_fiat / kotani_effective_rate, 2) if kotani_effective_rate else 0.0

    # 2) FX cache: USD → GBP/EUR (open.er-api.com backed, 6h TTL).
    fx_record = await refresh_fx_rates(db)
    rates = fx_record.get("rates") or {}
    if dst_code not in rates:
        raise HTTPException(status_code=502, detail=f"FX rate for {dst_code} unavailable.")

    dest_amount_gross = convert_fiat(usdc_amount, "USD", dst_code, rates)

    # 3) Vaulted service fee (USD, translated to destination fiat for display).
    vaulted_fee_usd = _vaulted_reverse_fee_usd(usdc_amount)
    vaulted_fee_dest = convert_fiat(vaulted_fee_usd, "USD", dst_code, rates)

    dest_amount_net = max(0.0, dest_amount_gross - vaulted_fee_dest)

    # 4) All-in effective rate the sender experiences (source_fiat per 1 unit dest fiat)
    #    e.g. how many KES per 1 GBP received.
    all_in_rate = src_amount / dest_amount_net if dest_amount_net > 0 else 0.0

    total_fee_usd = round(kotani_fee_usd + vaulted_fee_usd, 2)

    return {
        "quote_id": f"rev_{k_data.get('id') or ''}",
        "status": "quote_only",
        "waitlist_cta": True,
        "source": {
            "country": corridor["country"],
            "country_code": src_code,
            "currency": corridor["currency"],
            "flag": corridor["flag"],
            "amount": src_amount,
            "fund_via": corridor["fund_via"],
        },
        "bridge": {
            "chain": BRIDGE_CHAIN,
            "token": BRIDGE_TOKEN,
            "amount": round(usdc_amount, 6),
        },
        "destination": {
            "country": dest["country"],
            "currency": dst_code,
            "flag": dest["flag"],
            "symbol": dest["symbol"],
            "receive_via": dest["receive_via"],
            "amount": round(dest_amount_net, 2),
            "amount_gross": round(dest_amount_gross, 2),
        },
        "fees": {
            "kotani_fee_fiat": round(kotani_fee_fiat, 2),
            "kotani_fee_usd": kotani_fee_usd,
            "vaulted_fee_usd": vaulted_fee_usd,
            "vaulted_fee_dest": round(vaulted_fee_dest, 2),
            "total_fee_usd": total_fee_usd,
        },
        "rates": {
            "source_per_usdc": kotani_effective_rate,
            "all_in_source_per_dest": round(all_in_rate, 4),
            "usd_per_dest": rates.get(dst_code),
        },
        "kotani": {
            "rate_id": kotani.extract_rate_id(kot),
            "mode": mode,
        },
        "eta": corridor["eta"],
        "fetched_at": iso(now_utc()),
    }
