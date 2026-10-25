"""Iteration 29 — exercise payouts.dispatch_payout_for_remit directly.
Run: cd /app/backend && python tests/manual_iter29_payout_orchestrator.py"""
import asyncio
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(".env")
import payouts  # noqa: E402
from deps import db  # noqa: E402

CUR = {"KE": "KES", "GH": "GHS", "NG": "NGN", "IN": "INR"}


async def make_tx(user_id, country):
    tid = "TEST_" + uuid.uuid4().hex[:12]
    rec = {
        "id": tid, "user_id": user_id, "type": "remit", "status": "pending",
        "amount": 50.0, "fiat_value": 65.0, "counterparty": "+254712345678",
        "recipient_name": "TEST Recipient",
        "remit": {"destination_country_code": country, "destination_currency": CUR[country],
                  "source_currency": "GBP", "source_amount": 50.0, "destination_amount": 8000},
    }
    await db.transactions.insert_one(dict(rec))
    return rec


async def main():
    user = await db.users.find_one({"email": "smoketest@vaulted.app"}, {"_id": 0, "id": 1})
    uid = user["id"]
    orig = await payouts.get_settings()
    print("original settings:", orig)
    results, ids = [], []
    cases = [("kotani", "KE", "simulated"), ("kotani", "IN", "simulated"),
             ("yellowcard", "KE", "mock"), ("yellowcard", "GH", "mock"), ("yellowcard", "NG", "mock"),
             ("yellowcard", "IN", "simulated")]
    try:
        for provider, country, expect_mode in cases:
            await payouts.update_settings(provider, True, "test")
            rec = await make_tx(uid, country)
            ids.append(rec["id"])
            out = await payouts.dispatch_payout_for_remit(rec)
            tx = await db.transactions.find_one({"id": rec["id"]}, {"_id": 0})
            p = out.get("payout") or {}
            ok = p.get("mode") == expect_mode and tx["status"] == "settled" and (tx.get("payout") or {}).get("mode") == expect_mode
            results.append(ok)
            print(f"{'PASS' if ok else 'FAIL'} {provider}/{country}: mode={p.get('mode')} status={tx['status']} "
                  f"ref={p.get('reference_id')} reason={p.get('reason')}")
        # Beta OFF with unsupported country -> skipped, not settled
        await payouts.update_settings("kotani", False, "test")
        rec = await make_tx(uid, "IN")
        ids.append(rec["id"])
        out = await payouts.dispatch_payout_for_remit(rec)
        tx = await db.transactions.find_one({"id": rec["id"]}, {"_id": 0})
        ok = out["payout"].get("skipped") is True and tx["status"] == "pending"
        results.append(ok)
        print(f"{'PASS' if ok else 'FAIL'} kotani/IN beta-off: {out['payout']} status={tx['status']}")
        # Beta OFF, kotani KE (401) -> failed (not simulated)
        rec = await make_tx(uid, "KE")
        ids.append(rec["id"])
        out = await payouts.dispatch_payout_for_remit(rec)
        tx = await db.transactions.find_one({"id": rec["id"]}, {"_id": 0})
        ok = out["payout"].get("failed") is True and tx["status"] != "settled"
        results.append(ok)
        print(f"{'PASS' if ok else 'FAIL'} kotani/KE beta-off: failed={out['payout'].get('failed')} status={tx['status']}")
        # Beta OFF, yellowcard KE mock -> what happens?
        await payouts.update_settings("yellowcard", False, "test")
        rec = await make_tx(uid, "KE")
        ids.append(rec["id"])
        out = await payouts.dispatch_payout_for_remit(rec)
        tx = await db.transactions.find_one({"id": rec["id"]}, {"_id": 0})
        print(f"INFO yellowcard/KE beta-off (no keys): mode={out['payout'].get('mode')} status={tx['status']}")
    finally:
        await payouts.update_settings("kotani", True, "test")
        r = await db.transactions.delete_many({"id": {"$in": ids}})
        print("reset settings:", await payouts.get_settings(), "deleted txs:", r.deleted_count)
    print(f"RESULT {sum(results)}/{len(results)} passed")


asyncio.run(main())
