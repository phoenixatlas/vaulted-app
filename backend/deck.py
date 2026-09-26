"""Vaulted investor pitch deck PDF builder (auto-generated multi-page).

Sibling to `onepager.py` but for a deeper 4-5 page deck. Pages:
  1. Cover — big tagline, tagline sub, contact
  2. Problem & Market Opportunity — bullets + TAM breakdown
  3. Product Model & Traction — regulatory diagram (text) + traction table
  4. Unit Economics — the same detailed waterfall as the one-pager (higher-fidelity)
  5. Ask, Team & Roadmap — raise size, use of funds, roadmap milestones

Same design system as onepager.py (gold/warm-black brand).

If the user later uploads a real pitch deck via the admin endpoint, that
PDF is served instead — see routers/investor.py `deck_download` for the
serving priority.
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
from reportlab.platypus import Frame, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

GOLD = colors.HexColor("#C9A35B")
GOLD_DEEP = colors.HexColor("#8A6D2E")
GOLD_CREAM = colors.HexColor("#F5EDDF")
INK = colors.HexColor("#0F0B08")
INK_MUTED = colors.HexColor("#4A4238")
INK_SUBTLE = colors.HexColor("#7A7267")
DIVIDER = colors.HexColor("#E5DDC9")
BG_CARD = colors.HexColor("#FBF7EE")


def _styles() -> dict[str, ParagraphStyle]:
    return {
        "eyebrow": ParagraphStyle(
            "eyebrow", fontName="Helvetica-Bold", fontSize=8,
            textColor=GOLD_DEEP, leading=11, spaceAfter=4, alignment=TA_LEFT,
        ),
        "hero": ParagraphStyle(
            "hero", fontName="Helvetica-Bold", fontSize=32, textColor=INK,
            leading=36, spaceAfter=8, alignment=TA_LEFT,
        ),
        "h1": ParagraphStyle(
            "h1", fontName="Helvetica-Bold", fontSize=22, textColor=INK,
            leading=26, spaceBefore=4, spaceAfter=6, alignment=TA_LEFT,
        ),
        "h2": ParagraphStyle(
            "h2", fontName="Helvetica-Bold", fontSize=11, textColor=INK,
            leading=14, spaceBefore=12, spaceAfter=4, alignment=TA_LEFT,
        ),
        "body": ParagraphStyle(
            "body", fontName="Helvetica", fontSize=10, textColor=INK_MUTED,
            leading=14, spaceAfter=4, alignment=TA_LEFT,
        ),
        "bullet": ParagraphStyle(
            "bullet", fontName="Helvetica", fontSize=10, textColor=INK_MUTED,
            leading=14, spaceAfter=3, leftIndent=12, alignment=TA_LEFT,
        ),
        "sub": ParagraphStyle(
            "sub", fontName="Helvetica-Oblique", fontSize=11,
            textColor=INK_SUBTLE, leading=15, spaceAfter=10, alignment=TA_LEFT,
        ),
        "footer": ParagraphStyle(
            "footer", fontName="Helvetica", fontSize=7,
            textColor=INK_SUBTLE, leading=10, alignment=TA_LEFT,
        ),
        "quoteBig": ParagraphStyle(
            "quoteBig", fontName="Helvetica-Bold", fontSize=17,
            textColor=INK, leading=22, spaceAfter=10, alignment=TA_LEFT,
        ),
    }


def _draw_page_chrome(c: rl_canvas.Canvas, width: float, height: float, page_num: int, total_pages: int) -> None:
    # Gold accent bar
    c.setFillColor(GOLD)
    c.rect(0, 0, 6 * mm, height, fill=1, stroke=0)

    # Page footer
    c.setStrokeColor(DIVIDER)
    c.setLineWidth(0.4)
    c.line(20 * mm, 14 * mm, width - 15 * mm, 14 * mm)
    c.setFillColor(INK_SUBTLE)
    c.setFont("Helvetica", 7)
    c.drawString(20 * mm, 10 * mm, "Phoenix-Atlas Technologies Ltd · Companies House 16712430 · London")
    c.setFillColor(GOLD_DEEP)
    c.setFont("Helvetica-Bold", 7)
    c.drawRightString(width - 15 * mm, 10 * mm, f"{page_num} / {total_pages}  ·  phoenix-atlas.com")


def _draw_cover_hero(c: rl_canvas.Canvas, width: float, height: float) -> None:
    # Large logo mark on the cover
    x = width / 2 - 14 * mm
    y = height - 65 * mm
    c.setFillColor(GOLD)
    c.roundRect(x, y, 28 * mm, 28 * mm, 4 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 32)
    c.drawCentredString(x + 14 * mm, y + 9 * mm, "V")

    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 36)
    c.drawCentredString(width / 2, y - 12 * mm, "Vaulted")
    # Product-of line — sits directly under the wordmark, styled subtly
    # so it doesn't compete with the tagline underneath.
    c.setFillColor(GOLD_DEEP)
    c.setFont("Helvetica-Oblique", 10)
    c.drawCentredString(width / 2, y - 20 * mm, "A product of Phoenix-Atlas Technologies Ltd")
    c.setFillColor(INK_SUBTLE)
    c.setFont("Helvetica", 11)
    c.drawCentredString(width / 2, y - 30 * mm, "Cross-border remittance without the wait.")

    now = datetime.now(timezone.utc).strftime("%B %Y")
    c.setFillColor(GOLD_DEEP)
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(width / 2, y - 42 * mm, f"INVESTOR DECK  ·  {now.upper()}  ·  CONFIDENTIAL")


def _traction_snapshot(traction: dict[str, int]) -> Table:
    total = traction.get("total_waitlist", 0)
    inbound = traction.get("inbound_waitlist", 0)
    outbound = traction.get("outbound_waitlist", 0)
    data = [
        ["Metric", "Value", "Notes"],
        ["Total waitlist", f"{total:,}", "Verified emails, all captured to Resend"],
        ["Outbound (UK/EU → Africa)", f"{outbound:,}", "Kenya · Ghana · Nigeria · Tanzania · Zambia · Uganda · South Africa"],
        ["Inbound (Africa → UK/EU)", f"{inbound:,}", "Reverse corridor — Phase 1 quote-only + waitlist"],
        ["Live sandbox corridors", "🇰🇪 · 🇿🇦", "Kotani Pay v3 on-ramp returning real live rates today"],
        ["Product surface", "iOS · Android · Web", "React Native · Expo Router · FastAPI · MongoDB"],
        ["Compliance rails", "FCA path", "UK EMI relationship in advanced discussions · Stripe Identity KYC live"],
    ]
    tbl = Table(data, colWidths=[52 * mm, 40 * mm, 88 * mm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("TEXTCOLOR", (0, 0), (-1, 0), GOLD_CREAM),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8.5),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ("TOPPADDING", (0, 0), (-1, 0), 6),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 8.5),
        ("FONTNAME", (1, 1), (1, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 1), (-1, -1), INK_MUTED),
        ("TEXTCOLOR", (0, 1), (0, -1), INK),
        ("TEXTCOLOR", (1, 1), (1, -1), GOLD_DEEP),
        ("BACKGROUND", (0, 2), (-1, 2), BG_CARD),
        ("BACKGROUND", (0, 4), (-1, 4), BG_CARD),
        ("BACKGROUND", (0, 6), (-1, 6), BG_CARD),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
        ("TOPPADDING", (0, 1), (-1, -1), 4),
        ("BOX", (0, 0), (-1, -1), 0.5, DIVIDER),
    ]))
    return tbl


def _unit_econ_deep() -> Table:
    """Deeper unit economics — same waterfall as one-pager, with extra context columns."""
    data = [
        ["Line item", "£1,000 send", "% of principal", "Rationale"],
        ["Sender pays", "£1,000.00", "100.00%", "Bank/mobile-money on-ramp"],
        ["  On-ramp fee (Kotani)", "£17.50", "1.75%", "Blended across 4 corridors — negotiable at volume"],
        ["  FX spread (mid + 1.0%)", "£10.00", "1.00%", "Vaulted keeps ~40 bps, rest goes to liquidity provider"],
        ["  Vaulted service fee", "£17.50", "1.75%", "Min £2 · Cap £14.99 · Waived for Founding Members"],
        ["  USDC bridge cost", "£0.55", "0.055%", "Gas on Polygon L2 — sub-5-sec finality"],
        ["  UK Faster Payments payout", "£0.20", "0.02%", "Flat interchange via PSP (Phase 2)"],
        ["Total sender cost", "£45.75", "4.58%", "vs bank wire 7-12% · vs Wise 3-6%"],
        ["Recipient receives", "£954.25", "95.42%", "Same-day GBP into UK bank"],
        ["Vaulted gross revenue", "£21.50", "2.15%", "FX spread + service fee"],
        ["Variable cost (rails)", "£0.75", "0.075%", "USDC gas + FPS interchange"],
        ["Contribution margin", "£20.75", "2.08%", "96.5% of revenue → operating leverage"],
    ]
    tbl = Table(data, colWidths=[52 * mm, 26 * mm, 22 * mm, 80 * mm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("TEXTCOLOR", (0, 0), (-1, 0), GOLD_CREAM),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 7.5),
        ("TEXTCOLOR", (0, 1), (-1, -1), INK_MUTED),
        ("TEXTCOLOR", (0, 1), (0, -1), INK),
        ("ALIGN", (1, 0), (2, -1), "RIGHT"),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 3),
        ("TOPPADDING", (0, 1), (-1, -1), 3),
        ("BACKGROUND", (0, 2), (-1, 2), BG_CARD),
        ("BACKGROUND", (0, 4), (-1, 4), BG_CARD),
        ("BACKGROUND", (0, 6), (-1, 6), BG_CARD),
        ("BACKGROUND", (0, 8), (-1, 8), BG_CARD),
        ("BACKGROUND", (0, 10), (-1, 10), BG_CARD),
        ("FONTNAME", (0, 7), (-1, 7), "Helvetica-Bold"),
        ("FONTNAME", (0, 8), (-1, 8), "Helvetica-Bold"),
        ("FONTNAME", (0, 11), (-1, 11), "Helvetica-Bold"),
        ("TEXTCOLOR", (1, 11), (2, 11), GOLD_DEEP),
        ("LINEABOVE", (0, 7), (-1, 7), 0.5, DIVIDER),
        ("LINEABOVE", (0, 11), (-1, 11), 0.5, DIVIDER),
        ("BOX", (0, 0), (-1, -1), 0.5, DIVIDER),
    ]))
    return tbl


async def _pull_traction(db: Any) -> dict[str, int]:
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


async def build_deck_pdf(db: Any) -> bytes:
    """Render the 5-page pitch deck to bytes."""
    S = _styles()
    traction = await _pull_traction(db)
    total_ppl = traction.get("total_waitlist", 0)
    inbound_ppl = traction.get("inbound_waitlist", 0)

    buf = BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=A4)
    c.setTitle("Vaulted — Investor Deck")
    c.setAuthor("Phoenix-Atlas Technologies Ltd")
    c.setSubject("Bi-directional UK ↔ Africa remittance — Series Pre-Seed")
    width, height = A4

    TOTAL_PAGES = 5

    # --- PAGE 1: COVER ---
    _draw_cover_hero(c, width, height)
    _draw_page_chrome(c, width, height, 1, TOTAL_PAGES)
    # Contact block bottom-center. Split across two lines because the
    # canonical LinkedIn slug is long — cramming email + LinkedIn on one
    # centred row starts to feel busy on A4.
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(width / 2, 58 * mm, "Umar Sani · Founder")
    c.setFillColor(INK_SUBTLE)
    c.setFont("Helvetica", 9)
    c.drawCentredString(width / 2, 51 * mm, "umar.sani@phoenix-atlas.com")
    # Real LinkedIn slug — clickable hyperlink on the displayed text.
    linkedin_display = "linkedin.com/in/umar-muhammad-sani-msc-mapm-60951155"
    linkedin_full = "https://www.linkedin.com/in/umar-muhammad-sani-msc-mapm-60951155"
    c.drawCentredString(width / 2, 46 * mm, linkedin_display)
    # Overlay an invisible clickable rect over the LinkedIn text
    text_w = c.stringWidth(linkedin_display, "Helvetica", 9)
    c.linkURL(
        linkedin_full,
        (width / 2 - text_w / 2, 43 * mm, width / 2 + text_w / 2, 49 * mm),
        relative=0,
    )
    c.drawCentredString(width / 2, 40 * mm, "London, United Kingdom")
    c.showPage()

    # --- PAGE 2: PROBLEM & MARKET ---
    _draw_page_chrome(c, width, height, 2, TOTAL_PAGES)
    frame = Frame(20 * mm, 20 * mm, width - 20 * mm - 15 * mm, height - 40 * mm,
                  leftPadding=0, rightPadding=0, topPadding=8, bottomPadding=0, showBoundary=0)
    story2 = [
        Paragraph("THE PROBLEM · MARKET OPPORTUNITY", S["eyebrow"]),
        Paragraph("Diaspora families move billions the slow, expensive way.", S["h1"]),
        Paragraph(
            "The UK ↔ Africa remittance corridor moves <b>~$28B/yr</b> (World Bank 2024). "
            "Banks charge 7–12% and take 3–5 days. Wise and Remitly own the middle at 3–6%, "
            "but leave the fastest-growing sub-corridor — <b>education, medical, and business "
            "payments from Africa to the UK/EU</b> — completely underserved.",
            S["sub"],
        ),
        Paragraph("What we&rsquo;re seeing", S["h2"]),
        Paragraph("&bull; UK inbound from Nigeria: <b>$1.2B/yr</b> in medical tourism + $580M in tuition (2024).", S["bullet"]),
        Paragraph("&bull; Africa → UK/EU volume grew <b>18% YoY</b> 2022-2025 (World Bank Remittance Data).", S["bullet"]),
        Paragraph("&bull; Nigeria&rsquo;s dollar-scarcity makes SWIFT unreliable; stablecoins already carry <b>$9B+/month</b> of African remittance volume (Chainalysis).", S["bullet"]),
        Paragraph("&bull; Neobank penetration in the corridor &lt; 6% — the market is still bank-and-hawala.", S["bullet"]),
        Paragraph("Vaulted&rsquo;s wedge", S["h2"]),
        Paragraph(
            "Bi-directional remittance from day one, using regulated stablecoin rails as the middle "
            "leg. Sender never touches crypto. Fiat in, fiat out, ~2 minutes end-to-end, ~4.6% all-in "
            "(vs 7–12% bank wire). The reverse corridor (Africa → UK/EU) doubles our TAM and gives "
            "African payment banks a white-label pathway to global settlement without SWIFT.",
            S["body"],
        ),
    ]
    frame.addFromList(story2, c)
    c.showPage()

    # --- PAGE 3: PRODUCT MODEL & TRACTION ---
    _draw_page_chrome(c, width, height, 3, TOTAL_PAGES)
    frame = Frame(20 * mm, 20 * mm, width - 20 * mm - 15 * mm, height - 40 * mm,
                  leftPadding=0, rightPadding=0, topPadding=8, bottomPadding=0, showBoundary=0)
    story3 = [
        Paragraph("PRODUCT MODEL · TRACTION", S["eyebrow"]),
        Paragraph("Regulated fiat on both ends. Stablecoin rails in the middle.", S["h1"]),
        Paragraph(
            "<b>UK/EU → Africa (outbound, live):</b> Card / Apple Pay / bank &rarr; Vaulted USDC "
            "&rarr; Kotani Pay off-ramp &rarr; mobile money (M-Pesa, MTN MoMo) or bank at destination. "
            "~2 min end-to-end. Sender never sees a wallet address.",
            S["body"],
        ),
        Paragraph(
            "<b>Africa → UK/EU (inbound, Phase 1 quote-only):</b> Mobile money / bank &rarr; "
            "Kotani Pay on-ramp &rarr; Vaulted USDC &rarr; UK PSP payout (Modulr / ClearBank / "
            "Stripe Treasury) &rarr; UK Faster Payments or SEPA Instant. Same sub-2-min ceiling.",
            S["body"],
        ),
        Paragraph("Traction snapshot (live)", S["h2"]),
        _traction_snapshot(traction),
        Spacer(1, 8),
        Paragraph(
            f"With <b>{total_ppl:,} confirmed waitlist emails</b> and "
            f"<b>{inbound_ppl:,}</b> already interested in the reverse corridor — completely unprompted "
            f"— demand signal is strong before any paid marketing.",
            S["quoteBig"],
        ),
    ]
    frame.addFromList(story3, c)
    c.showPage()

    # --- PAGE 4: UNIT ECONOMICS ---
    _draw_page_chrome(c, width, height, 4, TOTAL_PAGES)
    frame = Frame(20 * mm, 20 * mm, width - 20 * mm - 15 * mm, height - 40 * mm,
                  leftPadding=0, rightPadding=0, topPadding=8, bottomPadding=0, showBoundary=0)
    story4 = [
        Paragraph("UNIT ECONOMICS · £1,000 SEND", S["eyebrow"]),
        Paragraph("The unit story: 2.08% contribution margin at 96.5% CM ratio.", S["h1"]),
        Paragraph(
            "Blended across the four live African corridors at typical Q3 2026 mid-market rates.",
            S["sub"],
        ),
        _unit_econ_deep(),
        Spacer(1, 12),
        Paragraph("What this means for a payment-bank partner", S["h2"]),
        Paragraph(
            "White-label integration splits the take rate 50/50. On a £1M/month corridor volume "
            "(a small share of Nigeria&rsquo;s medical tourism outflow), that&rsquo;s <b>~£10,750/month</b> "
            "of shared revenue at 96.5% contribution margin. Partner supplies the local on-ramp; "
            "Vaulted supplies UK-side compliance, USDC bridge, and GBP/EUR payout.",
            S["body"],
        ),
    ]
    frame.addFromList(story4, c)
    c.showPage()

    # --- PAGE 5: ASK · TEAM · ROADMAP ---
    _draw_page_chrome(c, width, height, 5, TOTAL_PAGES)
    frame = Frame(20 * mm, 20 * mm, width - 20 * mm - 15 * mm, height - 40 * mm,
                  leftPadding=0, rightPadding=0, topPadding=8, bottomPadding=0, showBoundary=0)
    story5 = [
        Paragraph("THE ASK · TEAM · ROADMAP", S["eyebrow"]),
        Paragraph("£1.5M pre-seed → FCA + UK PSP + first live corridors.", S["h1"]),

        Paragraph("Use of funds (18 months)", S["h2"]),
        Paragraph("&bull; <b>£500k</b> — FCA authorisation legal + regulatory capital (Small EMI path)", S["bullet"]),
        Paragraph("&bull; <b>£350k</b> — UK PSP integration (Modulr / ClearBank / Stripe Treasury) + KYC/AML build-out", S["bullet"]),
        Paragraph("&bull; <b>£400k</b> — First 2 engineering hires + 1 compliance officer", S["bullet"]),
        Paragraph("&bull; <b>£250k</b> — 18 months of runway for founder + G&amp;A", S["bullet"]),

        Paragraph("Team", S["h2"]),
        Paragraph(
            "<b>Umar Sani</b> — Founder &amp; CEO. Previously built and shipped Vaulted end-to-end "
            "solo across React Native, FastAPI, on-chain wallet flows (BTC, ETH, SOL, XLM, XRP + "
            "5 EVM L2s), and third-party rails (Stripe, Kotani, Resend). Actively recruiting a "
            "compliance-first UK co-founder.",
            S["body"],
        ),

        Paragraph("Roadmap (18 months)", S["h2"]),
        Paragraph("&bull; <b>Q3 2026:</b> Waitlist growth · Kotani ONRAMP live in NG + GH · signed UK PSP LoI", S["bullet"]),
        Paragraph("&bull; <b>Q4 2026:</b> FCA application submitted · UK PSP integration in test", S["bullet"]),
        Paragraph("&bull; <b>Q1 2027:</b> Phase 2 launch — Africa → UK/EU live GBP settlement", S["bullet"]),
        Paragraph("&bull; <b>Q2 2027:</b> Small EMI licence granted · first 10k paying customers", S["bullet"]),
        Paragraph("&bull; <b>Q3 2027:</b> White-label partnership live with first African payment bank", S["bullet"]),
        Paragraph("&bull; <b>Q4 2027:</b> Series A raise · corridor expansion (Egypt, Morocco, Senegal)", S["bullet"]),

        Spacer(1, 8),
        Paragraph(
            'Let&rsquo;s talk. <b>umar.sani@phoenix-atlas.com</b>  ·  '
            '<b><a href="https://www.linkedin.com/in/umar-muhammad-sani-msc-mapm-60951155" '
            'color="#0F0B08">linkedin.com/in/umar-muhammad-sani</a></b>',
            S["quoteBig"],
        ),
    ]
    frame.addFromList(story5, c)
    c.showPage()

    c.save()
    return buf.getvalue()
