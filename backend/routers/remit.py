"""Remit router — fiat-first cross-border remittance.

Extracted from server.py during the P2 refactor. Houses:
  * /remit/corridors — public corridor + source-fiat list
  * /remit/quote     — FX, chain selection, fees, KYC gate, free-tier gate
  * /remit/send      — crypto-funded send (uses on-chain balance directly)
  * /remit/fund      — Stripe Checkout session for fiat-funded sends

Phase-1 free tier: 3 sends per calendar month, bypassed by Vault Pro.
Every ``send`` emits a REMIT_SEND_SUCCESS audit event; every blocked
attempt emits a REMIT_SEND_BLOCKED event with the specific gate that
tripped (corridor, free-tier, sanctions, KYC, insufficient balance).

The ``_broadcast_eth_send`` helper on the wallet router is NOT used here —
remit sends go via XLM / XRP / USDC on an EVM L2, never native ETH.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime

import stripe
from fastapi import APIRouter, Depends, HTTPException

from deps import (
    db,
    STRIPE_API_KEY,
    logger,
    now_utc,
    iso,
    is_user_pro,
    get_current_user,
)
from models import RemitQuoteIn, RemitSendIn, RemitFundIn
from remit import (
    CORRIDORS,
    SOURCE_FIATS,
    refresh_fx_rates,
    convert_fiat,
    choose_chain,
    vaulted_fee_usd,
)
from multichain import (
    fetch_usdc_balance_micro,
    fetch_xlm_balance_stroops,
    fetch_xrp_balance_drops,
    xlm_send,
    xrp_send,
    USE_MAINNET,
)
from evm import fetch_usdc_balance_on_chain, usdc_send_on_chain
from compliance import (
    is_country_blocked,
    check_send_limits,
    COMPLIANCE_STRICT_MODE,
)
from audit import EventType, write_event as audit_write
from referrals import spend_credit_for_fee
from market import _refresh_market_prices
from routers.wallet import _ensure_multichain_addresses
from routers.stripe_router import _success_cancel_urls


router = APIRouter()


# ============================================================================
# Free-tier gate + helpers
# ============================================================================
FREE_TIER_REMIT_LIMIT = 3  # per calendar month, per user


def _first_of_month_utc() -> datetime:
    """UTC timestamp for 00:00 on the first day of the current month."""
    now = now_utc()
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def _remit_send_count_this_month(user_id: str) -> int:
    """Count of remittance sends the user has completed in the current month."""
    return await db.transactions.count_documents({
        "user_id": user_id,
        "category": {"$regex": "^Remit ·"},
        "status": {"$ne": "failed"},
        "created_at": {"$gte": iso(_first_of_month_utc())},
    })


def _stripe_payment_method_config(pm: str) -> dict:
    """Return kwargs for stripe.checkout.Session.create tailored to the
    selected payment method. Card + Apple Pay share Stripe's "card" type
    (Apple Pay / Google Pay are surfaced automatically on supported
    browsers). Bank transfer omits payment_method_types entirely so
    Stripe Checkout auto-shows every method enabled in the dashboard."""
    if pm == "bank":
        return {}
    return {"payment_method_types": ["card"]}


# ============================================================================
# /remit/corridors — public
# ============================================================================
@router.get("/remit/corridors")
async def remit_corridors():
    """Public — no auth needed for the marketing landing to preview corridors."""
    return {
        "source_fiats": SOURCE_FIATS,
        "corridors": [{"code": code, **info} for code, info in CORRIDORS.items()],
    }


# ============================================================================
# /remit/quote — fees + FX + chain selection + regulatory gates
# ============================================================================
@router.post("/remit/quote")
async def remit_quote(body: RemitQuoteIn, user=Depends(get_current_user)):
    """Return the best chain, fees, and destination-fiat receive amount for a corridor."""
    src = body.source_fiat.upper()
    if src not in SOURCE_FIATS:
        raise HTTPException(status_code=400, detail=f"Unsupported source currency: {src}")
    corridor = CORRIDORS.get(body.destination_code.upper())
    if not corridor:
        raise HTTPException(status_code=400, detail="Unsupported destination corridor")

    block_reason = is_country_blocked(body.destination_code)
    if block_reason:
        raise HTTPException(status_code=403, detail={
            "error": "corridor_blocked",
            "message": f"We cannot send money to {corridor['country']}. {block_reason}",
        })

    fx = await refresh_fx_rates(db)
    rates = fx.get("rates") or {}
    amount_usd = convert_fiat(body.amount, src, "USD", rates)
    if amount_usd <= 0:
        raise HTTPException(status_code=400, detail="Invalid quote amount")

    market = await _refresh_market_prices()
    market_assets = market.get("assets") or {}
    crypto_prices_usd = {sym: (ma.get("price_usd") or 0) for sym, ma in market_assets.items()}

    multichain_addrs = await _ensure_multichain_addresses(user)
    holdings: dict[str, float] = {}
    try:
        xlm_addr = multichain_addrs.get("xlm")
        if xlm_addr:
            holdings["XLM"] = (await fetch_xlm_balance_stroops(xlm_addr)) / 1e7
    except Exception as e:
        logger.warning(f"remit: XLM balance fetch failed: {e}")
        holdings["XLM"] = 0.0
    try:
        xrp_addr = multichain_addrs.get("xrp")
        if xrp_addr:
            holdings["XRP"] = (await fetch_xrp_balance_drops(xrp_addr)) / 1e6
    except Exception as e:
        logger.warning(f"remit: XRP balance fetch failed: {e}")
        holdings["XRP"] = 0.0
    try:
        eth_addr = user.get("wallet_address")
        if eth_addr and eth_addr.startswith("0x"):
            holdings["USDC"] = (await fetch_usdc_balance_micro(eth_addr)) / 1e6
            for l2, key in (("polygon", "USDC_POLYGON"), ("base", "USDC_BASE"), ("arbitrum", "USDC_ARBITRUM")):
                try:
                    holdings[key] = (await fetch_usdc_balance_on_chain(l2, eth_addr)) / 1e6
                except Exception as e:
                    logger.warning(f"remit: USDC {l2} balance fetch failed: {e}")
                    holdings[key] = 0.0
    except Exception as e:
        logger.warning(f"remit: USDC balance fetch failed: {e}")
        holdings["USDC"] = 0.0

    pick = choose_chain(amount_usd, holdings, crypto_prices_usd)

    is_pro = is_user_pro(user)
    svc_fee_usd = vaulted_fee_usd(amount_usd, is_pro)

    dst_fiat = corridor["currency"]
    dst_amount = convert_fiat(amount_usd, "USD", dst_fiat, rates)

    remit_used = await _remit_send_count_this_month(user["id"])
    remit_remaining = max(0, FREE_TIER_REMIT_LIMIT - remit_used) if not is_pro else None
    paywall_required = (not is_pro) and (remit_used >= FREE_TIER_REMIT_LIMIT)

    send_gbp = convert_fiat(body.amount, src, "GBP", rates)
    kyc_check = await check_send_limits(db, user, send_gbp)

    quote = {
        "quote_id": str(uuid.uuid4()),
        "source": {"currency": src, "amount": body.amount, "amount_usd": round(amount_usd, 2), "amount_gbp": round(send_gbp, 2)},
        "destination": {
            "code": body.destination_code.upper(),
            "country": corridor["country"],
            "currency": dst_fiat,
            "flag": corridor["flag"],
            "receive_via": corridor["receive_via"],
            "eta": corridor["eta"],
            "amount": round(dst_amount, 2),
        },
        "chain": pick,
        "fees": {
            "vaulted_service_usd": svc_fee_usd,
            "chain_fee_usd": (pick or {}).get("chain_fee_usd", 0.0),
            "total_fee_usd": round(svc_fee_usd + (pick or {}).get("chain_fee_usd", 0.0), 2),
        },
        "fx_rate": round(convert_fiat(1.0, src, dst_fiat, rates), 6),
        "fx_fetched_at": fx.get("fetched_at"),
        "free_tier": {
            "limit_per_month": FREE_TIER_REMIT_LIMIT,
            "used_this_month": remit_used,
            "remaining_this_month": remit_remaining,
            "paywall_required": paywall_required,
            "is_pro": is_pro,
        },
        "kyc": kyc_check,
        "sufficient_balance": pick is not None,
        "reason_if_no_chain": (
            "Not enough XLM, XRP, or USDC to cover this send + chain fee. "
            "Tap Receive on any of those assets to top up, then try again."
        ) if pick is None else None,
    }
    return quote


# ============================================================================
# /remit/send — crypto-funded send
# ============================================================================
@router.post("/remit/send")
async def remit_send(body: RemitSendIn, user=Depends(get_current_user)):
    """Fiat-first send: re-quotes, enforces free-tier gate, then broadcasts on the picked chain."""
    is_pro = is_user_pro(user)

    block_reason = is_country_blocked(body.destination_code)
    if block_reason:
        await audit_write(db, EventType.CORRIDOR_BLOCKED, user=user, data={
            "destination_code": body.destination_code, "reason": block_reason,
            "attempted_amount": body.amount, "source_fiat": body.source_fiat,
        })
        await audit_write(db, EventType.REMIT_SEND_BLOCKED, user=user, data={
            "block_type": "corridor_blocked",
            "destination_code": body.destination_code,
            "attempted_amount": body.amount, "source_fiat": body.source_fiat,
        })
        raise HTTPException(status_code=403, detail={
            "error": "corridor_blocked",
            "message": f"We cannot send to that destination. {block_reason}",
        })

    remit_used = await _remit_send_count_this_month(user["id"])
    if (not is_pro) and remit_used >= FREE_TIER_REMIT_LIMIT:
        await audit_write(db, EventType.REMIT_SEND_BLOCKED, user=user, data={
            "block_type": "free_tier_exhausted",
            "monthly_count": remit_used, "limit": FREE_TIER_REMIT_LIMIT,
            "destination_code": body.destination_code, "attempted_amount": body.amount,
        })
        raise HTTPException(
            status_code=402,
            detail={
                "error": "free_tier_exhausted",
                "message": (
                    f"You've used your {FREE_TIER_REMIT_LIMIT} free cross-border sends this month. "
                    f"Upgrade to Vault Pro for unlimited sends + 50% off service fees."
                ),
                "cta": "upgrade_to_pro",
            },
        )

    if COMPLIANCE_STRICT_MODE:
        user_kyc = user.get("kyc") or {}
        sanctions = user_kyc.get("sanctions") or {}
        if sanctions.get("degraded", True):
            await audit_write(db, EventType.REMIT_SEND_BLOCKED, user=user, data={
                "block_type": "sanctions_screening_unavailable",
                "degraded_reason": sanctions.get("degraded_reason"),
                "destination_code": body.destination_code,
                "attempted_amount": body.amount,
            })
            raise HTTPException(status_code=503, detail={
                "error": "sanctions_screening_unavailable",
                "message": (
                    "Cross-border sends are temporarily paused — our sanctions "
                    "screening provider is unavailable. Please try again in a few minutes "
                    "or contact support@phoenix-atlas.com."
                ),
                "degraded_reason": sanctions.get("degraded_reason"),
            })

    quote = await remit_quote(
        RemitQuoteIn(
            source_fiat=body.source_fiat,
            amount=body.amount,
            destination_code=body.destination_code,
        ),
        user=user,
    )
    if not quote["sufficient_balance"] or not quote.get("chain"):
        await audit_write(db, EventType.REMIT_SEND_BLOCKED, user=user, data={
            "block_type": "insufficient_balance",
            "destination_code": body.destination_code,
            "attempted_amount": body.amount, "source_fiat": body.source_fiat,
            "reason": quote.get("reason_if_no_chain"),
        })
        raise HTTPException(status_code=400, detail=quote.get("reason_if_no_chain") or "Insufficient balance")

    kyc = quote.get("kyc") or {}
    if not kyc.get("allowed"):
        await audit_write(db, EventType.REMIT_SEND_BLOCKED, user=user, data={
            "block_type": "kyc_required",
            "reason": kyc.get("reason"),
            "current_tier": kyc.get("current_tier"),
            "destination_code": body.destination_code,
            "attempted_amount": body.amount, "source_fiat": body.source_fiat,
        })
        raise HTTPException(status_code=403, detail={
            "error": "kyc_required",
            "reason": kyc.get("reason"),
            "current_tier": kyc.get("current_tier"),
            "current_tier_label": kyc.get("current_tier_label"),
            "limit": kyc.get("limit"),
            "usage": kyc.get("usage"),
            "upgrade": kyc.get("upgrade"),
            "message": (
                f"This send exceeds your {kyc.get('current_tier_label')} tier limit. "
                f"Verify your identity to unlock up to £{(kyc.get('upgrade') or {}).get('target_per_send_gbp', 0):,.0f} per send."
            ),
        })

    chain = quote["chain"]["chain"]
    crypto_amount = float(quote["chain"]["crypto_amount"])
    to = body.recipient_address.strip()

    if chain == "XLM" and not (to.startswith("G") and len(to) == 56):
        raise HTTPException(status_code=400, detail="Recipient must be a valid Stellar (G...) address")
    if chain == "XRP" and not (to.startswith("r") and 25 <= len(to) <= 40):
        raise HTTPException(status_code=400, detail="Recipient must be a valid XRP (r...) address")
    if chain.startswith("USDC") and not (to.startswith("0x") and len(to) == 42):
        raise HTTPException(status_code=400, detail="Recipient must be a valid Ethereum (0x...) address")

    mnemonic = user.get("eth_mnemonic") or user.get("mnemonic")
    if not mnemonic:
        raise HTTPException(status_code=400, detail="No mnemonic on file")

    memo_short = (body.memo or f"Vaulted-{body.destination_code.upper()}")[:28]

    _L2_MAP = {"USDC_POLYGON": "polygon", "USDC_BASE": "base", "USDC_ARBITRUM": "arbitrum", "USDC": "sepolia"}

    try:
        if chain == "XLM":
            result = await xlm_send(mnemonic, to, crypto_amount, memo=memo_short)
        elif chain == "XRP":
            result = await xrp_send(mnemonic, to, crypto_amount, memo=memo_short)
        elif chain in _L2_MAP:
            evm_chain = _L2_MAP[chain]
            pk = user.get("eth_private_key")
            eth_addr = user.get("wallet_address")
            if not pk or not eth_addr:
                raise HTTPException(status_code=400, detail="No ETH key on file")
            result = await usdc_send_on_chain(evm_chain, pk, eth_addr, to, crypto_amount)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported chain: {chain}")
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"{chain} submission failed: {str(e)[:200]}") from e

    dst = quote["destination"]
    tx_id = str(uuid.uuid4())

    # Referral credit — apply to the service fee (GBP-denominated).
    service_fee_usd = float(quote["fees"]["vaulted_service_usd"])
    service_fee_gbp = round(service_fee_usd * 0.80, 4)
    credit_applied_gbp = 0.0
    credit_balance_after_gbp = 0.0
    try:
        offset = await spend_credit_for_fee(
            db, user_id=user["id"], fee_gbp=service_fee_gbp, reference_id=tx_id,
        )
        credit_applied_gbp = offset["applied_gbp"]
        credit_balance_after_gbp = offset["balance_after_gbp"]
        if credit_applied_gbp > 0:
            await audit_write(db, EventType.CREDIT_SPENT, user=user, data={
                "amount_gbp": credit_applied_gbp,
                "reference_id": tx_id,
                "source": "remit_fee_offset",
                "balance_after_gbp": credit_balance_after_gbp,
            })
    except Exception as e:  # noqa: BLE001
        logger.warning(f"credit offset failed for remit {tx_id}: {e}")

    remaining_fee_gbp = max(0.0, round(service_fee_gbp - credit_applied_gbp, 4))
    effective_fee_usd = round(remaining_fee_gbp / 0.80, 4) if remaining_fee_gbp else 0.0

    record = {
        "id": tx_id,
        "user_id": user["id"],
        "type": "send",
        "category": f"Remit · {dst['country']}",
        "asset": "USDC" if chain.startswith("USDC") else chain,
        "amount": crypto_amount,
        "fiat_value": quote["source"]["amount_usd"],
        "counterparty": to,
        "recipient_name": body.recipient_name,
        "memo": memo_short,
        "network": "Mainnet" if USE_MAINNET else "Testnet",
        "tx_hash": result["tx_hash"],
        "explorer_url": result["explorer_url"],
        "status": "pending",
        "service_fee_usd": effective_fee_usd,
        "gross_service_fee_usd": service_fee_usd,
        "credit_applied_gbp": credit_applied_gbp,
        "credit_balance_after_gbp": credit_balance_after_gbp,
        "created_at": iso(now_utc()),
        "remit": {
            "source_currency": quote["source"]["currency"],
            "source_amount": quote["source"]["amount"],
            "destination_currency": dst["currency"],
            "destination_amount": dst["amount"],
            "destination_country": dst["country"],
            "destination_flag": dst["flag"],
            "chain": chain,
            "fx_rate": quote["fx_rate"],
            "receive_via": dst["receive_via"],
        },
    }
    await db.transactions.insert_one(record)
    record.pop("_id", None)

    user_kyc = user.get("kyc") or {}
    user_sanctions = user_kyc.get("sanctions") or {}
    await audit_write(db, EventType.REMIT_SEND_SUCCESS, user=user, data={
        "tx_id": record["id"],
        "tx_hash": record["tx_hash"],
        "chain": chain,
        "source_currency": record["remit"]["source_currency"],
        "source_amount": record["remit"]["source_amount"],
        "destination_country": record["remit"]["destination_country"],
        "destination_currency": record["remit"]["destination_currency"],
        "destination_amount": record["remit"]["destination_amount"],
        "recipient_address_hash": hashlib.sha256(to.lower().encode()).hexdigest()[:12],
        "recipient_name_hash": hashlib.sha256((body.recipient_name or "").strip().lower().encode()).hexdigest()[:12] if body.recipient_name else None,
        "service_fee_usd": record["service_fee_usd"],
        "gross_service_fee_usd": service_fee_usd,
        "credit_applied_gbp": credit_applied_gbp,
        "fiat_value_usd": record["fiat_value"],
        "tier_at_send": user_kyc.get("tier"),
        "sanctions_state_at_send": {
            "matched": user_sanctions.get("matched", False),
            "degraded": user_sanctions.get("degraded", True),
            "degraded_reason": user_sanctions.get("degraded_reason"),
        },
    })
    return record


# ============================================================================
# /remit/fund — Stripe Checkout for fiat-funded sends
# ============================================================================
@router.post("/remit/fund")
async def remit_fund(body: RemitFundIn, user=Depends(get_current_user)):
    """Create a Stripe Checkout session to fund a cross-border send with
    fiat. On completion the send is auto-executed by _apply_checkout_session.
    Front-end can call /stripe/sync to receive the tx receipt on return.

    KYC / free-tier / sanctions / corridor gates are enforced here BEFORE
    the user is charged — so we never take money for a blocked send.
    """
    if not STRIPE_API_KEY:
        raise HTTPException(status_code=503, detail="Stripe not configured")

    block_reason = is_country_blocked(body.destination_code)
    if block_reason:
        await audit_write(db, EventType.CORRIDOR_BLOCKED, user=user, data={
            "destination_code": body.destination_code, "reason": block_reason,
            "attempted_amount": body.amount, "source_fiat": body.source_fiat,
            "funding_method": "stripe",
        })
        raise HTTPException(status_code=403, detail={
            "error": "corridor_blocked",
            "message": f"We cannot send to that destination. {block_reason}",
        })

    is_pro = is_user_pro(user)
    remit_used = await _remit_send_count_this_month(user["id"])
    if (not is_pro) and remit_used >= FREE_TIER_REMIT_LIMIT:
        raise HTTPException(status_code=402, detail={
            "error": "free_tier_exhausted",
            "message": f"You've used your {FREE_TIER_REMIT_LIMIT} free cross-border sends this month.",
            "cta": "upgrade_to_pro",
        })

    quote = await remit_quote(
        RemitQuoteIn(
            source_fiat=body.source_fiat,
            amount=body.amount,
            destination_code=body.destination_code,
        ),
        user=user,
    )

    kyc = quote.get("kyc") or {}
    if not kyc.get("allowed"):
        raise HTTPException(status_code=403, detail={
            "error": "kyc_required",
            "reason": kyc.get("reason"),
            "current_tier": kyc.get("current_tier"),
            "current_tier_label": kyc.get("current_tier_label"),
            "limit": kyc.get("limit"),
            "usage": kyc.get("usage"),
            "upgrade": kyc.get("upgrade"),
            "message": (
                f"This send exceeds your {kyc.get('current_tier_label')} tier limit. "
                f"Verify your identity to unlock up to £{(kyc.get('upgrade') or {}).get('target_per_send_gbp', 0):,.0f} per send."
            ),
        })

    src_fiat = body.source_fiat.upper()
    if src_fiat not in ("GBP", "USD", "EUR"):
        raise HTTPException(status_code=400, detail="Unsupported source currency for fiat funding")

    total_fees_usd = float(quote["fees"]["total_fee_usd"])
    fees_in_src = total_fees_usd * (float(quote["source"]["amount"]) / max(float(quote["source"]["amount_usd"]), 0.01))
    charge_amount_src = round(float(quote["source"]["amount"]) + fees_in_src, 2)
    amount_cents = int(round(charge_amount_src * 100))

    dst = quote["destination"]
    line_item_name = f"Send to {dst['country']} · {dst['flag']}"
    line_item_desc = (
        f"{quote['source']['currency']} {quote['source']['amount']:.2f} → "
        f"{dst['currency']} {dst['amount']:,.2f} · fees included · arrives {dst['eta']}"
    )
    success, cancel = _success_cancel_urls("remit_fund")
    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            **_stripe_payment_method_config(body.payment_method),
            line_items=[{
                "price_data": {
                    "currency": src_fiat.lower(),
                    "product_data": {"name": line_item_name, "description": line_item_desc},
                    "unit_amount": amount_cents,
                },
                "quantity": 1,
            }],
            success_url=success,
            cancel_url=cancel,
            metadata={
                "user_id": user["id"],
                "flow": "remit_fund",
                "source_fiat": src_fiat,
                "source_amount": str(quote["source"]["amount"]),
                "destination_code": body.destination_code.upper(),
                "destination_currency": dst["currency"],
                "destination_amount": str(dst["amount"]),
                "destination_country": dst["country"],
                "destination_flag": dst["flag"],
                "recipient_address": body.recipient_address.strip(),
                "recipient_name": (body.recipient_name or "").strip()[:80],
                "memo": (body.memo or "")[:120],
                "payment_method": body.payment_method,
                "vaulted_service_usd": str(quote["fees"]["vaulted_service_usd"]),
                "fx_rate": str(quote["fx_rate"]),
                "receive_via": dst["receive_via"],
            },
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Stripe error: {e}") from e

    return {
        "checkout_url": session.url,
        "session_id": session.id,
        "charge_amount": charge_amount_src,
        "charge_currency": src_fiat,
        "destination": dst,
        "payment_method": body.payment_method,
    }
