"""Generic EVM chain registry + USDC transfer helpers.

Adds Polygon, Base, and Arbitrum on top of the existing Sepolia ETH/USDC
integration — all EVM-compatible so the *signing* stays identical (same
eth_account private key, same ERC-20 transfer calldata) — only the RPC
URL, chain_id, and USDC contract change.

Because the app already runs on `WALLET_NETWORK=testnet` we default every
L2 to its official testnet (Amoy, Base Sepolia, Arbitrum Sepolia). Flip
WALLET_NETWORK=mainnet and every L2 flips to mainnet in lockstep.

All fees on these L2s are tiny (< $0.01 typical), which is why they unlock
the USDC remittance corridor that mainnet ETH gas historically kills.
"""

from __future__ import annotations

import os
import struct
import httpx
from typing import Optional

from eth_account import Account


USE_MAINNET = os.environ.get("WALLET_NETWORK", "testnet").lower() == "mainnet"


# ---------- Chain registry --------------------------------------------------
# Each entry lists mainnet + testnet configs and Circle's official USDC
# contract on that network. Sourced from https://developers.circle.com/stablecoins/docs/usdc-on-main-networks
# (mainnet) and https://developers.circle.com/stablecoins/docs/usdc-on-test-networks (testnet).
_CHAIN_REGISTRY: dict[str, dict] = {
    # Existing Sepolia — kept here so the remit selector can enumerate it.
    "sepolia": {
        "display_name": "Ethereum (Sepolia)",
        "short": "Ethereum",
        "chain_id_mainnet": 1,
        "chain_id_testnet": 11155111,
        "rpc_mainnet": "https://eth-mainnet.public.blastapi.io",
        "rpc_testnet": "https://ethereum-sepolia-rpc.publicnode.com",
        "usdc_mainnet": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        "usdc_testnet": "0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238",
        "explorer_mainnet": "https://etherscan.io",
        "explorer_testnet": "https://sepolia.etherscan.io",
        "gas_estimate_usd": 2.50,       # historically high; used by remit
        "faucet_testnet": "https://sepoliafaucet.com/",
        # Circle publishes a USDC-specific faucet with ~10 USDC per drip
        "faucet_usdc_testnet": "https://faucet.circle.com/",
    },
    "polygon": {
        "display_name": "Polygon (PoS)",
        "short": "Polygon",
        # Polygon mainnet is chain 137; Amoy testnet is 80002
        "chain_id_mainnet": 137,
        "chain_id_testnet": 80002,
        "rpc_mainnet": "https://polygon-rpc.com",
        "rpc_testnet": "https://rpc-amoy.polygon.technology",
        "usdc_mainnet": "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359",
        "usdc_testnet": "0x41E94Eb019C0762f9Bfcf9Fb1E58725BfB0e7582",
        "explorer_mainnet": "https://polygonscan.com",
        "explorer_testnet": "https://amoy.polygonscan.com",
        "gas_estimate_usd": 0.01,
        "faucet_testnet": "https://faucet.polygon.technology/",
        "faucet_usdc_testnet": "https://faucet.circle.com/",
    },
    "base": {
        "display_name": "Base",
        "short": "Base",
        "chain_id_mainnet": 8453,
        "chain_id_testnet": 84532,      # Base Sepolia
        "rpc_mainnet": "https://mainnet.base.org",
        "rpc_testnet": "https://sepolia.base.org",
        "usdc_mainnet": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        "usdc_testnet": "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        "explorer_mainnet": "https://basescan.org",
        "explorer_testnet": "https://sepolia.basescan.org",
        "gas_estimate_usd": 0.01,
        "faucet_testnet": "https://www.alchemy.com/faucets/base-sepolia",
        "faucet_usdc_testnet": "https://faucet.circle.com/",
    },
    "arbitrum": {
        "display_name": "Arbitrum One",
        "short": "Arbitrum",
        "chain_id_mainnet": 42161,
        "chain_id_testnet": 421614,     # Arbitrum Sepolia
        "rpc_mainnet": "https://arb1.arbitrum.io/rpc",
        "rpc_testnet": "https://sepolia-rollup.arbitrum.io/rpc",
        "usdc_mainnet": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
        "usdc_testnet": "0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d",
        "explorer_mainnet": "https://arbiscan.io",
        "explorer_testnet": "https://sepolia.arbiscan.io",
        "gas_estimate_usd": 0.02,
        "faucet_testnet": "https://faucets.chain.link/arbitrum-sepolia",
        "faucet_usdc_testnet": "https://faucet.circle.com/",
    },
}


def _resolve(chain: str, key_mainnet: str, key_testnet: str):
    conf = _CHAIN_REGISTRY.get(chain.lower())
    if not conf:
        raise ValueError(f"Unsupported EVM chain: {chain}")
    return conf[key_mainnet] if USE_MAINNET else conf[key_testnet]


def evm_chain_config(chain: str) -> dict:
    """Return a fully-resolved (mainnet or testnet based on env) config dict."""
    conf = _CHAIN_REGISTRY.get(chain.lower())
    if not conf:
        raise ValueError(f"Unsupported EVM chain: {chain}")
    return {
        "chain": chain.lower(),
        "display_name": conf["display_name"],
        "short": conf["short"],
        "network": "Mainnet" if USE_MAINNET else "Testnet",
        "chain_id": _resolve(chain, "chain_id_mainnet", "chain_id_testnet"),
        "rpc_url": _resolve(chain, "rpc_mainnet", "rpc_testnet"),
        "usdc_contract": _resolve(chain, "usdc_mainnet", "usdc_testnet"),
        "explorer": _resolve(chain, "explorer_mainnet", "explorer_testnet"),
        "gas_estimate_usd": conf["gas_estimate_usd"],
        "faucet_native": None if USE_MAINNET else conf.get("faucet_testnet"),
        "faucet_usdc": None if USE_MAINNET else conf.get("faucet_usdc_testnet"),
    }


def list_evm_chains(include_sepolia: bool = True) -> list[dict]:
    """List every registered chain resolved to the current network."""
    out = []
    for chain in _CHAIN_REGISTRY.keys():
        if chain == "sepolia" and not include_sepolia:
            continue
        out.append(evm_chain_config(chain))
    return out


# ---------- Balance fetch (ERC-20 balanceOf) --------------------------------
async def _rpc_call(rpc_url: str, method: str, params: list, timeout: int = 10) -> dict:
    async with httpx.AsyncClient(timeout=timeout) as cx:
        r = await cx.post(rpc_url, json={"jsonrpc": "2.0", "method": method, "params": params, "id": 1})
        return r.json() if r.status_code == 200 else {}


async def fetch_usdc_balance_on_chain(chain: str, eth_address: str) -> int:
    """USDC balance (in micro-USDC) on the specified EVM chain."""
    if not (eth_address and eth_address.startswith("0x") and len(eth_address) == 42):
        return 0
    cfg = evm_chain_config(chain)
    data = "0x70a08231" + ("000000000000000000000000" + eth_address[2:].lower())
    resp = await _rpc_call(
        cfg["rpc_url"],
        "eth_call",
        [{"to": cfg["usdc_contract"], "data": data}, "latest"],
    )
    result = (resp or {}).get("result")
    if not result or result == "0x":
        return 0
    try:
        return int(result, 16)
    except ValueError:
        return 0


async def fetch_native_balance_on_chain(chain: str, eth_address: str) -> int:
    """Native token balance (in wei) — MATIC on Polygon, ETH on Base/Arb/Sepolia."""
    if not (eth_address and eth_address.startswith("0x") and len(eth_address) == 42):
        return 0
    cfg = evm_chain_config(chain)
    resp = await _rpc_call(cfg["rpc_url"], "eth_getBalance", [eth_address, "latest"])
    result = (resp or {}).get("result")
    if not result:
        return 0
    try:
        return int(result, 16)
    except ValueError:
        return 0


# ---------- USDC transfer send ---------------------------------------------
def _encode_erc20_transfer(to_address: str, amount_usdc: float) -> str:
    """ERC-20 transfer(address,uint256) calldata. USDC uses 6 decimals on every chain."""
    amount_units = int(round(amount_usdc * 1_000_000))
    selector = "a9059cbb"
    addr_padded = ("000000000000000000000000" + to_address[2:].lower())
    amount_padded = struct.pack(">Q", amount_units).hex().rjust(64, "0")
    return "0x" + selector + addr_padded + amount_padded


async def usdc_send_on_chain(
    chain: str,
    private_key: str,
    from_address: str,
    to_address: str,
    amount_usdc: float,
) -> dict:
    """Broadcast an ERC-20 USDC transfer on the given EVM chain.

    Uses legacy `gasPrice` (rather than EIP-1559 max fee) because it's the
    most portable format across all four networks and their public RPCs.
    Returns {tx_hash, explorer_url, chain, chain_id}.
    """
    cfg = evm_chain_config(chain)
    if not (to_address.startswith("0x") and len(to_address) == 42):
        raise ValueError("Invalid recipient (must be 0x-prefixed 42-char address)")
    if amount_usdc <= 0:
        raise ValueError("Amount must be positive")

    data = _encode_erc20_transfer(to_address, amount_usdc)

    nonce_resp = await _rpc_call(cfg["rpc_url"], "eth_getTransactionCount", [from_address, "latest"])
    nonce = int((nonce_resp or {}).get("result", "0x0"), 16)

    gas_price_resp = await _rpc_call(cfg["rpc_url"], "eth_gasPrice", [])
    gas_price = int((gas_price_resp or {}).get("result", "0x0"), 16) or 1_500_000_000  # 1.5 gwei fallback

    tx = {
        "to": cfg["usdc_contract"],
        "value": 0,
        "gas": 120000,          # ERC-20 transfers on L2s use ~50-80k; 120k headroom
        "gasPrice": gas_price,
        "nonce": nonce,
        "data": data,
        "chainId": cfg["chain_id"],
    }

    signed = Account.from_key(private_key).sign_transaction(tx)
    raw_hex = signed.raw_transaction.hex() if hasattr(signed, "raw_transaction") else signed.rawTransaction.hex()
    if not raw_hex.startswith("0x"):
        raw_hex = "0x" + raw_hex

    bcast = await _rpc_call(cfg["rpc_url"], "eth_sendRawTransaction", [raw_hex])
    if not bcast or bcast.get("error"):
        err = (bcast or {}).get("error", {}) or {}
        raise RuntimeError(err.get("message") or f"broadcast failed on {chain}")

    tx_hash = bcast.get("result")
    if not tx_hash:
        raise RuntimeError(f"no tx hash returned by {chain} RPC")

    return {
        "tx_hash": tx_hash,
        "explorer_url": f"{cfg['explorer']}/tx/{tx_hash}",
        "chain": chain,
        "chain_id": cfg["chain_id"],
        "network": cfg["network"],
    }


def explorer_url_evm(chain: str, address_or_tx: str, is_tx: bool = False) -> str:
    cfg = evm_chain_config(chain)
    kind = "tx" if is_tx else "address"
    return f"{cfg['explorer']}/{kind}/{address_or_tx}"


__all__ = [
    "USE_MAINNET",
    "evm_chain_config",
    "list_evm_chains",
    "fetch_usdc_balance_on_chain",
    "fetch_native_balance_on_chain",
    "usdc_send_on_chain",
    "explorer_url_evm",
]
