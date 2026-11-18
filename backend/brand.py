"""Shared Vaulted brand mark (brown & gold phoenix + VAULTED wordmark)
used on every generated PDF / DOCX (deck, one-pager, letterhead, receipts,
use-case doc)."""
from __future__ import annotations

from pathlib import Path

from reportlab.lib.utils import ImageReader

LOGO_PATH = Path(__file__).parent / "assets" / "vaulted-logo.png"
_LOGO = ImageReader(str(LOGO_PATH))


import os

# Emails always load the logo from the live server (independent of APP_PUBLIC_URL,
# which points at the web app for reset / KYC links).
LOGO_URL = os.environ.get("BRAND_LOGO_URL", "https://vaulted-app.onrender.com/api/brand/logo.png")


def brand_logo_img(size: int) -> str:
    """<img> tag for HTML emails."""
    return (
        f'<img src="{LOGO_URL}" width="{size}" height="{size}" alt="Vaulted" '
        f'style="display:block;margin:0 auto 14px;border-radius:{size // 5}px;border:0;" />'
    )


def draw_logo(c, x: float, y: float, size: float) -> None:
    """Draw the square logo tile with its bottom-left corner at (x, y)."""
    c.drawImage(_LOGO, x, y, width=size, height=size, mask="auto")


# ---- Phoenix-Atlas company logo (letterheads, company emails) -------------------
COMPANY_LOGO_PATH = Path(__file__).parent / "assets" / "phoenix-atlas-logo.png"      # horizontal, transparent
COMPANY_EMBLEM_PATH = Path(__file__).parent / "assets" / "phoenix-atlas-emblem.png"  # phoenix + globe, transparent
_COMPANY_LOGO = ImageReader(str(COMPANY_LOGO_PATH))
COMPANY_LOGO_RATIO = 1432 / 546
COMPANY_LOGO_URL = os.environ.get("COMPANY_LOGO_URL", LOGO_URL.replace("/brand/logo.png", "/brand/company-logo.png"))


def draw_company_logo(c, x: float, y: float, height: float) -> float:
    """Draw the horizontal Phoenix-Atlas logo (bottom-left at x, y). Returns its width."""
    w = height * COMPANY_LOGO_RATIO
    c.drawImage(_COMPANY_LOGO, x, y, width=w, height=height, mask="auto")
    return w


def company_logo_img(width: int) -> str:
    """<img> tag for company (non-Vaulted) HTML emails."""
    h = round(width / COMPANY_LOGO_RATIO)
    return (f'<img src="{COMPANY_LOGO_URL}" width="{width}" height="{h}" alt="Phoenix-Atlas Technologies Ltd" '
            f'style="display:block;margin:0 auto 18px;border:0;" />')
