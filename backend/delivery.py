"""Delivery emails — tell the sender the moment their money has arrived.

One idempotent entry point, `notify_if_delivered(tx_id)`, called right after
any path that marks a remit send `settled` (partner webhook, simulated beta
payout, blockchain confirmation). A 60-second background tick is the safety
net: it confirms pending crypto sends on-chain and emails any settled remit
that slipped through. The atomic `delivery_email_sent_at` claim guarantees
one email per transfer even when both paths fire together.

Only transfers created after the feature first ran are emailed, so the
back catalogue of old transfers never gets a surprise burst of emails.
"""
from __future__ import annotations

import html
from typing import Optional

from deps import db, iso, logger, now_utc
from emails import send_email_via_resend

_MAX_ATTEMPTS = 3


async def _since() -> str:
    doc = await db.config.find_one({"_id": "delivery_emails"})
    if doc and doc.get("since"):
        return doc["since"]
    since = iso(now_utc())
    await db.config.update_one({"_id": "delivery_emails"}, {"$setOnInsert": {"since": since}}, upsert=True)
    return (await db.config.find_one({"_id": "delivery_emails"}))["since"]


def _money(amount, currency: str) -> str:
    try:
        return f"{float(amount):,.2f} {currency}"
    except (TypeError, ValueError):
        return f"{amount} {currency}"


def delivery_email_html(tx: dict, user: dict) -> str:
    remit = tx.get("remit") or {}
    payout = tx.get("payout") or tx.get("kotani") or {}
    is_test = payout.get("mode") in ("simulated", "mock")
    e = lambda v: html.escape(str(v or ""))  # noqa: E731
    who = e(tx.get("recipient_name") or "your recipient")
    received = e(_money(remit.get("destination_amount"), remit.get("destination_currency", "")))
    sent = e(_money(remit.get("source_amount") or tx.get("amount"), remit.get("source_currency") or tx.get("asset", "")))
    rows = [
        ("They received", received),
        ("You sent", sent),
        ("Delivered via", e(remit.get("receive_via") or (tx.get("recipient_bank") or {}).get("name"))),
        ("Country", e(remit.get("destination_country"))),
        ("Receipt ID", e(tx.get("receipt_id") or tx.get("id", "")[:8].upper())),
    ]
    row_html = "".join(
        f'<tr><td style="padding:8px 0;color:#B8AFA1;font-size:13px">{k}</td>'
        f'<td style="padding:8px 0;color:#F5E9C9;font-size:13px;font-weight:600;text-align:right">{v}</td></tr>'
        for k, v in rows if v
    )
    test_note = (
        '<p style="font-size:12px;color:#E6C879;line-height:18px;margin:20px 0 0;padding:12px;border:1px solid #3a3020;border-radius:8px">'
        "Beta test payout: no real money was sent to the recipient.</p>" if is_test else ""
    )
    return f"""
    <div style="font-family:-apple-system,Helvetica,Arial,sans-serif;max-width:520px;margin:auto;padding:32px 24px;background:#0F0B08;color:#F5E9C9">
      <div style="font-size:24px;font-weight:700;color:#C9A35B;letter-spacing:-0.4px;margin-bottom:4px">Vaulted</div>
      <div style="font-size:11px;color:#B8AFA1;letter-spacing:2px;text-transform:uppercase;margin-bottom:28px">Money delivered</div>
      <div style="font-size:16px;margin-bottom:12px">Hi {e((user.get('name') or 'there').split(' ')[0])},</div>
      <p style="font-size:15px;line-height:22px;margin:0 0 20px">Good news: <b>{who}</b> has received <b style="color:#C9A35B">{received}</b>.</p>
      <table style="width:100%;border-collapse:collapse;border-top:1px solid #2a2320;border-bottom:1px solid #2a2320">{row_html}</table>
      {test_note}
      <p style="font-size:13px;color:#B8AFA1;line-height:20px;margin:24px 0 0">Open Vaulted and tap this transfer in Activity to see the full timeline, share the receipt, or send it again.</p>
      <p style="font-size:11px;color:#6d7a73;margin-top:28px">You can turn these emails off in Vaulted under Settings, Notifications.<br/>Vaulted \u00b7 Phoenix Atlas Ltd \u00b7 UK</p>
    </div>
    """


def _subject(tx: dict) -> str:
    remit = tx.get("remit") or {}
    who = tx.get("recipient_name") or "your recipient"
    return f"Delivered: {_money(remit.get('destination_amount'), remit.get('destination_currency', ''))} to {who}"


async def notify_if_delivered(tx_id: str) -> bool:
    """Send the delivery email once. Returns True if an email went out now."""
    since = await _since()
    tx = await db.transactions.find_one_and_update(
        {
            "id": tx_id, "type": "send", "remit": {"$exists": True}, "status": {"$in": ["settled", "completed"]},
            "created_at": {"$gte": since}, "user_deleted": {"$ne": True},
            "delivery_email_sent_at": {"$exists": False}, "receipt_emailed_at": {"$exists": False},
            "delivery_email_attempts": {"$not": {"$gte": _MAX_ATTEMPTS}},
        },
        {"$set": {"delivery_email_sent_at": iso(now_utc())}, "$inc": {"delivery_email_attempts": 1}},
        projection={"_id": 0},
    )
    if not tx:
        return False
    user = await db.users.find_one({"id": tx["user_id"]}, {"_id": 0, "email": 1, "name": 1, "delivery_emails": 1}) or {}
    if not user.get("email"):
        return False
    if user.get("delivery_emails") is False:  # opted out in Settings → Notifications
        await db.transactions.update_one({"id": tx_id}, {"$set": {"delivery_email_skipped": "opted_out"}})
        return False
    ok = await send_email_via_resend(user["email"], _subject(tx), delivery_email_html(tx, user))
    if not ok:  # release the claim so the next tick retries (max 3 attempts)
        await db.transactions.update_one({"id": tx_id}, {"$unset": {"delivery_email_sent_at": ""}})
        return False
    logger.info("[delivery-email] sent for tx %s", tx_id)
    return True


async def delivery_tick() -> dict:
    """Confirm pending crypto sends on-chain, then email any newly delivered transfer."""
    from routers.transactions import _chain_confirmation

    since = await _since()
    confirmed = 0
    pending = await db.transactions.find(
        {"type": "send", "status": "pending", "remit.chain": {"$exists": True},
         "tx_hash": {"$nin": [None, ""]}, "created_at": {"$gte": since}},
        {"_id": 0, "id": 1, "tx_hash": 1, "remit.chain": 1},
    ).limit(25).to_list(25)
    for p in pending:
        outcome = await _chain_confirmation(p["remit"]["chain"], p["tx_hash"])
        if outcome:
            await db.transactions.update_one({"id": p["id"], "status": "pending"},
                                             {"$set": {"status": outcome, "confirmed_at": iso(now_utc())}})
            confirmed += 1

    candidates = await db.transactions.find(
        {"type": "send", "remit": {"$exists": True}, "status": {"$in": ["settled", "completed"]},
         "created_at": {"$gte": since}, "delivery_email_sent_at": {"$exists": False},
         "receipt_emailed_at": {"$exists": False}, "user_deleted": {"$ne": True},
         "delivery_email_attempts": {"$not": {"$gte": _MAX_ATTEMPTS}}},
        {"_id": 0, "id": 1},
    ).limit(50).to_list(50)
    sent = 0
    for c in candidates:
        sent += int(await notify_if_delivered(c["id"]))
    return {"confirmed": confirmed, "emailed": sent}


async def safe_notify(tx_id: Optional[str]) -> None:
    """Fire-and-forget wrapper for call sites that must never fail."""
    if not tx_id:
        return
    try:
        await notify_if_delivered(tx_id)
    except Exception as e:  # noqa: BLE001
        logger.warning("[delivery-email] notify failed for %s: %s", tx_id, e)
