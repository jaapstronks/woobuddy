"""Generate the Open Graph image for WOO Buddy.

Run from repo root (or anywhere) with:

    python3 frontend/static/og-image.gen.py

Writes `og-image.png` (1200x630) next to this script. Committing the generator
alongside the output makes it trivial to regenerate the image if the branding
or copy changes.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

WIDTH, HEIGHT = 1200, 630

# Brand palette (mirrors frontend/src/app.css)
BG = (250, 250, 247)          # --color-bg  #fafaf7
SURFACE = (255, 255, 255)
INK = (26, 31, 44)            # --color-ink #1a1f2c
INK_SOFT = (74, 81, 96)       # --color-ink-soft #4a5160
INK_MUTE = (122, 129, 144)    # --color-ink-mute #7a8190
PRIMARY = (15, 76, 92)        # --color-primary #0f4c5c
ACCENT = (201, 123, 63)       # --color-accent #c97b3f
BORDER = (229, 225, 216)      # --color-border #e5e1d8
PRIMARY_SOFT = (230, 238, 240)
SUCCESS = (45, 106, 79)

# Iowan Old Style matches the site's --font-serif stack (see app.css) and
# ships with macOS, so the OG image uses the exact same display face as the
# landing page. Helvetica Neue Medium is a crisper sans than plain Helvetica
# Bold for the small uppercase / bullet labels.
FONT_IOWAN = "/System/Library/Fonts/Supplemental/Iowan Old Style.ttc"
IOWAN_ROMAN, IOWAN_BOLD, IOWAN_ITALIC, IOWAN_BOLDITALIC, IOWAN_BLACK = 0, 1, 2, 3, 4
FONT_HELVETICA_NEUE = "/System/Library/Fonts/HelveticaNeue.ttc"
HN_REGULAR, HN_BOLD, HN_MEDIUM = 0, 1, 10

HERE = Path(__file__).parent
LOGO_PATH = HERE / "woobuddy-logo.png"


def load_font(path: str, size: int, index: int = 0) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size=size, index=index)
    except Exception:
        return ImageFont.load_default()


def fit_font(
    draw: ImageDraw.ImageDraw,
    text: str,
    path: str,
    index: int,
    start: int,
    min_size: int,
    max_w: int,
) -> tuple[ImageFont.FreeTypeFont, tuple[int, int, int, int]]:
    """Return the largest font ≤ start that renders `text` within max_w px."""
    size = start
    while size > min_size:
        font = load_font(path, size, index=index)
        bbox = draw.textbbox((0, 0), text, font=font)
        if bbox[2] - bbox[0] <= max_w:
            return font, bbox
        size -= 2
    font = load_font(path, min_size, index=index)
    return font, draw.textbbox((0, 0), text, font=font)


def doc_right_margin() -> int:
    """x-coordinate where the right-side document card begins."""
    return WIDTH - 320 - 84


def draw_tracked_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int],
    tracking: int = 0,
) -> int:
    """Draw text with manual letter-spacing, return the total width."""
    x, y = xy
    start_x = x
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        bbox = draw.textbbox((0, 0), ch, font=font)
        x += (bbox[2] - bbox[0]) + tracking
    return x - start_x


def paste_soft_shadow(
    canvas: Image.Image,
    box: tuple[int, int, int, int],
    radius: int,
    offset: tuple[int, int] = (0, 18),
    blur: int = 24,
    opacity: int = 70,
) -> None:
    """Draw a blurred rounded-rect shadow underneath the given box."""
    x0, y0, x1, y1 = box
    pad = blur * 2
    shadow_layer = Image.new(
        "RGBA",
        (canvas.width, canvas.height),
        (0, 0, 0, 0),
    )
    sd = ImageDraw.Draw(shadow_layer)
    sd.rounded_rectangle(
        [
            (x0 + offset[0], y0 + offset[1]),
            (x1 + offset[0], y1 + offset[1]),
        ],
        radius=radius,
        fill=(0, 0, 0, opacity),
    )
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(blur))
    canvas.alpha_composite(shadow_layer)
    _ = pad  # silence unused-var


def main() -> None:
    img = Image.new("RGBA", (WIDTH, HEIGHT), (*BG, 255))
    draw = ImageDraw.Draw(img)

    # Left accent rule running full height — a restrained nod to the
    # "document margin" motif without being literal.
    draw.rectangle([(0, 0), (14, HEIGHT)], fill=PRIMARY)

    # --- Eyebrow chip ------------------------------------------------------
    chip_text = "WERKT 100% IN JE BROWSER"
    chip_font = load_font(FONT_HELVETICA_NEUE, 19, index=HN_MEDIUM)
    chip_tracking = 2  # open the spacing on the uppercase label
    chip_text_w = sum(
        (draw.textbbox((0, 0), ch, font=chip_font)[2]
         - draw.textbbox((0, 0), ch, font=chip_font)[0])
        + chip_tracking
        for ch in chip_text
    ) - chip_tracking
    chip_padding_x, chip_padding_y = 22, 12
    dot_r = 5
    chip_h = 44
    chip_w = chip_text_w + chip_padding_x * 2 + dot_r * 2 + 12
    chip_x, chip_y = 84, 80
    draw.rounded_rectangle(
        [(chip_x, chip_y), (chip_x + chip_w, chip_y + chip_h)],
        radius=chip_h // 2,
        fill=SURFACE,
        outline=BORDER,
        width=2,
    )
    dot_cx = chip_x + chip_padding_x + dot_r
    dot_cy = chip_y + chip_h // 2
    draw.ellipse(
        [(dot_cx - dot_r, dot_cy - dot_r), (dot_cx + dot_r, dot_cy + dot_r)],
        fill=SUCCESS,
    )
    # Vertically center the label inside the chip using its ascent.
    ascent, descent = chip_font.getmetrics()
    text_y = chip_y + (chip_h - (ascent + descent)) // 2
    draw_tracked_text(
        draw,
        (dot_cx + dot_r + 12, text_y),
        chip_text,
        chip_font,
        INK_SOFT,
        tracking=chip_tracking,
    )

    # --- Brand lockup: logo + wordmark ------------------------------------
    # Fit the lockup inside the left column so the document card on the right
    # doesn't clip "Buddy". The card starts at x ≈ 796, so we cap the lockup
    # at ~680 px.
    lockup_x = 84
    lockup_max_w = (WIDTH - doc_right_margin()) - lockup_x - 48
    wordmark_text = "WOO Buddy"
    wordmark_font, wm_bbox = fit_font(
        draw, wordmark_text, FONT_IOWAN, IOWAN_BLACK, start=96, min_size=68,
        max_w=lockup_max_w - 130,  # reserve room for the logo + gap
    )
    wm_h = wm_bbox[3] - wm_bbox[1]
    lockup_y = chip_y + chip_h + 40

    logo_h = wm_h + 12  # slightly taller than the cap-height for optical balance
    if LOGO_PATH.exists():
        logo = Image.open(LOGO_PATH).convert("RGBA")
        ratio = logo_h / logo.height
        logo_w = int(logo.width * ratio)
        logo = logo.resize((logo_w, logo_h), Image.LANCZOS)
        # Lift the logo a touch so its optical center matches the wordmark.
        img.alpha_composite(logo, (lockup_x, lockup_y - 6))
        wordmark_x = lockup_x + logo_w + 22
    else:
        wordmark_x = lockup_x

    draw.text(
        (wordmark_x, lockup_y - wm_bbox[1]),
        wordmark_text,
        font=wordmark_font,
        fill=INK,
    )

    # --- Headline (two lines, fit within left ~720 px) --------------------
    headline_font = load_font(FONT_IOWAN, 52, index=IOWAN_BOLD)
    headline_italic = load_font(FONT_IOWAN, 52, index=IOWAN_ITALIC)
    headline_y = lockup_y + max(wm_h, logo_h) + 36
    draw.text(
        (84, headline_y),
        "Lak Woo-documenten",
        font=headline_font,
        fill=INK,
    )
    draw.text(
        (84, headline_y + 64),
        "zonder uploaden, zonder AI.",
        font=headline_italic,
        fill=PRIMARY,
    )

    # --- Bottom bullet row -------------------------------------------------
    bullet_font = load_font(FONT_HELVETICA_NEUE, 22, index=HN_MEDIUM)
    bullets = ["Geen upload", "Geen AI", "Geen trackers"]
    bullet_y = HEIGHT - 78
    x_cursor = 84
    sep = "  ·  "
    for i, text in enumerate(bullets):
        draw.text((x_cursor, bullet_y), text, font=bullet_font, fill=INK_SOFT)
        bbox = draw.textbbox((0, 0), text, font=bullet_font)
        x_cursor += bbox[2] - bbox[0]
        if i < len(bullets) - 1:
            draw.text((x_cursor, bullet_y), sep, font=bullet_font, fill=INK_MUTE)
            sep_bbox = draw.textbbox((0, 0), sep, font=bullet_font)
            x_cursor += sep_bbox[2] - sep_bbox[0]

    # --- Right-side redaction motif ---------------------------------------
    doc_w, doc_h = 320, 420
    doc_x = WIDTH - doc_w - 84
    doc_y = 120

    paste_soft_shadow(
        img,
        (doc_x, doc_y, doc_x + doc_w, doc_y + doc_h),
        radius=12,
        offset=(0, 20),
        blur=28,
        opacity=55,
    )

    draw.rounded_rectangle(
        [(doc_x, doc_y), (doc_x + doc_w, doc_y + doc_h)],
        radius=12,
        fill=SURFACE,
        outline=BORDER,
        width=2,
    )

    line_margin = 30
    lines: list[tuple[int, tuple[int, int, int]]] = []
    # header block
    lines.append((int(doc_w * 0.55), INK))
    lines.append((int(doc_w * 0.35), INK_MUTE))
    lines.append((0, (0, 0, 0)))
    # paragraph 1
    lines.append((int(doc_w * 0.82), INK_SOFT))
    lines.append((int(doc_w * 0.78), INK_SOFT))
    lines.append((int(doc_w * 0.65), INK_SOFT))
    lines.append((0, (0, 0, 0)))
    # paragraph 2 with a redacted bar mixed in
    lines.append((int(doc_w * 0.85), INK_SOFT))
    lines.append((-1, INK))
    lines.append((int(doc_w * 0.72), INK_SOFT))
    lines.append((0, (0, 0, 0)))
    # paragraph 3
    lines.append((int(doc_w * 0.80), INK_SOFT))
    lines.append((-2, PRIMARY))
    lines.append((int(doc_w * 0.55), INK_SOFT))

    ly = doc_y + 44
    for width, color in lines:
        if width == 0:
            ly += 18
            continue
        if width == -1:
            bar_w = int(doc_w * 0.62)
            draw.rectangle(
                [
                    (doc_x + line_margin, ly),
                    (doc_x + line_margin + bar_w, ly + 14),
                ],
                fill=INK,
            )
        elif width == -2:
            bar_w = int(doc_w * 0.48)
            draw.rectangle(
                [
                    (doc_x + line_margin, ly),
                    (doc_x + line_margin + bar_w, ly + 14),
                ],
                fill=PRIMARY,
            )
        else:
            thickness = 10
            if color == INK:
                thickness = 18
            elif color == INK_MUTE:
                thickness = 12
            draw.rounded_rectangle(
                [
                    (doc_x + line_margin, ly),
                    (doc_x + line_margin + width, ly + thickness),
                ],
                radius=thickness // 2,
                fill=color,
            )
        ly += 26

    # Stamp in bottom right of the document card
    stamp_text = "AVG-proof"
    stamp_font = load_font(FONT_HELVETICA_NEUE, 20, index=HN_BOLD)
    bbox = draw.textbbox((0, 0), stamp_text, font=stamp_font)
    pad_x, pad_y = 14, 8
    sw = bbox[2] - bbox[0] + pad_x * 2
    sh = bbox[3] - bbox[1] + pad_y * 2
    sx = doc_x + doc_w - sw - 20
    sy = doc_y + doc_h - sh - 20
    draw.rounded_rectangle(
        [(sx, sy), (sx + sw, sy + sh)],
        radius=6,
        fill=PRIMARY_SOFT,
        outline=PRIMARY,
        width=2,
    )
    draw.text((sx + pad_x, sy + pad_y - 3), stamp_text, font=stamp_font, fill=PRIMARY)

    out = HERE / "og-image.png"
    img.convert("RGB").save(out, "PNG", optimize=True)
    print(f"wrote {out} ({WIDTH}x{HEIGHT})")


if __name__ == "__main__":
    main()
