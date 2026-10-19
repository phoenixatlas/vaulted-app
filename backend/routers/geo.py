"""Geo-IP detection — used to smart-pick a display currency on first launch.

Reads Cloudflare's `cf-ipcountry` header first (free, zero-latency, present
on every deploy behind Cloudflare), then falls back to a free IP geolocation
API (`ipapi.co`) if the header is missing. Returns a country code plus a
suggested display currency so the client can preselect it without the user
having to open Settings.

Response shape:
    {
      "country": "GB",
      "country_name": "United Kingdom",
      "suggested_currency": "GBP",
      "ip": "203.0.113.42",      # optional, for debug only
      "source": "cf-header" | "ipapi.co" | "fallback"
    }

Deliberately permissive: on ANY failure we return
`{country: null, suggested_currency: "USD", source: "fallback"}` so the
caller is never left without a sensible default.
"""
from __future__ import annotations

from typing import Optional

import httpx
from fastapi import APIRouter, Request

from deps import logger

router = APIRouter()

# Country → preferred display currency.  Must stay a strict subset of the
# codes the frontend's CURRENCIES list in `src/lib/currency.tsx` knows how
# to render — unknown codes degrade gracefully to USD.
COUNTRY_TO_CURRENCY: dict[str, str] = {
    # Our live African corridors + two upcoming.
    "NG": "NGN", "KE": "KES", "GH": "GHS",
    "UG": "UGX", "TZ": "TZS", "ZM": "ZMW",
    "ZA": "ZAR",
    # Primary UK/EU senders.
    "GB": "GBP", "IE": "EUR",
    # Eurozone — single map keeps the file compact, EUR is the right default
    # for all of these on day one.
    "DE": "EUR", "FR": "EUR", "IT": "EUR", "ES": "EUR", "NL": "EUR",
    "BE": "EUR", "AT": "EUR", "PT": "EUR", "FI": "EUR", "GR": "EUR",
    "LU": "EUR", "SK": "EUR", "SI": "EUR", "LV": "EUR", "LT": "EUR",
    "EE": "EUR", "CY": "EUR", "MT": "EUR", "HR": "EUR",
    # Diaspora hotspots that still get USD by default (not in our rate list)
    # — we leave them to USD rather than invent a code the UI can't render.
}

# Country code → friendly name for the "detected from your IP" subtext.
# Only the ones we actively map to a non-USD currency are worth naming;
# anything else falls back to the raw ISO code.
COUNTRY_NAMES: dict[str, str] = {
    "NG": "Nigeria", "KE": "Kenya", "GH": "Ghana",
    "UG": "Uganda", "TZ": "Tanzania", "ZM": "Zambia", "ZA": "South Africa",
    "GB": "United Kingdom", "IE": "Ireland",
    "DE": "Germany", "FR": "France", "IT": "Italy", "ES": "Spain",
    "NL": "Netherlands", "BE": "Belgium", "AT": "Austria", "PT": "Portugal",
    "FI": "Finland", "GR": "Greece", "LU": "Luxembourg", "SK": "Slovakia",
    "SI": "Slovenia", "LV": "Latvia", "LT": "Lithuania", "EE": "Estonia",
    "CY": "Cyprus", "MT": "Malta", "HR": "Croatia",
}


def _client_ip(request: Request) -> Optional[str]:
    """Extract the first public-looking IP from standard proxy headers."""
    fwd = (request.headers.get("x-forwarded-for") or "").split(",")
    for raw in fwd:
        ip = raw.strip()
        if ip and not ip.startswith(("10.", "192.168.", "172.")) and ip != "127.0.0.1":
            return ip
    real = request.headers.get("x-real-ip")
    if real:
        return real.strip()
    if request.client:
        return request.client.host
    return None


async def _lookup_country_via_api(ip: str) -> Optional[str]:
    """Free, unauthenticated IP geolocation. Returns a 2-letter country
    code on success, None otherwise. Short timeout so we never block
    the client's startup path for more than a second."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(2.5, connect=1.5)) as cx:
            r = await cx.get(f"https://ipapi.co/{ip}/country/")
            if r.status_code == 200:
                code = r.text.strip().upper()
                if len(code) == 2 and code.isalpha():
                    return code
    except Exception as e:  # noqa: BLE001
        logger.info("[geo] ipapi lookup failed for %s: %s", ip, e)
    return None


@router.get("/geo")
async def detect_geo(request: Request) -> dict:
    """Best-effort geo detection → suggested display currency."""
    cf_country = (request.headers.get("cf-ipcountry") or "").strip().upper()
    source = "fallback"
    country: Optional[str] = None

    if cf_country and len(cf_country) == 2 and cf_country not in ("XX", "T1"):
        country = cf_country
        source = "cf-header"

    if country is None:
        ip = _client_ip(request)
        if ip:
            fetched = await _lookup_country_via_api(ip)
            if fetched:
                country = fetched
                source = "ipapi.co"

    currency = COUNTRY_TO_CURRENCY.get(country or "", "USD")
    return {
        "country": country,
        "country_name": COUNTRY_NAMES.get(country or "", country or None),
        "suggested_currency": currency,
        "source": source,
    }
