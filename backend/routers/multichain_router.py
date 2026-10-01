"""Multichain router — EVM L2s (Polygon, Base, Arbitrum, Sepolia).

Extracted from server.py during the P2 refactor. Houses the two
/wallet/evm/* endpoints that power the Send screen's L2 picker and the
remit layer's chain selection. All EVM chains share the user's existing
0x address, so there is no new key derivation here — just balance lookup
and signed USDC transfer dispatch.

Named ``multichain_router.py`` (not ``multichain.py``) so it doesn't
shadow the top-level ``multichain`` module that holds the BTC/SOL/XLM/XRP
derivation + broadcast helpers.
"""
from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, HTTPException

from deps import (
    db,
    logger,
    now_utc,
    iso,
    get_current_user,
    _ensure_eth_private_key,
)
from models import SendEvmUsdcIn
from evm import (
    list_evm_chains,
    evm_chain_config,
    fetch_usdc_balance_on_chain,
    fetch_native_balance_on_chain,
    usdc_send_on_chain,
)

router = APIRouter()


@router.get("/wallet/evm/chains")
async def evm_chains(user=Depends(get_current_user)):
    """List every supported EVM chain with the current user's USDC balance and
    a live native-token balance (for gas). Powers the Send screen's L2 picker
    and the Remit chain selection UI."""
    addr = user.get("wallet_address")
    out = []
    for cfg in list_evm_chains(include_sepolia=True):
        usdc_bal = 0.0
        native_bal_wei = 0
        if addr and addr.startswith("0x"):
            try:
                usdc_bal = (await fetch_usdc_balance_on_chain(cfg["chain"], addr)) / 1e6
            except Exception as e:
                logger.warning(f"USDC balance failed on {cfg['chain']}: {e}")
            try:
                native_bal_wei = await fetch_native_balance_on_chain(cfg["chain"], addr)
            except Exception:
                native_bal_wei = 0
        out.append({
            **cfg,
            "usdc_balance": round(usdc_bal, 6),
            "native_balance": native_bal_wei / 1e18,
            "wallet_address": addr,
        })
    return {"chains": out}


@router.post("/wallet/evm/usdc/send")
async def evm_usdc_send(body: SendEvmUsdcIn, user=Depends(get_current_user)):
    """Broadcast a USDC transfer on the specified EVM chain (Polygon / Base /
    Arbitrum / Sepolia). Reuses the user's existing ETH private key — the
    same 0x address holds USDC on every EVM chain, so no new key derivation
    is needed."""
    chain = body.chain.lower().strip()
    try:
        cfg = evm_chain_config(chain)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    to = body.to_address.strip()
    if not (to.startswith("0x") and len(to) == 42):
        raise HTTPException(status_code=400, detail="Invalid recipient (0x-prefixed 42 chars required)")

    pk = await _ensure_eth_private_key(user)
    addr = user.get("wallet_address")
    if not pk or not addr:
        raise HTTPException(status_code=400, detail="No ETH key on file")

    try:
        bal_micro = await fetch_usdc_balance_on_chain(chain, addr)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"USDC balance error on {chain}: {e}") from e
    need_micro = int(round(body.amount_usdc * 1_000_000))
    if bal_micro < need_micro:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Insufficient USDC on {cfg['display_name']} "
                f"(need {body.amount_usdc}, have {bal_micro/1e6}). "
                f"Top up via {cfg.get('faucet_usdc') or 'the Circle faucet'}."
            ),
        )

    try:
        result = await usdc_send_on_chain(chain, pk, addr, to, body.amount_usdc)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"USDC send failed on {chain}: {str(e)[:200]}") from e

    fiat = round(body.amount_usdc * 1.0, 2)  # USDC ≈ $1
    record = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "type": "send",
        "category": f"Crypto · USDC ({cfg['short']})",
        "asset": "USDC",
        "amount": body.amount_usdc,
        "fiat_value": fiat,
        "counterparty": to,
        "network": cfg["network"],
        "chain": chain,
        "chain_id": cfg["chain_id"],
        "tx_hash": result["tx_hash"],
        "explorer_url": result["explorer_url"],
        "status": "pending",
        "service_fee_usd": 0.0,
        "created_at": iso(now_utc()),
    }
    await db.transactions.insert_one(record)
    record.pop("_id", None)
    return record
