"""International Bill Payments — education, healthcare and business
invoices paid from Africa (NGN/KES/GHS/ZAR) to institutions abroad
(GBP/EUR/USD/CAD).

Flow: config → quote → upload invoice → submit → admin review →
approve (test-mode payout via the selected partner) or reject.
Beta: test mode only — no real money moves.
"""
import uuid
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

import storage
from bill_providers import CATEGORIES, PAYER_COUNTRIES, PAYOUT_CURRENCIES, PROVIDERS, select_provider
from deps import db, get_current_user, iso, logger, now_utc, require_admin
from remit import convert_fiat, refresh_fx_rates

router = APIRouter()
MAX_INVOICE_BYTES = 10 * 1024 * 1024
INVOICE_TYPES = {"application/pdf": "pdf", "image/jpeg": "jpg", "image/png": "png"}
_MAGIC = {"pdf": (b"%PDF",), "jpg": (b"\xff\xd8\xff",), "png": (b"\x89PNG",)}
MIN_USD, MAX_USD = 20.0, 50000.0


class QuoteIn(BaseModel):
    category: str
    payer_country: str
    payout_currency: str
    amount: float = Field(gt=0)  # in payout currency (what the institution receives)


class Payee(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    bank_name: str = Field(min_length=2, max_length=120)
    account_number: str = Field(min_length=4, max_length=40)  # IBAN or account number
    routing: Optional[str] = Field(default="", max_length=40)  # sort code / ABA / transit
    swift: Optional[str] = Field(default="", max_length=11)
    address: Optional[str] = Field(default="", max_length=240)
    reference: str = Field(min_length=1, max_length=80)


class BillIn(QuoteIn):
    subtype: str
    beneficiary_name: str = Field(min_length=2, max_length=120)
    beneficiary_ref: str = Field(min_length=1, max_length=80)
    institution: str = Field(min_length=2, max_length=160)
    payee: Payee
    invoice_path: str
    invoice_name: Optional[str] = ""
    quote_id: str
    declaration: bool
    save_institution: bool = False


class DecisionIn(BaseModel):
    approve: bool
    note: Optional[str] = Field(default="", max_length=500)


async def _quote(body: QuoteIn) -> dict:
    if body.category not in CATEGORIES:
        raise HTTPException(400, "Choose Education, Healthcare or Business.")
    if body.payer_country not in PAYER_COUNTRIES:
        raise HTTPException(400, "Paying country not supported yet.")
    if body.payout_currency not in PAYOUT_CURRENCIES:
        raise HTTPException(400, "Payout currency not supported yet.")
    rates = (await refresh_fx_rates(db)).get("rates") or {}
    payer_cur = PAYER_COUNTRIES[body.payer_country]["currency"]
    amount_usd = convert_fiat(body.amount, body.payout_currency, "USD", rates)
    if not MIN_USD <= amount_usd <= MAX_USD:
        raise HTTPException(400, f"Amount must be between ${MIN_USD:,.0f} and ${MAX_USD:,.0f} equivalent.")
    p = select_provider(body.payer_country, body.payout_currency, body.category, amount_usd)
    if not p:
        raise HTTPException(400, "No partner supports this route yet.")
    mid = convert_fiat(1, body.payout_currency, payer_cur, rates)  # payer per 1 payout unit
    rate = mid * (1 + p["fx_margin"])
    principal = body.amount * rate
    fee_usd = amount_usd * p["fee_pct"] + p["fee_fixed_usd"]
    fee_payer = convert_fiat(fee_usd, "USD", payer_cur, rates)
    return {
        "category": body.category, "payer_country": body.payer_country, "payer_currency": payer_cur,
        "payout_currency": body.payout_currency, "payout_amount": round(body.amount, 2),
        "mid_market_rate": round(mid, 4), "rate": round(rate, 4), "fx_margin_pct": p["fx_margin"] * 100,
        "principal": round(principal, 2), "fee": round(fee_payer, 2), "total": round(principal + fee_payer, 2),
        "amount_usd": round(amount_usd, 2),
        "provider": {"id": p["id"], "label": p["label"], "mode": p["mode"], "settlement": p["settlement"]},
        "rail": PAYOUT_CURRENCIES[body.payout_currency]["rail"],
        "expires_at": iso(now_utc() + timedelta(minutes=15)), "test_mode": True,
    }


def _event(label: str, status: str) -> dict:
    return {"at": iso(now_utc()), "label": label, "status": status}


@router.get("/bills/config")
async def bills_config():
    return {
        "categories": [{"id": k, "label": v["label"], "tagline": v["tagline"], "subtypes": v["subtypes"],
                        "fields": [{"key": a, "label": b} for a, b in v["fields"]]} for k, v in CATEGORIES.items()],
        "payer_countries": [{"code": k, **v} for k, v in PAYER_COUNTRIES.items()],
        "payout_currencies": [{"code": k, **v} for k, v in PAYOUT_CURRENCIES.items()],
        "providers": [{"id": p["id"], "label": p["label"], "mode": p["mode"]} for p in PROVIDERS],
        "test_mode": True,
    }


@router.post("/bills/quote")
async def bills_quote(body: QuoteIn, user=Depends(get_current_user)):
    quote = await _quote(body)
    quote["id"] = str(uuid.uuid4())
    await db.bill_quotes.insert_one({"id": quote["id"], "user_id": user["id"], "quote": dict(quote),
                                     "expires_at": quote["expires_at"]})
    return quote


@router.post("/bills/invoice")
async def upload_invoice(file: UploadFile = File(...), user=Depends(get_current_user)):
    data = await file.read(MAX_INVOICE_BYTES + 1)
    ctype = (file.content_type or "").lower()
    if ctype not in INVOICE_TYPES:
        raise HTTPException(400, "Upload a PDF, JPG or PNG invoice.")
    if not data or len(data) > MAX_INVOICE_BYTES:
        raise HTTPException(400, "Invoice must be under 10 MB.")
    ext = INVOICE_TYPES[ctype]
    if not data.startswith(_MAGIC[ext]):
        raise HTTPException(400, "That file doesn't look like a valid PDF, JPG or PNG.")
    path = f"bills/{user['id']}/{uuid.uuid4().hex}.{ext}"
    res = await storage.put_object(path, data, ctype)
    full = res.get("path", path)
    await db.bill_invoices.insert_one({"path": full, "user_id": user["id"], "created_at": iso(now_utc())})
    return {"invoice_path": full, "invoice_name": file.filename or "invoice"}


@router.post("/bills")
async def create_bill(body: BillIn, user=Depends(get_current_user)):
    if not body.declaration:
        raise HTTPException(400, "Please confirm the payment is for the stated purpose.")
    if body.subtype not in CATEGORIES.get(body.category, {}).get("subtypes", []):
        raise HTTPException(400, "Choose what the payment is for.")
    if not await db.bill_invoices.find_one({"path": body.invoice_path, "user_id": user["id"]}):
        raise HTTPException(400, "Upload the supporting invoice first.")
    saved = await db.bill_quotes.find_one({"id": body.quote_id, "user_id": user["id"]}, {"_id": 0})
    if not saved or saved["expires_at"] < iso(now_utc()):
        raise HTTPException(400, "Your quote has expired — please get a new FX quote.")
    quote = saved["quote"]
    if (quote["category"], quote["payer_country"], quote["payout_currency"], quote["payout_amount"]) != \
            (body.category, body.payer_country, body.payout_currency, round(body.amount, 2)):
        raise HTTPException(400, "Details changed since your quote — please get a new FX quote.")
    bill = {
        "id": str(uuid.uuid4()), "user_id": user["id"], "user_email": user.get("email"),
        "reference": "IBP-" + uuid.uuid4().hex[:8].upper(),
        "category": body.category, "subtype": body.subtype,
        "beneficiary_name": body.beneficiary_name.strip(), "beneficiary_ref": body.beneficiary_ref.strip(),
        "institution": body.institution.strip(), "payee": body.payee.model_dump(),
        "invoice_path": body.invoice_path, "invoice_name": body.invoice_name,
        "quote": quote, "status": "under_review", "test_mode": True, "created_at": iso(now_utc()),
        "timeline": [_event("Request submitted with invoice", "submitted"),
                     _event("Compliance review of invoice and purpose", "under_review")],
    }
    await db.bill_payments.insert_one(dict(bill))
    if body.save_institution:
        await _save_institution(user["id"], body)
    return bill


# ---- Saved institutions ------------------------------------------------------
SAVED_FIELDS = {"_id": 0, "user_id": 0, "institution_key": 0}


async def _save_institution(user_id: str, body: BillIn) -> None:
    """Upsert by institution + account so re-saving refreshes, not duplicates."""
    payee = body.payee.model_dump()
    payee["reference"] = ""  # each invoice carries its own reference
    key = {"user_id": user_id, "institution_key": body.institution.strip().lower(),
           "account_number": payee["account_number"].strip()}
    await db.bill_saved_institutions.update_one(key, {
        "$set": {"category": body.category, "subtype": body.subtype, "institution": body.institution.strip(),
                 "beneficiary_name": body.beneficiary_name.strip(), "beneficiary_ref": body.beneficiary_ref.strip(),
                 "payer_country": body.payer_country, "payout_currency": body.payout_currency,
                 "payee": payee, "updated_at": iso(now_utc())},
        "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": iso(now_utc())}}, upsert=True)


@router.get("/bills/saved")
async def saved_institutions(user=Depends(get_current_user)):
    rows = await db.bill_saved_institutions.find({"user_id": user["id"]}, SAVED_FIELDS).sort("updated_at", -1).to_list(50)
    return {"saved": rows}


@router.delete("/bills/saved/{saved_id}")
async def delete_saved_institution(saved_id: str, user=Depends(get_current_user)):
    res = await db.bill_saved_institutions.delete_one({"id": saved_id, "user_id": user["id"]})
    if not res.deleted_count:
        raise HTTPException(404, "Saved institution not found")
    return {"ok": True}


@router.get("/bills")
async def my_bills(user=Depends(get_current_user)):
    rows = await db.bill_payments.find({"user_id": user["id"]}, {"_id": 0, "invoice_path": 0}).sort("created_at", -1).to_list(100)
    return {"bills": rows}


@router.get("/bills/{bill_id}")
async def get_bill(bill_id: str, user=Depends(get_current_user)):
    doc = await db.bill_payments.find_one({"id": bill_id, "user_id": user["id"]}, {"_id": 0, "invoice_path": 0})
    if not doc:
        raise HTTPException(404, "Bill payment not found")
    return doc


# ---- Admin review ------------------------------------------------------------
@router.get("/admin/bills")
async def admin_bills(_admin=Depends(require_admin)):
    rows = await db.bill_payments.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"bills": rows, "pending": sum(1 for r in rows if r["status"] == "under_review")}


@router.get("/admin/bills/{bill_id}/invoice")
async def admin_bill_invoice(bill_id: str, _admin=Depends(require_admin)):
    doc = await db.bill_payments.find_one({"id": bill_id}, {"_id": 0, "invoice_path": 1})
    if not doc:
        raise HTTPException(404, "Not found")
    try:
        data, ctype = await storage.get_object(doc["invoice_path"])
    except Exception as e:  # noqa: BLE001
        logger.warning("[bills] invoice fetch failed for %s: %s", bill_id, e)
        raise HTTPException(404, "Invoice file not found")
    return Response(content=data, media_type=ctype, headers={"Cache-Control": "no-store"})


@router.post("/admin/bills/{bill_id}/decision")
async def admin_bill_decision(bill_id: str, body: DecisionIn, admin=Depends(require_admin)):
    doc = await db.bill_payments.find_one({"id": bill_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Not found")
    if doc["status"] != "under_review":
        raise HTTPException(400, f"Already {doc['status']}.")
    prov = doc["quote"]["provider"]["label"]
    if body.approve:
        events = [_event("Approved by compliance", "approved"),
                  _event(f"Sent via {prov} (test mode — no real money)", "processing"),
                  _event(f"Paid to {doc['payee']['name']} (simulated)", "paid")]
        status = "paid"
    else:
        events = [_event("Rejected: " + (body.note or "documentation could not be verified"), "rejected")]
        status = "rejected"
    await db.bill_payments.update_one({"id": bill_id}, {
        "$set": {"status": status, "decided_by": admin.get("email"), "decided_at": iso(now_utc()), "decision_note": body.note},
        "$push": {"timeline": {"$each": events}}})
    logger.info("[bills] %s %s by %s", bill_id, status, admin.get("email"))
    return {"id": bill_id, "status": status}
