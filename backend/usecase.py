"""Investor use-case document generator (PDF + DOCX).

Builds a two-page, letterhead-branded use-case brief tailored for Nigerian
Payment Service Banks (PSBs). The content is parameterised on bank name,
recipient, and primary ask so Umar can regenerate for any PSB (9PSB,
MoMo PSB, SmartCash, Hope PSB, etc.) without touching code.

Default parameterisation is 9PSB with a strategic-partnership + equity
investment ask, as this is the one he's actively pitching.

Exports:
  * build_psb_usecase_pdf(**kwargs) -> bytes  (A4, 2 pages)
  * build_psb_usecase_docx(**kwargs) -> bytes (editable Word doc)

Both mirror the deck / onepager / letterhead / receipt visual language.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from typing import List, Optional

from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.pdfbase.pdfmetrics import stringWidth

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.shared import Pt, RGBColor, Mm
from docx.oxml.ns import qn
from docx.oxml import OxmlElement


# ---- Brand palette ---------------------------------------------------------
GOLD = colors.HexColor("#C9A35B")
GOLD_DEEP = colors.HexColor("#8A6D2E")
GOLD_SOFT = colors.HexColor("#F5E9C9")
INK = colors.HexColor("#0F0B08")
INK_SUBTLE = colors.HexColor("#7A7267")
DIVIDER = colors.HexColor("#E5DDC9")
BG_SOFT = colors.HexColor("#FBF6EB")

_INK_HEX = "0F0B08"
_GOLD_HEX = "C9A35B"
_GOLD_DEEP_HEX = "8A6D2E"
_SUBTLE_HEX = "7A7267"


# ---- Content payload (default = 9PSB) --------------------------------------
# Kept as a dataclass + default factory so the same values power both the
# PDF and DOCX pipelines. Any field can be overridden per-recipient at the
# route handler level without re-authoring the body.
@dataclass
class UseCaseContent:
    bank_name: str = "9mobile 9Payment Service Bank Ltd"
    bank_short: str = "9PSB"
    recipient_name: str = "The Managing Director"
    recipient_title: str = "Executive Office, 9mobile 9PSB"
    recipient_address_1: str = "Plot 208, Zone AO, Central Business District"
    recipient_address_2: str = "Abuja, Nigeria"
    salutation: str = "Dear Sir / Madam,"
    ask: str = "Strategic Partnership + Equity Investment"

    # Subject line
    subject: str = ("Vaulted — the Compliant Stablecoin-to-Naira Rail "
                    "9PSB can Build Cross-Border Remittance On")

    # Opening paragraph — reframes Vaulted as infrastructure, not a consumer app.
    opening: str = (
        "Thank you for the opportunity to introduce Vaulted. We are a "
        "UK-regulated payments-infrastructure company — not a consumer wallet "
        "and not a remittance brand. Our product is a developer-grade API, "
        "SDK and settlement engine that converts stablecoin liquidity "
        "(USDC / USDT) into compliant, same-day Naira delivered through any "
        "licensed Nigerian institution. We are writing to propose that {bank_short} "
        "becomes the exclusive mobile-money and agent-network partner on top "
        "of this rail, and to invite {bank_short} to participate as a strategic "
        "investor in the current Vaulted equity round at pre-seed terms."
    )

    opportunity_stats: list = None
    strategic_fit: list = None
    integration_steps: list = None
    commercial_options: list = None
    roadmap_phases: list = None
    next_steps: list = None

    def __post_init__(self):
        # ---- The opportunity --------------------------------------------
        # Stats chosen to frame the TAM for an *infrastructure* play, not
        # a consumer land-grab. We lead with inbound dollar volume, the
        # compliance cost of serving it on legacy rails, and the share
        # already migrating to stablecoin — i.e. the pipe 9PSB would own.
        if self.opportunity_stats is None:
            self.opportunity_stats = [
                ("$20.9B",  "Nigeria's annual diaspora inflow — the backbone cash-flow a cross-border rail must capture (World Bank, 2024)."),
                ("~55%",    "Share of 2024 Sub-Saharan remittances estimated to have touched a stablecoin at least once in the corridor (Chainalysis, 2024)."),
                ("7-9%",    "Average all-in cost of a $200 send on legacy rails. Vaulted's rail targets sub-3%, in line with the UN SDG benchmark."),
                ("T+0",     "Settlement window from stablecoin receipt to Naira in a bank or wallet — Vaulted's rail does not depend on correspondent banking."),
            ]

        # ---- Strategic fit — reframed as "you build on our rail" --------
        if self.strategic_fit is None:
            self.strategic_fit = [
                ("Keep the customer, own the brand",
                 "Vaulted is deliberately invisible to the end user. {bank_short} integrates our API "
                 "behind {bank_short}-branded screens; the diaspora sender sees '9PSB Global Transfer', "
                 "not 'Vaulted'. The customer, the deposit relationship, the data and the lifetime "
                 "value all stay inside {bank_short}'s balance sheet."),
                ("Compliant FX exposure without a new licence",
                 "The USDC → NGN conversion happens off-balance-sheet at Vaulted; {bank_short} only "
                 "ever books compliant domestic Naira, well within existing PSB licence scope. We "
                 "handle the FX risk, the on-chain custody, the AML screening and the sanctions "
                 "lists. {bank_short} handles distribution."),
                ("Infrastructure built for banks, not for crypto natives",
                 "Vaulted ships what institutional partners expect: signed webhooks, sandbox "
                 "environments, OpenAPI schemas, idempotency keys, SOC2-aligned audit logs, "
                 "per-transaction reconciliation, settlement reporting, and a dedicated "
                 "integration manager. No node to run, no wallet to secure, no on-chain exposure."),
                ("A rail — not a competitor",
                 "Vaulted does not operate a consumer brand in Nigeria and will contractually "
                 "exclude ourselves from direct-to-consumer distribution in-corridor for the "
                 "duration of the partnership. We make money when {bank_short} makes money."),
            ]

        # ---- Technical integration — API-first & modular ----------------
        if self.integration_steps is None:
            self.integration_steps = [
                ("Rail API",
                 "Three REST endpoints and a signed webhook: `POST /quote`, `POST /payout`, "
                 "`GET /tx/{id}` plus `webhook: payout.settled`. SDK bindings for Node, "
                 "Python and Kotlin are provided; sandbox credentials in 24 hours."),
                ("Compliance stack",
                 "Stripe Identity KYC, OpenSanctions + OFAC/HMT/EU AML screening, FATF Travel "
                 "Rule messaging, and chain-analytics tagging are embedded in the API. "
                 "{bank_short} inherits our compliance posture without new vendor contracts."),
                ("Settlement engine",
                 "Vaulted holds a working-capital float of stablecoin and Naira so {bank_short} "
                 "can disburse funds instantly and reconcile T+0. Daily settlement files are "
                 "posted to {bank_short}'s SFTP or S3 bucket in ISO 20022 pacs.008 format."),
                ("White-label SDK",
                 "If {bank_short} wants a native in-app experience, Vaulted ships a React Native "
                 "/ Flutter SDK with a drop-in send-money flow fully themeable to {bank_short}'s "
                 "design system — launched inside the 9mobile app in days, not months."),
            ]

        # ---- Commercial options — infrastructure licensing + equity ------
        if self.commercial_options is None:
            self.commercial_options = [
                ("Per-transaction infrastructure fee",
                 "Flat 25-40 bps on every USDC→NGN transaction routed through {bank_short}. "
                 "No minimums, no setup fees. Scales with volume; both parties aligned on growth."),
                ("Exclusive corridor licence",
                 "An annual rail-access fee grants {bank_short} exclusivity as Vaulted's sole "
                 "Nigerian disbursement partner for a defined set of corridors (UK→NG, EU→NG, "
                 "US→NG). Protects {bank_short}'s moat while the rail matures."),
                ("Strategic equity",
                 "{bank_short} participates in the current pre-seed round at agreed terms, "
                 "with a pro-rata right in subsequent rounds. Aligns incentives, cements the "
                 "partnership, and gives {bank_short} a seat at the table as the rail scales "
                 "pan-African."),
            ]

        # ---- Roadmap — pilot → scale → infrastructure moat --------------
        if self.roadmap_phases is None:
            self.roadmap_phases = [
                ("Phase 1 · 60-day technical integration",
                 "Vaulted ships sandbox credentials and sample code; {bank_short} integrates "
                 "`/payout` and the settlement webhook into a staging environment. "
                 "Milestone: 100 end-to-end sandbox transactions, dual-sided compliance sign-off."),
                ("Phase 2 · 90-day production pilot",
                 "UK→NG corridor goes live with {bank_short} as sole disbursement partner. "
                 "Target: 1,000 real transactions, median landed cost under 3%, zero failed "
                 "settlements. Equity term sheet negotiated in parallel."),
                ("Phase 3 · 12-month exclusive rail",
                 "Expand to EU and US origination; add agent-network cash-out to extend reach "
                 "to the unbanked. Co-marketing campaign in UK Nigerian diaspora communities. "
                 "Vaulted begins work on eNaira / cNGN rail integration — {bank_short} is "
                 "first-mover on the next-generation CBDC leg."),
            ]

        # ---- Next steps -------------------------------------------------
        if self.next_steps is None:
            self.next_steps = [
                "A 45-minute technical working session with {bank_short}'s product and engineering leads to walk through the API, SDK, and settlement engine.",
                "An NDA + data-room exchange so we can share detailed unit economics, cap table, security architecture, and the SOC2-readiness roadmap.",
                "A joint go/no-go decision on the Phase 1 sandbox integration within 21 days of this correspondence.",
            ]
        # Template-substitute {bank_short} inside every string, so changing
        # the bank_short default propagates everywhere without manual edits.
        # Use .replace() rather than .format() so stray `{id}` or `{json}`
        # tokens in example API paths don't blow up as KeyError.
        def _sub(items):
            if items is None:
                return items
            def _s(txt):
                return txt.replace("{bank_short}", self.bank_short) if isinstance(txt, str) else txt
            out = []
            for item in items:
                if isinstance(item, tuple):
                    out.append(tuple(_s(x) for x in item))
                else:
                    out.append(_s(item))
            return out
        self.strategic_fit = _sub(self.strategic_fit)
        self.integration_steps = _sub(self.integration_steps)
        self.commercial_options = _sub(self.commercial_options)
        self.roadmap_phases = _sub(self.roadmap_phases)
        self.next_steps = _sub(self.next_steps)


def _default_content(**overrides) -> UseCaseContent:
    """Build a UseCaseContent with per-call overrides applied."""
    c = UseCaseContent()
    for k, v in overrides.items():
        if hasattr(c, k) and v is not None:
            setattr(c, k, v)
    return c


# ============================================================================
# PDF VERSION — 2 pages, letterhead-branded
# ============================================================================
def _draw_header(c, width: float, height: float) -> float:
    """Draw the shared letterhead header. Returns y-coordinate below the
    gold hairline so the caller knows where safe body content starts."""
    y_top = height - 22 * mm

    # Logo mark
    c.setFillColor(GOLD)
    c.roundRect(20 * mm, y_top - 4 * mm, 14 * mm, 14 * mm, 2.5 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 15)
    c.drawCentredString(27 * mm, y_top, "V")

    # Wordmark + product-of
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(38 * mm, y_top + 1 * mm, "Vaulted")
    c.setFillColor(INK_SUBTLE)
    c.setFont("Helvetica-Oblique", 8.5)
    c.drawString(38 * mm, y_top - 4 * mm,
                 "A product of Phoenix-Atlas Technologies Ltd")

    # Right contact block
    c.setFillColor(INK)
    c.setFont("Helvetica", 8.5)
    c.drawRightString(width - 20 * mm, y_top + 1 * mm, "71-75 Shelton Street")
    c.drawRightString(width - 20 * mm, y_top - 3 * mm,
                      "London, WC2H 9JQ, United Kingdom")
    c.setFillColor(GOLD_DEEP)
    c.setFont("Helvetica-Bold", 8.5)
    c.drawRightString(width - 20 * mm, y_top - 8 * mm,
                      "umar.sani@phoenix-atlas.com")

    # Gold hairlines
    c.setStrokeColor(GOLD)
    c.setLineWidth(0.8)
    c.line(20 * mm, y_top - 14 * mm, width - 20 * mm, y_top - 14 * mm)
    c.setStrokeColor(DIVIDER)
    c.setLineWidth(0.4)
    c.line(20 * mm, y_top - 15.5 * mm, width - 20 * mm, y_top - 15.5 * mm)

    return y_top - 20 * mm


def _draw_footer(c, width: float, page_num: int, total_pages: int) -> None:
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
                 "Phoenix-Atlas Technologies Ltd  ·  Companies House 16712430  "
                 "·  Registered in England & Wales")
    c.drawString(20 * mm, yf + 1 * mm,
                 "Registered office: 71-75 Shelton Street, London, WC2H 9JQ.")

    c.setFillColor(GOLD_DEEP)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawRightString(width - 20 * mm, yf + 4 * mm, "phoenix-atlas.com")
    c.setFillColor(INK_SUBTLE)
    c.setFont("Helvetica", 7)
    c.drawRightString(width - 20 * mm, yf + 1 * mm,
                      f"Page {page_num} of {total_pages}")


def _wrap_text(text: str, width_pts: float, font_name: str, font_size: float) -> List[str]:
    """Simple greedy word-wrap into lines fitting `width_pts`."""
    words = text.split()
    if not words:
        return [""]
    lines: List[str] = []
    current = words[0]
    for w in words[1:]:
        tentative = current + " " + w
        if stringWidth(tentative, font_name, font_size) <= width_pts:
            current = tentative
        else:
            lines.append(current)
            current = w
    lines.append(current)
    return lines


def _draw_paragraph(c, x: float, y: float, text: str, *,
                    font: str = "Helvetica", size: float = 10,
                    color=INK, max_width: float, leading: float = 1.45) -> float:
    """Draw a wrapped paragraph. Returns the y-coordinate below the last line."""
    c.setFillColor(color)
    c.setFont(font, size)
    line_h = size * leading
    for line in _wrap_text(text, max_width, font, size):
        c.drawString(x, y, line)
        y -= line_h
    return y


def _draw_section_title(c, x: float, y: float, text: str) -> float:
    c.setFillColor(GOLD_DEEP)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(x, y, text.upper())
    # Gold underline
    c.setStrokeColor(GOLD)
    c.setLineWidth(0.6)
    c.line(x, y - 1.5 * mm, x + 18 * mm, y - 1.5 * mm)
    return y - 6 * mm


def build_psb_usecase_pdf(**overrides) -> bytes:
    """Render the full two-page PSB use case as PDF bytes."""
    data = _default_content(**overrides)
    buf = BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"Vaulted × {data.bank_short} — Strategic Use Case")
    c.setAuthor("Phoenix-Atlas Technologies Ltd")
    c.setSubject(data.subject)

    width, height = A4
    content_width = width - 40 * mm
    left_margin = 20 * mm

    # ================= PAGE 1 =================
    y = _draw_header(c, width, height)

    # Date
    c.setFillColor(INK_SUBTLE)
    c.setFont("Helvetica", 9)
    today = datetime.now(timezone.utc).strftime("%d %B %Y")
    c.drawRightString(width - 20 * mm, y, today)
    y -= 10 * mm

    # Recipient block
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 10.5)
    c.drawString(left_margin, y, data.recipient_name)
    y -= 4.5 * mm
    c.setFont("Helvetica", 10)
    c.drawString(left_margin, y, data.recipient_title)
    y -= 4.5 * mm
    c.setFillColor(INK_SUBTLE)
    c.drawString(left_margin, y, data.bank_name)
    y -= 4.5 * mm
    c.drawString(left_margin, y, data.recipient_address_1)
    y -= 4.5 * mm
    c.drawString(left_margin, y, data.recipient_address_2)
    y -= 10 * mm

    # Subject line
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 11)
    y = _draw_paragraph(c, left_margin, y, f"Subject: {data.subject}",
                        font="Helvetica-Bold", size=11, color=INK,
                        max_width=content_width, leading=1.4)
    y -= 2 * mm

    # Salutation
    c.setFillColor(INK)
    c.setFont("Helvetica", 10.5)
    c.drawString(left_margin, y, data.salutation)
    y -= 7 * mm

    # Opening paragraph
    opening = data.opening.replace("{bank_short}", data.bank_short)
    y = _draw_paragraph(c, left_margin, y, opening,
                        size=10, max_width=content_width, leading=1.5)
    y -= 4 * mm

    # ---- The Opportunity (stats grid) ----
    y = _draw_section_title(c, left_margin, y, "The opportunity")

    # 2x2 stats grid
    grid_cols = 2
    grid_w = content_width / grid_cols
    grid_h = 18 * mm
    for i, (big, small) in enumerate(data.opportunity_stats):
        col = i % grid_cols
        row = i // grid_cols
        gx = left_margin + col * grid_w
        gy = y - row * grid_h
        # Soft background card
        c.setFillColor(BG_SOFT)
        c.setStrokeColor(DIVIDER)
        c.setLineWidth(0.4)
        c.roundRect(gx + 1 * mm, gy - grid_h + 2 * mm, grid_w - 3 * mm,
                    grid_h - 2.5 * mm, 2 * mm, fill=1, stroke=1)
        # Big stat
        c.setFillColor(GOLD_DEEP)
        c.setFont("Helvetica-Bold", 14)
        c.drawString(gx + 4 * mm, gy - 5 * mm, big)
        # Tagline — wrap into max 2 lines fitting cell width
        c.setFillColor(INK)
        c.setFont("Helvetica", 7.5)
        lines = _wrap_text(small, grid_w - 8 * mm, "Helvetica", 7.5)[:2]
        ty = gy - 9 * mm
        for ln in lines:
            c.drawString(gx + 4 * mm, ty, ln)
            ty -= 3.3 * mm
    y -= grid_h * ((len(data.opportunity_stats) + 1) // 2) + 2 * mm

    # ---- Strategic fit ----
    y = _draw_section_title(c, left_margin, y, f"Strategic fit for {data.bank_short}")
    for title, body in data.strategic_fit:
        # Bullet marker
        c.setFillColor(GOLD)
        c.circle(left_margin + 1.5 * mm, y - 1 * mm, 1.2 * mm, fill=1, stroke=0)
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(left_margin + 5 * mm, y, title)
        y -= 4.5 * mm
        y = _draw_paragraph(c, left_margin + 5 * mm, y, body,
                            size=9.5, color=INK_SUBTLE,
                            max_width=content_width - 5 * mm, leading=1.4)
        y -= 2 * mm

    _draw_footer(c, width, 1, 2)

    # ================= PAGE 2 =================
    c.showPage()
    y = _draw_header(c, width, height)
    y -= 4 * mm

    # ---- Technical integration ----
    y = _draw_section_title(c, left_margin, y, "Technical integration model")
    for i, (title, body) in enumerate(data.integration_steps, start=1):
        c.setFillColor(GOLD)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(left_margin, y, f"{i}.")
        c.setFillColor(INK)
        c.drawString(left_margin + 6 * mm, y, title)
        y -= 4.5 * mm
        y = _draw_paragraph(c, left_margin + 6 * mm, y, body,
                            size=9.5, color=INK_SUBTLE,
                            max_width=content_width - 6 * mm, leading=1.4)
        y -= 2 * mm

    # ---- Commercial model ----
    y = _draw_section_title(c, left_margin, y, "Commercial options")
    for i, (title, body) in enumerate(data.commercial_options):
        # Letter badge A/B/C
        letter = chr(ord("A") + i)
        c.setFillColor(GOLD_DEEP)
        c.roundRect(left_margin, y - 4.3 * mm, 6 * mm, 5.5 * mm, 1 * mm,
                    fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(left_margin + 3 * mm, y - 2.5 * mm, letter)

        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(left_margin + 9 * mm, y, title)
        y -= 4.5 * mm
        y = _draw_paragraph(c, left_margin + 9 * mm, y, body,
                            size=9.5, color=INK_SUBTLE,
                            max_width=content_width - 9 * mm, leading=1.4)
        y -= 1.5 * mm

    # ---- Roadmap ----
    y = _draw_section_title(c, left_margin, y, "Proposed roadmap")
    for title, body in data.roadmap_phases:
        c.setFillColor(GOLD)
        c.rect(left_margin, y - 3.5 * mm, 2 * mm, 4 * mm, fill=1, stroke=0)
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(left_margin + 5 * mm, y, title)
        y -= 4.5 * mm
        y = _draw_paragraph(c, left_margin + 5 * mm, y, body,
                            size=9.5, color=INK_SUBTLE,
                            max_width=content_width - 5 * mm, leading=1.4)
        y -= 1.5 * mm

    # ---- Next steps ----
    y = _draw_section_title(c, left_margin, y, "Next steps")
    for step in data.next_steps:
        c.setFillColor(GOLD)
        c.circle(left_margin + 1.5 * mm, y - 1 * mm, 1 * mm, fill=1, stroke=0)
        y = _draw_paragraph(c, left_margin + 5 * mm, y, step,
                            size=9.5, color=INK, max_width=content_width - 5 * mm,
                            leading=1.4)
        y -= 1.5 * mm

    # ---- Sign-off (anchored above footer so it never overlaps) ----------
    # The footer sits in the bottom 24mm of the page (gold rule at 24mm,
    # company lines down to 15mm). We pin the sign-off block to start
    # ~58mm from the page bottom so there's a clean 10mm gap between the
    # founder's email line and the footer rule — comfortable enough to
    # read even if the printer trims a few mm off the margin.
    SIGNOFF_ANCHOR_Y = 58 * mm  # top of "Yours sincerely," from page bottom

    # If the body content has already dipped below the anchor, we respect
    # whichever is lower (i.e. don't force an overlap up top). Otherwise
    # we jump straight to the anchor so Next-steps keeps its generous
    # breathing room above the sign-off.
    y = min(y, SIGNOFF_ANCHOR_Y)

    c.setFillColor(INK)
    c.setFont("Helvetica", 10)
    c.drawString(left_margin, y, "Yours sincerely,")
    y -= 10 * mm
    c.setFont("Helvetica-Bold", 10.5)
    c.drawString(left_margin, y, "Umar Sani")
    y -= 4.5 * mm
    c.setFillColor(INK_SUBTLE)
    c.setFont("Helvetica", 9.5)
    c.drawString(left_margin, y, "Founder & Chief Executive, Phoenix-Atlas Technologies Ltd")
    y -= 4.5 * mm
    c.setFillColor(GOLD_DEEP)
    c.setFont("Helvetica-Bold", 9.5)
    c.drawString(left_margin, y, "umar.sani@phoenix-atlas.com")

    _draw_footer(c, width, 2, 2)

    c.save()
    return buf.getvalue()


# ============================================================================
# DOCX VERSION — fully editable
# ============================================================================
def _run(paragraph, text: str, *, bold: bool = False, italic: bool = False,
         size: float = 11, color: str = _INK_HEX, font: str = "Calibri"):
    r = paragraph.add_run(text)
    r.bold = bold
    r.italic = italic
    r.font.size = Pt(size)
    r.font.name = font
    r.font.color.rgb = RGBColor.from_string(color)
    return r


def _add_horizontal_rule(paragraph, color_hex: str, size: int = 8) -> None:
    p_pr = paragraph._p.get_or_add_pPr()
    p_bdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), str(size))
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), color_hex)
    p_bdr.append(bottom)
    p_pr.append(p_bdr)


def _no_cell_borders(cell) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_borders = OxmlElement("w:tcBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        b = OxmlElement(f"w:{edge}")
        b.set(qn("w:val"), "nil")
        tc_borders.append(b)
    tc_pr.append(tc_borders)


def _add_section_heading(doc, text: str) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(14)
    p.paragraph_format.space_after = Pt(4)
    _run(p, text.upper(), bold=True, size=11, color=_GOLD_DEEP_HEX)
    _add_horizontal_rule(p, _GOLD_HEX, size=10)


def build_psb_usecase_docx(**overrides) -> bytes:
    """Render an editable Word document for the PSB use case."""
    data = _default_content(**overrides)
    doc = Document()

    # Set default Normal style to match
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    section = doc.sections[0]
    section.top_margin = Mm(22)
    section.bottom_margin = Mm(22)
    section.left_margin = Mm(20)
    section.right_margin = Mm(20)
    section.header_distance = Mm(10)
    section.footer_distance = Mm(10)

    # -------- Header --------
    header = section.header
    for p in list(header.paragraphs):
        p.text = ""

    header_tbl = header.add_table(rows=1, cols=2, width=Mm(170))
    header_tbl.autofit = False
    header_tbl.columns[0].width = Mm(100)
    header_tbl.columns[1].width = Mm(70)
    for row in header_tbl.rows:
        for cell in row.cells:
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            _no_cell_borders(cell)
    left_cell, right_cell = header_tbl.rows[0].cells

    p1 = left_cell.paragraphs[0]
    p1.alignment = WD_ALIGN_PARAGRAPH.LEFT
    _run(p1, "VAULTED", bold=True, size=22, color=_INK_HEX)
    p2 = left_cell.add_paragraph()
    _run(p2, "A product of Phoenix-Atlas Technologies Ltd",
         italic=True, size=9, color=_SUBTLE_HEX)

    r1 = right_cell.paragraphs[0]
    r1.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _run(r1, "71-75 Shelton Street", size=9, color=_INK_HEX)
    r2 = right_cell.add_paragraph()
    r2.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _run(r2, "London, WC2H 9JQ, United Kingdom", size=9, color=_INK_HEX)
    r3 = right_cell.add_paragraph()
    r3.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _run(r3, "umar.sani@phoenix-atlas.com",
         bold=True, size=9, color=_GOLD_DEEP_HEX)

    rule_h = header.add_paragraph()
    _add_horizontal_rule(rule_h, _GOLD_HEX, size=12)

    # -------- Body --------
    # Date
    date_p = doc.add_paragraph()
    date_p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _run(date_p, datetime.now(timezone.utc).strftime("%d %B %Y"),
         size=10, color=_SUBTLE_HEX)

    # Recipient block
    recip = doc.add_paragraph()
    _run(recip, data.recipient_name, bold=True, size=11)
    r2b = doc.add_paragraph()
    _run(r2b, data.recipient_title, size=11)
    r3b = doc.add_paragraph()
    _run(r3b, data.bank_name, size=11, color=_SUBTLE_HEX)
    r4 = doc.add_paragraph()
    _run(r4, data.recipient_address_1, size=11, color=_SUBTLE_HEX)
    r5 = doc.add_paragraph()
    _run(r5, data.recipient_address_2, size=11, color=_SUBTLE_HEX)

    doc.add_paragraph()  # spacer

    # Subject
    subj = doc.add_paragraph()
    _run(subj, "Subject: ", bold=True, size=11)
    _run(subj, data.subject, bold=True, size=11)

    # Salutation
    sal = doc.add_paragraph()
    sal.paragraph_format.space_before = Pt(10)
    _run(sal, data.salutation, size=11)

    # Opening paragraph
    op = doc.add_paragraph()
    op.paragraph_format.space_before = Pt(6)
    _run(op, data.opening.replace("{bank_short}", data.bank_short), size=11)

    # ---- The Opportunity ----
    _add_section_heading(doc, "The Opportunity")
    stats_tbl = doc.add_table(rows=2, cols=2)
    stats_tbl.autofit = False
    for row in stats_tbl.rows:
        for cell in row.cells:
            cell.vertical_alignment = WD_ALIGN_VERTICAL.TOP
            _no_cell_borders(cell)
    for i, (big, small) in enumerate(data.opportunity_stats):
        cell = stats_tbl.rows[i // 2].cells[i % 2]
        p = cell.paragraphs[0]
        _run(p, big, bold=True, size=16, color=_GOLD_DEEP_HEX)
        p2 = cell.add_paragraph()
        _run(p2, small, size=9.5, color=_SUBTLE_HEX)

    # ---- Strategic Fit ----
    _add_section_heading(doc, f"Strategic Fit for {data.bank_short}")
    for title, body in data.strategic_fit:
        bullet = doc.add_paragraph(style="List Bullet")
        _run(bullet, title + ". ", bold=True, size=11)
        _run(bullet, body, size=10.5, color=_SUBTLE_HEX)

    # ---- Technical Integration ----
    _add_section_heading(doc, "Technical Integration Model")
    for i, (title, body) in enumerate(data.integration_steps, start=1):
        step = doc.add_paragraph(style="List Number")
        _run(step, title + ". ", bold=True, size=11)
        _run(step, body, size=10.5, color=_SUBTLE_HEX)

    # ---- Commercial Options ----
    _add_section_heading(doc, "Commercial Options")
    for i, (title, body) in enumerate(data.commercial_options):
        letter = chr(ord("A") + i)
        opt = doc.add_paragraph()
        _run(opt, f"{letter}.  ", bold=True, size=11, color=_GOLD_DEEP_HEX)
        _run(opt, title + ". ", bold=True, size=11)
        _run(opt, body, size=10.5, color=_SUBTLE_HEX)

    # ---- Roadmap ----
    _add_section_heading(doc, "Proposed Roadmap")
    for title, body in data.roadmap_phases:
        p = doc.add_paragraph()
        _run(p, "▌ ", bold=True, size=11, color=_GOLD_HEX)
        _run(p, title + ". ", bold=True, size=11)
        _run(p, body, size=10.5, color=_SUBTLE_HEX)

    # ---- Next Steps ----
    _add_section_heading(doc, "Next Steps")
    for step in data.next_steps:
        b = doc.add_paragraph(style="List Bullet")
        _run(b, step, size=11)

    # ---- Sign-off ----
    doc.add_paragraph()
    so = doc.add_paragraph()
    _run(so, "Yours sincerely,", size=11)
    doc.add_paragraph()
    doc.add_paragraph()
    name = doc.add_paragraph()
    _run(name, "Umar Sani", bold=True, size=12)
    role = doc.add_paragraph()
    _run(role, "Founder & Chief Executive, Phoenix-Atlas Technologies Ltd",
         size=10.5, color=_SUBTLE_HEX)
    email = doc.add_paragraph()
    _run(email, "umar.sani@phoenix-atlas.com",
         bold=True, size=10.5, color=_GOLD_DEEP_HEX)

    # -------- Footer --------
    footer = section.footer
    for p in list(footer.paragraphs):
        p.text = ""
    rule_f = footer.paragraphs[0]
    _add_horizontal_rule(rule_f, _GOLD_HEX, size=12)

    footer_tbl = footer.add_table(rows=1, cols=2, width=Mm(170))
    footer_tbl.autofit = False
    footer_tbl.columns[0].width = Mm(120)
    footer_tbl.columns[1].width = Mm(50)
    for row in footer_tbl.rows:
        for cell in row.cells:
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            _no_cell_borders(cell)
    lf, rf = footer_tbl.rows[0].cells
    fp1 = lf.paragraphs[0]
    _run(fp1,
         "Phoenix-Atlas Technologies Ltd  ·  Companies House 16712430  "
         "·  Registered in England & Wales",
         size=7.5, color=_SUBTLE_HEX)
    fp2 = lf.add_paragraph()
    _run(fp2, "Registered office: 71-75 Shelton Street, London, WC2H 9JQ.",
         size=7.5, color=_SUBTLE_HEX)
    rfp1 = rf.paragraphs[0]
    rfp1.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _run(rfp1, "phoenix-atlas.com", bold=True, size=8, color=_GOLD_DEEP_HEX)
    rfp2 = rf.add_paragraph()
    rfp2.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _run(rfp2, "umar.sani@phoenix-atlas.com", size=7.5, color=_SUBTLE_HEX)

    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ============================================================================
# COVER EMAIL — HTML body + default subject for the one-click dispatcher
# ============================================================================
# Dark gold-on-ink aesthetic consistent with the password-reset / receipt
# templates. Umar can override the body via `cover_note` on the admin
# dispatcher form; whatever he types is inserted verbatim as a signed
# message between the greeting and the PDF-attached call-out.
def build_usecase_cover_html(
    *,
    recipient_name: str,
    bank_short: str = "9PSB",
    bank_name: Optional[str] = None,
    sender_name: str = "Umar Sani",
    sender_title: str = "Founder & Chief Executive, Phoenix-Atlas Technologies Ltd",
    sender_email: str = "umar.sani@phoenix-atlas.com",
    cover_note: Optional[str] = None,
    body_text: Optional[str] = None,
    greeting_override: Optional[str] = None,
    cta_text: Optional[str] = None,
    booking_url: Optional[str] = None,
) -> str:
    """Build the HTML email body for the one-click PSB use case dispatch.

    Argument priority (lowest to highest):
      1. `cover_note` legacy single-paragraph override (back-compat).
      2. `body_text` multi-paragraph user-authored content from the
         draft editor. Blank lines become paragraph breaks; HTML is
         escaped so operators can't accidentally break the template.

    `greeting_override`, `cta_text` and `booking_url` let the draft
    editor nudge the surrounding chrome without needing raw HTML.
    """
    import html as _html

    salutation_name = (recipient_name or "").strip().split()[-1] if recipient_name else bank_short
    greeting = (greeting_override or (f"Dear {salutation_name}," if salutation_name else "Hello,")).strip()

    default_note = (
        f"Attached is a two-page brief on how {bank_short} can build its cross-border "
        "remittance proposition on Vaulted's compliant stablecoin-to-Naira "
        "infrastructure. We've outlined the technical integration, three "
        "commercial options (per-transaction, exclusive corridor licence, "
        "and strategic equity), and a 60/90/365-day roadmap we believe lands "
        "a working rail inside the quarter."
    )

    if body_text and body_text.strip():
        # Split on blank lines → paragraphs. Escape HTML to prevent
        # operators pasting content that breaks the template. Line
        # breaks inside a paragraph become <br> so poetic formatting
        # survives the trip.
        paragraphs = [p.strip() for p in body_text.strip().split("\n\n") if p.strip()]
        body_html = "".join(
            f'<p style="font-size:14px;color:#F5E9C9;line-height:22px;margin:0 0 16px">'
            f'{_html.escape(p).replace(chr(10), "<br>")}'
            f'</p>'
            for p in paragraphs
        )
    else:
        note = (cover_note or default_note).strip()
        body_html = (
            f'<p style="font-size:14px;color:#F5E9C9;line-height:22px;margin:0 0 20px">'
            f'{_html.escape(note)}</p>'
        )

    closing_default = (
        "I'm happy to walk your product and strategy leads through the architecture "
        "at a time that suits. Any reply to this email reaches me directly."
    )
    closing_text = _html.escape(cta_text.strip()) if cta_text and cta_text.strip() else closing_default

    booking_block = ""
    if booking_url:
        booking_block = f"""
      <div style="margin:28px 0 20px">
        <a href="{booking_url}"
           style="display:inline-block;background:#C9A35B;color:#0F0B08;
                  text-decoration:none;font-weight:700;padding:12px 22px;
                  border-radius:999px;font-size:13px;letter-spacing:0.3px">
          Book a 45-min working session
        </a>
      </div>
    """

    return f"""
    <div style="font-family:-apple-system,Helvetica,Arial,sans-serif;max-width:580px;margin:auto;padding:36px 28px;background:#0F0B08;color:#F5E9C9;border-radius:14px">
      <div style="font-size:24px;font-weight:700;color:#C9A35B;letter-spacing:-0.4px;margin-bottom:4px">Vaulted</div>
      <div style="font-size:10.5px;color:#B8AFA1;letter-spacing:2px;text-transform:uppercase;margin-bottom:28px">A product of Phoenix-Atlas Technologies Ltd</div>

      <div style="font-size:16px;color:#F5E9C9;margin-bottom:18px">{_html.escape(greeting)}</div>

      {body_html}

      <div style="background:#1C1612;border:1px solid #2a2320;border-radius:12px;padding:16px 18px;margin:22px 0 18px">
        <div style="font-size:11px;color:#B8AFA1;letter-spacing:1.5px;text-transform:uppercase;margin-bottom:6px">Attached</div>
        <div style="font-size:14px;color:#F5E9C9;font-weight:600">
          Vaulted — {bank_short} Strategic Use Case <span style="color:#8A6D2E">(2 pages, PDF)</span>
        </div>
      </div>

      <p style="font-size:13px;color:#B8AFA1;line-height:20px;margin:0 0 8px">
        {closing_text}
      </p>

      {booking_block}

      <div style="margin:28px 0 0;font-size:13px;color:#F5E9C9">
        Yours sincerely,
      </div>
      <div style="margin-top:16px">
        <div style="font-size:15px;font-weight:700;color:#F5E9C9">{sender_name}</div>
        <div style="font-size:12px;color:#B8AFA1;margin-top:2px">{sender_title}</div>
        <div style="font-size:12px;color:#C9A35B;margin-top:4px;font-weight:600">
          <a href="mailto:{sender_email}" style="color:#C9A35B;text-decoration:none">{sender_email}</a>
        </div>
      </div>

      <div style="border-top:1px solid #2a2320;margin:28px 0 14px"></div>
      <p style="font-size:10.5px;color:#6d7a73;margin:0;line-height:16px">
        Phoenix-Atlas Technologies Ltd · Companies House 16712430 · Registered in England &amp; Wales ·<br/>
        Registered office: 71-75 Shelton Street, London WC2H 9JQ, United Kingdom
      </p>
    </div>
    """


def default_body_text(bank_short: str = "9PSB") -> str:
    """The plain-text version of the default pitch — used as the
    starting point for a new draft so operators always have a sane
    baseline to tweak instead of a blank textarea."""
    return (
        f"Attached is a two-page brief on how {bank_short} can build its cross-border "
        "remittance proposition on Vaulted's compliant stablecoin-to-Naira "
        "infrastructure.\n\n"
        "We've outlined the technical integration, three commercial options "
        "(per-transaction, exclusive corridor licence, and strategic equity), "
        "and a 60/90/365-day roadmap we believe lands a working rail inside the quarter.\n\n"
        f"I'd welcome a short call to walk the {bank_short} product and strategy leads "
        "through the architecture at a time that suits."
    )
