"""Chat routes: contacts, conversations, messages, in-chat crypto sends,
groups. All 6 endpoints share the `db.conversations` / `db.messages` /
`db.contacts` collections.

Extracted from server.py during the P2 refactor.

Note: `/chat/send_crypto` delegates the actual ETH broadcast to
`_broadcast_eth_send` (lives in server.py under wallet code, to be extracted
in a future session). We lazy-import that helper at call-time to avoid a
circular server <-> chat import cycle.
"""
from __future__ import annotations

import hashlib
import uuid

from eth_account import Account
from fastapi import APIRouter, Depends, HTTPException

from deps import MULTISIG_THRESHOLD_ETH, db, get_current_user, is_user_pro, iso, logger, now_utc
from models import CreateGroupIn, SendChatCryptoIn, SendMessageIn
from push import send_push

router = APIRouter()


@router.get("/chat/contacts")
async def contacts(user=Depends(get_current_user)):
    cur = db.contacts.find({"user_id": user["id"]}, {"_id": 0}).sort("name", 1)
    return await cur.to_list(200)


@router.get("/chat/conversations")
async def conversations(user=Depends(get_current_user)):
    is_pro = is_user_pro(user)
    cur = db.conversations.find({"user_id": user["id"]}, {"_id": 0}).sort("last_message_at", -1)
    items = await cur.to_list(200)
    if is_pro:
        # Pin priority conversations (Vault Support) to the top while preserving
        # last_message_at ordering within each group (Python sort is stable).
        items.sort(key=lambda c: 0 if c.get("priority") else 1)
    return items


@router.get("/chat/messages/{conversation_id}")
async def get_messages(conversation_id: str, user=Depends(get_current_user)):
    conv = await db.conversations.find_one({"id": conversation_id, "user_id": user["id"]}, {"_id": 0})
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    # Mark read
    await db.conversations.update_one({"id": conversation_id}, {"$set": {"unread": 0}})
    cur = db.messages.find({"conversation_id": conversation_id}, {"_id": 0}).sort("created_at", 1)
    msgs = await cur.to_list(1000)
    return {"conversation": conv, "messages": msgs}


@router.post("/chat/messages")
async def send_message(body: SendMessageIn, user=Depends(get_current_user)):
    conv = await db.conversations.find_one({"id": body.conversation_id, "user_id": user["id"]}, {"_id": 0})
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    msg = {
        "id": str(uuid.uuid4()),
        "conversation_id": body.conversation_id,
        "user_id": user["id"],
        "sender": "me",
        "text": body.text,
        "nonce": body.nonce,
        "encrypted": bool(body.encrypted),
        "created_at": iso(now_utc()),
    }
    await db.messages.insert_one(msg)
    preview = "\U0001f512 Encrypted message" if body.encrypted else body.text
    await db.conversations.update_one(
        {"id": body.conversation_id},
        {"$set": {"last_message": preview, "last_message_at": msg["created_at"], "unread": 0}},
    )
    # Auto echo response from contact (server-generated, always plaintext system message)
    auto = {
        "id": str(uuid.uuid4()),
        "conversation_id": body.conversation_id,
        "user_id": user["id"],
        "sender": "contact",
        "text": "Got it \u2014 secure message received.",
        "nonce": None,
        "encrypted": False,
        "created_at": iso(now_utc()),
    }
    await db.messages.insert_one(auto)
    await db.conversations.update_one(
        {"id": body.conversation_id},
        {"$set": {"last_message": auto["text"], "last_message_at": auto["created_at"]}},
    )
    msg.pop("_id", None)
    # Push the encrypted-message notification to the other party
    try:
        if conv.get("is_group"):
            recipients = [m.get("contact_id") for m in (conv.get("members") or []) if m.get("contact_id")]
            title = f"\U0001f4ac New message in {conv.get('group_name') or 'group'}"
        else:
            cid = conv.get("contact_id")
            recipients = [cid] if cid else []
            title = f"\U0001f4ac {user.get('name') or 'A friend'} sent you a message"
        if recipients:
            await send_push(
                recipients=recipients,
                data={
                    "title": title,
                    "message": "\U0001f512 Encrypted message \u00b7 tap to read",
                    "action_url": f"/chat/{body.conversation_id}",
                },
                idempotency_key=f"chat-msg-{msg['id']}",
            )
    except Exception as e:  # noqa: BLE001
        logger.warning("push chat-msg failed: %s", e)
    return msg


async def _get_or_create_contact_eth_address(contact_id: str) -> str:
    """Lazily derive a deterministic Sepolia address for a seeded contact.
    Stored once on the contact doc so subsequent sends are idempotent."""
    c = await db.contacts.find_one({"id": contact_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Contact not found")
    addr = c.get("eth_address")
    if addr and addr.startswith("0x") and len(addr) == 42:
        return addr
    # derive deterministically from email so the same contact always maps to the same address
    seed = hashlib.sha256(f"vaulted-contact::{c.get('email','')}".encode()).digest()
    acct = Account.from_key(seed)
    addr = acct.address
    await db.contacts.update_one({"id": contact_id}, {"$set": {"eth_address": addr}})
    return addr


@router.post("/chat/send_crypto")
async def chat_send_crypto(body: SendChatCryptoIn, user=Depends(get_current_user)):
    """Send ETH inside a chat and post a tx_card receipt.

    For 1-on-1 chats the recipient is the conversation's contact. For groups,
    `to_contact_id` MUST identify a member of the group. UX guard caps
    in-chat sends below MULTISIG_THRESHOLD_ETH to avoid email-approval gating.
    """
    if body.amount_eth >= MULTISIG_THRESHOLD_ETH:
        raise HTTPException(
            status_code=400,
            detail=f"In-chat sends are capped under {MULTISIG_THRESHOLD_ETH} ETH. Use the Send screen for larger amounts.",
        )
    conv = await db.conversations.find_one(
        {"id": body.conversation_id, "user_id": user["id"]}, {"_id": 0}
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    is_group = bool(conv.get("is_group"))
    if is_group:
        if not body.to_contact_id:
            raise HTTPException(status_code=400, detail="Pick a recipient from the group")
        members = conv.get("members") or []
        if not any(m.get("contact_id") == body.to_contact_id for m in members):
            raise HTTPException(status_code=400, detail="Recipient is not in this group")
        contact_id = body.to_contact_id
    else:
        contact_id = conv.get("contact_id")
        if not contact_id:
            raise HTTPException(status_code=400, detail="Conversation has no recipient")

    pk = user.get("eth_private_key")
    addr = user.get("wallet_address")
    if not pk or not addr:
        raise HTTPException(status_code=400, detail="No ETH key on file")

    to_addr = await _get_or_create_contact_eth_address(contact_id)
    # Lazy import to avoid circular: server.py imports this router at
    # module load, and this router would otherwise need to import
    # _broadcast_eth_send from server at load time.
    from server import _broadcast_eth_send  # noqa: PLC0415
    result = await _broadcast_eth_send(user, addr, pk, to_addr, body.amount_eth)
    tx_hash = result.get("tx_hash")
    explorer = result.get("explorer_url")

    # Find recipient display name for the tx_card label
    recipient_name = None
    if is_group:
        recipient_name = next(
            (m.get("name") for m in (conv.get("members") or []) if m.get("contact_id") == contact_id),
            None,
        )
    else:
        recipient_name = conv.get("contact_name")

    msg = {
        "id": str(uuid.uuid4()),
        "conversation_id": body.conversation_id,
        "user_id": user["id"],
        "sender": "me",
        "kind": "tx_card",
        "text": f"Sent {body.amount_eth} ETH" + (f" to {recipient_name}" if recipient_name else ""),
        "tx_hash": tx_hash,
        "explorer_url": explorer,
        "amount_eth": body.amount_eth,
        "asset": "ETH",
        "to_address": to_addr,
        "to_contact_id": contact_id,
        "to_name": recipient_name,
        "tx_status": result.get("status", "pending"),
        "encrypted": False,
        "created_at": iso(now_utc()),
    }
    await db.messages.insert_one(msg)

    preview = f"\U0001f4b8 Sent {body.amount_eth} ETH" + (f" to {recipient_name}" if recipient_name else "")
    await db.conversations.update_one(
        {"id": body.conversation_id},
        {"$set": {"last_message": preview, "last_message_at": msg["created_at"], "unread": 0}},
    )
    # Auto-ack only for 1-on-1 chats (groups would feel chatty)
    if not is_group:
        ack = {
            "id": str(uuid.uuid4()),
            "conversation_id": body.conversation_id,
            "user_id": user["id"],
            "sender": "contact",
            "kind": "text",
            "text": f"Received {body.amount_eth} ETH \u2014 thank you! \u2728",
            "encrypted": False,
            "created_at": iso(now_utc()),
        }
        await db.messages.insert_one(ack)
        await db.conversations.update_one(
            {"id": body.conversation_id},
            {"$set": {"last_message": ack["text"], "last_message_at": ack["created_at"]}},
        )
    msg.pop("_id", None)
    # Fire-and-forget push to the recipient - never blocks the broadcast
    if contact_id:
        try:
            await send_push(
                recipients=[contact_id],
                data={
                    "title": f"\U0001f4b8 {user.get('name') or 'A friend'} sent you {body.amount_eth} ETH",
                    "message": "Tap to view the transaction in your chat.",
                    "action_url": f"/chat/{body.conversation_id}",
                },
                idempotency_key=f"chat-crypto-{msg['id']}",
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("push send_crypto failed: %s", e)
    return msg


# ---------- Contacts & Groups -------------------------------------------------
@router.post("/chat/groups")
async def create_group(body: CreateGroupIn, user=Depends(get_current_user)):
    """Spin up an encrypted group conversation with the given contact ids."""
    if not body.contact_ids:
        raise HTTPException(status_code=400, detail="Pick at least one member")
    cur = db.contacts.find({"user_id": user["id"], "id": {"$in": body.contact_ids}}, {"_id": 0})
    contacts_docs = await cur.to_list(50)
    if len(contacts_docs) != len(set(body.contact_ids)):
        raise HTTPException(status_code=400, detail="Some contacts not found")
    members = [
        {"contact_id": c["id"], "name": c.get("name"), "avatar": c.get("avatar")}
        for c in contacts_docs
    ]
    conv_id = str(uuid.uuid4())
    conv = {
        "id": conv_id,
        "user_id": user["id"],
        "is_group": True,
        "group_name": body.name.strip(),
        "contact_name": body.name.strip(),  # used by list rows
        "contact_avatar": (contacts_docs[0].get("avatar") if contacts_docs else None),
        "members": members,
        "last_message": f"Group created with {len(members)} member{'s' if len(members)!=1 else ''}.",
        "last_message_at": iso(now_utc()),
        "encrypted": True,
        "priority": False,
        "unread": 0,
    }
    await db.conversations.insert_one(conv)
    # Seed a system message inside the group so it isn't empty.
    sys_msg = {
        "id": str(uuid.uuid4()),
        "conversation_id": conv_id,
        "user_id": user["id"],
        "sender": "contact",
        "kind": "text",
        "text": f"\U0001f512 {body.name.strip()} created. Messages here are end-to-end encrypted.",
        "encrypted": False,
        "created_at": iso(now_utc()),
    }
    await db.messages.insert_one(sys_msg)
    conv.pop("_id", None)
    return conv
