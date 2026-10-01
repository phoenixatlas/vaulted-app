"""Vaulted — slim bootstrap entrypoint.

Historically this file was a ~2000-line monolith owning every endpoint. After
the P2 refactor every route lives in /app/backend/routers/*.py (one file per
feature area) and this module is intentionally kept as a lightweight
composition root — it wires routers onto FastAPI, owns app lifecycle hooks
(CORS, startup/shutdown, Resend domain poller), and nothing else.

Grouping:
  routers/wallet.py           — crypto balances + per-chain sends + /market/prices
  routers/multichain_router.py — EVM L2 chains + USDC transfers
  routers/remit.py             — cross-border remittance (quote/send/fund)
  routers/transactions.py      — activity history + CSV export + fiat deposit/withdraw
  routers/auth.py              — register / login / password reset / language
  routers/kyc.py               — Stripe Identity verification + webhooks
  routers/stripe_router.py     — subscriptions, portals, webhook dispatcher
  routers/admin.py             — admin dashboard / Kotani health / observability
  routers/offramp.py           — Kotani mobile-money payout triggers
  routers/reverse_remit.py     — Africa → UK/EU corridor quote engine
  routers/investor.py          — investor PDFs + email flows + book-click attribution
  routers/waitlist.py          — public waitlist + referrals + analytics
  routers/multisig.py          — ETH approval queue + cosigners
  routers/chat.py              — E2EE chat + in-chat crypto sends
  routers/calls.py             — Daily.co video call rooms
  routers/referrals.py         — referral codes + credit ledger
  routers/keys.py              — public key registry (WebAuthn-style stubs)
  market.py                    — CoinGecko-backed price helper, shared by
                                 wallet + remit routers.
"""
from __future__ import annotations

import os
import stripe
from fastapi import FastAPI, APIRouter
from starlette.middleware.cors import CORSMiddleware

from deps import client, db, STRIPE_API_KEY, logger
from emails import start_resend_domain_poller

if STRIPE_API_KEY:
    stripe.api_key = STRIPE_API_KEY

app = FastAPI(title="Vaulted Wallet API")
api = APIRouter(prefix="/api")


# ----------------------------- Routes -----------------------------
@api.get("/")
async def root():
    return {"service": "vaulted", "status": "ok"}


# --- Stripe payments extracted to /routers/stripe_router.py (P2 refactor) ---
# Re-exported here so any legacy code paths grepping for it on server work.
from routers.stripe_router import _success_cancel_urls  # noqa: E402, F401


# --- P2 refactor: extracted routers ---------------------------------------
# Each router is a self-contained APIRouter defined in /routers/*.py. Mount
# them onto the top-level /api router BEFORE app.include_router(api) so
# their routes get the /api prefix (and appear in OpenAPI, in the same
# position they had before extraction).
from routers.admin import router as admin_router
from routers.referrals import router as referrals_router
from routers.offramp import router as offramp_router, trigger_kotani_offramp_for_remit  # noqa: F401
from routers.calls import router as calls_router
from routers.keys import router as keys_router
from routers.chat import router as chat_router
from routers.multisig import router as multisig_router, _send_approval_email  # noqa: F401
from routers.waitlist import router as waitlist_router
from routers.auth import router as auth_router
from routers.reverse_remit import router as reverse_remit_router
from routers.investor import router as investor_router
from routers.stripe_router import router as stripe_router
from routers.kyc import (
    router as kyc_router,
    _apply_identity_verified,  # noqa: F401 — re-exported for webhook dispatcher
    _apply_identity_requires_input,  # noqa: F401
)
# P2 refactor wave 2 — the big extraction. These four routers carry
# ~1700 of the ~2000 lines previously inside server.py.
from routers.wallet import router as wallet_router, _broadcast_eth_send  # noqa: F401
from routers.multichain_router import router as multichain_router
from routers.remit import router as remit_router
from routers.transactions import router as transactions_router

api.include_router(wallet_router)
api.include_router(multichain_router)
api.include_router(remit_router)
api.include_router(transactions_router)
api.include_router(admin_router)
api.include_router(referrals_router)
api.include_router(offramp_router)
api.include_router(calls_router)
api.include_router(keys_router)
api.include_router(chat_router)
api.include_router(multisig_router)
api.include_router(waitlist_router)
api.include_router(auth_router)
api.include_router(reverse_remit_router)
api.include_router(investor_router)
api.include_router(stripe_router)
api.include_router(kyc_router)

# Push notifications: register-push uses raw /api/register-push (no double
# prefix), so it's mounted directly on `app` rather than through `api`.
from push import register_push_router, send_push  # noqa: F401 — send_push is
# re-exported here so any remaining server.py code (chat_send_crypto's
# lazy-imports have already been extracted) can find it via `server.send_push`.
app.include_router(register_push_router)

app.include_router(api)


# Lightweight liveness probe for Railway/Render/Fly health checks.
@app.api_route("/api/health", methods=["GET", "HEAD"])
async def health() -> dict:
    return {"status": "ok"}


# CORS — env-driven for prod, falls back to '*' for local dev.
# Set CORS_ALLOW_ORIGINS in Railway/Vercel as a comma-separated list, e.g.:
#   CORS_ALLOW_ORIGINS=https://vaulted.vercel.app,https://app.vaulted.io
_origins_env = os.environ.get("CORS_ALLOW_ORIGINS", "").strip()
_allow_origins = (
    [o.strip() for o in _origins_env.split(",") if o.strip()] if _origins_env else ["*"]
)
# Browsers reject `allow_credentials=True` with `allow_origins=*`, so flip credentials
# off when we're in the wildcard fallback.
_allow_credentials = _allow_origins != ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_credentials=_allow_credentials,
    allow_origins=_allow_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()


# ---------- Resend domain auto-poller -----------------------------------------
# The poller lives in emails.py (extracted during the P2 refactor). We just
# schedule it from here as an @app.on_event("startup") hook so it fires as
# part of FastAPI's normal startup sequence.


@app.on_event("startup")
async def _start_resend_poller():
    # Fire-and-forget; FastAPI will keep this task alive for the process lifetime.
    start_resend_domain_poller()


@app.on_event("startup")
async def _ensure_audit_indexes():
    """Ensure the query patterns on the audit-log endpoint stay fast even as
    the collection grows to 100k+ events. Idempotent — safe to run on every
    startup."""
    try:
        await db.audit_events.create_index([("timestamp", -1)])
        await db.audit_events.create_index([("user_id", 1), ("timestamp", -1)])
        await db.audit_events.create_index([("event_type", 1), ("timestamp", -1)])
        # Referrals + credit-ledger indexes
        await db.users.create_index("referral_code", unique=True, sparse=True)
        await db.referrals.create_index("referrer_user_id")
        await db.referrals.create_index("referred_user_id", unique=True, sparse=True)
        await db.credit_ledger.create_index([("user_id", 1), ("created_at", -1)])
    except Exception as e:
        logger.warning(f"audit_events index creation failed: {e}")


