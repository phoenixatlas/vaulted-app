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
    """Slim institutional top brand strip for Slide 1. The previous
    full-page splash cover has been consolidated into a compact header so
    Slide 1 can carry the Macro Arbitrage narrative + data card directly.
    Founder contact + booking CTA now live on Slide 5 next to the Ask."""
    # Logo mark — small gold square, top-left
    y_top = height - 24 * mm
    c.setFillColor(GOLD)
    c.roundRect(20 * mm, y_top - 2 * mm, 12 * mm, 12 * mm, 2 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 13)
    c.drawCentredString(26 * mm, y_top + 1 * mm, "V")

    # Wordmark + product-of line, right of the logo
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(37 * mm, y_top + 2 * mm, "Vaulted")
    c.setFillColor(INK_SUBTLE)
    c.setFont("Helvetica-Oblique", 8.5)
    c.drawString(37 * mm, y_top - 3 * mm, "A product of Phoenix-Atlas Technologies Ltd")

    # Right-aligned deck meta — doc classification + month
    now = datetime.now(timezone.utc).strftime("%B %Y")
    c.setFillColor(GOLD_DEEP)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawRightString(width - 15 * mm, y_top + 2 * mm, "INVESTOR DECK")
    c.setFillColor(INK_SUBTLE)
    c.setFont("Helvetica", 7.5)
    c.drawRightString(width - 15 * mm, y_top - 3 * mm, f"{now.upper()}  ·  CONFIDENTIAL")

    # Hairline divider under the strip
    c.setStrokeColor(DIVIDER)
    c.setLineWidth(0.5)
    c.line(20 * mm, y_top - 8 * mm, width - 15 * mm, y_top - 8 * mm)


def _phase_one_highlight() -> Table:
    """Phase 1 B2B highlight callout — replaces the old waitlist-counts table.
    Positioned on Slide 3 to communicate the current operational posture
    (quote-only, API-first, white-label distribution) without leaning on
    pre-launch vanity metrics."""
    data = [[
        Paragraph(
            "<b>Phase 1 quote-only engine fully operational.</b>  Initial B2B "
            "distribution strategy focused on white-label API integrations "
            "with regional African payment institutions.",
            ParagraphStyle(
                "phaseOneCallout",
                fontName="Helvetica",
                fontSize=10,
                leading=15,
                textColor=INK,
                alignment=TA_LEFT,
            ),
        )
    ]]
    tbl = Table(data, colWidths=[172 * mm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BG_CARD),
        ("BOX", (0, 0), (-1, -1), 0.75, GOLD),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
    ]))
    return tbl


def _proof_points_table() -> Table:
    """Operational proof points for Slide 3 — swaps the old 7-row traction
    table for institutional-grade validation data (integrations, corridor
    reach, tech stack). No pre-launch user counts."""
    surface_style = ParagraphStyle(
        "ppSurface", fontName="Helvetica-Bold", fontSize=8.5, leading=11,
        textColor=INK, alignment=TA_LEFT,
    )
    detail_style = ParagraphStyle(
        "ppDetail", fontName="Helvetica", fontSize=8.5, leading=12,
        textColor=INK_MUTED, alignment=TA_LEFT,
    )
    status_style = ParagraphStyle(
        "ppStatus", fontName="Helvetica-Bold", fontSize=8.5, leading=11,
        textColor=GOLD_DEEP, alignment=TA_LEFT,
    )

    def row(surface: str, status: str, detail: str):
        return [
            Paragraph(surface, surface_style),
            Paragraph(status, status_style),
            Paragraph(detail, detail_style),
        ]

    data = [
        ["Validation surface", "Status", "Operational detail"],
        row(
            "Live infrastructure integrations",
            "Operational",
            "Kotani Pay v3 API on-ramps returning real-time FX and execution liquidity rates",
        ),
        row(
            "Corridor architectural reach",
            "7 corridors",
            "Kenya &middot; Ghana &middot; Nigeria &middot; Tanzania &middot; Zambia &middot; Uganda &middot; South Africa",
        ),
        row(
            "Platform runtime",
            "iOS &middot; Android &middot; Web",
            "React Native &middot; Expo Router &middot; FastAPI &middot; MongoDB",
        ),
        row(
            "Compliance primitives",
            "Live in test",
            "Stripe Identity KYC flows fully live in test environments",
        ),
        row(
            "Settlement layer",
            "Regulated stablecoin",
            "USDC on Polygon L2 &mdash; sub-5-sec finality, auditable on-chain",
        ),
    ]
    tbl = Table(data, colWidths=[48 * mm, 36 * mm, 88 * mm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("TEXTCOLOR", (0, 0), (-1, 0), GOLD_CREAM),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8.5),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ("TOPPADDING", (0, 0), (-1, 0), 6),
        ("BACKGROUND", (0, 2), (-1, 2), BG_CARD),
        ("BACKGROUND", (0, 4), (-1, 4), BG_CARD),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 7),
        ("TOPPADDING", (0, 1), (-1, -1), 7),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 0.5, DIVIDER),
    ]))
    return tbl


def _macro_data_card() -> Table:
    """Slide 1 data card — the four hard numbers institutional LPs use to
    size the opportunity. Framed as a 2x2 grid so it reads at a glance."""
    big = ParagraphStyle(
        "macroBig", fontName="Helvetica-Bold", fontSize=19,
        leading=22, textColor=GOLD_DEEP, alignment=TA_LEFT,
    )
    lbl = ParagraphStyle(
        "macroLbl", fontName="Helvetica", fontSize=8.5,
        leading=12, textColor=INK_MUTED, alignment=TA_LEFT,
    )

    def cell(value: str, label: str):
        return [Paragraph(value, big), Paragraph(label, lbl)]

    data = [
        [
            cell("$1.2B / yr", "UK inbound from Nigeria — medical care only"),
            cell("$580M / yr", "UK inbound from Nigeria — academic tuition"),
        ],
        [
            cell("+18% YoY", "Africa → UK/EU remittance growth, 2022–2025"),
            cell("$9B+ / mo", "African remittance already settling via stablecoins"),
        ],
    ]
    tbl = Table(data, colWidths=[86 * mm, 86 * mm], rowHeights=[26 * mm, 26 * mm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BG_CARD),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOX", (0, 0), (-1, -1), 0.5, DIVIDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, DIVIDER),
    ]))
    return tbl


def _architecture_flow_table() -> Table:
    """Slide 2 architecture diagram — two directional flows rendered as a
    monospace-feeling pipeline so the Web3-under-fiat story reads instantly."""
    arrow_style = ParagraphStyle(
        "flowStep", fontName="Helvetica", fontSize=9.5,
        leading=14, textColor=INK_MUTED, alignment=TA_LEFT,
    )
    header_style = ParagraphStyle(
        "flowHead", fontName="Helvetica-Bold", fontSize=9,
        leading=12, textColor=GOLD_DEEP, alignment=TA_LEFT,
    )
    data = [
        [Paragraph("OUTBOUND  ·  UK/EU → Africa", header_style)],
        [Paragraph(
            "Card / Apple Pay / local bank transfer "
            "<font color='#8A6D2E'>&rarr;</font>  automated conversion to Vaulted USDC "
            "<font color='#8A6D2E'>&rarr;</font>  Kotani Pay off-ramp "
            "<font color='#8A6D2E'>&rarr;</font>  local mobile money (M-Pesa, MTN MoMo, Airtel) or bank payout",
            arrow_style,
        )],
        [Paragraph("INBOUND  ·  Africa → UK/EU  (reverse corridor)", header_style)],
        [Paragraph(
            "Local mobile money / bank "
            "<font color='#8A6D2E'>&rarr;</font>  Kotani Pay on-ramp "
            "<font color='#8A6D2E'>&rarr;</font>  Vaulted USDC "
            "<font color='#8A6D2E'>&rarr;</font>  UK PSP API rails (Modulr / ClearBank / Stripe Treasury) "
            "<font color='#8A6D2E'>&rarr;</font>  real-time UK Faster Payments or SEPA Instant",
            arrow_style,
        )],
    ]
    tbl = Table(data, colWidths=[172 * mm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BG_CARD),
        ("BOX", (0, 0), (-1, -1), 0.5, DIVIDER),
        ("LINEABOVE", (0, 2), (-1, 2), 0.4, DIVIDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
        ("TOPPADDING", (0, 0), (0, 0), 10),
        ("TOPPADDING", (0, 2), (0, 2), 10),
        ("TOPPADDING", (0, 1), (0, 1), 2),
        ("TOPPADDING", (0, 3), (0, 3), 2),
        ("BOTTOMPADDING", (0, 0), (0, 0), 2),
        ("BOTTOMPADDING", (0, 2), (0, 2), 2),
        ("BOTTOMPADDING", (0, 1), (0, 1), 12),
        ("BOTTOMPADDING", (0, 3), (0, 3), 12),
    ]))
    return tbl


def _capital_allocation_table() -> Table:
    """Slide 5 use-of-funds breakdown — four line items that match the
    user's £1.5M allocation with the regulatory + banking + hiring + G&A
    narrative institutional LPs expect to see explicitly broken out."""
    prog_style = ParagraphStyle(
        "capProg", fontName="Helvetica", fontSize=8, leading=11,
        textColor=INK_MUTED, alignment=TA_LEFT,
    )
    alloc_style = ParagraphStyle(
        "capAlloc", fontName="Helvetica-Bold", fontSize=8.2, leading=11,
        textColor=INK, alignment=TA_LEFT,
    )

    def P(text: str, style: ParagraphStyle) -> Paragraph:
        return Paragraph(text, style)

    data = [
        ["Allocation", "Amount", "Programme"],
        [
            P("Regulatory licensing &amp; legal capital reserves", alloc_style),
            "£500k",
            P(
                "UK compliance counsel, FCA submission, Full EMI vs Small EMI "
                "pathway selection, prudential capital reserve",
                prog_style,
            ),
        ],
        [
            P("Tier-1 banking infrastructure integration", alloc_style),
            "£350k",
            P(
                "API links into Modulr / ClearBank clearing; institutional "
                "KYC/AML real-time transaction monitoring",
                prog_style,
            ),
        ],
        [
            P("Strategic engineering &amp; compliance hires", alloc_style),
            "£400k",
            P(
                "Core engineering squad expansion; dedicated UK-based "
                "Head of Compliance",
                prog_style,
            ),
        ],
        [
            P("General &amp; administrative operations", alloc_style),
            "£250k",
            P(
                "Executive runway, technical audits, operational G&amp;A overhead",
                prog_style,
            ),
        ],
        [
            P("<b>Total</b>", alloc_style),
            "£1.5M",
            P(
                "<b>18-month runway through Phase 2 live settlement</b>",
                prog_style,
            ),
        ],
    ]
    tbl = Table(data, colWidths=[58 * mm, 22 * mm, 92 * mm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("TEXTCOLOR", (0, 0), (-1, 0), GOLD_CREAM),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8.5),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ("TOPPADDING", (0, 0), (-1, 0), 6),
        ("FONTNAME", (1, 1), (1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (1, 1), (1, -1), 9),
        ("TEXTCOLOR", (1, 1), (1, -1), GOLD_DEEP),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("BACKGROUND", (0, 2), (-1, 2), BG_CARD),
        ("BACKGROUND", (0, 4), (-1, 4), BG_CARD),
        ("BACKGROUND", (0, 5), (-1, 5), colors.HexColor("#FFF4DC")),
        ("LINEABOVE", (0, 5), (-1, 5), 0.5, DIVIDER),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 6),
        ("TOPPADDING", (0, 1), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 0.5, DIVIDER),
    ]))
    return tbl


def _traction_snapshot(traction: dict[str, int]) -> Table:
    """Legacy helper — retained for backwards compatibility with callers
    that may still reference waitlist-based traction. The current deck
    no longer uses this; see `_phase_one_highlight` + `_proof_points_table`.
    """
    data = [
        ["Metric", "Value", "Notes"],
        ["Live sandbox corridors", "KE · ZA", "Kotani Pay v3 on-ramp returning real live rates today"],
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
    """Render the 5-page institutional pitch deck to bytes.

    Slide 1 — Macro Arbitrage & Unlocks (also carries the brand strip)
    Slide 2 — Infrastructure Model (fiat-on-surface, Web3 under)
    Slide 3 — Validation & Sandbox Traction (production-ready proof points)
    Slide 4 — High-Margin Unit Economics (£1,000 inbound waterfall + B2B multiplier)
    Slide 5 — The £1.5M Ask & Execution Roadmap
    """
    S = _styles()
    # Note: traction is intentionally no longer pulled from the waitlist
    # table — this deck is framed for institutional investment committees,
    # not consumer growth metrics. See `_phase_one_highlight` on Slide 3.
    _ = await _pull_traction(db)  # kept for backwards-compat side effects

    buf = BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=A4)
    c.setTitle("Vaulted — Investor Deck")
    c.setAuthor("Phoenix-Atlas Technologies Ltd")
    c.setSubject("Bi-directional UK ↔ Africa remittance — Institutional Pre-Seed")
    width, height = A4

    TOTAL_PAGES = 5

    # ============================================================
    # SLIDE 1 — THE MACRO ARBITRAGE & UNLOCKS
    # ============================================================
    _draw_cover_hero(c, width, height)   # slim top brand strip
    _draw_page_chrome(c, width, height, 1, TOTAL_PAGES)
    # Content frame starts below the brand strip, ends above the footer
    frame = Frame(20 * mm, 20 * mm, width - 20 * mm - 15 * mm, height - 55 * mm,
                  leftPadding=0, rightPadding=0, topPadding=4, bottomPadding=0, showBoundary=0)
    story1 = [
        Paragraph("SLIDE 1 · THE MACRO ARBITRAGE &amp; UNLOCKS", S["eyebrow"]),
        Paragraph(
            "Capturing the $28B UK&nbsp;&harr;&nbsp;Africa corridor via regulated stablecoin rails.",
            S["h1"],
        ),
        Paragraph(
            "Legacy cross-border banking forces <b>7–12% fees</b> and <b>3–5 day</b> settlement "
            "windows. While current market incumbents (Wise, Remitly) compete heavily on outbound "
            "retail transactions, they leave the highest-value, fastest-growing sub-corridors "
            "entirely unserved.",
            S["sub"],
        ),
        Paragraph("The inbound data edge", S["h2"]),
        _macro_data_card(),
        Spacer(1, 10),
        Paragraph(
            "Severe regional dollar scarcity renders traditional SWIFT wires highly unreliable, "
            "driving a massive organic migration toward digital stablecoins (<b>$9B+/month</b> "
            "of African remittance volume already settling on-chain).",
            S["body"],
        ),
        Paragraph("Our wedge", S["h2"]),
        Paragraph(
            "Bi-directional, fiat-in / fiat-out remittance settling in <b>under 2 minutes</b> at "
            "an all-in cost of <b>~4.6%</b> &mdash; slashing legacy banking costs in half while "
            "unlocking a clear, non-SWIFT white-label pathway for African commercial payment banks.",
            S["body"],
        ),
    ]
    frame.addFromList(story1, c)
    c.showPage()

    # ============================================================
    # SLIDE 2 — THE INFRASTRUCTURE MODEL
    # ============================================================
    _draw_page_chrome(c, width, height, 2, TOTAL_PAGES)
    frame = Frame(20 * mm, 20 * mm, width - 20 * mm - 15 * mm, height - 40 * mm,
                  leftPadding=0, rightPadding=0, topPadding=8, bottomPadding=0, showBoundary=0)
    story2 = [
        Paragraph("SLIDE 2 · THE INFRASTRUCTURE MODEL", S["eyebrow"]),
        Paragraph(
            "Fiat UX on the surface. High-velocity Web3 capital rails underneath.",
            S["h1"],
        ),
        Paragraph(
            "A regulated-fiat experience on both ends of every corridor, with a programmable "
            "stablecoin settlement layer invisible to the end user.",
            S["sub"],
        ),
        Paragraph("The architecture", S["h2"]),
        _architecture_flow_table(),
        Spacer(1, 12),
        Paragraph("The competitive advantage", S["h2"]),
        Paragraph(
            "Complete abstraction of the Web3 layer. End-users interact purely with native fiat "
            "balances. <b>No seed phrases, no gas-fee exposure, zero crypto-native experience "
            "required</b> &mdash; while the underlying rails deliver sub-5-second finality on "
            "Polygon L2 and full on-chain auditability for compliance teams.",
            S["body"],
        ),
    ]
    frame.addFromList(story2, c)
    c.showPage()

    # ============================================================
    # SLIDE 3 — VALIDATION & SANDBOX TRACTION
    # ============================================================
    _draw_page_chrome(c, width, height, 3, TOTAL_PAGES)
    frame = Frame(20 * mm, 20 * mm, width - 20 * mm - 15 * mm, height - 40 * mm,
                  leftPadding=0, rightPadding=0, topPadding=8, bottomPadding=0, showBoundary=0)
    story3 = [
        Paragraph("SLIDE 3 · VALIDATION &amp; SANDBOX TRACTION", S["eyebrow"]),
        Paragraph(
            "Production-ready infrastructure across seven core corridors.",
            S["h1"],
        ),
        Paragraph(
            "Bypassing standard early-stage development risk by deploying direct sandbox "
            "integrations with the clearing and payout partners we will scale with.",
            S["sub"],
        ),
        Paragraph("The core proof points", S["h2"]),
        _proof_points_table(),
        Spacer(1, 14),
        Paragraph("Current operating posture", S["h2"]),
        _phase_one_highlight(),
    ]
    frame.addFromList(story3, c)
    c.showPage()

    # ============================================================
    # SLIDE 4 — HIGH-MARGIN UNIT ECONOMICS
    # ============================================================
    _draw_page_chrome(c, width, height, 4, TOTAL_PAGES)
    frame = Frame(20 * mm, 20 * mm, width - 20 * mm - 15 * mm, height - 40 * mm,
                  leftPadding=0, rightPadding=0, topPadding=8, bottomPadding=0, showBoundary=0)
    story4 = [
        Paragraph("SLIDE 4 · HIGH-MARGIN UNIT ECONOMICS", S["eyebrow"]),
        Paragraph(
            "2.08% contribution margin anchored by a 96.5% CM ratio.",
            S["h1"],
        ),
        Paragraph(
            "£1,000 inbound transaction breakdown &mdash; blended across live African corridors "
            "at typical Q3 2026 mid-market rates.",
            S["sub"],
        ),
        _unit_econ_deep(),
        Spacer(1, 12),
        Paragraph("The B2B multiplier", S["h2"]),
        Paragraph(
            "A <b>50/50 revenue-split</b> model on our white-label API infrastructure. "
            "Processing just <b>£1M/month</b> in regional medical / tuition outflows yields "
            "<b>£10,750/month</b> in high-margin shared revenue for our banking partners. "
            "Partner supplies the local on-ramp; Vaulted supplies UK-side compliance, the USDC "
            "settlement bridge, and GBP/EUR payout.",
            S["body"],
        ),
    ]
    frame.addFromList(story4, c)
    c.showPage()

    # ============================================================
    # SLIDE 5 — THE £1.5M ASK & EXECUTION ROADMAP
    # ============================================================
    _draw_page_chrome(c, width, height, 5, TOTAL_PAGES)
    frame = Frame(20 * mm, 20 * mm, width - 20 * mm - 15 * mm, height - 40 * mm,
                  leftPadding=0, rightPadding=0, topPadding=8, bottomPadding=0, showBoundary=0)
    story5 = [
        Paragraph("SLIDE 5 · THE £1.5M ASK &amp; EXECUTION ROADMAP", S["eyebrow"]),
        Paragraph(
            "Securing regulatory frameworks and clearing institutional scale.",
            S["h1"],
        ),
        Paragraph("Capital allocation (18-month runway)", S["h2"]),
        _capital_allocation_table(),
        Spacer(1, 12),
        Paragraph("The milestones", S["h2"]),
        Paragraph(
            "&bull; <b>Q3 2026:</b> Execute B2B partner pilots; secure formal Letters of Intent "
            "(LoI) with target UK PSP clearing banks.",
            S["bullet"],
        ),
        Paragraph(
            "&bull; <b>Q4 2026:</b> Formally submit the comprehensive FCA license application; "
            "enter live testing environments with banking rails.",
            S["bullet"],
        ),
        Paragraph(
            "&bull; <b>Q1 2027:</b> Phase 2 Launch &mdash; opening live Africa &rarr; UK/EU "
            "real-time GBP fiat settlement corridors.",
            S["bullet"],
        ),
        Paragraph(
            "&bull; <b>Q2 2027:</b> Secure regulatory approval; scale processing architecture to "
            "target the first 10k active transaction users.",
            S["bullet"],
        ),

        Spacer(1, 12),
        Paragraph(
            'Let&rsquo;s talk.  <b>Umar Sani</b> &mdash; Founder &amp; CEO  ·  '
            '<b>umar.sani@phoenix-atlas.com</b>  ·  '
            '<b><a href="https://www.linkedin.com/in/umar-muhammad-sani-msc-mapm-60951155" '
            'color="#0F0B08">linkedin.com/in/umar-muhammad-sani</a></b>',
            S["quoteBig"],
        ),
        Spacer(1, 4),
        Paragraph(
            '<b><a href="https://calendar.app.google/U1r2UbqrQqQCxQrcA" '
            'color="#8A6D2E">Book a 20-min sandbox walkthrough &rarr;</a></b>',
            S["quoteBig"],
        ),
    ]
    frame.addFromList(story5, c)
    c.showPage()

    c.save()
    return buf.getvalue()
