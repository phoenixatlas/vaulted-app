"""Iteration 31 helper — direct-DB actions (no emails sent).
Usage: python tests/iter31_helper.py <cmd> <user_id> [args]
  seed_rec_fb <uid>      -> insert a TEST_ recipient + feedback doc for user
  count <uid>            -> count recipients + feedback docs for user
  shot_token <fb_id>     -> print a valid short-lived screenshot token
  seed_ke_momo <uid>     -> seed KE momo recipient (UI chip test)
  cleanup <uid>          -> delete TEST_ recipients + TEST_ feedback for user
"""
import asyncio
import json
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(".env", override=True)

from deps import db  # noqa: E402
from routers.recipients import save_recipient  # noqa: E402


async def main():
    cmd, arg = sys.argv[1], sys.argv[2]
    if cmd == "seed_rec_fb":
        await save_recipient(arg, name="TEST_Del Me", country_code="KE", currency="KES",
                             account="+254700000999", rail="momo")
        await db.feedback.insert_one({"id": str(uuid.uuid4()), "user_id": arg, "note": "TEST_fb", "created_at": "x"})
        print(json.dumps({"ok": True}))
    elif cmd == "count":
        print(json.dumps({"recipients": await db.recipients.count_documents({"user_id": arg}),
                          "feedback": await db.feedback.count_documents({"user_id": arg})}))
    elif cmd == "shot_token":
        from routers.feedback import _shot_token
        print(json.dumps({"t": _shot_token(arg)}))
    elif cmd == "seed_ke_momo":
        await save_recipient(arg, name="TEST_Wanjiru Kamau", country_code="KE", currency="KES",
                             account="+254712345678", rail="momo")
        print(json.dumps(await db.recipients.find({"user_id": arg}, {"_id": 0}).to_list(50)))
    elif cmd == "cleanup":
        r = await db.recipients.delete_many({"user_id": arg, "name": {"$regex": "^TEST_"}})
        f = await db.feedback.delete_many({"user_id": arg, "note": {"$regex": "^TEST_"}})
        print(json.dumps({"deleted": r.deleted_count, "fb_deleted": f.deleted_count}))


asyncio.run(main())
