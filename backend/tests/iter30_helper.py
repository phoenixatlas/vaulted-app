"""Iteration 30 helper — direct-DB actions for recipients/stripe-apply tests.
Usage: python tests/iter30_helper.py <cmd> <user_id> [args]
  save_twice <uid>            -> upsert same recipient twice, print JSON row
  seed_ke <uid>               -> seed one KE recipient (for UI chip test)
  apply_ng <uid> <session_id> -> run _apply_checkout_session for an NG remit
  cleanup <uid>               -> delete TEST_ recipients for user
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(".env", override=True)

from deps import db  # noqa: E402
from routers.recipients import save_recipient  # noqa: E402


async def main():
    cmd, uid = sys.argv[1], sys.argv[2]
    if cmd == "save_twice":
        for _ in range(2):
            await save_recipient(uid, name="TEST_Ada Obi", country_code="ng", currency="NGN",
                                 account="0123456789", rail="bank", bank_id="ng_058", bank_name="GTBank", verified=True)
        await save_recipient(uid, name="TEST_Wanjiru", country_code="KE", currency="KES",
                             account="+254700000001", rail="momo")
        rows = await db.recipients.find({"user_id": uid}, {"_id": 0}).to_list(50)
        print(json.dumps(rows))
    elif cmd == "seed_ke":
        await save_recipient(uid, name="TEST_Wanjiru Kamau", country_code="KE", currency="KES",
                             account="+254712345678", rail="momo")
        print(json.dumps(await db.recipients.find({"user_id": uid}, {"_id": 0}).to_list(50)))
    elif cmd == "apply_ng":
        from routers.stripe_router import _apply_checkout_session
        sess = {
            "id": sys.argv[3], "mode": "payment", "payment_status": "paid", "amount_total": 2500,
            "metadata": {
                "user_id": uid, "flow": "remit_fund", "source_fiat": "GBP", "source_amount": "20",
                "destination_code": "NG", "destination_currency": "NGN", "destination_amount": "40000",
                "destination_country": "Nigeria", "destination_flag": "NG",
                "recipient_address": "0123456789", "recipient_name": "TEST_Ada Obi",
                "payment_method": "card", "recipient_bank_id": "ng_058", "recipient_bank_name": "GTBank",
                "recipient_verified": "1", "save_recipient": "1", "vaulted_service_usd": "0.5",
                "fx_rate": "2000", "receive_via": "bank",
            },
        }
        res = await _apply_checkout_session(sess)
        tx = res.get("tx") or {}
        rec = await db.recipients.find_one({"user_id": uid, "country_code": "NG"}, {"_id": 0})
        print(json.dumps({"applied": res.get("applied"), "recipient_bank": tx.get("recipient_bank"),
                          "tx_status": tx.get("status"), "recipient": rec}, default=str))
    elif cmd == "cleanup":
        r = await db.recipients.delete_many({"user_id": uid, "name": {"$regex": "^TEST_"}})
        print(json.dumps({"deleted": r.deleted_count}))


asyncio.run(main())
