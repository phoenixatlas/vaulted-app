"""Transactions router — history, CSV export, and fiat top-up/withdraw.

Extracted from server.py during the P2 refactor. Houses:
  * /transactions — paginated activity feed (newest first)
  * /transactions/export — tax-ready CSV with date / asset / type filters,
    compatible with Koinly, CoinTracker, Excel, Google Sheets
  * /fiat/deposit — simulated USD → USDC 1:1 top-up
  * /fiat/withdraw — simulated USDC → USD 1:1 off-ramp

The fiat endpoints are simulated for the MVP wallet experience. Real
cross-border fiat flows go through /remit/* (crypto-funded or
Stripe-funded) with proper KYC + sanctions gates.
"""
from __future__ import annotations

import csv
import secrets
import uuid
from io import StringIO
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from deps import db, now_utc, iso, get_current_user
from models import FiatTxIn

router = APIRouter()


# ---------------------------------------------------------------------------
# Fiat deposit / withdraw — simulated 1:1 USDC backing for the MVP flow
# ---------------------------------------------------------------------------
@router.post("/fiat/deposit")
async def fiat_deposit(body: FiatTxIn, user=Depends(get_current_user)):
    await db.balances.update_one(
        {"user_id": user["id"], "symbol": "USDC"},
        {"$inc": {"amount": body.amount}, "$set": {"updated_at": iso(now_utc())}},
    )
    tx = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "type": "deposit",
        "category": "fiat",
        "asset": body.currency,
        "amount": body.amount,
        "fiat_value": body.amount,
        "counterparty": f"{body.method.upper()} Top-up",
        "method": body.method,
        "status": "completed",
        "receipt_id": "VLT-" + secrets.token_hex(4).upper(),
        "created_at": iso(now_utc()),
    }
    await db.transactions.insert_one(tx)
    tx.pop("_id", None)
    return tx


@router.post("/fiat/withdraw")
async def fiat_withdraw(body: FiatTxIn, user=Depends(get_current_user)):
    bal = await db.balances.find_one({"user_id": user["id"], "symbol": "USDC"}, {"_id": 0})
    if not bal or bal["amount"] < body.amount:
        raise HTTPException(status_code=400, detail="Insufficient USDC balance")
    await db.balances.update_one(
        {"user_id": user["id"], "symbol": "USDC"},
        {"$inc": {"amount": -body.amount}, "$set": {"updated_at": iso(now_utc())}},
    )
    tx = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "type": "withdraw",
        "category": "fiat",
        "asset": body.currency,
        "amount": body.amount,
        "fiat_value": body.amount,
        "counterparty": f"{body.method.upper()} Withdrawal",
        "method": body.method,
        "status": "completed",
        "receipt_id": "VLT-" + secrets.token_hex(4).upper(),
        "created_at": iso(now_utc()),
    }
    await db.transactions.insert_one(tx)
    tx.pop("_id", None)
    return tx


# ---------------------------------------------------------------------------
# /transactions — activity feed
# ---------------------------------------------------------------------------
@router.get("/transactions")
async def list_transactions(user=Depends(get_current_user), limit: int = 100):
    cur = db.transactions.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).limit(limit)
    return await cur.to_list(limit)


# ---------------------------------------------------------------------------
# /transactions/export — tax-ready CSV with filters
# ---------------------------------------------------------------------------
@router.get("/transactions/export")
async def export_transactions_csv(
    user=Depends(get_current_user),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    assets: Optional[str] = None,   # comma-separated symbols, e.g. "ETH,USDC"
    types: Optional[str] = None,    # comma-separated, e.g. "send,receive"
):
    """Return a tax-ready CSV of the user's transactions, filterable by
    date range / asset / type. Compatible with most accounting tools
    (Koinly, CoinTracker, Excel, Google Sheets)."""
    q: dict = {"user_id": user["id"]}
    if date_from:
        q.setdefault("created_at", {})["$gte"] = date_from
    if date_to:
        q.setdefault("created_at", {})["$lte"] = f"{date_to}T23:59:59.999Z"
    if assets:
        wanted = [a.strip().upper() for a in assets.split(",") if a.strip()]
        if wanted:
            q["asset"] = {"$in": wanted}
    if types:
        wanted_t = [t.strip().lower() for t in types.split(",") if t.strip()]
        if wanted_t:
            q["type"] = {"$in": wanted_t}

    cur = db.transactions.find(q, {"_id": 0}).sort("created_at", 1)
    rows = await cur.to_list(10000)

    buf = StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "Date (UTC)", "Type", "Category", "Asset", "Amount",
        "USD Value", "Cost Basis USD", "Service Fee USD", "Net USD",
        "Counterparty", "Network", "Tx Hash", "Status", "Explorer URL",
    ])
    for r in rows:
        fiat = float(r.get("fiat_value") or 0)
        fee = float(r.get("service_fee_usd") or 0)
        t = r.get("type")
        sign = -1 if t in ("send", "withdraw") else 1
        net = round(sign * fiat - fee, 2)
        writer.writerow([
            r.get("created_at", ""),
            t or "",
            r.get("category", ""),
            r.get("asset", ""),
            r.get("amount", ""),
            f"{fiat:.2f}",
            f"{fiat:.2f}",
            f"{fee:.2f}",
            f"{net:.2f}",
            r.get("counterparty", ""),
            r.get("network", ""),
            r.get("tx_hash", ""),
            r.get("status", ""),
            r.get("explorer_url", ""),
        ])

    name = "vaulted-transactions"
    if date_from or date_to:
        name += f"-{(date_from or 'all')}_to_{(date_to or 'now')}"
    name += ".csv"
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )



# ---------------------------------------------------------------------------
# Payout receipt download (settled offramp only)
# ---------------------------------------------------------------------------
# Rebuilds the PDF receipt on demand so users can re-download if they lose
# the one that was auto-emailed on settlement. Only returns 200 when:
#   • the tx belongs to the caller (prevents enumeration attacks)
#   • the tx is in a settled state (nothing to receipt for a pending/failed)
@router.get("/transactions/{tx_id}/receipt.pdf")
async def download_offramp_receipt(tx_id: str, user=Depends(get_current_user)):
    from fastapi.responses import Response
    from receipt import build_offramp_receipt_pdf

    tx = await db.transactions.find_one({"id": tx_id, "user_id": user["id"]}, {"_id": 0})
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")

    status = (tx.get("status") or "").lower()
    kotani_status = ((tx.get("kotani") or {}).get("status") or "").upper()
    is_settled = status == "settled" or kotani_status in {"SUCCESSFUL", "SUCCESS", "COMPLETED"}
    if not is_settled:
        raise HTTPException(status_code=400, detail="Receipt only available for settled transactions")

    pdf = build_offramp_receipt_pdf(tx, user)
    ref = ((tx.get("kotani") or {}).get("reference_id")) or tx_id
    safe_ref = "".join(c for c in str(ref) if c.isalnum() or c in "-_") or "receipt"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="vaulted-receipt-{safe_ref}.pdf"'},
    )


# ---------------------------------------------------------------------------
# /transactions/{id} — detail + tracking timeline + "send again" prefill
# ---------------------------------------------------------------------------
_PAY_LABEL = {"card": "card", "apple_pay": "Apple Pay", "google_pay": "Google Pay", "bank": "bank transfer"}
_DONE_STATUSES = ("settled", "completed")


def _short(s: Optional[str]) -> str:
    s = s or ""
    return s if len(s) <= 18 else f"{s[:8]}…{s[-6:]}"


def build_timeline(tx: dict) -> list[dict]:
    """Ordered steps with state done | current | pending | failed."""
    remit = tx.get("remit") or {}
    payout = tx.get("payout") or tx.get("kotani") or {}
    status = (tx.get("status") or "").lower()
    created = tx.get("created_at")
    delivered = status in _DONE_STATUSES
    failed = status == "failed" or bool(payout.get("failed"))
    who = tx.get("recipient_name") or "recipient"

    if not remit:
        steps = [
            {"key": "created", "label": "Started", "at": created, "done": True},
            {"key": "done", "label": "Completed", "at": created if delivered else None, "done": delivered},
        ]
    elif tx.get("funding_method") == "stripe":
        partner = payout.get("provider_label") or "payout partner"
        steps = [
            {"key": "paid", "label": f"Paid {remit.get('source_amount')} {remit.get('source_currency')}",
             "detail": f"By {_PAY_LABEL.get(tx.get('payment_method') or '', 'card')}", "at": created, "done": True},
            {"key": "converted", "label": "Converted to digital dollars",
             "detail": f"1 {remit.get('source_currency')} = {remit.get('fx_rate')} {remit.get('destination_currency')}",
             "at": created, "done": True},
            {"key": "sent", "label": f"Sent to {partner}",
             "detail": f"Ref {_short(payout.get('reference_id'))}" if payout.get("reference_id") else None,
             "at": payout.get("initiated_at"), "done": bool(payout.get("reference_id"))},
            {"key": "delivered", "label": f"Delivered to {who}",
             "detail": f"{remit.get('destination_amount')} {remit.get('destination_currency')} · {remit.get('receive_via')}",
             "at": (payout.get("updated_at") or payout.get("initiated_at")) if delivered else None, "done": delivered},
        ]
    else:
        steps = [
            {"key": "sent", "label": "Sent from your wallet",
             "detail": f"{tx.get('amount')} {tx.get('asset')} on {remit.get('chain') or tx.get('network')}",
             "at": created, "done": True},
            {"key": "confirmed", "label": "Confirmed on the blockchain",
             "detail": f"Tx {_short(tx.get('tx_hash'))}" if tx.get("tx_hash") else None,
             "at": tx.get("confirmed_at") or created if delivered else None, "done": delivered},
            {"key": "delivered", "label": f"Delivered to {who}",
             "detail": f"{remit.get('destination_amount')} {remit.get('destination_currency')} · {remit.get('receive_via')}",
             "at": tx.get("confirmed_at") or created if delivered else None, "done": delivered},
        ]

    current_set = False
    for s in steps:
        if s["done"]:
            s["state"] = "done"
        elif not current_set:
            s["state"] = "failed" if failed else "current"
            if failed:
                s["detail"] = payout.get("reason") or "The payout didn't go through. Our team has been alerted."
            current_set = True
        else:
            s["state"] = "pending"
        s.pop("done")
    return steps


def _repeat_prefill(tx: dict) -> Optional[dict]:
    from remit import CORRIDORS
    remit = tx.get("remit") or {}
    if tx.get("type") != "send" or not remit or tx.get("user_deleted") or not tx.get("counterparty"):
        return None
    code = remit.get("destination_country_code") or next(
        (c for c, v in CORRIDORS.items() if v["country"] == remit.get("destination_country")), None)
    if not code:
        return None
    bank = tx.get("recipient_bank") or {}
    return {
        "destination_code": code,
        "source_fiat": remit.get("source_currency"),
        "amount": remit.get("source_amount"),
        "funding": (tx.get("payment_method") or "card") if tx.get("funding_method") == "stripe" else "crypto",
        "recipient_address": tx.get("counterparty"),
        "recipient_name": tx.get("recipient_name") or "",
        "bank_id": bank.get("id"),
        "bank_name": bank.get("name"),
    }


_EVM_CHAIN = {"USDC_POLYGON": "polygon", "USDC_BASE": "base", "USDC_ARBITRUM": "arbitrum", "USDC": "sepolia"}


async def _chain_confirmation(chain: str, tx_hash: str) -> Optional[str]:
    """Ask the blockchain whether a crypto send landed.
    Returns 'settled', 'failed', or None (not yet known / RPC unavailable)."""
    import httpx
    from evm import _rpc_call, evm_chain_config
    from multichain import XLM_HORIZON_URL, XRP_RPC_URL
    try:
        if chain == "XLM":
            async with httpx.AsyncClient(timeout=8) as cx:
                r = await cx.get(f"{XLM_HORIZON_URL}/transactions/{tx_hash}")
            if r.status_code == 200:
                return "settled" if r.json().get("successful") else "failed"
            return None
        if chain == "XRP":
            async with httpx.AsyncClient(timeout=8) as cx:
                r = await cx.post(XRP_RPC_URL, json={"method": "tx", "params": [{"transaction": tx_hash}]})
            res = (r.json() or {}).get("result") or {}
            if not res.get("validated"):
                return None
            return "settled" if (res.get("meta") or {}).get("TransactionResult") == "tesSUCCESS" else "failed"
        if chain in _EVM_CHAIN:
            rpc = evm_chain_config(_EVM_CHAIN[chain])["rpc_url"]
            receipt = (await _rpc_call(rpc, "eth_getTransactionReceipt", [tx_hash], timeout=8)).get("result")
            if not receipt:
                return None
            return "settled" if receipt.get("status") == "0x1" else "failed"
    except Exception:  # noqa: BLE001 — RPC hiccup: just try again on the next poll
        return None
    return None


@router.get("/transactions/{tx_id}")
async def get_transaction(tx_id: str, user=Depends(get_current_user)):
    tx = await db.transactions.find_one({"id": tx_id, "user_id": user["id"]}, {"_id": 0})
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    # Crypto-funded sends are saved as "pending" at broadcast; confirm them
    # against the chain the first time someone looks at them.
    chain = (tx.get("remit") or {}).get("chain")
    if tx.get("status") == "pending" and chain and tx.get("tx_hash"):
        outcome = await _chain_confirmation(chain, tx["tx_hash"])
        if outcome:
            await db.transactions.update_one({"id": tx_id}, {"$set": {"status": outcome, "confirmed_at": iso(now_utc())}})
            tx["status"] = outcome
            tx["confirmed_at"] = iso(now_utc())
            if outcome == "settled":
                from delivery import safe_notify
                await safe_notify(tx_id)
    status = (tx.get("status") or "").lower()
    return {
        "tx": tx,
        "timeline": build_timeline(tx),
        "is_final": status in _DONE_STATUSES or status == "failed" or bool((tx.get("payout") or {}).get("failed")),
        "repeat": _repeat_prefill(tx),
    }
