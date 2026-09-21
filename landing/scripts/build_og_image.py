"""Generate the /landing OG social card (1200x630).

Regenerate whenever the brand copy changes:
    python /app/landing/scripts/build_og_image.py

Outputs /app/landing/og-image.png. The landing HTML references it via
absolute URL: https://app.phoenix-atlas.com/og-image.png so Twitter,
LinkedIn, Slack, WhatsApp and iMessage all see the same asset.

Design uses the same palette as index.html (#0A0807 bg, #C9A35B brand,
#F5E9C9 cream) so shares feel continuous with the landing itself.
"""
from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# -- Palette --------------------------------------------------------------
BG          = (10, 8, 7)         # #0A0807
BG_ELEV     = (22, 18, 16)       # #161210
BG_CARD     = (31, 24, 21)       # #1F1815
GOLD        = (201, 163, 91)     # #C9A35B
GOLD_LIGHT  = (230, 200, 121)    # #E6C879
GOLD_CREAM  = (245, 233, 201)    # #F5E9C9
TEXT_SEC    = (168, 152, 120)    # #A89878
TEXT_MUTED  = (107, 95, 74)      # #6B5F4A
BORDER      = (61, 47, 34)       # subtle dark-gold border

# -- Canvas ---------------------------------------------------------------
W, H = 1200, 630
img = Image.new("RGB", (W, H), BG)
dr = ImageDraw.Draw(img)

# -- Fonts ---------------------------------------------------------------
def _font(family: str, size: int) -> ImageFont.FreeTypeFont:
    """Load a font by fontconfig-resolvable name, falling back if missing."""
    candidates = {
        "sans":       "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "sans-bold":  "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "serif-it":   "/usr/share/fonts/truetype/liberation/LiberationSerif-BoldItalic.ttf",
        "mono":       "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
    }
    path = candidates.get(family)
    if path and Path(path).exists():
        return ImageFont.truetype(path, size)
    return ImageFont.load_default()


F_LOGO_V     = _font("sans-bold", 72)
F_WORDMARK   = _font("serif-it", 54)
F_HEAD       = _font("sans-bold", 96)     # main headline
F_SUB        = _font("sans-bold", 40)     # sub-headline (kes amount line)
F_TAG        = _font("sans", 26)          # tagline
F_TAG_BOLD   = _font("sans-bold", 26)
F_FLAGS      = _font("sans", 44)          # flags rendered as text
F_META       = _font("sans", 18)          # bottom meta
F_META_BOLD  = _font("sans-bold", 18)

# -- Background flourishes -----------------------------------------------
# Subtle gold "V" watermark in top-right, low-opacity via a compositing
# trick: draw on a separate layer and paste with alpha.
def draw_watermark_v() -> None:
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    # Massive translucent "V" bottom-right — style accent.
    huge_v_font = _font("serif-it", 620)
    ld.text((W - 380, H - 640), "V", font=huge_v_font, fill=(*GOLD, 14))  # 14/255 ≈ 5.5% opacity
    img.paste(layer, (0, 0), layer)


draw_watermark_v()

# -- Left column ----------------------------------------------------------
LEFT_X = 72

# Logo tile — small gold rounded square with a white V.
tile_x, tile_y, tile_sz = LEFT_X, 72, 76
tile_radius = 18
dr.rounded_rectangle(
    (tile_x, tile_y, tile_x + tile_sz, tile_y + tile_sz),
    radius=tile_radius, fill=GOLD,
)
# Center V inside tile
bbox = dr.textbbox((0, 0), "V", font=F_LOGO_V)
v_w, v_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
dr.text(
    (tile_x + (tile_sz - v_w) / 2 - bbox[0], tile_y + (tile_sz - v_h) / 2 - bbox[1] - 2),
    "V", font=F_LOGO_V, fill=(255, 255, 255),
)
# "Vaulted" serif-italic to the right of the tile
dr.text((tile_x + tile_sz + 20, tile_y + 8), "Vaulted", font=F_WORDMARK, fill=GOLD_LIGHT)

# -- Headline (main claim) ------------------------------------------------
# Left column is only ~680px wide (receipt card starts at x=740). Keep
# headline lines short enough to fit that width at 96pt — measured, not
# eyeballed. Copy chosen to lean on the receipt card as visual proof.
HEAD_Y = 190
dr.text((LEFT_X, HEAD_Y),      "Cheap. Fast.",     font=F_HEAD, fill=GOLD_CREAM)
dr.text((LEFT_X, HEAD_Y + 108), "Self-custody.",   font=F_HEAD, fill=GOLD_CREAM)

# -- Tagline --------------------------------------------------------------
TAG_Y = HEAD_Y + 108 + 118
dr.text((LEFT_X, TAG_Y),
        "UK to Africa remittance without the wait.",
        font=F_TAG, fill=TEXT_SEC)
dr.text((LEFT_X, TAG_Y + 36),
        "Fiat in, fiat out \u2014 crypto rails underneath.",
        font=F_TAG, fill=TEXT_SEC)

# -- Flags row (live corridors) ------------------------------------------
# NotoColorEmoji only ships at fixed 109px — render at native size on a
# small transparent layer, then resize before pasting so the flags don't
# collide with the legal footer.
try:
    emoji_font_path = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"
    if not Path(emoji_font_path).exists():
        raise RuntimeError("no emoji font")
    emoji_font = ImageFont.truetype(emoji_font_path, size=109)
    flags = ["🇰🇪", "🇬🇭", "🇹🇿", "🇿🇲"]
    # Render each flag onto its own 109x120 canvas (RGBA), then resize to
    # ~52px tall so we control the on-page footprint precisely.
    target_h = 50
    scale = target_h / 72   # NotoColorEmoji glyphs render ~72px tall
    tile_w = int(112 * scale)     # ~78px each after resize
    gap = 12
    FLAG_Y = TAG_Y + 88
    cursor_x = LEFT_X
    for f in flags:
        # Big source: transparent 130x120 to comfortably contain the emoji
        src = Image.new("RGBA", (130, 130), (0, 0, 0, 0))
        sd = ImageDraw.Draw(src)
        sd.text((0, 0), f, font=emoji_font, embedded_color=True)
        # Resize preserving alpha
        w_scaled, h_scaled = int(130 * scale), int(130 * scale)
        src = src.resize((w_scaled, h_scaled), Image.LANCZOS)
        img.paste(src, (cursor_x, FLAG_Y), src)
        cursor_x += tile_w + gap
    # "live now" caption to the right of the flags
    dr.text((cursor_x + 4, FLAG_Y + 14), "live now",
            font=_font("sans-bold", 22), fill=GOLD)
except Exception:
    # Fallback: render ISO codes as gold pills
    FLAG_Y = TAG_Y + 88
    codes = ["KE", "GH", "TZ", "ZM"]
    cursor = LEFT_X
    for c in codes:
        pill_w = 74
        dr.rounded_rectangle(
            (cursor, FLAG_Y, cursor + pill_w, FLAG_Y + 40),
            radius=20, outline=GOLD, width=2,
        )
        bbox = dr.textbbox((0, 0), c, font=F_TAG_BOLD)
        tw = bbox[2] - bbox[0]
        dr.text((cursor + (pill_w - tw) / 2 - bbox[0], FLAG_Y + 5),
                c, font=F_TAG_BOLD, fill=GOLD_LIGHT)
        cursor += pill_w + 12

# -- Right column: "receipt" card ----------------------------------------
CARD_X, CARD_Y = 740, 130
CARD_W, CARD_H = 380, 380
dr.rounded_rectangle(
    (CARD_X, CARD_Y, CARD_X + CARD_W, CARD_Y + CARD_H),
    radius=28, fill=BG_CARD, outline=BORDER, width=2,
)

# LIVE badge (top-right of card)
badge_w, badge_h = 78, 26
badge_x = CARD_X + CARD_W - badge_w - 20
badge_y = CARD_Y + 20
dr.rounded_rectangle(
    (badge_x, badge_y, badge_x + badge_w, badge_y + badge_h),
    radius=13, fill=GOLD,
)
badge_label = "SANDBOX"
badge_bbox = dr.textbbox((0, 0), badge_label, font=_font("sans-bold", 13))
badge_lw = badge_bbox[2] - badge_bbox[0]
dr.text((badge_x + (badge_w - badge_lw) / 2 - badge_bbox[0], badge_y + 5),
        badge_label, font=_font("sans-bold", 13), fill=BG)

# "You send" label + amount
dr.text((CARD_X + 32, CARD_Y + 30), "YOU SEND", font=_font("sans-bold", 14), fill=TEXT_MUTED)
dr.text((CARD_X + 32, CARD_Y + 52), "£50.00",   font=_font("sans-bold", 54), fill=GOLD_CREAM)
dr.text((CARD_X + 194, CARD_Y + 82), "GBP",     font=_font("sans", 22), fill=TEXT_SEC)

# Divider
dr.line((CARD_X + 32, CARD_Y + 155, CARD_X + CARD_W - 32, CARD_Y + 155),
        fill=BORDER, width=1)

# Down-arrow (unicode ↓ rendered as text)
dr.text((CARD_X + CARD_W // 2 - 12, CARD_Y + 145), "\u2193",
        font=_font("sans-bold", 32), fill=GOLD)

# "Recipient gets" label + amount
dr.text((CARD_X + 32, CARD_Y + 205), "RECIPIENT GETS", font=_font("sans-bold", 14), fill=TEXT_MUTED)
dr.text((CARD_X + 32, CARD_Y + 227), "8,631",           font=_font("sans-bold", 54), fill=GOLD_LIGHT)
dr.text((CARD_X + 210, CARD_Y + 257), "KES",           font=_font("sans", 22), fill=TEXT_SEC)

# Footer inside card: via + settlement
dr.line((CARD_X + 32, CARD_Y + 310, CARD_X + CARD_W - 32, CARD_Y + 310),
        fill=BORDER, width=1)
dr.text((CARD_X + 32, CARD_Y + 325), "M-Pesa \u00b7 fee \u00a30.75 \u00b7 ~30 sec",
        font=_font("sans", 18), fill=TEXT_SEC)

# -- Bottom-left legal footer --------------------------------------------
FOOTER_Y = H - 46
dr.text((LEFT_X, FOOTER_Y),
        "Phoenix-Atlas Technologies Ltd \u00b7 UK Co. No. 17432346 \u00b7 phoenix-atlas.com",
        font=F_META, fill=TEXT_MUTED)

# -- Save -----------------------------------------------------------------
out = Path(__file__).resolve().parent.parent / "og-image.png"
img.save(out, "PNG", optimize=True, quality=95)
print(f"wrote {out} ({out.stat().st_size / 1024:.1f} KB, {W}x{H})")
