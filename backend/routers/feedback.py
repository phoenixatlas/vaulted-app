"""Beta tester feedback — note + optional screenshot.

POST /feedback          (auth, multipart) → stored in db.feedback, screenshot
                        in object storage, emailed to every ADMIN_EMAILS address.
GET  /admin/feedback    (admin) → latest 50 reports.
GET  /admin/feedback/{id}/screenshot?t=… — `t` is a 30-min token scoped to
                        that one screenshot (issued by the list call), so the
                        web admin page can show images in <img> tags without
                        putting the admin's login token in a URL.
"""
from __future__ import annotations

import html
import uuid
from datetime import timedelta
from typing import Optional

import jwt
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

import storage
from deps import ADMIN_EMAILS, JWT_ALG, JWT_SECRET, db, get_current_user, iso, logger, now_utc, require_admin
from emails import send_email_via_resend, send_email_via_resend_with_attachment

router = APIRouter()

MAX_SCREENSHOT_BYTES = 5 * 1024 * 1024


@router.post("/feedback")
async def submit_feedback(
    note: str = Form(..., min_length=1, max_length=4000),
    screen: str = Form(default="", max_length=200),
    platform: str = Form(default="", max_length=40),
    app_version: str = Form(default="", max_length=40),
    screenshot: Optional[UploadFile] = File(default=None),
    background: BackgroundTasks = None,
    user=Depends(get_current_user),
):
    fb_id = str(uuid.uuid4())
    shot_path = None
    shot_bytes = b""
    if screenshot is not None:
        shot_bytes = await screenshot.read()
        if len(shot_bytes) > MAX_SCREENSHOT_BYTES:
            raise HTTPException(status_code=413, detail="Screenshot too large (max 5 MB)")
        if shot_bytes:
            ctype = screenshot.content_type or "image/png"
            ext = "jpg" if "jpeg" in ctype or "jpg" in ctype else "png"
            try:
                res = await storage.put_object(f"feedback/{user['id']}/{fb_id}.{ext}", shot_bytes, ctype)
                shot_path = res.get("path")
            except Exception as e:  # noqa: BLE001 — keep the note even if upload fails
                logger.warning("[feedback] screenshot upload failed: %s", e)

    doc = {
        "id": fb_id, "user_id": user["id"], "email": user.get("email"), "name": user.get("name"),
        "note": note.strip(), "screen": screen, "platform": platform, "app_version": app_version,
        "screenshot_path": shot_path, "created_at": iso(now_utc()),
    }
    await db.feedback.insert_one(dict(doc))

    subject = f"Vaulted beta feedback · {screen or 'app'} · {user.get('email')}"
    body = (
        f"<p><b>{html.escape(user.get('name') or '')}</b> ({html.escape(user.get('email') or '')})</p>"
        f"<p>{html.escape(note).replace(chr(10), '<br>')}</p>"
        f"<p style='color:#888'>Screen: {html.escape(screen)} · {html.escape(platform)} · v{html.escape(app_version)}</p>"
    )
    text = f"{user.get('email')}\n\n{note}\n\nScreen: {screen} · {platform} · v{app_version}"
    mime = (screenshot.content_type if screenshot is not None else None) or "image/png"
    # Email in the background so the tester's "Send" returns immediately.
    background.add_task(_notify_admins, subject, body, text, shot_bytes, mime, fb_id)
    return {"ok": True, "id": fb_id, "screenshot_saved": bool(shot_path)}


async def _notify_admins(subject: str, body: str, text: str, shot: bytes, mime: str, fb_id: str) -> None:
    ext = "jpg" if "jpeg" in mime or "jpg" in mime else "png"
    for to in ADMIN_EMAILS:
        try:
            if shot:
                await send_email_via_resend_with_attachment(
                    to, subject, body, attachment_bytes=shot,
                    attachment_filename=f"screenshot-{fb_id[:8]}.{ext}", attachment_mime=mime,
                )
            else:
                await send_email_via_resend(to, subject, body, text=text)
        except Exception as e:  # noqa: BLE001
            logger.warning("[feedback] admin email to %s failed: %s", to, e)


def _shot_token(fb_id: str) -> str:
    """Short-lived, single-screenshot token so image URLs never carry the
    admin's login token (URLs end up in access logs)."""
    return jwt.encode({"fb": fb_id, "scope": "fb_shot", "exp": now_utc() + timedelta(minutes=30)},
                      JWT_SECRET, algorithm=JWT_ALG)


@router.get("/admin/feedback")
async def admin_list_feedback(_admin=Depends(require_admin)):
    rows = await db.feedback.find({}, {"_id": 0}).sort("created_at", -1).limit(50).to_list(50)
    for r in rows:
        if r.get("screenshot_path"):
            r["shot_token"] = _shot_token(r["id"])
    return {"feedback": rows, "total": await db.feedback.count_documents({})}


@router.get("/admin/feedback/{fb_id}/screenshot")
async def admin_feedback_screenshot(fb_id: str, t: str = ""):
    try:
        claims = jwt.decode(t, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=401, detail="Invalid or expired link") from e
    if claims.get("scope") != "fb_shot" or claims.get("fb") != fb_id:
        raise HTTPException(status_code=403, detail="Link not valid for this screenshot")
    doc = await db.feedback.find_one({"id": fb_id}, {"screenshot_path": 1})
    if not doc or not doc.get("screenshot_path"):
        raise HTTPException(status_code=404, detail="No screenshot")
    data, ctype = await storage.get_object(doc["screenshot_path"])
    return Response(content=data, media_type=ctype, headers={"Cache-Control": "private, max-age=1800"})
