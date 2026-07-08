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

# Stellar Horizon RPC (public server) + explorer.
XLM_HORIZON_URL = os.environ.get(
    "XLM_HORIZON_URL",
    "https://horizon.stellar.org" if USE_MAINNET else "https://horizon-testnet.stellar.org",
)
XLM_NETWORK_PASSPHRASE = (
    "Public Global Stellar Network ; September 2015"
    if USE_MAINNET
    else "Test SDF Network ; September 2015"
)
XLM_EXPLORER_BASE = "https://stellar.expert/explorer/public" if USE_MAINNET else "https://stellar.expert/explorer/testnet"


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

    xlm = (
        Bip44.FromSeed(seed, Bip44Coins.STELLAR)
        .Purpose().Coin().Account(0).Change(Bip44Changes.CHAIN_EXT).AddressIndex(0)
    )

    return {
        "btc": btc.PublicKey().ToAddress(),
        "sol": sol.PublicKey().ToAddress(),
        "xlm": xlm.PublicKey().ToAddress(),
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


# ---------- BTC send (testnet3 / mainnet via the `bit` library) -------------
def _btc_wif_from_mnemonic(mnemonic: str) -> str:
    seed = Bip39SeedGenerator(mnemonic).Generate()
    coin = Bip44Coins.BITCOIN_TESTNET if BTC_TESTNET else Bip44Coins.BITCOIN
    node = (
        Bip44.FromSeed(seed, coin)
        .Purpose().Coin().Account(0).Change(Bip44Changes.CHAIN_EXT).AddressIndex(0)
    )
    return node.PrivateKey().ToWif()


async def btc_send(mnemonic: str, to_address: str, amount_btc: float) -> dict:
    """Broadcast a BTC transfer on testnet3 (or mainnet if WALLET_NETWORK=mainnet).
    `bit` handles UTXO selection, change, and broadcast — it just needs a WIF.
    Returns {tx_hash, explorer_url}."""
    import asyncio
    wif = _btc_wif_from_mnemonic(mnemonic)

    def _send_sync():
        from bit import PrivateKey, PrivateKeyTestnet
        key = (PrivateKey if not BTC_TESTNET else PrivateKeyTestnet)(wif)
        # Outputs list of (address, amount, 'btc') tuples
        return key.send([(to_address, amount_btc, "btc")])

    # bit's blockstream calls are sync — run in a thread to avoid blocking the loop
    tx_hash = await asyncio.to_thread(_send_sync)
    return {"tx_hash": tx_hash, "explorer_url": explorer_url_btc(tx_hash, is_tx=True)}


# ---------- SOL send (devnet / mainnet) -------------------------------------
def _sol_keypair_from_mnemonic(mnemonic: str):
    from solders.keypair import Keypair
    seed = Bip39SeedGenerator(mnemonic).Generate()
    node = (
        Bip44.FromSeed(seed, Bip44Coins.SOLANA)
        .Purpose().Coin().Account(0).Change(Bip44Changes.CHAIN_EXT).AddressIndex(0)
    )
    priv = node.PrivateKey().Raw().ToBytes()
    return Keypair.from_seed(priv)


async def sol_send(mnemonic: str, to_address: str, amount_sol: float) -> dict:
    """Broadcast a SOL transfer on devnet (or mainnet if WALLET_NETWORK=mainnet)."""
    from solders.pubkey import Pubkey
    from solders.system_program import TransferParams, transfer as sol_transfer
    from solders.message import Message
    from solders.transaction import Transaction
    from solders.hash import Hash

    kp = _sol_keypair_from_mnemonic(mnemonic)
    to_pk = Pubkey.from_string(to_address)
    lamports = int(round(amount_sol * 1_000_000_000))
    if lamports <= 0:
        raise ValueError("Amount too small (1 lamport = 1e-9 SOL)")

    async with httpx.AsyncClient(timeout=15) as c:
        bh_resp = await c.post(
            SOL_RPC_URL,
            json={"jsonrpc": "2.0", "id": 1, "method": "getLatestBlockhash", "params": []},
        )
        bh_json = bh_resp.json() or {}
        blockhash_str = ((bh_json.get("result") or {}).get("value") or {}).get("blockhash")
        if not blockhash_str:
            raise RuntimeError(f"getLatestBlockhash failed: {bh_json.get('error') or bh_json}")
        blockhash = Hash.from_string(blockhash_str)

        ix = sol_transfer(TransferParams(from_pubkey=kp.pubkey(), to_pubkey=to_pk, lamports=lamports))
        msg = Message.new_with_blockhash([ix], kp.pubkey(), blockhash)
        tx = Transaction([kp], msg, blockhash)
        raw = base64.b64encode(bytes(tx)).decode()

        send_resp = await c.post(
            SOL_RPC_URL,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "sendTransaction",
                "params": [raw, {"encoding": "base64", "preflightCommitment": "confirmed"}],
            },
        )
        send_json = send_resp.json() or {}
        if send_json.get("error"):
            raise RuntimeError(send_json["error"].get("message") or str(send_json["error"]))
        sig = send_json.get("result")
        if not sig:
            raise RuntimeError(f"sendTransaction returned no signature: {send_json}")
        return {"tx_hash": sig, "explorer_url": explorer_url_sol(sig, is_tx=True)}


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


def explorer_url_xlm(address_or_tx: str, is_tx: bool = False) -> str:
    kind = "tx" if is_tx else "account"
    return f"{XLM_EXPLORER_BASE}/{kind}/{address_or_tx}"


# ---------- Stellar (XLM) ---------------------------------------------------
def _xlm_keypair_from_mnemonic(mnemonic: str):
    """Derive a Stellar Keypair from the user's BIP-39 mnemonic (path m/44'/148'/0')."""
    from stellar_sdk import Keypair
    seed = Bip39SeedGenerator(mnemonic).Generate()
    xlm = (
        Bip44.FromSeed(seed, Bip44Coins.STELLAR)
        .Purpose().Coin().Account(0).Change(Bip44Changes.CHAIN_EXT).AddressIndex(0)
    )
    # bip_utils gives us the raw ed25519 private key; feed it to stellar-sdk.
    raw_priv = xlm.PrivateKey().Raw().ToBytes()
    return Keypair.from_raw_ed25519_seed(raw_priv)


async def fetch_xlm_balance_stroops(address: str) -> int:
    """Return XLM balance in stroops (1 XLM = 10_000_000 stroops).
    Returns 0 if account isn't funded yet (Stellar accounts need a ~1 XLM
    minimum reserve to exist on-chain)."""
    if not (address and address.startswith("G") and len(address) == 56):
        return 0
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(f"{XLM_HORIZON_URL}/accounts/{address}")
        if r.status_code == 404:
            return 0  # Unfunded account
        if r.status_code != 200:
            return 0
        data = r.json() or {}
        for bal in data.get("balances", []) or []:
            if bal.get("asset_type") == "native":
                try:
                    # Horizon returns e.g. "9.9999900" — convert XLM → stroops.
                    return int(round(float(bal.get("balance", "0")) * 10_000_000))
                except (TypeError, ValueError):
                    return 0
        return 0


async def xlm_send(mnemonic: str, to_address: str, amount_xlm: float, memo: Optional[str] = None) -> dict:
    """Build, sign & submit a native XLM payment via Stellar Horizon."""
    from stellar_sdk import (
        Server, TransactionBuilder, Asset, Network, Keypair, Memo,
    )

    if not to_address or not to_address.startswith("G") or len(to_address) != 56:
        raise ValueError("Invalid Stellar (G...) address")
    if amount_xlm <= 0:
        raise ValueError("Amount must be positive")

    kp = _xlm_keypair_from_mnemonic(mnemonic)
    server = Server(horizon_url=XLM_HORIZON_URL)
    try:
        source_account = server.load_account(account_id=kp.public_key)
    except Exception as e:
        # Unfunded source account — Horizon returns 404
        raise RuntimeError(
            f"XLM account not funded yet. Send at least 1 XLM to {kp.public_key} first "
            f"(Stellar requires a minimum reserve to activate the account)."
        ) from e

    builder = (
        TransactionBuilder(
            source_account=source_account,
            network_passphrase=XLM_NETWORK_PASSPHRASE,
            base_fee=100,  # 100 stroops (~0.00001 XLM) — well below any real fee cost
        )
        .add_time_bounds(0, 0)  # no time bounds
        .append_payment_op(
            destination=to_address,
            asset=Asset.native(),
            amount=f"{amount_xlm:.7f}",  # Stellar amounts have 7 decimals
        )
    )
    if memo:
        builder = builder.add_text_memo(memo[:28])  # Stellar text memo max 28 bytes
    tx = builder.build()
    tx.sign(kp)

    try:
        response = server.submit_transaction(tx)
    except Exception as e:
        raise RuntimeError(f"XLM submission failed: {str(e)[:200]}") from e

    tx_hash = response.get("hash") if isinstance(response, dict) else getattr(response, "hash", None)
    if not tx_hash:
        raise RuntimeError(f"XLM submission returned no hash: {response}")
    return {"tx_hash": tx_hash, "explorer_url": explorer_url_xlm(tx_hash, is_tx=True)}


__all__ = [
    "USE_MAINNET", "BTC_TESTNET", "USDC_CONTRACT",
    "ETH_RPC_URL", "SOL_RPC_URL", "BTC_API",
    "XLM_HORIZON_URL", "XLM_NETWORK_PASSPHRASE",
    "derive_addresses",
    "fetch_btc_balance_sats", "fetch_sol_balance_lamports",
    "fetch_usdc_balance_micro", "fetch_xlm_balance_stroops",
    "encode_usdc_transfer",
    "explorer_url_btc", "explorer_url_sol", "explorer_url_xlm",
    "btc_send", "sol_send", "xlm_send",
]
