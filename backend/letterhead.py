"""Reusable letterhead template generator (PDF + DOCX).

Produces two artefacts in the exact visual language of the investor deck
and one-pager:
  * ``build_letterhead_pdf()`` — a print-ready A4 PDF Umar can use as a
    static header (import into Pages / Word / Google Docs as a background,
    or print and type/sign on physical copies).
  * ``build_letterhead_docx()`` — a FULLY EDITABLE Word document with the
    same gold-and-ink header + Companies House footer baked in. Uploads
    cleanly to OneDrive and edits natively in Word Online.

Both outputs are stateless — nothing is read from Mongo, nothing cached.
"""
from __future__ import annotations

from io import BytesIO
from datetime import datetime, timezone

from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.shared import Pt, RGBColor, Mm, Cm
from docx.oxml.ns import qn, nsmap
from docx.oxml import OxmlElement


# ---- Brand palette (mirrors deck.py / onepager.py) ----
GOLD = colors.HexColor("#C9A35B")
GOLD_DEEP = colors.HexColor("#8A6D2E")
INK = colors.HexColor("#0F0B08")
INK_SUBTLE = colors.HexColor("#7A7267")
DIVIDER = colors.HexColor("#E5DDC9")


# ============================================================================
# PDF VERSION — print-ready letterhead on A4
# ============================================================================
def build_letterhead_pdf() -> bytes:
    """Render a single-page A4 letterhead PDF.

    Header: gold V-mark + "Vaulted" wordmark top-left, document type + date
    top-right. Body area intentionally empty for printing / overlaying.
    Footer: Phoenix-Atlas Companies House + registered office + contact.
    """
    buf = BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=A4)
    c.setTitle("Vaulted — Letterhead Template")
    c.setAuthor("Phoenix-Atlas Technologies Ltd")
    c.setSubject("Reusable company letterhead")

    width, height = A4

    # ----- Header -----
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
    c.drawString(38 * mm, y_top - 4 * mm, "A product of Phoenix-Atlas Technologies Ltd")

    # Right-aligned contact block
    c.setFillColor(INK)
    c.setFont("Helvetica", 8.5)
    c.drawRightString(width - 20 * mm, y_top + 1 * mm, "71-75 Shelton Street")
    c.drawRightString(width - 20 * mm, y_top - 3 * mm, "London, WC2H 9JQ, United Kingdom")
    c.setFillColor(GOLD_DEEP)
    c.setFont("Helvetica-Bold", 8.5)
    c.drawRightString(width - 20 * mm, y_top - 8 * mm, "umar.sani@phoenix-atlas.com")

    # Gold hairline under the header
    c.setStrokeColor(GOLD)
    c.setLineWidth(0.8)
    c.line(20 * mm, y_top - 14 * mm, width - 20 * mm, y_top - 14 * mm)

    # Subtle secondary hairline
    c.setStrokeColor(DIVIDER)
    c.setLineWidth(0.4)
    c.line(20 * mm, y_top - 15.5 * mm, width - 20 * mm, y_top - 15.5 * mm)

    # ----- Date & subject helper lines (printed in subtle grey so they're
    #       visible on screen but blend in when the sheet is printed and
    #       written on by hand) -----
    y_body = y_top - 30 * mm
    c.setFillColor(INK_SUBTLE)
    c.setFont("Helvetica", 9)
    today = datetime.now(timezone.utc).strftime("%d %B %Y")
    c.drawRightString(width - 20 * mm, y_body, today)

    # ----- Footer -----
    yf = 14 * mm
    c.setStrokeColor(GOLD)
    c.setLineWidth(0.8)
    c.line(20 * mm, yf + 10 * mm, width - 20 * mm, yf + 10 * mm)
    c.setStrokeColor(DIVIDER)
    c.setLineWidth(0.4)
    c.line(20 * mm, yf + 8.5 * mm, width - 20 * mm, yf + 8.5 * mm)

    c.setFillColor(INK_SUBTLE)
    c.setFont("Helvetica", 7)
    c.drawString(
        20 * mm, yf + 4 * mm,
        "Phoenix-Atlas Technologies Ltd  ·  Companies House 16712430  ·  "
        "Registered in England & Wales",
    )
    c.drawString(
        20 * mm, yf + 1 * mm,
        "Registered office: 71-75 Shelton Street, London, WC2H 9JQ.",
    )

    c.setFillColor(GOLD_DEEP)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawRightString(width - 20 * mm, yf + 4 * mm, "phoenix-atlas.com")
    c.setFillColor(INK_SUBTLE)
    c.setFont("Helvetica", 7)
    c.drawRightString(width - 20 * mm, yf + 1 * mm, "umar.sani@phoenix-atlas.com")

    c.save()
    return buf.getvalue()


# ============================================================================
# DOCX VERSION — editable Word template for OneDrive
# ============================================================================
# A letterhead in DOCX uses the "header" + "footer" sections of the first
# page. We build those once, then leave a blank "Your letter goes here"
# body paragraph the user can replace. The user can save-as from Word and
# it will keep the branding on every page they type.

_INK_HEX = "0F0B08"
_GOLD_HEX = "C9A35B"
_GOLD_DEEP_HEX = "8A6D2E"
_SUBTLE_HEX = "7A7267"


def _run(paragraph, text: str, *, bold: bool = False, italic: bool = False,
         size: float = 10, color: str = _INK_HEX, font: str = "Calibri"):
    """Add a configured text run to a Word paragraph."""
    run = paragraph.add_run(text)
    run.bold = bold
    run.italic = italic
    run.font.size = Pt(size)
    run.font.name = font
    run.font.color.rgb = RGBColor.from_string(color)
    return run


def _set_cell_shading(cell, color_hex: str) -> None:
    """Shade a Word table cell — python-docx doesn't expose this directly."""
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), color_hex)
    tc_pr.append(shd)


def _add_horizontal_rule(paragraph, color_hex: str, size: int = 8) -> None:
    """Append a bottom-border rule under a paragraph (used for the gold line)."""
    p_pr = paragraph._p.get_or_add_pPr()
    p_bdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), str(size))
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), color_hex)
    p_bdr.append(bottom)
    p_pr.append(p_bdr)


def build_letterhead_docx() -> bytes:
    """Render an editable DOCX letterhead template."""
    doc = Document()

    # --- Page margins ---
    section = doc.sections[0]
    section.top_margin = Mm(22)
    section.bottom_margin = Mm(22)
    section.left_margin = Mm(20)
    section.right_margin = Mm(20)
    section.header_distance = Mm(10)
    section.footer_distance = Mm(10)

    # ========== HEADER ==========
    header = section.header

    # Clear the default blank paragraph so we can lay things out explicitly.
    for p in list(header.paragraphs):
        p.text = ""

    # Two-column header using a 1x2 borderless table so left/right align
    # survive OneDrive / Word Online round-trips (floating text frames
    # don't).
    header_tbl = header.add_table(rows=1, cols=2, width=Mm(170))
    header_tbl.autofit = False
    header_tbl.columns[0].width = Mm(100)
    header_tbl.columns[1].width = Mm(70)

    # Remove table borders (both cells)
    for row in header_tbl.rows:
        for cell in row.cells:
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            tc_pr = cell._tc.get_or_add_tcPr()
            tc_borders = OxmlElement("w:tcBorders")
            for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
                b = OxmlElement(f"w:{edge}")
                b.set(qn("w:val"), "nil")
                tc_borders.append(b)
            tc_pr.append(tc_borders)

    left_cell, right_cell = header_tbl.rows[0].cells

    # Left: Vaulted wordmark + product-of
    p1 = left_cell.paragraphs[0]
    p1.alignment = WD_ALIGN_PARAGRAPH.LEFT
    _run(p1, "VAULTED", bold=True, size=22, color=_INK_HEX)
    p2 = left_cell.add_paragraph()
    _run(p2, "A product of Phoenix-Atlas Technologies Ltd",
         italic=True, size=9, color=_SUBTLE_HEX)

    # Right: contact block
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

    # Gold rule below header
    rule_p = header.add_paragraph()
    _add_horizontal_rule(rule_p, _GOLD_HEX, size=12)

    # ========== BODY — placeholder paragraphs for the user to type over ==========
    date_p = doc.add_paragraph()
    date_p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _run(date_p, datetime.now(timezone.utc).strftime("%d %B %Y"),
         size=10, color=_SUBTLE_HEX)

    doc.add_paragraph()  # spacer

    # Recipient block
    recip = doc.add_paragraph()
    _run(recip, "[Recipient name]", size=11, color=_INK_HEX)
    _run(recip.add_run().add_break() or recip, "", size=11)  # safe break noop

    recip2 = doc.add_paragraph()
    _run(recip2, "[Recipient title / company]", size=11, color=_INK_HEX)
    recip3 = doc.add_paragraph()
    _run(recip3, "[Recipient address, line 1]", size=11, color=_INK_HEX)
    recip4 = doc.add_paragraph()
    _run(recip4, "[Recipient address, line 2]", size=11, color=_INK_HEX)

    doc.add_paragraph()

    salutation = doc.add_paragraph()
    _run(salutation, "Dear [Name],", size=11, color=_INK_HEX)

    doc.add_paragraph()

    body = doc.add_paragraph()
    _run(body,
         "[Type your letter here. This template keeps the Phoenix-Atlas / "
         "Vaulted branding on every page you add — the header and footer "
         "repeat automatically.]",
         italic=True, size=11, color=_SUBTLE_HEX)

    doc.add_paragraph()
    doc.add_paragraph()

    signoff = doc.add_paragraph()
    _run(signoff, "Yours sincerely,", size=11, color=_INK_HEX)
    doc.add_paragraph()
    doc.add_paragraph()
    doc.add_paragraph()

    name = doc.add_paragraph()
    _run(name, "Umar Sani", bold=True, size=11, color=_INK_HEX)
    role = doc.add_paragraph()
    _run(role, "Founder & CEO, Phoenix-Atlas Technologies Ltd",
         size=10, color=_SUBTLE_HEX)

    # ========== FOOTER ==========
    footer = section.footer
    for p in list(footer.paragraphs):
        p.text = ""

    # Gold rule above footer text
    rule_f = footer.paragraphs[0]
    _add_horizontal_rule(rule_f, _GOLD_HEX, size=12)

    footer_tbl = footer.add_table(rows=1, cols=2, width=Mm(170))
    footer_tbl.autofit = False
    footer_tbl.columns[0].width = Mm(120)
    footer_tbl.columns[1].width = Mm(50)
    for row in footer_tbl.rows:
        for cell in row.cells:
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            tc_pr = cell._tc.get_or_add_tcPr()
            tc_borders = OxmlElement("w:tcBorders")
            for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
                b = OxmlElement(f"w:{edge}")
                b.set(qn("w:val"), "nil")
                tc_borders.append(b)
            tc_pr.append(tc_borders)

    lf, rf = footer_tbl.rows[0].cells
    fp1 = lf.paragraphs[0]
    _run(fp1, "Phoenix-Atlas Technologies Ltd  ·  Companies House 16712430  "
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

    # ========== Serialise ==========
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()
