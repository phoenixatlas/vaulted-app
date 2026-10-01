"""Live market-prices helper (CoinGecko, DB-cached).

Extracted from server.py during the P2 refactor so wallet.py and remit.py
can both call ``_refresh_market_prices`` without a circular import back
into server. Nothing stateful lives here — the only cache is in Mongo
``market_cache._id='prices'`` with a 5-minute TTL.
"""
from __future__ import annotations

from datetime import datetime
import httpx

from deps import db, logger, now_utc, iso


# CoinGecko ids for every asset we price. Keep this in sync with the
# wallet's DEFAULT_ASSETS catalogue — any new on-chain asset must be
# added here or its live price will silently fall back to 0.
COINGECKO_IDS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "USDC": "usd-coin",
    "SOL": "solana",
    "XLM": "stellar",
    "XRP": "ripple",
}

# 5-minute cache — balances between fresh prices and CoinGecko rate limits.
PRICE_CACHE_TTL_SECONDS = 300


async def _refresh_market_prices() -> dict:
    """Fetch latest prices + 24h change + 7d sparkline. Cache in DB with TTL."""
    cached = await db.market_cache.find_one({"_id": "prices"}, {"_id": 0})
    if cached and cached.get("fetched_at"):
        try:
            t = datetime.fromisoformat(cached["fetched_at"])
            age = (now_utc() - t).total_seconds()
            if age < PRICE_CACHE_TTL_SECONDS:
                return cached
        except Exception:
            pass

    ids = ",".join(COINGECKO_IDS.values())
    url = (
        "https://api.coingecko.com/api/v3/coins/markets"
        f"?ids={ids}&vs_currency=usd&sparkline=true&price_change_percentage=24h"
    )
    out_assets: dict[str, dict] = {}
    try:
        async with httpx.AsyncClient(timeout=10) as cx:
            r = await cx.get(url)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list):
                    cg_to_sym = {v: k for k, v in COINGECKO_IDS.items()}
                    for coin in data:
                        sym = cg_to_sym.get(coin.get("id"))
                        if not sym:
                            continue
                        sparkline = coin.get("sparkline_in_7d", {}).get("price", [])
                        out_assets[sym] = {
                            "symbol": sym,
                            "price_usd": float(coin.get("current_price") or 0),
                            "change_24h_pct": float(coin.get("price_change_percentage_24h") or 0),
                            "sparkline_7d": [float(x) for x in sparkline[-48:]],
                            "market_cap": coin.get("market_cap"),
                        }
    except Exception as e:
        logger.warning(f"coingecko fetch failed: {e}")

    if not out_assets:
        if cached and cached.get("assets"):
            return cached
        out_assets = {
            sym: {"symbol": sym, "price_usd": p, "change_24h_pct": 0.0, "sparkline_7d": []}
            for sym, p in [("BTC", 67000), ("ETH", 3500), ("USDC", 1.0), ("SOL", 150), ("XLM", 0.12), ("XRP", 0.52)]
        }

    record = {
        "assets": out_assets,
        "fetched_at": iso(now_utc()),
        "stale": False,
    }
    await db.market_cache.update_one({"_id": "prices"}, {"$set": record}, upsert=True)
    return record
