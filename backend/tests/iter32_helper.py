"""Iteration 32 helper — seed/cleanup transfer-tracking + feedback-reply docs directly in Mongo.
Usage: python tests/iter32_helper.py <cmd> <user_id>
  seed <uid>     -> insert _iter32 txs + feedback-with-reply; prints ids JSON
  unread <uid>   -> re-flag the seeded feedback as unread
  cleanup <uid>  -> delete all _iter32 docs
"""
import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(".env", override=True)
from deps import db  # noqa: E402


def _iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


def _remit(code, country, cur, amt, chain=None):
    r = {"source_amount": 20, "source_currency": "GBP", "destination_country": country,
         "destination_currency": cur, "destination_amount": amt, "fx_rate": round(amt / 20, 2),
         "receive_via": "Bank transfer (via partner)" if code == "NG" else "M-Pesa (via partner)"}
    if code:
        r["destination_country_code"] = code
    if chain:
        r["chain"] = chain
    return r


async def seed(uid):
    now = datetime.now(timezone.utc)
    ids = {k: f"iter32-{k}-{uuid.uuid4().hex[:8]}" for k in
           ("ng_settled", "ke_processing", "failed", "crypto", "deposit", "other")}
    base = {"user_id": uid, "_iter32": True, "type": "send", "category": "remit", "asset": "USDC",
            "amount": 25.3, "fiat_value": 25.3, "receipt_id": "VLT-ITER32"}
    docs = [
        {**base, "id": ids["ng_settled"], "status": "settled", "funding_method": "stripe", "payment_method": "card",
         "remit": _remit("NG", "Nigeria", "NGN", 40000), "counterparty": "0123456789",
         "recipient_name": "TEST ACCOUNT HOLDER", "recipient_bank": {"id": "ng_058", "name": "GTBank"},
         "payout": {"reference_id": "YC-REF-1234567890ABCDEF", "provider_label": "Yellow Card", "mode": "mock",
                    "initiated_at": _iso(now - timedelta(minutes=4)), "updated_at": _iso(now - timedelta(minutes=3))},
         "created_at": _iso(now - timedelta(minutes=5))},
        # old record: no destination_country_code -> fallback by country name
        {**base, "id": ids["ke_processing"], "status": "processing", "funding_method": "stripe", "payment_method": "card",
         "remit": _remit(None, "Kenya", "KES", 3300), "counterparty": "+254712345678",
         "recipient_name": "TEST Wanjiru Kamau", "created_at": _iso(now - timedelta(minutes=1))},
        {**base, "id": ids["failed"], "status": "processing", "funding_method": "stripe", "payment_method": "apple_pay",
         "remit": _remit("KE", "Kenya", "KES", 3300), "counterparty": "+254700000111", "recipient_name": "TEST Fail",
         "payout": {"failed": True, "reason": "TEST_ partner rejected the account", "provider_label": "Kotani Pay"},
         "created_at": _iso(now - timedelta(minutes=7))},
        {**base, "id": ids["crypto"], "status": "completed", "remit": _remit("KE", "Kenya", "KES", 3300, chain="base"),
         "counterparty": "0xabc0000000000000000000000000000000000def", "recipient_name": "TEST Crypto",
         "tx_hash": "0x" + "ab" * 32, "network": "base", "created_at": _iso(now - timedelta(minutes=9))},
        {**base, "id": ids["deposit"], "type": "deposit", "category": "fiat", "status": "completed",
         "counterparty": "CARD Top-up", "created_at": _iso(now - timedelta(minutes=11))},
        {**base, "id": ids["other"], "user_id": "iter32-someone-else", "status": "settled", "funding_method": "stripe",
         "remit": _remit("NG", "Nigeria", "NGN", 40000), "counterparty": "0123456789",
         "created_at": _iso(now)},
    ]
    await db.transactions.insert_many(docs)
    fb_id, rep_id = f"iter32-fb-{uuid.uuid4().hex[:8]}", f"iter32-rep-{uuid.uuid4().hex[:8]}"
    await db.feedback.insert_one({
        "id": fb_id, "user_id": uid, "_iter32": True, "note": "TEST_iter32 the send button was slow",
        "screen": "remit", "created_at": _iso(now),
        "replies": [{"id": rep_id, "message": "TEST_iter32 thanks, fixed in next build", "at": _iso(now), "by": "Vaulted team"}],
        "unread_reply": True})
    ids["fb"], ids["reply"] = fb_id, rep_id
    print(json.dumps(ids))


async def main():
    cmd, uid = sys.argv[1], sys.argv[2]
    if cmd == "seed":
        await seed(uid)
    elif cmd == "unread":
        r = await db.feedback.update_many({"user_id": uid, "_iter32": True}, {"$set": {"unread_reply": True}})
        print(json.dumps({"updated": r.modified_count}))
    elif cmd == "cleanup":
        t = await db.transactions.delete_many({"_iter32": True})
        f = await db.feedback.delete_many({"_iter32": True})
        print(json.dumps({"tx_deleted": t.deleted_count, "fb_deleted": f.deleted_count}))


asyncio.run(main())
