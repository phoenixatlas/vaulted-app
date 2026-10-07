"""Use case document router — serves tailored partner/investor briefs.

Primary artefact today: a two-page, letterhead-branded PSB use case
pitched as a **strategic partnership + equity** play. Default
parameterisation targets 9PSB; all content fields can be overridden via
query string so Umar can regenerate for any Nigerian PSB (MoMo PSB,
SmartCash PSB, Hope PSB, Globacom-approved) without a code change.

Routes
------
GET /api/usecase/psb.pdf          → Two-page A4 PDF (print/email-ready)
GET /api/usecase/psb.docx         → Fully editable Word doc (OneDrive-friendly)
GET /api/usecase/psb/preview      → JSON preview of resolved content

Both PDF/DOCX endpoints accept these optional query parameters:
  bank_name, bank_short, recipient_name, recipient_title,
  recipient_address_1, recipient_address_2, salutation, subject

Example (SmartCash):
    /api/usecase/psb.pdf?bank_short=SmartCash&bank_name=SmartCash Payment
     Service Bank Ltd&recipient_name=The Managing Director
"""
from __future__ import annotations

from io import BytesIO
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from usecase import build_psb_usecase_pdf, build_psb_usecase_docx, _default_content

router = APIRouter()


def _collect_overrides(
    bank_name: Optional[str],
    bank_short: Optional[str],
    recipient_name: Optional[str],
    recipient_title: Optional[str],
    recipient_address_1: Optional[str],
    recipient_address_2: Optional[str],
    salutation: Optional[str],
    subject: Optional[str],
) -> dict:
    """Compact dict of only the non-None overrides so dataclass defaults
    survive untouched fields."""
    return {k: v for k, v in {
        "bank_name": bank_name,
        "bank_short": bank_short,
        "recipient_name": recipient_name,
        "recipient_title": recipient_title,
        "recipient_address_1": recipient_address_1,
        "recipient_address_2": recipient_address_2,
        "salutation": salutation,
        "subject": subject,
    }.items() if v is not None}


@router.get("/usecase/psb.pdf")
async def usecase_psb_pdf(
    bank_name: Optional[str] = Query(None),
    bank_short: Optional[str] = Query(None),
    recipient_name: Optional[str] = Query(None),
    recipient_title: Optional[str] = Query(None),
    recipient_address_1: Optional[str] = Query(None),
    recipient_address_2: Optional[str] = Query(None),
    salutation: Optional[str] = Query(None),
    subject: Optional[str] = Query(None),
):
    """Serve the two-page PSB use case PDF."""
    overrides = _collect_overrides(bank_name, bank_short, recipient_name,
                                   recipient_title, recipient_address_1,
                                   recipient_address_2, salutation, subject)
    pdf_bytes = build_psb_usecase_pdf(**overrides)
    short = overrides.get("bank_short", "9PSB")
    filename = f"Vaulted-UseCase-{short}.pdf"
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/usecase/psb.docx")
async def usecase_psb_docx(
    bank_name: Optional[str] = Query(None),
    bank_short: Optional[str] = Query(None),
    recipient_name: Optional[str] = Query(None),
    recipient_title: Optional[str] = Query(None),
    recipient_address_1: Optional[str] = Query(None),
    recipient_address_2: Optional[str] = Query(None),
    salutation: Optional[str] = Query(None),
    subject: Optional[str] = Query(None),
):
    """Serve the editable PSB use case Word document."""
    overrides = _collect_overrides(bank_name, bank_short, recipient_name,
                                   recipient_title, recipient_address_1,
                                   recipient_address_2, salutation, subject)
    docx_bytes = build_psb_usecase_docx(**overrides)
    short = overrides.get("bank_short", "9PSB")
    filename = f"Vaulted-UseCase-{short}.docx"
    return StreamingResponse(
        BytesIO(docx_bytes),
        media_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/usecase/psb/preview")
async def usecase_psb_preview(
    bank_name: Optional[str] = Query(None),
    bank_short: Optional[str] = Query(None),
):
    """Debug / UI helper — returns the resolved content so the admin page
    can preview section titles without re-downloading the full artefact."""
    content = _default_content(**_collect_overrides(
        bank_name, bank_short, None, None, None, None, None, None,
    ))
    return {
        "bank_name": content.bank_name,
        "bank_short": content.bank_short,
        "subject": content.subject,
        "sections": {
            "opportunity_stats": content.opportunity_stats,
            "strategic_fit": [t for t, _ in content.strategic_fit],
            "integration_steps": [t for t, _ in content.integration_steps],
            "commercial_options": [t for t, _ in content.commercial_options],
            "roadmap_phases": [t for t, _ in content.roadmap_phases],
            "next_steps_count": len(content.next_steps),
        },
    }
