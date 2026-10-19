"""Fiat FX rates — USD base, used for client-side display currency.

All balances/prices across the app are stored in USD. This endpoint
hands the client the live rate table so a user picking GBP/EUR/NGN/KES
in Settings sees their balances re-rendered in that currency, without
touching the ledger.

Source: https://open.er-api.com (free, no key, 24h refresh upstream).
Cache: Mongo (`fx_rates_cache`) with 1h TTL to protect the upstream.
Fallback: a static snapshot shipped with the code so we NEVER return
an empty rate map even if the upstream is down.
"""
from __future__ import annotations

import os
import time
from typing import Optional

import httpx
from fastapi import APIRouter

from deps import db, iso, logger, now_utc

router = APIRouter()

# Supported display currencies. Keep in sync with
# frontend/src/lib/currency.tsx `CURRENCIES` list — the client falls back
# to USD for anything not in this map.
SUPPORTED_CODES: tuple[str, ...] = (
    "USD", "GBP", "EUR",
    "NGN", "KES", "GHS", "UGX", "TZS", "ZMW", "ZAR",
)

# Static fallback — snapshot mid-June 2026. Updated anytime we deploy a
# release so it's never more than ~a few weeks stale. The live upstream
# fetch overrides these the moment it succeeds.
_FALLBACK_RATES: dict[str, float] = {
    "USD": 1.0,
    "GBP": 0.787,
    "EUR": 0.925,
    "NGN": 1546.0,
    "KES": 129.0,
    "GHS": 15.6,
    "UGX": 3745.0,
    "TZS": 2612.0,
    "ZMW": 27.1,
    "ZAR": 18.4,
}

_CACHE_ID = "usd_base"
_CACHE_TTL_SECONDS = 60 * 60  # 1h — upstream only refreshes once a day


async def _fetch_live_rates() -> Optional[dict[str, float]]:
    """Pull USD-base rates from open.er-api.com. Returns None on any
    failure so the caller falls back to cache/snapshot without raising."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(8.0, connect=4.0)) as cx:
            r = await cx.get("https://open.er-api.com/v6/latest/USD")
            if r.status_code != 200:
                logger.warning("[rates] upstream http %s", r.status_code)
                return None
            body = r.json() or {}
            rates = body.get("rates") or {}
            if not isinstance(rates, dict):
                return None
            # Keep only the currencies we care about so the payload stays
            # tiny and we never surprise the client with an unknown code.
            filtered: dict[str, float] = {}
            for code in SUPPORTED_CODES:
                v = rates.get(code)
                if isinstance(v, (int, float)) and v > 0:
                    filtered[code] = float(v)
            # Guarantee USD is always present with rate 1.0 even if the
            # upstream omitted it (it won't, but belt-and-braces).
            filtered.setdefault("USD", 1.0)
            if len(filtered) < 2:  # upstream clearly misbehaved
                return None
            return filtered
    except Exception as e:  # noqa: BLE001
        logger.warning("[rates] upstream fetch exception: %s", e)
        return None


async def _cached_rates() -> dict[str, float]:
    """Mongo-cached rates with 1h TTL. On cache miss or stale, fetch
    live; on fetch failure, use last-known-good or static fallback."""
    try:
        doc = await db.fx_rates_cache.find_one({"_id": _CACHE_ID}) or {}
    except Exception:
        doc = {}
    fetched_at = doc.get("fetched_at_ts") or 0
    rates = doc.get("rates") or {}
    fresh = isinstance(rates, dict) and rates and (time.time() - fetched_at) < _CACHE_TTL_SECONDS

    if fresh:
        return rates

    live = await _fetch_live_rates()
    if live:
        try:
            await db.fx_rates_cache.update_one(
                {"_id": _CACHE_ID},
                {"$set": {
                    "rates": live,
                    "fetched_at_ts": time.time(),
                    "fetched_at_iso": iso(now_utc()),
                    "source": "open.er-api.com",
                }},
                upsert=True,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("[rates] cache persist failed: %s", e)
        return live

    # Live failed — serve last known good even if stale, else static.
    if isinstance(rates, dict) and rates:
        return rates
    return dict(_FALLBACK_RATES)


@router.get("/rates/fiat")
async def get_fiat_rates() -> dict:
    """Public endpoint — returns USD-base conversion rates for the
    display currencies the app supports. Response shape:

        {
          "base": "USD",
          "rates": {"USD": 1.0, "GBP": 0.787, "EUR": 0.925, ...},
          "fetched_at": "2026-06-18T10:04:12Z",
          "source": "open.er-api.com",
          "fallback": false
        }
    """
    rates = await _cached_rates()
    try:
        doc = await db.fx_rates_cache.find_one({"_id": _CACHE_ID}) or {}
    except Exception:
        doc = {}
    is_fallback = not doc.get("rates")
    return {
        "base": "USD",
        "rates": rates,
        "fetched_at": doc.get("fetched_at_iso") or iso(now_utc()),
        "source": doc.get("source") or ("open.er-api.com" if not is_fallback else "fallback-snapshot"),
        "fallback": is_fallback,
        "supported": list(SUPPORTED_CODES),
    }
