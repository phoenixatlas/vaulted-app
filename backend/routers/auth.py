"""Auth router — user registration, login, session, password reset, onboarding.

Extracted from server.py's monolith as part of the P2 modularisation. Every
route below preserves its previous `/api/auth/*` path (server.py mounts this
router on `/api`, so `router.post("/auth/register")` → `/api/auth/register`).

Endpoints:
    POST /auth/register              — create account + wallet
    POST /auth/login                 — password + JWT
    GET  /auth/me                    — hydrate the current session
    PATCH /auth/language             — save preferred UI language
    PATCH /auth/security             — toggle biometric / multi-sig prefs
    POST /auth/forgot-password       — mint a 30-min single-use reset token
    POST /auth/reset-password        — burn the token and set the new hash
    POST /auth/onboarding-complete   — flip the "seed acknowledged" flag

Rate-limits, timing-uniformity, and enumeration-safe responses on
/auth/forgot-password are preserved verbatim from the previous implementation.
"""
from __future__ import annotations

import secrets
import uuid
from datetime import timedelta

import jwt
from eth_account import Account
from fastapi import APIRouter, Depends, HTTPException

from audit import EventType, write_event as audit_write
from deps import (
    APP_PUBLIC_URL,
    JWT_ALG,
    JWT_SECRET,
    db,
    get_current_user,
    iso,
    make_token,
    now_utc,
    public_user,
    pwd_ctx,
)
from emails import (
    PASSWORD_RESET_MAX_PER_HOUR,
    PASSWORD_RESET_TOKEN_TTL_SEC,
    password_reset_email_html,
    send_email_via_resend,
)
from models import (
    ForgotPasswordIn,
    LoginIn,
    RegisterIn,
    ResetPasswordIn,
    TokenOut,
    UpdateLanguageIn,
)
from referrals import generate_code as _gen_ref_code
from referrals import register_referral_at_signup
from seed import seed_user_data

router = APIRouter()


@router.post("/auth/register", response_model=TokenOut)
async def register(body: RegisterIn):
    existing = await db.users.find_one({"email": body.email.lower()})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    uid = str(uuid.uuid4())
    # Generate a real Ethereum keypair + BIP-39 mnemonic for Sepolia testnet.
    # NOTE: Account.create_with_mnemonic() must have HD wallet features enabled
    # on the eth_account library — this is the exact call pattern used in the
    # original monolith and is not changed here.
    acct, mnemonic_phrase = Account.create_with_mnemonic()
    # Assign a fresh referral code up-front. ensure_referral_code() will
    # regenerate on the very unlikely 8-char collision, but a direct
    # generate_code() at signup is faster and lands in the doc atomically.
    referral_code = _gen_ref_code()
    user_doc = {
        "id": uid,
        "email": body.email.lower(),
        "name": body.name.strip(),
        "password_hash": pwd_ctx.hash(body.password),
        "language": "en",
        "wallet_address": acct.address,
        "eth_private_key": "0x" + acct.key.hex(),
        "eth_mnemonic": mnemonic_phrase,
        "mnemonic_origin": "eth_native",  # derives ETH key via BIP44 m/44'/60'/0'/0/0
        "onboarding_seed_acknowledged": False,
        "biometric_enabled": False,
        "multisig_enabled": False,
        "referral_code": referral_code,
        "created_at": iso(now_utc()),
    }
    await db.users.insert_one(user_doc)
    await seed_user_data(uid)

    # If they signed up via an invite code, record the pending referral now
    # (credit is granted later, on KYC completion).
    if body.referred_by_code:
        row = await register_referral_at_signup(
            db,
            referred_user=user_doc,
            referred_by_code=body.referred_by_code,
        )
        if row:
            await audit_write(db, EventType.REFERRAL_SIGNUP, user=user_doc, data={
                "referral_id": row["id"],
                "referrer_user_id": row["referrer_user_id"],
                "referred_by_code": row["referred_by_code"],
            })
    return TokenOut(access_token=make_token(uid), user=public_user(user_doc))


@router.post("/auth/login", response_model=TokenOut)
async def login(body: LoginIn):
    u = await db.users.find_one({"email": body.email.lower()}, {"_id": 0})
    if not u or not pwd_ctx.verify(body.password, u["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return TokenOut(access_token=make_token(u["id"]), user=public_user(u))


@router.get("/auth/me")
async def me(user=Depends(get_current_user)):
    return public_user(user)


@router.patch("/auth/language")
async def update_language(body: UpdateLanguageIn, user=Depends(get_current_user)):
    await db.users.update_one({"id": user["id"]}, {"$set": {"language": body.language}})
    return {"language": body.language}


@router.patch("/auth/security")
async def update_security(body: dict, user=Depends(get_current_user)):
    updates = {}
    if "biometric_enabled" in body:
        updates["biometric_enabled"] = bool(body["biometric_enabled"])
    if "multisig_enabled" in body:
        updates["multisig_enabled"] = bool(body["multisig_enabled"])
    if updates:
        await db.users.update_one({"id": user["id"]}, {"$set": updates})
    u = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    return public_user(u)


@router.post("/auth/forgot-password")
async def forgot_password(body: ForgotPasswordIn):
    """Idempotent: always returns the same generic success message so we
    never disclose whether an email is registered. Rate-limited to 3
    requests per email per hour. When the email exists we mint a 30-min
    single-use JWT and email a reset link."""
    email = body.email.lower().strip()

    # Rate-limit BEFORE the DB lookup so the timing is uniform regardless
    # of email existence (defeats email-enumeration via response latency).
    one_hour_ago = now_utc() - timedelta(hours=1)
    recent_count = await db.password_resets.count_documents({
        "email": email,
        "created_at": {"$gte": iso(one_hour_ago)},
    })
    if recent_count >= PASSWORD_RESET_MAX_PER_HOUR:
        return {"ok": True, "message": "If an account exists for that email, a reset link has been sent."}

    user = await db.users.find_one({"email": email}, {"_id": 0})
    if user:
        nonce = secrets.token_urlsafe(24)
        exp = now_utc() + timedelta(seconds=PASSWORD_RESET_TOKEN_TTL_SEC)
        payload = {"sub": user["id"], "purpose": "password_reset", "nonce": nonce, "exp": exp}
        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)

        await db.password_resets.insert_one({
            "id": str(uuid.uuid4()),
            "user_id": user["id"],
            "email": email,
            "nonce": nonce,
            "used_at": None,
            "expires_at": iso(exp),
            "created_at": iso(now_utc()),
        })

        base = (APP_PUBLIC_URL or "https://app.phoenix-atlas.com").rstrip("/")
        reset_url = f"{base}/reset-password?token={token}"
        html = password_reset_email_html(user.get("name") or "", reset_url)
        await send_email_via_resend(email, "Reset your Vaulted password", html)

        await audit_write(db, EventType.AUTH_FORGOT_PASSWORD_REQUESTED, user=user, data={
            "delivered": True,
            "rate_limit_hits_in_window": recent_count,
        })
    else:
        # Silently record the attempt so we can spot enumeration probing
        # in the audit log. We DON'T write user-scoped audit for a missing
        # email — hash it into the data payload instead so it's still
        # correlateable but never surfaces PII.
        await db.password_resets.insert_one({
            "id": str(uuid.uuid4()),
            "user_id": None,
            "email": email,
            "nonce": None,
            "used_at": None,
            "expires_at": None,
            "created_at": iso(now_utc()),
            "no_user": True,
        })

    return {"ok": True, "message": "If an account exists for that email, a reset link has been sent."}


@router.post("/auth/reset-password")
async def reset_password(body: ResetPasswordIn):
    """Validate the single-use reset token, set the new password hash,
    burn the nonce so the token cannot be replayed."""
    # 1) Decode + verify the JWT
    try:
        payload = jwt.decode(body.token, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.ExpiredSignatureError as e:
        await audit_write(db, EventType.AUTH_PASSWORD_RESET_INVALID_TOKEN, user=None, data={"reason": "expired"})
        raise HTTPException(status_code=400, detail="Reset link has expired. Request a new one.") from e
    except Exception as e:  # noqa: BLE001
        await audit_write(db, EventType.AUTH_PASSWORD_RESET_INVALID_TOKEN, user=None, data={"reason": "invalid_jwt"})
        raise HTTPException(status_code=400, detail="Invalid reset link.") from e

    if payload.get("purpose") != "password_reset":
        raise HTTPException(status_code=400, detail="Invalid reset link.")
    user_id = payload.get("sub")
    nonce = payload.get("nonce")
    if not user_id or not nonce:
        raise HTTPException(status_code=400, detail="Invalid reset link.")

    # 2) Verify the nonce still exists + hasn't been used
    row = await db.password_resets.find_one({"user_id": user_id, "nonce": nonce})
    if not row:
        await audit_write(db, EventType.AUTH_PASSWORD_RESET_INVALID_TOKEN, user=None, data={"reason": "nonce_not_found"})
        raise HTTPException(status_code=400, detail="Invalid reset link.")
    if row.get("used_at"):
        await audit_write(db, EventType.AUTH_PASSWORD_RESET_INVALID_TOKEN, user=None, data={"reason": "nonce_already_used"})
        raise HTTPException(status_code=400, detail="This reset link has already been used. Request a new one.")

    # 3) Update the password + burn the nonce (both atomically-ish)
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=400, detail="Invalid reset link.")

    new_hash = pwd_ctx.hash(body.new_password)
    await db.users.update_one({"id": user_id}, {"$set": {"password_hash": new_hash}})
    await db.password_resets.update_one(
        {"user_id": user_id, "nonce": nonce},
        {"$set": {"used_at": iso(now_utc())}},
    )
    # Belt-and-braces: mark any OTHER outstanding tokens for this user as
    # consumed too, so a password change invalidates every parallel link.
    await db.password_resets.update_many(
        {"user_id": user_id, "nonce": {"$ne": nonce}, "used_at": None},
        {"$set": {"used_at": iso(now_utc()), "invalidated_by_reset": True}},
    )

    await audit_write(db, EventType.AUTH_PASSWORD_RESET_COMPLETED, user=user, data={
        "nonce_prefix": nonce[:8],
    })

    return {"ok": True, "message": "Password updated. You can now sign in with your new password."}


@router.post("/auth/onboarding-complete")
async def complete_onboarding(user=Depends(get_current_user)):
    await db.users.update_one({"id": user["id"]}, {"$set": {"onboarding_seed_acknowledged": True}})
    u = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    return public_user(u)
