"""Vaulted investor one-pager PDF builder.

Generates a single-page A4 PDF summarising the reverse-corridor
opportunity: TAM, product model, unit economics, traction, and ask.
Built with reportlab so it renders deterministically on any host without
system-level HTML-to-PDF binaries (WeasyPrint / wkhtmltopdf are
unnecessary here — this doc is text + tables, no chrome-level layout
tricks needed).

Design principles:
  - One physical page. Investors will *not* scroll a PDF.
  - Real numbers pulled live from Mongo (waitlist count, corridor mix).
  - Vaulted brand: warm-black + gold (#C9A35B) on cream (#F5EDDF).
  - Regeneratable at any time — this module has no side effects.

Public entry point:
    async def build_onepager_pdf(db) -> bytes

Callers should stream the returned bytes with:
    Content-Type: application/pdf
    Content-Disposition: attachment; filename="Vaulted-Reverse-Corridor-OnePager.pdf"
"""
from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import Frame, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER

# ---- Brand palette --------------------------------------------------------
GOLD = colors.HexColor("#C9A35B")
GOLD_DEEP = colors.HexColor("#8A6D2E")
GOLD_CREAM = colors.HexColor("#F5EDDF")
INK = colors.HexColor("#0F0B08")
INK_MUTED = colors.HexColor("#4A4238")
INK_SUBTLE = colors.HexColor("#7A7267")
DIVIDER = colors.HexColor("#E5DDC9")
BG_CARD = colors.HexColor("#FBF7EE")


def _styles() -> dict[str, ParagraphStyle]:
    """Small local stylesheet — we don't need reportlab's stock one."""
    return {
        "eyebrow": ParagraphStyle(
            "eyebrow", fontName="Helvetica-Bold", fontSize=7.5,
            textColor=GOLD_DEEP, leading=10, spaceAfter=2, alignment=TA_LEFT,
        ),
        "h1": ParagraphStyle(
            "h1", fontName="Helvetica-Bold", fontSize=17, textColor=INK,
            leading=20, spaceAfter=4, alignment=TA_LEFT,
        ),
        "h2": ParagraphStyle(
            "h2", fontName="Helvetica-Bold", fontSize=9.5, textColor=INK,
            leading=12, spaceBefore=8, spaceAfter=3, alignment=TA_LEFT,
        ),
        "body": ParagraphStyle(
            "body", fontName="Helvetica", fontSize=8.5, textColor=INK_MUTED,
            leading=11.5, spaceAfter=3, alignment=TA_LEFT,
        ),
        "bodyTight": ParagraphStyle(
            "bodyTight", fontName="Helvetica", fontSize=8, textColor=INK_MUTED,
            leading=10.5, spaceAfter=1, alignment=TA_LEFT,
        ),
        "callout": ParagraphStyle(
            "callout", fontName="Helvetica-Bold", fontSize=9,
            textColor=INK, leading=12, spaceAfter=2, alignment=TA_LEFT,
        ),
        "footer": ParagraphStyle(
            "footer", fontName="Helvetica", fontSize=6.5,
            textColor=INK_SUBTLE, leading=9, alignment=TA_LEFT,
        ),
        "sub": ParagraphStyle(
            "sub", fontName="Helvetica-Oblique", fontSize=8.5,
            textColor=INK_SUBTLE, leading=11, spaceAfter=6, alignment=TA_LEFT,
        ),
    }


# ---- Draw the branded header (logo mark + wordmark) ----------------------
def _draw_header(c: rl_canvas.Canvas, width: float, height: float) -> None:
    # Gold accent bar down the left edge — nods to the app's brand
    c.setFillColor(GOLD)
    c.rect(0, 0, 8 * mm, height, fill=1, stroke=0)

    # Logo mark (rounded gold square with "V")
    x, y = 22 * mm, height - 26 * mm
    c.setFillColor(GOLD)
    c.roundRect(x, y, 12 * mm, 12 * mm, 2 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(x + 6 * mm, y + 3.6 * mm, "V")

    # Wordmark
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(x + 16 * mm, y + 5 * mm, "Vaulted")

    # Product-of byline — italic gold, sits directly under the wordmark
    # for visual consistency with the investor deck cover.
    c.setFillColor(GOLD_DEEP)
    c.setFont("Helvetica-Oblique", 7.5)
    c.drawString(x + 16 * mm, y + 1 * mm, "A product of Phoenix-Atlas Technologies Ltd  ·  UK")

    # Top-right stamp
    now = datetime.now(timezone.utc).strftime("%B %Y")
    c.setFillColor(GOLD_DEEP)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawRightString(width - 15 * mm, height - 15 * mm, "INVESTOR ONE-PAGER")
    c.setFillColor(INK_SUBTLE)
    c.setFont("Helvetica", 7)
    c.drawRightString(width - 15 * mm, height - 19 * mm, f"Prepared {now}  ·  Confidential")

    # Divider under header
    c.setStrokeColor(DIVIDER)
    c.setLineWidth(0.5)
    c.line(22 * mm, height - 30 * mm, width - 15 * mm, height - 30 * mm)


def _draw_footer(c: rl_canvas.Canvas, width: float) -> None:
    y = 12 * mm
    c.setStrokeColor(DIVIDER)
    c.setLineWidth(0.5)
    c.line(22 * mm, y + 6 * mm, width - 15 * mm, y + 6 * mm)

    c.setFillColor(INK_SUBTLE)
    c.setFont("Helvetica", 6.5)
    c.drawString(
        22 * mm, y + 2 * mm,
        "Phoenix-Atlas Technologies Ltd (England & Wales, Companies House "
        "16712430). Registered office: 71-75 Shelton Street, London, WC2H 9JQ.",
    )
    c.drawString(
        22 * mm, y - 1 * mm,
        "Illustrative unit economics only. Not an offer to invest or a "
        "financial promotion. Not authorised by the FCA at the time of "
        "this document. See risk disclosure at phoenix-atlas.com/risk.",
    )
    c.setFillColor(GOLD_DEEP)
    c.setFont("Helvetica-Bold", 7)
    c.drawRightString(width - 15 * mm, y + 2 * mm, "phoenix-atlas.com")
    c.setFillColor(INK_SUBTLE)
    c.setFont("Helvetica", 6.5)
    c.drawRightString(width - 15 * mm, y - 1 * mm, "invest@phoenix-atlas.com")

    # Booking CTA — clickable hyperlink over the "book a 20-min call" text.
    # Sits centred above the divider so it's the first thing the eye lands on
    # when the reader finishes scanning the page.
    booking_text = "📅  Book a 20-min call →  calendar.app.google/U1r2UbqrQqQCxQrcA"
    booking_url = "https://calendar.app.google/U1r2UbqrQqQCxQrcA"
    c.setFillColor(GOLD_DEEP)
    c.setFont("Helvetica-Bold", 7.5)
    text_w = c.stringWidth(booking_text, "Helvetica-Bold", 7.5)
    booking_y = y + 9 * mm
    c.drawCentredString(width / 2, booking_y, booking_text)
    c.linkURL(
        booking_url,
        (width / 2 - text_w / 2, booking_y - 1.5 * mm,
         width / 2 + text_w / 2, booking_y + 3 * mm),
        relative=0,
    )


async def _pull_traction(db: Any) -> dict[str, int]:
    """Read live traction metrics from Mongo. Safe defaults on any error
    so the PDF still renders if the DB is transiently unavailable."""
    stats = {"total_waitlist": 0, "inbound_waitlist": 0, "outbound_waitlist": 0}
    try:
        stats["total_waitlist"] = await db.waitlist.count_documents({})
    except Exception:
        pass
    try:
        stats["inbound_waitlist"] = await db.waitlist.count_documents({"direction": "inbound"})
    except Exception:
        pass
    try:
        stats["outbound_waitlist"] = await db.waitlist.count_documents(
            {"$or": [{"direction": "outbound"}, {"direction": {"$exists": False}}]}
        )
    except Exception:
        pass
    return stats


def _unit_econ_table() -> Table:
    """Per-£1,000 reverse corridor unit economics."""
    data = [
        ["Line item", "Africa → UK", "Notes"],
        ["Sender pays (equiv. GBP)", "£1,000.00", "Local fiat (NGN/KES/GHS/ZAR) via on-ramp"],
        ["On-ramp fee (Kotani/partner)", "£17.50",  "≈ 1.75% of principal (blended)"],
        ["FX spread (mid + ~1.0%)",    "£10.00",  "Vaulted keeps 40 bps net of provider"],
        ["Vaulted service fee",        "£17.50",  "1.75% (min £2, cap £14.99)"],
        ["USDC bridge cost",           "£0.55",   "Gas on Polygon (< 5s)"],
        ["UK Faster Payments payout",  "£0.20",   "Interchange-flat via PSP (Phase 2)"],
        ["Total sender cost",          "£45.75",  "≈ 4.58% all-in vs 7–12% bank wire"],
        ["Recipient receives",         "£954.25", "Same-day GBP into UK bank"],
        ["Vaulted gross revenue",      "£21.50",  "FX spread capture + service fee"],
        ["Variable cost (rails)",      "£0.75",   "USDC gas + FPS interchange"],
        ["Contribution margin",        "£20.75",  "96.5% CM  ·  ~2.1% of GMV"],
    ]
    tbl = Table(data, colWidths=[57 * mm, 26 * mm, 92 * mm])
    tbl.setStyle(TableStyle([
        # Header row
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("TEXTCOLOR", (0, 0), (-1, 0), GOLD_CREAM),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
        ("TOPPADDING", (0, 0), (-1, 0), 5),

        # Body
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 7.7),
        ("TEXTCOLOR", (0, 1), (-1, -1), INK_MUTED),
        ("TEXTCOLOR", (0, 1), (0, -1), INK),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 3),
        ("TOPPADDING", (0, 1), (-1, -1), 3),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),

        # Alternating row shading
        ("BACKGROUND", (0, 1), (-1, 1), BG_CARD),
        ("BACKGROUND", (0, 3), (-1, 3), BG_CARD),
        ("BACKGROUND", (0, 5), (-1, 5), BG_CARD),
        ("BACKGROUND", (0, 7), (-1, 7), BG_CARD),
        ("BACKGROUND", (0, 9), (-1, 9), BG_CARD),
        ("BACKGROUND", (0, 11), (-1, 11), BG_CARD),

        # Emphasize totals
        ("FONTNAME", (0, 7), (-1, 7), "Helvetica-Bold"),
        ("FONTNAME", (0, 8), (-1, 8), "Helvetica-Bold"),
        ("FONTNAME", (0, 11), (-1, 11), "Helvetica-Bold"),
        ("TEXTCOLOR", (1, 11), (1, 11), GOLD_DEEP),
        ("LINEABOVE", (0, 7), (-1, 7), 0.5, DIVIDER),
        ("LINEABOVE", (0, 11), (-1, 11), 0.5, DIVIDER),
        ("BOX", (0, 0), (-1, -1), 0.5, DIVIDER),
    ]))
    return tbl


def _traction_table(t: dict[str, int]) -> Table:
    total = max(t.get("total_waitlist", 0), 1)
    outbound = t.get("outbound_waitlist", 0)
    inbound = t.get("inbound_waitlist", 0)
    outbound_pct = f"{(outbound / total * 100):.0f}%" if total else "—"
    inbound_pct = f"{(inbound / total * 100):.0f}%" if total else "—"

    data = [
        ["Metric", "Value", "Detail"],
        ["Total waitlist", f"{t.get('total_waitlist', 0):,}",
         "Verified emails via Resend Audiences"],
        ["Outbound (UK/EU → Africa)", f"{outbound:,}  ({outbound_pct})",
         "Kenya · Ghana · Tanzania · Zambia · Nigeria · Uganda · South Africa"],
        ["Inbound (Africa → UK/EU)", f"{inbound:,}  ({inbound_pct})",
         "Launched Phase 1 — quote-only + waitlist"],
        ["Live sandbox corridors", "🇰🇪 · 🇿🇦", "Kotani Pay v3 on-ramp — real live rates today"],
        ["Enabling shortly",       "🇳🇬 · 🇬🇭", "Kotani permission gate pending (weeks)"],
    ]
    tbl = Table(data, colWidths=[45 * mm, 40 * mm, 90 * mm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("TEXTCOLOR", (0, 0), (-1, 0), GOLD_CREAM),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
        ("TOPPADDING", (0, 0), (-1, 0), 5),

        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 7.7),
        ("TEXTCOLOR", (0, 1), (-1, -1), INK_MUTED),
        ("TEXTCOLOR", (0, 1), (0, -1), INK),
        ("TEXTCOLOR", (1, 1), (1, -1), GOLD_DEEP),
        ("FONTNAME", (1, 1), (1, -1), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 3),
        ("TOPPADDING", (0, 1), (-1, -1), 3),

        ("BACKGROUND", (0, 1), (-1, 1), BG_CARD),
        ("BACKGROUND", (0, 3), (-1, 3), BG_CARD),
        ("BACKGROUND", (0, 5), (-1, 5), BG_CARD),
        ("BOX", (0, 0), (-1, -1), 0.5, DIVIDER),
    ]))
    return tbl


async def build_onepager_pdf(db: Any) -> bytes:
    """Render the investor one-pager to a bytes buffer. Single A4 page."""
    S = _styles()
    traction = await _pull_traction(db)

    buf = BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=A4)
    c.setTitle("Vaulted — Reverse-Corridor Investor One-Pager")
    c.setAuthor("Phoenix-Atlas Technologies Ltd")
    c.setSubject("Bi-directional cross-border remittance — Africa ↔ UK/EU")

    width, height = A4
    _draw_header(c, width, height)
    _draw_footer(c, width)

    # Content frame (below header, above footer)
    frame = Frame(
        22 * mm, 22 * mm,                       # x, y
        width - 22 * mm - 15 * mm,             # width
        height - 30 * mm - 22 * mm,            # height
        leftPadding=0, rightPadding=0,
        topPadding=8, bottomPadding=0,
        showBoundary=0,
    )

    total = traction.get("total_waitlist", 0)
    inbound = traction.get("inbound_waitlist", 0)

    story = [
        Paragraph("BI-DIRECTIONAL REMITTANCE · REVERSE CORRIDOR", S["eyebrow"]),
        Paragraph(
            "Africa &rarr; UK/EU: the missing half of the diaspora corridor.",
            S["h1"],
        ),
        Paragraph(
            "Families in Lagos pay UK tuition. Parents in Nairobi cover London medical treatment. "
            "Businesses in Accra pay Irish suppliers. Bank wires cost 7-12% and take 3-5 days. "
            "Vaulted uses regulated stablecoin rails to compress that to ~2 minutes at ~4.6% all-in.",
            S["sub"],
        ),

        Paragraph("MARKET OPPORTUNITY", S["h2"]),
        Paragraph(
            "&bull; UK inbound flow from Nigeria alone: ~<b>$1.2B/yr</b> in medical tourism, "
            "$580M in university-fee remittance (LSE / UCAS surveys, 2024).",
            S["body"],
        ),
        Paragraph(
            "&bull; Africa &rarr; UK/EU corridor grew <b>18% YoY</b> 2022-2025 (World Bank Remittance "
            "Data). Wise + banks capture the bulk; neobank penetration &lt; 6%.",
            S["body"],
        ),
        Paragraph(
            "&bull; Regulatory tailwind: Nigeria&rsquo;s dollar-scarcity makes SWIFT unreliable; "
            "stablecoins already carry $9B+ in monthly African remittance volume (Chainalysis).",
            S["body"],
        ),

        Paragraph("PRODUCT MODEL", S["h2"]),
        Paragraph(
            "Sender in NG/KE/GH/ZA funds with mobile money or bank transfer &rarr; Kotani Pay on-ramp "
            "&rarr; USDC on Polygon (bridge) &rarr; UK/EU PSP payout &rarr; recipient bank via Faster "
            "Payments or SEPA Instant. Crypto rails in the middle, fiat on both ends — sender never "
            "touches crypto. Fully compliant KYC/AML at both entry and exit.",
            S["body"],
        ),

        Paragraph("UNIT ECONOMICS · £1,000 SEND", S["h2"]),
        _unit_econ_table(),
        Spacer(1, 6),

        Paragraph("TRACTION (live snapshot)", S["h2"]),
        _traction_table(traction),
        Spacer(1, 6),

        Paragraph("ASK · PARTNERSHIP", S["h2"]),
        Paragraph(
            "Vaulted is raising a <b>£1.5M pre-seed</b> to complete FCA authorisation and integrate a "
            "UK Payment Service Provider (Modulr / ClearBank / Stripe Treasury) for the Phase 2 GBP "
            "payout rail. For African payment banks specifically: white-label integration is available "
            "as an alternative to equity — Vaulted supplies the UK payout leg and compliance, you "
            "supply the on-ramp and local KYC. Revenue share: 50/50 of the take-rate.",
            S["body"],
        ),
        Paragraph(
            f"Sign the mutual NDA and we&rsquo;ll open the data room within 24 hours — "
            f"including a live sandbox demo with real Kotani onramp rates. "
            f"Currently at <b>{total}</b> confirmed waitlist emails "
            f"(<b>{inbound}</b> on the inbound side, unprompted).",
            S["callout"],
        ),
    ]

    frame.addFromList(story, c)
    c.showPage()
    c.save()
    return buf.getvalue()
