"""Multi-chain wallet derivation + balance fetchers.

Single mnemonic → addresses for ETH (Sepolia), USDC (ERC-20 on Sepolia),
BTC (testnet3), SOL (devnet). Mainnet flip is controlled by env vars so
production rollout is a config change, not a code change.

This module is intentionally HTTP-client-only — no chain nodes, no
peer-to-peer networking, just signed-tx broadcast / read-only RPC.
"""

from __future__ import annotations

import os
import base64
import struct
import httpx
from typing import Optional

from bip_utils import (
    Bip39SeedGenerator,
    Bip44,
    Bip44Coins,
    Bip44Changes,
)


# ---------- Network selection -----------------------------------------------
USE_MAINNET = os.environ.get("WALLET_NETWORK", "testnet").lower() == "mainnet"

# Sepolia by default; flip via env to mainnet ETH RPC if desired.
ETH_RPC_URL = os.environ.get(
    "ETH_RPC_URL",
    "https://eth-mainnet.public.blastapi.io" if USE_MAINNET else "https://ethereum-sepolia-rpc.publicnode.com",
)
# USDC on Sepolia: official Circle deployment. Mainnet: 0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48
USDC_CONTRACT = os.environ.get(
    "USDC_CONTRACT",
    "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48" if USE_MAINNET else "0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238",
)

BTC_TESTNET = not USE_MAINNET
BTC_API = "https://blockstream.info/api" if USE_MAINNET else "https://blockstream.info/testnet/api"

SOL_RPC_URL = os.environ.get(
    "SOL_RPC_URL",
    "https://api.mainnet-beta.solana.com" if USE_MAINNET else "https://api.devnet.solana.com",
)
SOL_EXPLORER_BASE = "https://explorer.solana.com" if USE_MAINNET else "https://explorer.solana.com/?cluster=devnet"
BTC_EXPLORER_BASE = "https://mempool.space" if USE_MAINNET else "https://mempool.space/testnet"


# ---------- Address derivation ----------------------------------------------
def derive_addresses(mnemonic: str) -> dict:
    """Return {'btc': addr, 'sol': addr} derived from the user's BIP-39 mnemonic.
    ETH is derived elsewhere (via eth_account.Account.from_mnemonic)."""
    seed = Bip39SeedGenerator(mnemonic).Generate()

    btc_coin = Bip44Coins.BITCOIN_TESTNET if BTC_TESTNET else Bip44Coins.BITCOIN
    btc = (
        Bip44.FromSeed(seed, btc_coin)
        .Purpose().Coin().Account(0).Change(Bip44Changes.CHAIN_EXT).AddressIndex(0)
    )

    sol = (
        Bip44.FromSeed(seed, Bip44Coins.SOLANA)
        .Purpose().Coin().Account(0).Change(Bip44Changes.CHAIN_EXT).AddressIndex(0)
    )

    return {
        "btc": btc.PublicKey().ToAddress(),
        "sol": sol.PublicKey().ToAddress(),
    }


# ---------- Balance fetchers ------------------------------------------------
async def fetch_btc_balance_sats(address: str) -> int:
    """Confirmed + mempool balance in satoshis, via Blockstream's public API."""
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(f"{BTC_API}/address/{address}")
        if r.status_code != 200:
            return 0
        data = r.json()
        # chain_stats has confirmed funded/spent; mempool_stats has unconfirmed
        chain = data.get("chain_stats", {})
        mp = data.get("mempool_stats", {})
        funded = int(chain.get("funded_txo_sum", 0)) + int(mp.get("funded_txo_sum", 0))
        spent = int(chain.get("spent_txo_sum", 0)) + int(mp.get("spent_txo_sum", 0))
        return max(0, funded - spent)


async def fetch_sol_balance_lamports(address: str) -> int:
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(
            SOL_RPC_URL,
            json={"jsonrpc": "2.0", "id": 1, "method": "getBalance", "params": [address]},
        )
        if r.status_code != 200:
            return 0
        return int(((r.json() or {}).get("result") or {}).get("value", 0))


async def fetch_usdc_balance_micro(eth_address: str) -> int:
    """USDC has 6 decimals — returns balance in micro-USDC (1 USDC = 1_000_000)."""
    if not (eth_address and eth_address.startswith("0x") and len(eth_address) == 42):
        return 0
    # ERC-20 balanceOf(address) selector + padded address
    data = "0x70a08231" + ("000000000000000000000000" + eth_address[2:].lower())
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(
            ETH_RPC_URL,
            json={
                "jsonrpc": "2.0", "id": 1, "method": "eth_call",
                "params": [{"to": USDC_CONTRACT, "data": data}, "latest"],
            },
        )
        if r.status_code != 200:
            return 0
        result = (r.json() or {}).get("result")
        if not result or result == "0x":
            return 0
        try:
            return int(result, 16)
        except ValueError:
            return 0


# ---------- USDC ERC-20 transfer encoder ------------------------------------
def encode_usdc_transfer(to_address: str, amount_usdc: float) -> str:
    """Return the calldata for ERC-20 transfer(to, amount). USDC has 6 decimals."""
    amount_units = int(round(amount_usdc * 1_000_000))
    # function selector for transfer(address,uint256) = 0xa9059cbb
    selector = "a9059cbb"
    addr_padded = ("000000000000000000000000" + to_address[2:].lower())
    amount_padded = struct.pack(">Q", amount_units).hex().rjust(64, "0")
    return "0x" + selector + addr_padded + amount_padded


def explorer_url_btc(address_or_tx: str, is_tx: bool = False) -> str:
    kind = "tx" if is_tx else "address"
    return f"{BTC_EXPLORER_BASE}/{kind}/{address_or_tx}"


def explorer_url_sol(address_or_tx: str, is_tx: bool = False) -> str:
    if USE_MAINNET:
        kind = "tx" if is_tx else "address"
        return f"{SOL_EXPLORER_BASE}/{kind}/{address_or_tx}"
    # devnet uses query string
    kind = "tx" if is_tx else "address"
    return f"https://explorer.solana.com/{kind}/{address_or_tx}?cluster=devnet"


__all__ = [
    "USE_MAINNET", "BTC_TESTNET", "USDC_CONTRACT",
    "derive_addresses",
    "fetch_btc_balance_sats", "fetch_sol_balance_lamports", "fetch_usdc_balance_micro",
    "encode_usdc_transfer",
    "explorer_url_btc", "explorer_url_sol",
]
