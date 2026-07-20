"""Multi-signature co-signer + approval routes.

Sends >= MULTISIG_THRESHOLD_ETH require an email-based approval from a
designated co-signer before the tx is broadcast to Sepolia. Endpoints:
 - GET  /cosigners             list my co-signers
 - POST /cosigners             add a co-signer (Pro-gated)
 - DEL  /cosigners/{id}        remove a co-signer
 - GET  /approvals/pending     my currently pending sends
 - POST /approvals/decide      cosigner-facing endpoint (unauth'd,
                               token-authenticated) that broadcasts or
                               cancels the pending tx

Extracted from server.py during the P2 refactor. Broadcast delegates to
`_broadcast_eth_send` (still in server.py) via a lazy import.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException

from deps import (
    APP_PUBLIC_URL,
    APPROVAL_TTL_HOURS,
    MULTISIG_THRESHOLD_ETH,
    db,
    get_current_user,
    iso,
    logger,
    now_utc,
)
from emails import RESEND_API_KEY, get_resend_from
from models import ApprovalActionIn, CosignerInviteIn
from push import send_push

router = APIRouter()


async def _send_approval_email(pending: dict) -> None:
    if not RESEND_API_KEY:
        logger.warning("RESEND_API_KEY not set; skipping approval email")
        return
    base = APP_PUBLIC_URL.rstrip("/")
    approve_url = f"{base}/approve?token={pending['approver_token']}&decision=approve"
    reject_url = f"{base}/approve?token={pending['approver_token']}&decision=reject"
    short_to = pending["to_address"][:10] + "..." + pending["to_address"][-6:]
    html = f"""
    <div style="font-family:-apple-system,Helvetica,Arial,sans-serif;max-width:520px;margin:auto;padding:24px;background:#fcfcfc;color:#1a1d1a">
      <div style="font-size:22px;font-weight:700;color:#3F6156;margin-bottom:4px">Vaulted</div>
      <div style="font-size:13px;color:#6d7a73;margin-bottom:24px">Multi-signature approval request</div>
      <div style="background:#f3f4f3;padding:16px;border-radius:12px">
        <div style="font-size:13px;color:#6d7a73">{pending['user_name']} ({pending['user_email']}) wants to send</div>
        <div style="font-size:28px;font-weight:700;margin-top:6px">{pending['amount_eth']} ETH</div>
        <div style="font-size:12px;color:#6d7a73;margin-top:6px">to <code>{short_to}</code> on Sepolia</div>
      </div>
      <p style="font-size:13px;color:#4a524d;margin-top:18px">As their designated co-signer, your approval is required for sends \u2265 {MULTISIG_THRESHOLD_ETH} ETH. This request expires in {APPROVAL_TTL_HOURS}h.</p>
      <div style="margin-top:24px">
        <a href="{approve_url}" style="display:inline-block;background:#3F6156;color:#fff;padding:12px 20px;border-radius:10px;text-decoration:none;font-weight:600;margin-right:8px">Approve</a>
        <a href="{reject_url}" style="display:inline-block;background:#fff;color:#b83a3a;padding:12px 20px;border-radius:10px;text-decoration:none;font-weight:600;border:1px solid #b83a3a">Reject</a>
      </div>
      <div style="font-size:11px;color:#6d7a73;margin-top:24px">If you didn't expect this, reject and let {pending['user_email']} know \u2014 their account may be compromised.</div>
    </div>
    """
    try:
        async with httpx.AsyncClient(timeout=12) as cx:
            r = await cx.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
                json={
                    "from": get_resend_from(),
                    "to": [pending["cosigner_email"]],
                    "subject": f"Approve {pending['amount_eth']} ETH from Vaulted?",
                    "html": html,
                },
            )
            if r.status_code >= 400:
                logger.warning(f"resend send failed {r.status_code}: {r.text[:200]}")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"resend send exception: {e}")


@router.get("/cosigners")
async def list_cosigners(user=Depends(get_current_user)):
    cur = db.cosigners.find({"user_id": user["id"]}, {"_id": 0})
    return await cur.to_list(50)


@router.post("/cosigners")
async def add_cosigner(body: CosignerInviteIn, user=Depends(get_current_user)):
    if (user.get("subscription") or {}).get("status") not in ("active", "trialing"):
        raise HTTPException(status_code=402, detail="Vault Pro required to add co-signers")
    existing = await db.cosigners.find_one({"user_id": user["id"], "email": body.email.lower()}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=400, detail="Co-signer already added")
    doc = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "email": body.email.lower(),
        "label": body.label or body.email.split("@")[0],
        "status": "active",
        "added_at": iso(now_utc()),
    }
    await db.cosigners.insert_one(doc)
    # Send a welcome / "you are now a co-signer" email so the recipient knows
    if RESEND_API_KEY:
        try:
            async with httpx.AsyncClient(timeout=10) as cx:
                await cx.post(
                    "https://api.resend.com/emails",
                    headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
                    json={
                        "from": get_resend_from(),
                        "to": [body.email],
                        "subject": f"You're now a Vaulted co-signer for {user.get('name')}",
                        "html": f"<p>{user.get('name')} ({user.get('email')}) added you as a co-signer on their Vaulted wallet. You'll receive an email any time they try to send \u2265 {MULTISIG_THRESHOLD_ETH} ETH; tap Approve or Reject in those emails.</p>",
                    },
                )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"welcome email failed: {e}")
    doc.pop("_id", None)
    return doc


@router.delete("/cosigners/{cosigner_id}")
async def remove_cosigner(cosigner_id: str, user=Depends(get_current_user)):
    r = await db.cosigners.delete_one({"id": cosigner_id, "user_id": user["id"]})
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Co-signer not found")
    return {"removed": True}


@router.get("/approvals/pending")
async def list_pending_approvals(user=Depends(get_current_user)):
    cur = db.eth_approvals.find(
        {"user_id": user["id"], "status": "pending"}, {"_id": 0, "approver_token": 0}
    ).sort("created_at", -1)
    return await cur.to_list(50)


@router.post("/approvals/decide")
async def decide_approval(body: ApprovalActionIn):
    """Public endpoint hit from email link (no auth - the token is the credential)."""
    approval = await db.eth_approvals.find_one({"approver_token": body.token}, {"_id": 0})
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found or already used")
    if approval["status"] != "pending":
        return {"status": approval["status"], "already": True, "approval": approval}

    try:
        expires = datetime.fromisoformat(approval["expires_at"])
        if now_utc() > expires:
            await db.eth_approvals.update_one(
                {"id": approval["id"]}, {"$set": {"status": "expired", "decided_at": iso(now_utc())}}
            )
            raise HTTPException(status_code=410, detail="Approval expired")
    except HTTPException:
        raise
    except Exception:
        pass

    if body.decision == "reject":
        await db.eth_approvals.update_one(
            {"id": approval["id"]}, {"$set": {"status": "rejected", "decided_at": iso(now_utc())}}
        )
        try:
            await send_push(
                recipients=[approval["user_id"]],
                data={
                    "title": f"\u26d4 Co-signer rejected {approval['amount_eth']} ETH",
                    "message": "Your multi-sig transaction was not broadcast.",
                    "action_url": "/approvals",
                },
                idempotency_key=f"approval-{approval['id']}-rejected",
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("push approval-rejected failed: %s", e)
        return {"status": "rejected", "approval_id": approval["id"]}

    # Approve -> broadcast the tx now using the sender's key
    user = await db.users.find_one({"id": approval["user_id"]}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="Original sender not found")
    # Lazy import to avoid circular; _broadcast_eth_send lives in server.py
    # under wallet code (not yet extracted).
    from server import _broadcast_eth_send  # noqa: PLC0415
    try:
        tx_record = await _broadcast_eth_send(
            user, user["wallet_address"], user["eth_private_key"],
            approval["to_address"], approval["amount_eth"],
        )
    except HTTPException as e:
        await db.eth_approvals.update_one(
            {"id": approval["id"]},
            {"$set": {"status": "failed", "decided_at": iso(now_utc()), "failure_reason": e.detail}},
        )
        raise
    await db.eth_approvals.update_one(
        {"id": approval["id"]},
        {"$set": {
            "status": "approved",
            "decided_at": iso(now_utc()),
            "tx_hash": tx_record.get("tx_hash"),
            "explorer_url": tx_record.get("explorer_url"),
        }},
    )
    # Notify the wallet owner that their cosigner approved & the broadcast is live
    try:
        await send_push(
            recipients=[approval["user_id"]],
            data={
                "title": f"\u2705 Co-signer approved {approval['amount_eth']} ETH",
                "message": "Your multi-sig transaction is now on Sepolia.",
                "action_url": "/approvals",
            },
            idempotency_key=f"approval-{approval['id']}-approved",
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("push approval-approved failed: %s", e)
    return {"status": "approved", "approval_id": approval["id"], "tx_hash": tx_record.get("tx_hash"), "explorer_url": tx_record.get("explorer_url")}
