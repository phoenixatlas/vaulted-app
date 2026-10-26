"""Shared Vaulted brand mark (brown & gold phoenix + VAULTED wordmark)
used on every generated PDF / DOCX (deck, one-pager, letterhead, receipts,
use-case doc)."""
from __future__ import annotations

from pathlib import Path

from reportlab.lib.utils import ImageReader

LOGO_PATH = Path(__file__).parent / "assets" / "vaulted-logo.png"
_LOGO = ImageReader(str(LOGO_PATH))


def brand_logo_img(size: int) -> str:
    """<img> tag for HTML emails, served publicly from /api/brand/logo.png."""
    import os
    base = (os.environ.get("APP_PUBLIC_URL", "") or "").rstrip("/")
    return (
        f'<img src="{base}/api/brand/logo.png" width="{size}" height="{size}" alt="Vaulted" '
        f'style="display:block;margin:0 auto 14px;border-radius:{size // 5}px;border:0;" />'
    )


def draw_logo(c, x: float, y: float, size: float) -> None:
    """Draw the square logo tile with its bottom-left corner at (x, y)."""
    c.drawImage(_LOGO, x, y, width=size, height=size, mask="auto")
