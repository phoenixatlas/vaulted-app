"""Flutterwave dispatch_payout_for_remit + reconcile_flutterwave integration (real sandbox).
Creates TEST_ remit transactions for NG (bank 044 / 0690000031) and KE (M-Pesa 254712345678),
dispatches, reconciles, asserts settled, then cleans up."""
import asyncio
import os
import sys
import uuid

import pytest

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv  # noqa: E402

load_dotenv("/app/backend/.env")


def _record(user_id, country, currency, amount, counterparty, bank=None):
    from deps import iso, now_utc
    rec = {
        "id": str(uuid.uuid4()), "user_id": user_id, "type": "send", "status": "pending",
        "asset": "USDC", "amount": 10.0, "counterparty": counterparty, "recipient_name": "Ajadi Jackson",
        "created_at": iso(now_utc()), "test_marker": "TEST_flutterwave",
        "remit": {"destination_country_code": country, "destination_currency": currency,
                  "destination_amount": amount, "source_currency": "GBP", "source_amount": 10.0,
                  "destination_country": country},
    }
    if bank:
        rec["recipient_bank"] = bank
    return rec


async def _run():
    import payouts
    from deps import db
    cfg = await payouts.get_settings()
    assert cfg["provider"] == "flutterwave", cfg
    user = await db.users.find_one({"email": "smoketest@vaulted.app"}, {"_id": 0, "id": 1})
    recs = [
        _record(user["id"], "NG", "NGN", 1500.0, "0690000031", {"id": "044", "name": "Access Bank"}),
        _record(user["id"], "KE", "KES", 150.0, "254712345678"),
    ]
    ids = [r["id"] for r in recs]
    out = {}
    try:
        for r in recs:
            await db.transactions.insert_one(dict(r))
            res = await payouts.dispatch_payout_for_remit(r)
            out[r["remit"]["destination_country_code"]] = res["payout"]
            print("dispatch", r["remit"]["destination_country_code"], res["payout"])
        for c, p in out.items():
            assert p.get("provider") == "flutterwave", (c, p)
            assert p.get("mode") == "live", (c, p)
            assert p.get("sandbox") is True, (c, p)
            assert str(p.get("reference_id", "")).startswith("trf_"), (c, p)
        settled = 0
        for _ in range(6):
            settled += await payouts.reconcile_flutterwave()
            docs = await db.transactions.find({"id": {"$in": ids}}, {"_id": 0, "id": 1, "status": 1, "payout": 1}).to_list(5)
            print("reconcile pass", [(d["id"][-6:], d["status"], d["payout"].get("status")) for d in docs])
            if all(d["status"] == "settled" for d in docs):
                break
            await asyncio.sleep(5)
        docs = await db.transactions.find({"id": {"$in": ids}}, {"_id": 0}).to_list(5)
        return docs
    finally:
        await db.transactions.delete_many({"id": {"$in": ids}})
        left = await db.transactions.count_documents({"id": {"$in": ids}})
        print("cleanup remaining:", left)


def test_dispatch_and_reconcile_flutterwave():
    docs = asyncio.run(_run())
    for d in docs:
        assert d["status"] == "settled", d
        assert d["payout"]["status"] == "SUCCESSFUL", d["payout"]
