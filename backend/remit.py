"""Cross-border remittance quote engine.

Turns a fiat-first user intent ("send £50 to Kenya") into a concrete
crypto payment: picks the cheapest chain the user has liquidity on,
computes the exact crypto amount, and shows the recipient the amount
in their local currency. Uses:

  - CoinGecko (already wired via server._refresh_market_prices) for
    crypto/USD prices.
  - open.er-api.com (free, no-key) for fiat/fiat conversion, cached in
    Mongo with a 6-hour TTL.

The receiver still ultimately gets crypto in this iteration — a real
fiat off-ramp partner (Kotani, Onafriq, YellowCard, etc.) is Phase C.
The fiat display gives the sender a familiar UX right now so we can
market the app as a remittance product.
"""

from __future__ import annotations

import os
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx


logger = logging.getLogger("vaulted.remit")


# ---------- Corridor catalog ------------------------------------------------
# The countries we launch with — chosen for high UK/US-outbound remittance
# volume and existing (or imminent) crypto off-ramp presence.
CORRIDORS: dict[str, dict] = {
    "KE": {"country": "Kenya", "currency": "KES", "flag": "🇰🇪", "receive_via": "M-Pesa (via partner)", "eta": "~30s"},
    "NG": {"country": "Nigeria", "currency": "NGN", "flag": "🇳🇬", "receive_via": "Bank transfer (via partner)", "eta": "~1min"},
    "IN": {"country": "India", "currency": "INR", "flag": "🇮🇳", "receive_via": "UPI / bank (via partner)", "eta": "~1min"},
    "PH": {"country": "Philippines", "currency": "PHP", "flag": "🇵🇭", "receive_via": "GCash / bank (via partner)", "eta": "~1min"},
    "SN": {"country": "Senegal", "currency": "XOF", "flag": "🇸🇳", "receive_via": "Wave / Orange Money (via partner)", "eta": "~30s"},
    "CI": {"country": "Côte d'Ivoire", "currency": "XOF", "flag": "🇨🇮", "receive_via": "Wave / Orange Money (via partner)", "eta": "~30s"},
    "GH": {"country": "Ghana", "currency": "GHS", "flag": "🇬🇭", "receive_via": "MoMo (via partner)", "eta": "~30s"},
    "MX": {"country": "Mexico", "currency": "MXN", "flag": "🇲🇽", "receive_via": "SPEI / bank (via partner)", "eta": "~1min"},
}

# Fiat currencies we let the *sender* denominate in.
SOURCE_FIATS = ["GBP", "USD", "EUR"]

# Chains that are viable for remittances (fast + cheap). Ordered by preference:
# XLM first (5s finality, near-zero fee), XRP second (3-5s, ~10 drops),
# USDC on ETH last (slow + expensive gas on mainnet — used only as fallback
# and mostly for corridors where stablecoin liquidity matters most, e.g. NGN).
REMIT_CHAINS = ["XLM", "XRP", "USDC"]

# Per-chain per-tx fee in the chain's native token, converted to USD at quote time.
CHAIN_FIXED_FEE_NATIVE = {
    "XLM": 0.00001,   # 100 stroops
    "XRP": 0.00001,   # ~10 drops of headroom
    "USDC": 0.0,      # gas paid in ETH, we absorb this in "protocol_fee_usd"
}
# When the chain is USDC on Ethereum, gas dominates — we quote a flat estimate
# rather than probing gas price per quote (would slow down every quote request).
USDC_GAS_ESTIMATE_USD = 2.50  # Sepolia we pay $0; keeping conservative estimate for UX honesty


# ---------- Fiat FX cache ---------------------------------------------------
FX_CACHE_TTL_SECONDS = 6 * 3600  # 6 hours — fiat rates rarely move meaningfully within a day
_FX_URL = "https://open.er-api.com/v6/latest/USD"  # free, no API key


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


async def refresh_fx_rates(db) -> dict:
    """Fetch USD-base fiat rates and cache them in `db.fx_cache`.

    Returns {"rates": {"USD": 1, "GBP": 0.78, ...}, "fetched_at": iso}.
    Falls back to cached (even stale) values if the API is unreachable so
    that the app degrades gracefully offline / during upstream outages.
    """
    cached = await db.fx_cache.find_one({"_id": "usd_rates"}, {"_id": 0})
    if cached and cached.get("fetched_at"):
        try:
            t = datetime.fromisoformat(cached["fetched_at"])
            age = (_now_utc() - t).total_seconds()
            if age < FX_CACHE_TTL_SECONDS:
                return cached
        except Exception:
            pass

    rates: dict[str, float] = {}
    try:
        async with httpx.AsyncClient(timeout=8) as cx:
            r = await cx.get(_FX_URL)
            if r.status_code == 200:
                data = r.json() or {}
                if data.get("result") == "success":
                    rates = {k: float(v) for k, v in (data.get("rates") or {}).items() if isinstance(v, (int, float))}
    except Exception as e:
        logger.warning(f"FX fetch failed: {e}")

    if not rates:
        if cached and cached.get("rates"):
            return cached  # stale but usable
        # Last-resort fallback so remittance quotes always work
        rates = {"USD": 1.0, "GBP": 0.78, "EUR": 0.92, "KES": 130.0, "NGN": 1580.0,
                 "INR": 83.4, "PHP": 58.5, "XOF": 605.0, "GHS": 15.2, "MXN": 18.9}

    record = {"rates": rates, "fetched_at": _iso(_now_utc())}
    await db.fx_cache.update_one({"_id": "usd_rates"}, {"$set": record}, upsert=True)
    return record


def convert_fiat(amount: float, src: str, dst: str, rates: dict[str, float]) -> float:
    """Convert `amount` from `src` fiat → `dst` fiat using USD-base rates."""
    if src == dst:
        return amount
    r_src = rates.get(src.upper()) or 1.0
    r_dst = rates.get(dst.upper()) or 1.0
    if r_src == 0:
        return 0.0
    return amount * (r_dst / r_src)


# ---------- Chain selection ------------------------------------------------
def choose_chain(
    amount_usd: float,
    holdings: dict[str, float],
    crypto_prices_usd: dict[str, float],
    preferred_chains: Optional[list[str]] = None,
) -> Optional[dict]:
    """Pick the cheapest chain the user has enough liquidity on.

    Returns {chain, crypto_amount, crypto_price_usd, fee_usd, total_cost_usd}
    or None if the user has insufficient liquidity across all supported chains.
    """
    chains = preferred_chains or REMIT_CHAINS
    for chain in chains:
        price = crypto_prices_usd.get(chain)
        if not price or price <= 0:
            continue
        # Chain fee in USD
        if chain == "USDC":
            fee_usd = USDC_GAS_ESTIMATE_USD
        else:
            fee_usd = CHAIN_FIXED_FEE_NATIVE.get(chain, 0.0) * price

        # Amount of crypto needed to cover the send + chain fee
        crypto_needed = amount_usd / price
        held = holdings.get(chain, 0.0)
        # For XLM: 1 XLM reserved for account; for XRP: 1 XRP testnet / 10 mainnet
        reserve = 1.0 if chain == "XLM" else (1.0 if chain == "XRP" else 0.0)
        if held < crypto_needed + reserve + (CHAIN_FIXED_FEE_NATIVE.get(chain, 0.0) * 2):
            continue

        return {
            "chain": chain,
            "crypto_amount": round(crypto_needed, 7),
            "crypto_price_usd": price,
            "chain_fee_usd": round(fee_usd, 4),
        }
    return None


# ---------- Vaulted service fee ---------------------------------------------
# Flat corridor fee model: 1.5% of send amount, min $0.50, max $9.99.
# Pro users get 50% off (matches the /wallet Send screen's Pro discount).
def vaulted_fee_usd(amount_usd: float, is_pro: bool) -> float:
    base = max(0.50, min(9.99, amount_usd * 0.015))
    if is_pro:
        base *= 0.5
    return round(base, 2)


__all__ = [
    "CORRIDORS", "SOURCE_FIATS", "REMIT_CHAINS",
    "refresh_fx_rates", "convert_fiat",
    "choose_chain", "vaulted_fee_usd",
    "USDC_GAS_ESTIMATE_USD", "CHAIN_FIXED_FEE_NATIVE",
]
