"""Wallet router — crypto balances, sends, and recovery flows.

Extracted from server.py during the P2 refactor. Contains:
  * Wallet overview: /wallet/assets
  * Per-chain info + send: /wallet/eth/*, /wallet/btc/*, /wallet/sol/*,
    /wallet/usdc/* (Sepolia USDC), /wallet/xlm/*, /wallet/xrp/*
  * Market feed: /market/prices
  * Generic simulated send for non-chain assets: /wallet/send
  * Shared helpers for other routers:
    ``_eth_rpc``, ``_fetch_eth_balance_wei``, ``_ensure_multichain_addresses``,
    ``_broadcast_eth_send`` (reused by multisig + chat routers for
    cosigner-approved sends), and per-asset USD converters.

Keep this file flat — it's intentionally one router + its helpers so
imports stay shallow and the ``routers`` package stays easy to read.
"""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from eth_account import Account

from deps import (
    db,
    SEPOLIA_RPC_URL,
    SEPOLIA_CHAIN_ID,
    logger,
    now_utc,
    iso,
    is_user_pro,
    get_current_user,
    _ensure_eth_private_key,  # kept for parity with evm router importers
)
from models import (
    SendCryptoIn, SendUsdcIn, SendCoinIn, SendXlmIn, SendXrpIn, SendEthIn,
)
from multichain import (
    derive_addresses,
    fetch_btc_balance_sats,
    fetch_sol_balance_lamports,
    fetch_usdc_balance_micro,
    fetch_xlm_balance_stroops,
    fetch_xrp_balance_drops,
    encode_usdc_transfer,
    explorer_url_btc,
    explorer_url_sol,
    explorer_url_xlm,
    explorer_url_xrp,
    btc_send,
    sol_send,
    xlm_send,
    xrp_send,
    USDC_CONTRACT,
    BTC_TESTNET,
    USE_MAINNET,
)
from evm import fetch_usdc_balance_on_chain
from seed import DEFAULT_ASSETS, SEED_BALANCES
from market import _refresh_market_prices, PRICE_CACHE_TTL_SECONDS

router = APIRouter()


# ---------------------------------------------------------------------------
# ETH JSON-RPC helpers
# ---------------------------------------------------------------------------
async def _eth_rpc(method: str, params: list) -> dict:
    async with httpx.AsyncClient(timeout=12) as cx:
        r = await cx.post(
            SEPOLIA_RPC_URL,
            json={"jsonrpc": "2.0", "method": method, "params": params, "id": 1},
        )
        return r.json()


async def _fetch_eth_balance_wei(addr: str) -> int:
    data = await _eth_rpc("eth_getBalance", [addr, "latest"])
    return int(data.get("result", "0x0"), 16)


# ---------------------------------------------------------------------------
# Multichain address derivation (BTC + SOL + XLM + XRP)
# ---------------------------------------------------------------------------
async def _ensure_multichain_addresses(user: dict) -> dict:
    """Derive BTC + SOL + XLM + XRP addresses from the user's mnemonic if
    not yet stored. For legacy accounts created before BIP-39 onboarding,
    a fresh mnemonic is generated transparently — the old ETH key is
    preserved untouched (multichain derivation just needs *a* mnemonic,
    not the one that birthed the ETH key)."""
    if (
        user.get("btc_address")
        and user.get("sol_address")
        and user.get("xlm_address")
        and user.get("xrp_address")
    ):
        return {
            "btc": user["btc_address"],
            "sol": user["sol_address"],
            "xlm": user["xlm_address"],
            "xrp": user["xrp_address"],
        }
    mnemonic = user.get("eth_mnemonic") or user.get("mnemonic")
    update: dict = {}
    if not mnemonic:
        try:
            Account.enable_unaudited_hdwallet_features()
            _, mnemonic = Account.create_with_mnemonic()
        except Exception as e:
            logger.warning(f"legacy mnemonic backfill failed: {e}")
            return {"btc": None, "sol": None, "xlm": None, "xrp": None}
        update["eth_mnemonic"] = mnemonic
        update["mnemonic_origin"] = "multichain_only"
    try:
        addrs = derive_addresses(mnemonic)
    except Exception as e:
        logger.warning(f"multichain derivation failed: {e}")
        return {"btc": None, "sol": None, "xlm": None, "xrp": None}
    update["btc_address"] = addrs["btc"]
    update["sol_address"] = addrs["sol"]
    update["xlm_address"] = addrs["xlm"]
    update["xrp_address"] = addrs["xrp"]
    await db.users.update_one({"id": user["id"]}, {"$set": update})
    user.update(update)
    return {
        "btc": addrs["btc"],
        "sol": addrs["sol"],
        "xlm": addrs["xlm"],
        "xrp": addrs["xrp"],
    }


# ---------------------------------------------------------------------------
# Per-asset fiat converters
# ---------------------------------------------------------------------------
async def _price_usd(symbol: str) -> float:
    try:
        market = await _refresh_market_prices()
        assets = market.get("assets") or {}
        if isinstance(assets, dict):
            return float((assets.get(symbol) or {}).get("price_usd", 0))
        # Backwards-compat for the legacy list-shape cached rows
        for a in assets:
            if a.get("symbol") == symbol:
                return float(a.get("price_usd", 0))
    except Exception:
        pass
    return 0.0


async def _btc_to_usd(amount_btc: float) -> float:
    try:
        return round(amount_btc * await _price_usd("BTC"), 2)
    except Exception:
        return 0.0


async def _sol_to_usd(amount_sol: float) -> float:
    try:
        return round(amount_sol * await _price_usd("SOL"), 2)
    except Exception:
        return 0.0


async def _xlm_to_usd(amount_xlm: float) -> float:
    try:
        return round(amount_xlm * await _price_usd("XLM"), 2)
    except Exception:
        return 0.0


async def _xrp_to_usd(amount_xrp: float) -> float:
    try:
        return round(amount_xrp * await _price_usd("XRP"), 2)
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Wallet overview — /wallet/assets
# ---------------------------------------------------------------------------
@router.get("/wallet/assets")
async def wallet_assets(user=Depends(get_current_user)):
    cursor = db.balances.find({"user_id": user["id"]}, {"_id": 0})
    items = await cursor.to_list(100)

    # Backfill: ensure every DEFAULT_ASSET has a balance row for this user.
    existing_syms = {b.get("symbol") for b in items}
    for a in DEFAULT_ASSETS:
        if a["symbol"] not in existing_syms:
            row = {
                "id": str(uuid.uuid4()),
                "user_id": user["id"],
                "symbol": a["symbol"],
                "name": a["name"],
                "amount": SEED_BALANCES.get(a["symbol"], 0),
                "icon": a["icon"],
                "updated_at": iso(now_utc()),
            }
            try:
                await db.balances.insert_one(row)
            except Exception as e:
                logger.warning(f"balance backfill failed for {a['symbol']}: {e}")
            row.pop("_id", None)
            items.append(row)

    market = await _refresh_market_prices()
    market_assets = market.get("assets") or {}
    price_map = {sym: ma.get("price_usd", 0) for sym, ma in market_assets.items()}
    for a in DEFAULT_ASSETS:
        price_map.setdefault(a["symbol"], a["price_usd"])

    addr = user.get("wallet_address")
    eth_wei = 0
    if addr and addr.startswith("0x") and len(addr) == 42:
        try:
            eth_wei = await _fetch_eth_balance_wei(addr)
        except Exception as e:
            logger.warning(f"eth balance fetch failed: {e}")
    eth_amount = eth_wei / 1e18

    multichain_addrs = await _ensure_multichain_addresses(user)
    btc_addr = multichain_addrs.get("btc")
    sol_addr = multichain_addrs.get("sol")
    xlm_addr = multichain_addrs.get("xlm")
    xrp_addr = multichain_addrs.get("xrp")

    btc_amount = 0.0
    sol_amount = 0.0
    usdc_amount = 0.0
    xlm_amount = 0.0
    xrp_amount = 0.0
    try:
        if btc_addr:
            btc_amount = (await fetch_btc_balance_sats(btc_addr)) / 1e8
    except Exception as e:
        logger.warning(f"btc balance fetch failed: {e}")
    try:
        if sol_addr:
            sol_amount = (await fetch_sol_balance_lamports(sol_addr)) / 1e9
    except Exception as e:
        logger.warning(f"sol balance fetch failed: {e}")
    try:
        if addr and addr.startswith("0x"):
            usdc_amount = (await fetch_usdc_balance_micro(addr)) / 1e6
    except Exception as e:
        logger.warning(f"usdc balance fetch failed: {e}")

    # L2 USDC aggregation
    usdc_by_chain = {"sepolia": usdc_amount}
    if addr and addr.startswith("0x"):
        for l2 in ("polygon", "base", "arbitrum"):
            try:
                bal = (await fetch_usdc_balance_on_chain(l2, addr)) / 1e6
                usdc_by_chain[l2] = bal
                usdc_amount += bal
            except Exception as e:
                logger.warning(f"USDC balance fetch failed on {l2}: {e}")
                usdc_by_chain[l2] = 0.0
    try:
        if xlm_addr:
            xlm_amount = (await fetch_xlm_balance_stroops(xlm_addr)) / 1e7
    except Exception as e:
        logger.warning(f"xlm balance fetch failed: {e}")
    try:
        if xrp_addr:
            xrp_amount = (await fetch_xrp_balance_drops(xrp_addr)) / 1e6
    except Exception as e:
        logger.warning(f"xrp balance fetch failed: {e}")

    on_chain_amount = {
        "ETH": eth_amount, "BTC": btc_amount, "USDC": usdc_amount,
        "SOL": sol_amount, "XLM": xlm_amount, "XRP": xrp_amount,
    }
    network_for = {
        "ETH": "Mainnet" if USE_MAINNET else "Sepolia",
        "USDC": "Mainnet" if USE_MAINNET else "Sepolia",
        "BTC": "Mainnet" if not BTC_TESTNET else "Testnet3",
        "SOL": "Mainnet" if USE_MAINNET else "Devnet",
        "XLM": "Mainnet" if USE_MAINNET else "Testnet",
        "XRP": "Mainnet" if USE_MAINNET else "Testnet",
    }
    address_for = {"ETH": addr, "USDC": addr, "BTC": btc_addr, "SOL": sol_addr, "XLM": xlm_addr, "XRP": xrp_addr}

    total_usd = 0.0
    out = []
    for b in items:
        sym = b["symbol"]
        p = price_map.get(sym, 0)
        amt = b["amount"]
        on_chain = False
        if sym in on_chain_amount:
            amt = on_chain_amount[sym]
            on_chain = True
            await db.balances.update_one(
                {"user_id": user["id"], "symbol": sym},
                {"$set": {"amount": amt, "updated_at": iso(now_utc())}},
            )
        fiat = round(amt * p, 2)
        total_usd += fiat
        ma = market_assets.get(sym, {})
        out.append({
            **b,
            "amount": amt,
            "price_usd": p,
            "fiat_value": fiat,
            "on_chain": on_chain,
            "network": network_for.get(sym) if on_chain else None,
            "wallet_address": address_for.get(sym),
            "change_24h_pct": ma.get("change_24h_pct", 0.0),
            "sparkline_7d": ma.get("sparkline_7d", []),
        })
    out.sort(key=lambda x: x["fiat_value"], reverse=True)
    return {
        "total_usd": round(total_usd, 2),
        "wallet_address": addr,
        "btc_address": btc_addr,
        "sol_address": sol_addr,
        "xlm_address": xlm_addr,
        "xrp_address": xrp_addr,
        "usdc_by_chain": usdc_by_chain,
        "assets": out,
        "prices_fetched_at": market.get("fetched_at"),
    }


# ---------------------------------------------------------------------------
# ETH / Sepolia
# ---------------------------------------------------------------------------
@router.get("/wallet/eth/info")
async def eth_info(user=Depends(get_current_user)):
    addr = user.get("wallet_address")
    if not addr:
        raise HTTPException(status_code=400, detail="No wallet address")
    try:
        wei = await _fetch_eth_balance_wei(addr)
        gas_price_resp = await _eth_rpc("eth_gasPrice", [])
        gas_price_wei = int(gas_price_resp.get("result", "0x0"), 16)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Sepolia RPC error: {e}")
    return {
        "address": addr,
        "balance_wei": str(wei),
        "balance_eth": wei / 1e18,
        "chain_id": SEPOLIA_CHAIN_ID,
        "network": "Sepolia",
        "gas_price_wei": str(gas_price_wei),
        "gas_price_gwei": gas_price_wei / 1e9,
        "explorer": f"https://sepolia.etherscan.io/address/{addr}",
        "faucet": "https://sepoliafaucet.com/",
    }


@router.post("/wallet/eth/send")
async def eth_send(body: SendEthIn, user=Depends(get_current_user)):
    """ETH send with optional multisig gate. If multisig is enabled AND
    the user has an active cosigner AND the amount is above the threshold,
    the send is parked as a pending approval; otherwise it broadcasts."""
    import secrets as _secrets
    from datetime import timedelta
    from deps import MULTISIG_THRESHOLD_ETH, APPROVAL_TTL_HOURS

    pk = user.get("eth_private_key")
    addr = user.get("wallet_address")
    if not pk or not addr:
        raise HTTPException(status_code=400, detail="No ETH key on file")
    to = body.to_address.strip()
    if not (to.startswith("0x") and len(to) == 42):
        raise HTTPException(status_code=400, detail="Invalid recipient address")

    multisig_on = bool(user.get("multisig_enabled"))
    cosigner = await db.cosigners.find_one(
        {"user_id": user["id"], "status": "active"}, {"_id": 0}
    )
    needs_approval = (
        multisig_on
        and cosigner is not None
        and body.amount_eth >= MULTISIG_THRESHOLD_ETH
    )
    if needs_approval:
        # Lazy import — avoids circular (multisig router imports from wallet)
        from routers.multisig import _send_approval_email  # noqa: PLC0415

        approval_id = str(uuid.uuid4())
        token = _secrets.token_urlsafe(32)
        expires = now_utc() + timedelta(hours=APPROVAL_TTL_HOURS)
        pending = {
            "id": approval_id,
            "user_id": user["id"],
            "user_name": user.get("name"),
            "user_email": user.get("email"),
            "from_address": addr,
            "to_address": to,
            "amount_eth": body.amount_eth,
            "cosigner_id": cosigner["id"],
            "cosigner_email": cosigner["email"],
            "approver_token": token,
            "status": "pending",
            "created_at": iso(now_utc()),
            "expires_at": iso(expires),
        }
        await db.eth_approvals.insert_one(pending)
        await _send_approval_email(pending)
        pending.pop("_id", None)
        return {
            "approval_required": True,
            "approval_id": approval_id,
            "cosigner_email": cosigner["email"],
            "amount_eth": body.amount_eth,
            "to_address": to,
            "expires_at": pending["expires_at"],
            "message": f"Awaiting approval from {cosigner['email']}",
        }

    return await _broadcast_eth_send(user, addr, pk, to, body.amount_eth)


async def _broadcast_eth_send(user: dict, addr: str, pk: str, to: str, amount_eth: float) -> dict:
    """Broadcast an ETH transfer. Shared with the multisig + chat routers so
    cosigner-approved sends go through the identical signing/broadcast path."""
    value_wei = int(round(amount_eth * 1e18))
    try:
        nonce_resp = await _eth_rpc("eth_getTransactionCount", [addr, "pending"])
        nonce = int(nonce_resp["result"], 16)
        gas_resp = await _eth_rpc("eth_gasPrice", [])
        gas_price = int(gas_resp["result"], 16)
        bal_wei = await _fetch_eth_balance_wei(addr)
        gas_limit = 21000
        total_cost = value_wei + gas_price * gas_limit
        if total_cost > bal_wei:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient ETH (need {total_cost/1e18:.6f}, have {bal_wei/1e18:.6f})",
            )

        tx = {
            "nonce": nonce,
            "to": to,
            "value": value_wei,
            "gas": gas_limit,
            "gasPrice": gas_price,
            "chainId": SEPOLIA_CHAIN_ID,
        }
        signed = Account.sign_transaction(tx, pk)
        send_resp = await _eth_rpc("eth_sendRawTransaction", [signed.raw_transaction.hex()])
        if "error" in send_resp:
            raise HTTPException(status_code=502, detail=f"RPC error: {send_resp['error']}")
        tx_hash = send_resp["result"]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Sepolia send failed: {e}")

    is_pro = is_user_pro(user)
    service_fee_usd = 0.05 if is_pro else 0.10

    price = next((a["price_usd"] for a in DEFAULT_ASSETS if a["symbol"] == "ETH"), 0)
    tx_record = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "type": "send",
        "category": "crypto",
        "asset": "ETH",
        "amount": amount_eth,
        "fiat_value": round(amount_eth * price, 2),
        "counterparty": to,
        "tx_hash": tx_hash,
        "network": "Sepolia",
        "service_fee_usd": service_fee_usd,
        "pro_discount_applied": is_pro,
        "explorer_url": f"https://sepolia.etherscan.io/tx/{tx_hash}",
        "status": "pending",
        "created_at": iso(now_utc()),
    }
    await db.transactions.insert_one(tx_record)
    tx_record.pop("_id", None)
    return tx_record


@router.get("/wallet/eth/export")
async def eth_export_key(user=Depends(get_current_user)):
    """Reveals the private key so the user can take true self-custody.
    For Sepolia testnet only; never expose live keys this way in production."""
    pk = user.get("eth_private_key")
    if not pk:
        raise HTTPException(status_code=404, detail="No private key on file")
    return {
        "address": user.get("wallet_address"),
        "private_key": pk,
        "network": "Sepolia (chain id 11155111)",
        "warning": "Never share this key. Anyone with it controls your wallet.",
    }


@router.get("/wallet/eth/mnemonic")
async def eth_mnemonic(user=Depends(get_current_user)):
    """Reveals the 12-word BIP-39 recovery phrase. For Sepolia testnet only."""
    mnemonic_phrase = user.get("eth_mnemonic")
    if not mnemonic_phrase:
        raise HTTPException(status_code=404, detail="No recovery phrase on file. Re-register to get one.")

    origin = user.get("mnemonic_origin")
    if not origin:
        try:
            Account.enable_unaudited_hdwallet_features()
            derived_addr = Account.from_mnemonic(mnemonic_phrase).address
        except Exception:
            derived_addr = None
        stored_addr = user.get("wallet_address")
        if derived_addr and stored_addr and derived_addr.lower() == stored_addr.lower():
            origin = "eth_native"
        else:
            origin = "multichain_only"
        await db.users.update_one({"id": user["id"]}, {"$set": {"mnemonic_origin": origin}})
        user["mnemonic_origin"] = origin

    if origin == "multichain_only":
        raise HTTPException(
            status_code=409,
            detail=(
                "This account was created before BIP-39 onboarding, so we can't show a "
                "recovery phrase for your existing ETH key. Use Export Private Key instead."
            ),
        )
    return {
        "address": user.get("wallet_address"),
        "mnemonic": mnemonic_phrase,
        "word_count": len(mnemonic_phrase.split()),
        "network": "Sepolia (chain id 11155111)",
        "warning": "Anyone with these 12 words controls your wallet.",
    }


# ---------------------------------------------------------------------------
# BTC
# ---------------------------------------------------------------------------
@router.get("/wallet/btc/info")
async def btc_info(user=Depends(get_current_user)):
    addrs = await _ensure_multichain_addresses(user)
    a = addrs["btc"]
    if not a:
        raise HTTPException(status_code=400, detail="No BTC address (mnemonic missing)")
    try:
        sats = await fetch_btc_balance_sats(a)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"BTC RPC error: {e}")
    return {
        "address": a,
        "balance_sats": sats,
        "balance_btc": sats / 1e8,
        "network": "Mainnet" if not BTC_TESTNET else "Testnet",
        "explorer": explorer_url_btc(a),
        "faucet": "https://coinfaucet.eu/en/btc-testnet/" if BTC_TESTNET else None,
        "send_supported": True,
    }


@router.post("/wallet/btc/send")
async def btc_send_route(body: SendCoinIn, user=Depends(get_current_user)):
    """Broadcast a BTC transfer (testnet3 by default). `bit` selects UTXOs and
    handles change automatically. The mnemonic is loaded from the user's doc;
    addresses are auto-derived on first call."""
    await _ensure_multichain_addresses(user)
    mnemonic = user.get("eth_mnemonic") or user.get("mnemonic")
    if not mnemonic:
        raise HTTPException(status_code=400, detail="No mnemonic on file")
    to = body.to_address.strip()
    if not to or len(to) < 26:
        raise HTTPException(status_code=400, detail="Invalid recipient address")

    btc_addr = user.get("btc_address")
    if btc_addr:
        try:
            sats = await fetch_btc_balance_sats(btc_addr)
        except Exception:
            sats = None
        if sats is not None:
            have = sats / 1e8
            if have < body.amount + 0.00001:
                raise HTTPException(
                    status_code=400,
                    detail=f"Insufficient BTC (need {body.amount}+fee, have {have})",
                )

    try:
        result = await btc_send(mnemonic, to, body.amount)
    except Exception as e:
        msg = str(e)
        if "insufficient" in msg.lower():
            raise HTTPException(status_code=400, detail="Insufficient BTC (incl. miner fee)") from e
        raise HTTPException(status_code=400, detail=f"BTC broadcast failed: {msg[:200]}") from e

    fiat_value = await _btc_to_usd(body.amount)
    record = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "type": "send",
        "category": "Crypto · BTC",
        "asset": "BTC",
        "amount": body.amount,
        "fiat_value": fiat_value,
        "counterparty": to,
        "network": "Mainnet" if not BTC_TESTNET else "Testnet",
        "tx_hash": result["tx_hash"],
        "explorer_url": result["explorer_url"],
        "status": "pending",
        "service_fee_usd": 0.0,
        "created_at": iso(now_utc()),
    }
    await db.transactions.insert_one(record)
    record.pop("_id", None)
    return record


# ---------------------------------------------------------------------------
# SOL
# ---------------------------------------------------------------------------
@router.get("/wallet/sol/info")
async def sol_info(user=Depends(get_current_user)):
    addrs = await _ensure_multichain_addresses(user)
    a = addrs["sol"]
    if not a:
        raise HTTPException(status_code=400, detail="No SOL address (mnemonic missing)")
    try:
        lamports = await fetch_sol_balance_lamports(a)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"SOL RPC error: {e}")
    return {
        "address": a,
        "balance_lamports": lamports,
        "balance_sol": lamports / 1e9,
        "network": "Mainnet" if USE_MAINNET else "Devnet",
        "explorer": explorer_url_sol(a),
        "faucet": "https://faucet.solana.com/" if not USE_MAINNET else None,
        "send_supported": True,
    }


@router.post("/wallet/sol/send")
async def sol_send_route(body: SendCoinIn, user=Depends(get_current_user)):
    """Broadcast a SOL transfer (devnet by default). Signs via solders ed25519."""
    await _ensure_multichain_addresses(user)
    mnemonic = user.get("eth_mnemonic") or user.get("mnemonic")
    if not mnemonic:
        raise HTTPException(status_code=400, detail="No mnemonic on file")
    to = body.to_address.strip()
    if not to or len(to) < 32:
        raise HTTPException(status_code=400, detail="Invalid Solana address")

    addr = user.get("sol_address")
    if addr:
        try:
            bal = await fetch_sol_balance_lamports(addr)
        except Exception:
            bal = None
        if bal is not None:
            need = int(round(body.amount * 1_000_000_000))
            if bal < need + 5000:
                raise HTTPException(
                    status_code=400,
                    detail=f"Insufficient SOL (need {body.amount}+fee, have {bal/1e9})",
                )

    try:
        result = await sol_send(mnemonic, to, body.amount)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"SOL broadcast failed: {str(e)[:200]}") from e

    fiat_value = await _sol_to_usd(body.amount)
    record = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "type": "send",
        "category": "Crypto · SOL",
        "asset": "SOL",
        "amount": body.amount,
        "fiat_value": fiat_value,
        "counterparty": to,
        "network": "Mainnet" if USE_MAINNET else "Devnet",
        "tx_hash": result["tx_hash"],
        "explorer_url": result["explorer_url"],
        "status": "pending",
        "service_fee_usd": 0.0,
        "created_at": iso(now_utc()),
    }
    await db.transactions.insert_one(record)
    record.pop("_id", None)
    return record


# ---------------------------------------------------------------------------
# USDC on Sepolia (ERC-20 transfer)
# ---------------------------------------------------------------------------
@router.get("/wallet/usdc/info")
async def usdc_info(user=Depends(get_current_user)):
    addr = user.get("wallet_address")
    if not addr:
        raise HTTPException(status_code=400, detail="No wallet address")
    try:
        micro = await fetch_usdc_balance_micro(addr)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"USDC balance error: {e}")
    return {
        "address": addr,
        "balance_micro": micro,
        "balance_usdc": micro / 1e6,
        "network": "Mainnet" if USE_MAINNET else "Sepolia",
        "contract": USDC_CONTRACT,
        "explorer": f"https://sepolia.etherscan.io/address/{addr}",
        "send_supported": True,
    }


@router.post("/wallet/usdc/send")
async def usdc_send(body: SendUsdcIn, user=Depends(get_current_user)):
    pk = user.get("eth_private_key")
    addr = user.get("wallet_address")
    if not pk or not addr:
        raise HTTPException(status_code=400, detail="No ETH key on file")
    to = body.to_address.strip()
    if not (to.startswith("0x") and len(to) == 42):
        raise HTTPException(status_code=400, detail="Invalid recipient address")

    try:
        bal_micro = await fetch_usdc_balance_micro(addr)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"USDC balance error: {e}")
    need_micro = int(round(body.amount_usdc * 1_000_000))
    if bal_micro < need_micro:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient USDC (need {body.amount_usdc}, have {bal_micro/1e6})",
        )

    try:
        data = encode_usdc_transfer(to, body.amount_usdc)
        nonce_resp = await _eth_rpc("eth_getTransactionCount", [addr, "latest"])
        nonce = int(nonce_resp.get("result", "0x0"), 16)
        gas_price_resp = await _eth_rpc("eth_gasPrice", [])
        gas_price = int(gas_price_resp.get("result", "0x0"), 16)

        tx = {
            "to": USDC_CONTRACT,
            "value": 0,
            "gas": 100000,
            "gasPrice": gas_price,
            "nonce": nonce,
            "data": data,
            "chainId": SEPOLIA_CHAIN_ID,
        }
        signed = Account.from_key(pk).sign_transaction(tx)
        raw_hex = signed.raw_transaction.hex() if hasattr(signed, "raw_transaction") else signed.rawTransaction.hex()
        if not raw_hex.startswith("0x"):
            raw_hex = "0x" + raw_hex
        bcast = await _eth_rpc("eth_sendRawTransaction", [raw_hex])
        tx_hash = bcast.get("result")
        if not tx_hash:
            err = bcast.get("error", {})
            raise HTTPException(status_code=400, detail=err.get("message", "Broadcast failed"))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"USDC send failed: {e}")

    fiat = round(body.amount_usdc * 1.0, 2)  # USDC ≈ $1
    record = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "type": "send",
        "category": "Crypto · USDC",
        "asset": "USDC",
        "amount": body.amount_usdc,
        "fiat_value": fiat,
        "counterparty": to,
        "network": "Mainnet" if USE_MAINNET else "Sepolia",
        "tx_hash": tx_hash,
        "explorer_url": f"https://sepolia.etherscan.io/tx/{tx_hash}",
        "status": "pending",
        "service_fee_usd": 0.0,
        "created_at": iso(now_utc()),
    }
    await db.transactions.insert_one(record)
    record.pop("_id", None)
    return record


# ---------------------------------------------------------------------------
# XLM
# ---------------------------------------------------------------------------
@router.get("/wallet/xlm/info")
async def xlm_info(user=Depends(get_current_user)):
    addrs = await _ensure_multichain_addresses(user)
    a = addrs["xlm"]
    if not a:
        raise HTTPException(status_code=400, detail="No XLM address (mnemonic missing)")
    try:
        stroops = await fetch_xlm_balance_stroops(a)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"XLM Horizon error: {e}")
    return {
        "address": a,
        "balance_stroops": stroops,
        "balance_xlm": stroops / 1e7,
        "network": "Mainnet" if USE_MAINNET else "Testnet",
        "explorer": explorer_url_xlm(a),
        "faucet": "https://friendbot.stellar.org/?addr=" + a if not USE_MAINNET else None,
        "send_supported": True,
        "min_reserve_xlm": 1.0,
    }


@router.post("/wallet/xlm/send")
async def xlm_send_route(body: SendXlmIn, user=Depends(get_current_user)):
    """Broadcast a native XLM payment via Stellar Horizon. Signs via stellar-sdk (ed25519)."""
    await _ensure_multichain_addresses(user)
    mnemonic = user.get("eth_mnemonic") or user.get("mnemonic")
    if not mnemonic:
        raise HTTPException(status_code=400, detail="No mnemonic on file")
    to = body.to_address.strip()
    if not to.startswith("G") or len(to) != 56:
        raise HTTPException(status_code=400, detail="Invalid Stellar (G...) address")

    addr = user.get("xlm_address")
    if addr:
        try:
            stroops = await fetch_xlm_balance_stroops(addr)
        except Exception:
            stroops = None
        if stroops is not None:
            have_xlm = stroops / 1e7
            if have_xlm < body.amount + 1.0001:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Insufficient XLM (need {body.amount}+1 reserve, have {have_xlm:.4f}). "
                        f"Stellar requires a 1 XLM minimum reserve to keep accounts active."
                    ),
                )

    try:
        result = await xlm_send(mnemonic, to, body.amount, memo=body.memo)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"XLM submission failed: {str(e)[:200]}") from e

    fiat_value = await _xlm_to_usd(body.amount)
    record = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "type": "send",
        "category": "Crypto · XLM",
        "asset": "XLM",
        "amount": body.amount,
        "fiat_value": fiat_value,
        "counterparty": to,
        "memo": body.memo,
        "network": "Mainnet" if USE_MAINNET else "Testnet",
        "tx_hash": result["tx_hash"],
        "explorer_url": result["explorer_url"],
        "status": "pending",
        "service_fee_usd": 0.0,
        "created_at": iso(now_utc()),
    }
    await db.transactions.insert_one(record)
    record.pop("_id", None)
    return record


# ---------------------------------------------------------------------------
# XRP
# ---------------------------------------------------------------------------
@router.get("/wallet/xrp/info")
async def xrp_info(user=Depends(get_current_user)):
    addrs = await _ensure_multichain_addresses(user)
    a = addrs["xrp"]
    if not a:
        raise HTTPException(status_code=400, detail="No XRP address (mnemonic missing)")
    try:
        drops = await fetch_xrp_balance_drops(a)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"XRPL RPC error: {e}")
    return {
        "address": a,
        "balance_drops": drops,
        "balance_xrp": drops / 1e6,
        "network": "Mainnet" if USE_MAINNET else "Testnet",
        "explorer": explorer_url_xrp(a),
        "faucet": "https://faucet.altnet.rippletest.net/accounts" if not USE_MAINNET else None,
        "send_supported": True,
        "min_reserve_xrp": 10.0 if USE_MAINNET else 1.0,
    }


@router.post("/wallet/xrp/send")
async def xrp_send_route(body: SendXrpIn, user=Depends(get_current_user)):
    """Broadcast a native XRP payment via the XRPL JSON-RPC. Signs via xrpl-py (secp256k1)."""
    await _ensure_multichain_addresses(user)
    mnemonic = user.get("eth_mnemonic") or user.get("mnemonic")
    if not mnemonic:
        raise HTTPException(status_code=400, detail="No mnemonic on file")
    to = body.to_address.strip()
    if not to.startswith("r") or not (25 <= len(to) <= 40):
        raise HTTPException(status_code=400, detail="Invalid XRP (r...) address")

    addr = user.get("xrp_address")
    reserve_xrp = 10.0 if USE_MAINNET else 1.0
    if addr:
        try:
            drops = await fetch_xrp_balance_drops(addr)
        except Exception:
            drops = None
        if drops is not None:
            have_xrp = drops / 1e6
            if have_xrp < body.amount + reserve_xrp + 0.001:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Insufficient XRP (need {body.amount}+{reserve_xrp} reserve, have {have_xrp:.6f}). "
                        f"XRPL requires a {reserve_xrp} XRP minimum reserve to keep accounts active."
                    ),
                )

    try:
        result = await xrp_send(mnemonic, to, body.amount, memo=body.memo)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"XRP submission failed: {str(e)[:200]}") from e

    fiat_value = await _xrp_to_usd(body.amount)
    record = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "type": "send",
        "category": "Crypto · XRP",
        "asset": "XRP",
        "amount": body.amount,
        "fiat_value": fiat_value,
        "counterparty": to,
        "memo": body.memo,
        "network": "Mainnet" if USE_MAINNET else "Testnet",
        "tx_hash": result["tx_hash"],
        "explorer_url": result["explorer_url"],
        "status": "pending",
        "service_fee_usd": 0.0,
        "created_at": iso(now_utc()),
    }
    await db.transactions.insert_one(record)
    record.pop("_id", None)
    return record


# ---------------------------------------------------------------------------
# Market prices (public endpoint for the wallet overview)
# ---------------------------------------------------------------------------
@router.get("/market/prices")
async def market_prices(_=Depends(get_current_user)):
    rec = await _refresh_market_prices()
    return {
        "assets": rec["assets"],
        "fetched_at": rec.get("fetched_at"),
        "ttl_seconds": PRICE_CACHE_TTL_SECONDS,
    }


# ---------------------------------------------------------------------------
# Simulated send for non-chain assets (kept for compatibility with the
# existing wallet UI's generic "send" path). Real chains must use the
# per-chain /wallet/<chain>/send endpoints above.
# ---------------------------------------------------------------------------
@router.post("/wallet/send")
async def wallet_send(body: SendCryptoIn, user=Depends(get_current_user)):
    if body.asset.upper() == "ETH":
        raise HTTPException(status_code=400, detail="Use /wallet/eth/send for ETH (on-chain)")
    bal = await db.balances.find_one({"user_id": user["id"], "symbol": body.asset.upper()}, {"_id": 0})
    if not bal:
        raise HTTPException(status_code=400, detail="Asset not found")
    if bal["amount"] < body.amount:
        raise HTTPException(status_code=400, detail="Insufficient balance")
    new_amt = round(bal["amount"] - body.amount, 8)
    await db.balances.update_one(
        {"user_id": user["id"], "symbol": body.asset.upper()},
        {"$set": {"amount": new_amt, "updated_at": iso(now_utc())}},
    )
    price = next((a["price_usd"] for a in DEFAULT_ASSETS if a["symbol"] == body.asset.upper()), 0)
    tx = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "type": "send",
        "category": "crypto",
        "asset": body.asset.upper(),
        "amount": body.amount,
        "fiat_value": round(body.amount * price, 2),
        "counterparty": body.to_address,
        "memo": body.memo,
        "status": "completed",
        "tx_hash": "0x" + secrets.token_hex(32),
        "created_at": iso(now_utc()),
    }
    await db.transactions.insert_one(tx)
    tx.pop("_id", None)
    return tx
