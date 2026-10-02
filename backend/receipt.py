"""Branded PDF receipt generator for settled Kotani Pay offramps.

Produces a one-page A4 PDF the user receives by email the moment their
crypto → M-Pesa payout settles. Mirrors the letterhead / deck / one-pager
visual language so it reads as a cohesive Vaulted / Phoenix-Atlas artefact,
not a generic receipt.

Key design calls:
  * Stateless — accepts a plain dict rather than reading Mongo so the
    offramp webhook handler can call it directly with whatever payload
    came off the wire.
  * Zero-raise — bad / missing fields fall back to "—" so a weird Kotani
    payload still produces a readable (if partial) receipt rather than
    a 500 that breaks the webhook.
  * ReportLab-only — no external template engine, no file-system temp
    writes; everything lives in memory and comes back as bytes.
"""
from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from typing import Any, Optional

from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors


# ---- Brand palette (mirrors letterhead.py / deck.py / onepager.py) --------
GOLD = colors.HexColor("#C9A35B")
GOLD_DEEP = colors.HexColor("#8A6D2E")
GOLD_SOFT = colors.HexColor("#F5E9C9")
INK = colors.HexColor("#0F0B08")
INK_SUBTLE = colors.HexColor("#7A7267")
DIVIDER = colors.HexColor("#E5DDC9")
BG_SOFT = colors.HexColor("#FBF6EB")
OK_GREEN = colors.HexColor("#1E7B46")


def _fmt_amount(value: Any, currency: str) -> str:
    """Format a numeric amount with sensible fallbacks.

    Crypto balances get up to 6 dp (USDC/USDT are 6-dp assets); fiat gets
    locale-ish thousand separators + 2 dp. Non-numeric / None → "—"."""
    if value is None or value == "":
        return "—"
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)
    cur = (currency or "").upper()
    is_crypto = cur in {"USDC", "USDT", "DAI", "ETH", "BTC", "SOL", "XLM"}
    if is_crypto:
        # Trim trailing zeros but keep at least 2 decimals for readability.
        return f"{num:,.6f}".rstrip("0").rstrip(".") or "0"
    return f"{num:,.2f}"


def _fmt_ts(iso: Any) -> str:
    """Render an ISO timestamp as `02 Oct 2026, 15:34 UTC`."""
    if not iso:
        return "—"
    try:
        if isinstance(iso, datetime):
            dt = iso
        else:
            dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.strftime("%d %b %Y, %H:%M UTC")
    except Exception:
        return str(iso)


def build_offramp_receipt_pdf(tx: dict, user: Optional[dict] = None) -> bytes:
    """Render a settled-offramp receipt as A4 PDF bytes.

    Expected tx shape (dict — all fields optional with graceful fallback):

        {
          "id": "vlt_tx_abc...",
          "amount_crypto": 38.5,
          "token": "USDC",
          "amount_fiat": 5000,
          "fiat_currency": "KES",
          "rate": 142.35,
          "corridor": "KE",
          "created_at": "2026-10-02T15:30:00Z",
          "kotani": {
             "reference_id": "kp_...",
             "mpesa_receipt": "QHS8K2L9MR",
             "settled_at": "2026-10-02T15:34:12Z",
             "fiat_transaction_amount": 4850,
             "transaction_hash": "0xdef...",
             "status": "SUCCESSFUL"
          }
        }

    The user block only contributes a name/email line — if omitted,
    the receipt reads as issued to the wallet address.
    """
    k = tx.get("kotani") or {}
    corridor = (tx.get("corridor") or "—").upper()
    ref_id = k.get("reference_id") or tx.get("id") or "—"
    mpesa = k.get("mpesa_receipt") or "—"
    chain_tx = k.get("transaction_hash") or tx.get("tx_hash") or "—"
    status = (k.get("status") or tx.get("status") or "SETTLED").upper()
    rate = tx.get("rate") or tx.get("exchange_rate")
    fiat_cur = tx.get("fiat_currency") or k.get("fiat_currency") or "—"
    token = tx.get("token") or "USDC"
    sent_fiat = k.get("fiat_transaction_amount") or tx.get("amount_fiat")
    sent_crypto = tx.get("amount_crypto") or tx.get("crypto_amount")

    buf = BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"Vaulted — Payout Receipt {ref_id}")
    c.setAuthor("Phoenix-Atlas Technologies Ltd")
    c.setSubject("Crypto → Mobile Money Payout Receipt")

    width, height = A4

    # ================= HEADER =================
    y_top = height - 22 * mm

    # Logo chip
    c.setFillColor(GOLD)
    c.roundRect(20 * mm, y_top - 4 * mm, 14 * mm, 14 * mm, 2.5 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 15)
    c.drawCentredString(27 * mm, y_top, "V")

    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(38 * mm, y_top + 1 * mm, "Vaulted")
    c.setFillColor(INK_SUBTLE)
    c.setFont("Helvetica-Oblique", 8.5)
    c.drawString(38 * mm, y_top - 4 * mm, "A product of Phoenix-Atlas Technologies Ltd")

    # Right: document type + issue date
    c.setFillColor(GOLD_DEEP)
    c.setFont("Helvetica-Bold", 11)
    c.drawRightString(width - 20 * mm, y_top + 1 * mm, "PAYOUT RECEIPT")
    c.setFillColor(INK_SUBTLE)
    c.setFont("Helvetica", 8.5)
    c.drawRightString(width - 20 * mm, y_top - 4 * mm,
                      f"Issued {datetime.now(timezone.utc).strftime('%d %b %Y, %H:%M UTC')}")

    # Gold hairline
    c.setStrokeColor(GOLD)
    c.setLineWidth(0.8)
    c.line(20 * mm, y_top - 14 * mm, width - 20 * mm, y_top - 14 * mm)
    c.setStrokeColor(DIVIDER)
    c.setLineWidth(0.4)
    c.line(20 * mm, y_top - 15.5 * mm, width - 20 * mm, y_top - 15.5 * mm)

    # ================= HERO: STATUS + AMOUNTS =================
    y = y_top - 30 * mm

    # Status pill
    c.setFillColor(OK_GREEN)
    c.roundRect(20 * mm, y, 32 * mm, 7 * mm, 3.5 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 8.5)
    c.drawCentredString(36 * mm, y + 2 * mm, "✓  SETTLED" if status in {"SUCCESSFUL", "SUCCESS", "SETTLED"} else status)

    y -= 10 * mm
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 22)
    c.drawString(20 * mm, y, f"{_fmt_amount(sent_fiat, fiat_cur)} {fiat_cur}")
    c.setFillColor(INK_SUBTLE)
    c.setFont("Helvetica", 10)
    c.drawString(20 * mm, y - 5 * mm, f"delivered to recipient — M-Pesa code {mpesa}")

    # ================= DETAILS CARD =================
    y -= 18 * mm
    card_y = y
    card_h = 90 * mm
    c.setFillColor(BG_SOFT)
    c.setStrokeColor(DIVIDER)
    c.setLineWidth(0.5)
    c.roundRect(20 * mm, card_y - card_h, width - 40 * mm, card_h, 3 * mm, fill=1, stroke=1)

    # Card header strip
    c.setFillColor(GOLD_SOFT)
    c.rect(20 * mm, card_y - 10 * mm, width - 40 * mm, 10 * mm, fill=1, stroke=0)
    c.setFillColor(GOLD_DEEP)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(24 * mm, card_y - 7 * mm, "TRANSACTION DETAILS")

    # Rows (label-right, value-left pairs)
    rows = [
        ("Sent (crypto)", f"{_fmt_amount(sent_crypto, token)} {token}"),
        ("Received (fiat)", f"{_fmt_amount(sent_fiat, fiat_cur)} {fiat_cur}"),
        ("Exchange rate", f"1 {token} = {_fmt_amount(rate, fiat_cur)} {fiat_cur}" if rate else "—"),
        ("Corridor", corridor),
        ("Mobile money reference", mpesa),
        ("Kotani reference ID", ref_id),
        ("On-chain hash", (chain_tx[:14] + "…" + chain_tx[-6:]) if chain_tx != "—" and len(chain_tx) > 24 else chain_tx),
        ("Initiated at", _fmt_ts(tx.get("created_at"))),
        ("Settled at", _fmt_ts(k.get("settled_at"))),
    ]
    row_y = card_y - 16 * mm
    row_h = 7.5 * mm
    for i, (label, value) in enumerate(rows):
        if i % 2 == 1:
            c.setFillColor(colors.white)
            c.rect(22 * mm, row_y - row_h + 2 * mm, width - 44 * mm, row_h,
                   fill=1, stroke=0)
        c.setFillColor(INK_SUBTLE)
        c.setFont("Helvetica", 9)
        c.drawString(24 * mm, row_y, label)
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 9.5)
        c.drawRightString(width - 24 * mm, row_y, str(value))
        row_y -= row_h

    # ================= RECIPIENT ATTRIBUTION =================
    y = card_y - card_h - 10 * mm
    c.setFillColor(INK_SUBTLE)
    c.setFont("Helvetica", 8.5)
    recipient_line = "Issued to"
    if user:
        name = user.get("name") or user.get("full_name") or ""
        email = user.get("email") or ""
        if name and email:
            recipient_line = f"Issued to {name} ({email})"
        elif email:
            recipient_line = f"Issued to {email}"
    c.drawString(20 * mm, y, recipient_line)

    # ================= DISCLAIMER =================
    y -= 8 * mm
    c.setFillColor(INK_SUBTLE)
    c.setFont("Helvetica-Oblique", 7.5)
    disclaimer_lines = [
        "This receipt confirms a settled crypto → mobile-money payout on the Kotani Pay rails.",
        "Keep it with your records for compliance / tax purposes. The M-Pesa reference is",
        "independently verifiable with Safaricom; the on-chain hash is auditable on-chain.",
        "If you spot anything that looks wrong, reply to this email within 24h.",
    ]
    for line in disclaimer_lines:
        c.drawString(20 * mm, y, line)
        y -= 4 * mm

    # ================= FOOTER =================
    yf = 14 * mm
    c.setStrokeColor(GOLD)
    c.setLineWidth(0.8)
    c.line(20 * mm, yf + 10 * mm, width - 20 * mm, yf + 10 * mm)
    c.setStrokeColor(DIVIDER)
    c.setLineWidth(0.4)
    c.line(20 * mm, yf + 8.5 * mm, width - 20 * mm, yf + 8.5 * mm)

    c.setFillColor(INK_SUBTLE)
    c.setFont("Helvetica", 7)
    c.drawString(20 * mm, yf + 4 * mm,
                 "Phoenix-Atlas Technologies Ltd  ·  Companies House 16712430  ·  Registered in England & Wales")
    c.drawString(20 * mm, yf + 1 * mm,
                 "Registered office: 71-75 Shelton Street, London, WC2H 9JQ.")

    c.setFillColor(GOLD_DEEP)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawRightString(width - 20 * mm, yf + 4 * mm, "phoenix-atlas.com")
    c.setFillColor(INK_SUBTLE)
    c.setFont("Helvetica", 7)
    c.drawRightString(width - 20 * mm, yf + 1 * mm, "umar.sani@phoenix-atlas.com")

    c.save()
    return buf.getvalue()


# ============================================================================
# Email HTML — matches the dark gold-on-ink aesthetic of password reset
# ============================================================================
def offramp_receipt_email_html(tx: dict, user: Optional[dict] = None) -> str:
    """Build the HTML body for the settlement receipt email. The PDF is
    attached separately in `send_offramp_receipt_email`."""
    k = tx.get("kotani") or {}
    sent_fiat = k.get("fiat_transaction_amount") or tx.get("amount_fiat")
    fiat_cur = tx.get("fiat_currency") or k.get("fiat_currency") or ""
    mpesa = k.get("mpesa_receipt") or "—"
    rate = tx.get("rate")
    token = tx.get("token") or "USDC"
    sent_crypto = tx.get("amount_crypto") or tx.get("crypto_amount")
    corridor = (tx.get("corridor") or "").upper()

    name = ((user or {}).get("name") or (user or {}).get("full_name") or "").strip().split(" ")[0] or "there"

    return f"""
    <div style="font-family:-apple-system,Helvetica,Arial,sans-serif;max-width:560px;margin:auto;padding:36px 28px;background:#0F0B08;color:#F5E9C9;border-radius:14px">
      <div style="font-size:24px;font-weight:700;color:#C9A35B;letter-spacing:-0.4px;margin-bottom:4px">Vaulted</div>
      <div style="font-size:11px;color:#B8AFA1;letter-spacing:2px;text-transform:uppercase;margin-bottom:28px">Payout settled ✓</div>

      <div style="font-size:16px;color:#F5E9C9;margin-bottom:16px">Hi {name},</div>
      <p style="font-size:14px;color:#F5E9C9;line-height:22px;margin:0 0 24px">
        Your {token} → {fiat_cur or 'mobile money'} payout just settled on the Kotani Pay rails. The recipient has already received the funds via M-Pesa.
      </p>

      <div style="background:#1C1612;border:1px solid #2a2320;border-radius:12px;padding:20px 22px;margin:0 0 24px">
        <div style="font-size:11px;color:#B8AFA1;letter-spacing:1.5px;text-transform:uppercase;margin-bottom:6px">Amount delivered</div>
        <div style="font-size:28px;font-weight:700;color:#E6C879;letter-spacing:-0.5px">{_fmt_amount(sent_fiat, fiat_cur)} {fiat_cur}</div>
        <div style="font-size:12px;color:#B8AFA1;margin-top:6px">from {_fmt_amount(sent_crypto, token)} {token}{f' · corridor {corridor}' if corridor else ''}</div>
      </div>

      <table style="width:100%;font-size:13px;border-collapse:collapse;margin:0 0 24px">
        <tr><td style="padding:6px 0;color:#B8AFA1">M-Pesa code</td><td style="padding:6px 0;text-align:right;color:#F5E9C9;font-weight:600">{mpesa}</td></tr>
        <tr><td style="padding:6px 0;color:#B8AFA1">Exchange rate</td><td style="padding:6px 0;text-align:right;color:#F5E9C9">1 {token} = {_fmt_amount(rate, fiat_cur)} {fiat_cur}</td></tr>
        <tr><td style="padding:6px 0;color:#B8AFA1">Settled at</td><td style="padding:6px 0;text-align:right;color:#F5E9C9">{_fmt_ts(k.get('settled_at'))}</td></tr>
      </table>

      <p style="font-size:13px;color:#B8AFA1;line-height:20px;margin:0 0 20px">
        The attached PDF is your official receipt — keep it for your records. The M-Pesa reference is independently verifiable with Safaricom; the on-chain hash is auditable on-chain.
      </p>
      <p style="font-size:12px;color:#6d7a73;line-height:18px;margin:28px 0 0">
        Spot anything off? Just reply to this email within 24h.
      </p>
      <div style="border-top:1px solid #2a2320;margin:28px 0 16px"></div>
      <p style="font-size:11px;color:#6d7a73;margin:0">Vaulted · Phoenix-Atlas Technologies Ltd · Companies House 16712430 · UK</p>
    </div>
    """
