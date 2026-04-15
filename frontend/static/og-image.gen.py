"""Generate the Open Graph image for WOO Buddy.

Run from repo root (or anywhere) with:

    python3 frontend/static/og-image.gen.py

Writes `og-image.png` (1200x630) next to this script. Committing the generator
alongside the output makes it trivial to regenerate the image if the branding
or copy changes.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

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

FONT_GEORGIA_BOLD = "/System/Library/Fonts/Supplemental/Georgia Bold.ttf"
FONT_GEORGIA_ITALIC = "/System/Library/Fonts/Supplemental/Georgia Italic.ttf"
FONT_HELVETICA = "/System/Library/Fonts/Helvetica.ttc"


def load_font(path: str, size: int, index: int = 0) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size=size, index=index)
    except Exception:
        return ImageFont.load_default()


def main() -> None:
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)

    # Subtle paper grain by drawing a soft top gradient band
    for y in range(120):
        alpha = int(255 * (1 - y / 120) * 0.25)
        draw.line([(0, y), (WIDTH, y)], fill=(255, 255, 255))

    # Left accent rule running full height — a restrained nod to the
    # "document margin" motif without being literal.
    draw.rectangle([(0, 0), (12, HEIGHT)], fill=PRIMARY)

    # --- Eyebrow chip ------------------------------------------------------
    chip_text = "WERKT 100% IN JE BROWSER"
    chip_font = load_font(FONT_HELVETICA, 20, index=1)  # Bold
    chip_padding_x, chip_padding_y = 20, 10
    chip_bbox = draw.textbbox((0, 0), chip_text, font=chip_font)
    chip_w = chip_bbox[2] - chip_bbox[0] + chip_padding_x * 2 + 22
    chip_h = chip_bbox[3] - chip_bbox[1] + chip_padding_y * 2
    chip_x, chip_y = 80, 80
    draw.rounded_rectangle(
        [(chip_x, chip_y), (chip_x + chip_w, chip_y + chip_h)],
        radius=chip_h // 2,
        fill=SURFACE,
        outline=BORDER,
        width=2,
    )
    dot_r = 5
    dot_cx = chip_x + chip_padding_x + dot_r
    dot_cy = chip_y + chip_h // 2
    draw.ellipse(
        [(dot_cx - dot_r, dot_cy - dot_r), (dot_cx + dot_r, dot_cy + dot_r)],
        fill=(45, 106, 79),  # success green
    )
    draw.text(
        (dot_cx + dot_r + 10, chip_y + chip_padding_y - 2),
        chip_text,
        font=chip_font,
        fill=INK_SOFT,
    )

    # --- Wordmark ----------------------------------------------------------
    wordmark_font = load_font(FONT_GEORGIA_BOLD, 92)
    wordmark_y = chip_y + chip_h + 34
    draw.text((80, wordmark_y), "WOO Buddy", font=wordmark_font, fill=INK)

    # --- Headline (two lines, fit within left ~720 px) --------------------
    headline_font = load_font(FONT_GEORGIA_BOLD, 48)
    headline_y = wordmark_y + 125
    draw.text(
        (80, headline_y),
        "Lak Woo-documenten",
        font=headline_font,
        fill=INK,
    )
    headline_italic = load_font(FONT_GEORGIA_ITALIC, 48)
    draw.text(
        (80, headline_y + 58),
        "zonder uploaden, zonder AI.",
        font=headline_italic,
        fill=PRIMARY,
    )

    # --- Bottom bullet row -------------------------------------------------
    bullet_font = load_font(FONT_HELVETICA, 24, index=1)  # Bold
    bullets = [
        "Geen upload",
        "Geen AI",
        "Geen trackers",
    ]
    bullet_y = HEIGHT - 80
    x_cursor = 80
    sep = " · "
    for i, text in enumerate(bullets):
        draw.text((x_cursor, bullet_y), text, font=bullet_font, fill=INK_SOFT)
        bbox = draw.textbbox((0, 0), text, font=bullet_font)
        x_cursor += bbox[2] - bbox[0]
        if i < len(bullets) - 1:
            draw.text((x_cursor, bullet_y), sep, font=bullet_font, fill=INK_MUTE)
            sep_bbox = draw.textbbox((0, 0), sep, font=bullet_font)
            x_cursor += sep_bbox[2] - sep_bbox[0]

    # --- Right-side redaction motif ---------------------------------------
    # A small fake document with progressive redaction bars — establishes
    # the product category at a glance.
    doc_w, doc_h = 320, 420
    doc_x = WIDTH - doc_w - 80
    doc_y = 120
    # Soft shadow
    for i in range(10):
        draw.rounded_rectangle(
            [(doc_x + i, doc_y + i + 2), (doc_x + doc_w + i, doc_y + doc_h + i + 2)],
            radius=10,
            fill=(0, 0, 0, 0),
            outline=(235, 231, 222),
        )
    draw.rounded_rectangle(
        [(doc_x, doc_y), (doc_x + doc_w, doc_y + doc_h)],
        radius=10,
        fill=SURFACE,
        outline=BORDER,
        width=2,
    )

    # Header line (smaller) — like a document title
    line_margin = 28
    lines: list[tuple[int, tuple[int, int, int]]] = []
    # a header block
    lines.append((int(doc_w * 0.55), INK))
    lines.append((int(doc_w * 0.35), INK_MUTE))
    # spacer
    lines.append((0, (0, 0, 0)))
    # paragraph 1
    lines.append((int(doc_w * 0.82), INK_SOFT))
    lines.append((int(doc_w * 0.78), INK_SOFT))
    lines.append((int(doc_w * 0.65), INK_SOFT))
    lines.append((0, (0, 0, 0)))
    # paragraph 2 with a redacted bar mixed in
    lines.append((int(doc_w * 0.85), INK_SOFT))
    lines.append((-1, INK))  # redaction bar 1
    lines.append((int(doc_w * 0.72), INK_SOFT))
    lines.append((0, (0, 0, 0)))
    # paragraph 3
    lines.append((int(doc_w * 0.80), INK_SOFT))
    lines.append((-2, PRIMARY))  # redaction bar 2
    lines.append((int(doc_w * 0.55), INK_SOFT))

    ly = doc_y + 40
    for width, color in lines:
        if width == 0:
            ly += 18
            continue
        if width == -1:
            # solid ink-black redaction bar
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
            # thickness varies per line role
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
    stamp_font = load_font(FONT_HELVETICA, 20, index=1)
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

    out = Path(__file__).parent / "og-image.png"
    img.save(out, "PNG", optimize=True)
    print(f"wrote {out} ({WIDTH}x{HEIGHT})")


if __name__ == "__main__":
    main()
