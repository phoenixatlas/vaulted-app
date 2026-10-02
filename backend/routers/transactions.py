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
