"""
generate_art.py — Pillow-based art engine for nu.a daily Instagram posts.

Selects a product photo from media/<product>/ and overlays
image_headline + image_subheadline using Poppins fonts.

Public API (used by run_daily.py):
    generate(product: str, headline: str, subheadline: str) -> Path
"""

from __future__ import annotations

import random
import textwrap
from pathlib import Path
from typing import Tuple

from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter

# ---------------------------------------------------------------------------
# Paths (relative to repo root)
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
MEDIA_DIR = REPO_ROOT / "media"
FONTS_DIR = REPO_ROOT / "assets" / "fonts"
OUTPUT_DIR = REPO_ROOT / "output"          # generated images land here
OUTPUT_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Typography & layout constants
# ---------------------------------------------------------------------------
FONT_BOLD = FONTS_DIR / "Poppins-Bold.ttf"
FONT_MEDIUM = FONTS_DIR / "Poppins-Medium.ttf"

# Target Instagram feed size (1:1). We resize/crop the source photo to this.
TARGET_SIZE = (1080, 1080)

# Text safe zone (bottom third, with padding)
PADDING_X = 60
PADDING_BOTTOM = 80
MAX_TEXT_WIDTH_RATIO = 0.85          # % of image width the text block can use

# Visual treatment
DARKEN_OVERLAY_OPACITY = 0.42        # semi-transparent black bar behind text
HEADLINE_SIZE = 64
SUBHEADLINE_SIZE = 36
LINE_SPACING = 12
HEADLINE_TO_SUB_GAP = 18


def _load_font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    if not path.exists():
        raise FileNotFoundError(
            f"Font not found: {path}\n"
            "Expected Poppins-Bold.ttf and Poppins-Medium.ttf in assets/fonts/"
        )
    return ImageFont.truetype(str(path), size)


def _pick_photo(product: str) -> Path:
    """Pick a random photo from media/<product>/."""
    product = product.lower().strip()
    folder = MEDIA_DIR / product

    if not folder.exists():
        raise FileNotFoundError(
            f"No media folder for product '{product}'. "
            f"Expected: {folder}"
        )

    candidates = [
        p for p in folder.iterdir()
        if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
    ]

    if not candidates:
        raise FileNotFoundError(f"No images found in {folder}")

    return random.choice(candidates)


def _resize_and_crop(img: Image.Image, target: Tuple[int, int]) -> Image.Image:
    """Center-crop to target aspect ratio, then resize."""
    target_w, target_h = target
    src_w, src_h = img.size
    src_ratio = src_w / src_h
    target_ratio = target_w / target_h

    if src_ratio > target_ratio:
        # source is wider → crop sides
        new_w = int(src_h * target_ratio)
        left = (src_w - new_w) // 2
        img = img.crop((left, 0, left + new_w, src_h))
    else:
        # source is taller → crop top/bottom
        new_h = int(src_w / target_ratio)
        top = (src_h - new_h) // 2
        img = img.crop((0, top, src_w, top + new_h))

    return img.resize(target, Image.Resampling.LANCZOS)


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Simple word-wrap that respects the font metrics."""
    words = text.split()
    lines: list[str] = []
    current = ""

    for word in words:
        test = f"{current} {word}".strip()
        bbox = font.getbbox(test)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _draw_text_block(
    draw: ImageDraw.ImageDraw,
    img_width: int,
    img_height: int,
    headline: str,
    subheadline: str,
    font_bold: ImageFont.FreeTypeFont,
    font_medium: ImageFont.FreeTypeFont,
) -> None:
    max_text_width = int(img_width * MAX_TEXT_WIDTH_RATIO)

    headline_lines = _wrap_text(headline.upper(), font_bold, max_text_width)
    sub_lines = _wrap_text(subheadline, font_medium, max_text_width) if subheadline else []

    # Calculate total block height
    def line_height(font: ImageFont.FreeTypeFont) -> int:
        bbox = font.getbbox("Ay")
        return bbox[3] - bbox[1]

    h_line_h = line_height(font_bold)
    s_line_h = line_height(font_medium)

    total_h = (
        len(headline_lines) * h_line_h
        + max(0, len(headline_lines) - 1) * LINE_SPACING
        + (HEADLINE_TO_SUB_GAP if sub_lines else 0)
        + len(sub_lines) * s_line_h
        + max(0, len(sub_lines) - 1) * LINE_SPACING
    )

    # Starting Y (bottom-aligned with padding)
    y = img_height - PADDING_BOTTOM - total_h

    # Semi-transparent background bar for readability
    bar_top = y - 40
    bar_bottom = img_height
    overlay = Image.new("RGBA", (img_width, img_height), (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.rectangle(
        [(0, bar_top), (img_width, bar_bottom)],
        fill=(0, 0, 0, int(255 * DARKEN_OVERLAY_OPACITY)),
    )

    # We need to composite later; for now just draw text on the main image
    # (caller will handle the overlay)

    # Center each line
    def draw_centered(lines: list[str], font: ImageFont.FreeTypeFont, start_y: int, fill: str) -> int:
        current_y = start_y
        for line in lines:
            bbox = font.getbbox(line)
            text_w = bbox[2] - bbox[0]
            x = (img_width - text_w) // 2
            draw.text((x, current_y), line, font=font, fill=fill)
            current_y += (bbox[3] - bbox[1]) + LINE_SPACING
        return current_y

    # Draw headline (white)
    y = draw_centered(headline_lines, font_bold, y, "#FFFFFF")

    if sub_lines:
        y += HEADLINE_TO_SUB_GAP - LINE_SPACING  # adjust because draw_centered already added spacing
        draw_centered(sub_lines, font_medium, y, "#F0F0F0")


def generate(product: str, headline: str, subheadline: str = "") -> Path:
    """
    Generate a finished Instagram post image.

    Args:
        product:     one of "essencial", "invisible", "sculpt"
        headline:    short text that goes on the image (image_headline)
        subheadline: secondary text (image_subheadline)

    Returns:
        Path to the generated PNG file.
    """
    if not headline or not headline.strip():
        raise ValueError("headline is required")

    # 1. Pick photo
    photo_path = _pick_photo(product)
    print(f"[art] using photo: {photo_path.name}")

    # 2. Load & prepare base image
    img = Image.open(photo_path).convert("RGB")
    img = _resize_and_crop(img, TARGET_SIZE)

    # Optional subtle polish
    img = ImageEnhance.Contrast(img).enhance(1.05)
    img = ImageEnhance.Color(img).enhance(1.08)

    # 3. Create dark overlay bar for text legibility
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)

    # Calculate text block height first so the bar is the right size
    font_bold = _load_font(FONT_BOLD, HEADLINE_SIZE)
    font_medium = _load_font(FONT_MEDIUM, SUBHEADLINE_SIZE)

    max_text_width = int(TARGET_SIZE[0] * MAX_TEXT_WIDTH_RATIO)
    headline_lines = _wrap_text(headline.upper(), font_bold, max_text_width)
    sub_lines = _wrap_text(subheadline, font_medium, max_text_width) if subheadline else []

    def _lh(font):
        b = font.getbbox("Ay")
        return b[3] - b[1]

    total_text_h = (
        len(headline_lines) * _lh(font_bold)
        + max(0, len(headline_lines) - 1) * LINE_SPACING
        + (HEADLINE_TO_SUB_GAP if sub_lines else 0)
        + len(sub_lines) * _lh(font_medium)
        + max(0, len(sub_lines) - 1) * LINE_SPACING
    )

    bar_top = TARGET_SIZE[1] - PADDING_BOTTOM - total_text_h - 50
    overlay_draw.rectangle(
        [(0, bar_top), (TARGET_SIZE[0], TARGET_SIZE[1])],
        fill=(0, 0, 0, int(255 * DARKEN_OVERLAY_OPACITY)),
    )

    # Composite the dark bar
    img = img.convert("RGBA")
    img = Image.alpha_composite(img, overlay)

    # 4. Draw text
    draw = ImageDraw.Draw(img)
    _draw_text_block(
        draw,
        TARGET_SIZE[0],
        TARGET_SIZE[1],
        headline,
        subheadline,
        font_bold,
        font_medium,
    )

    # 5. Save
    img = img.convert("RGB")
    out_path = OUTPUT_DIR / f"post_{product}_{photo_path.stem}.png"
    img.save(out_path, "PNG", optimize=True)
    print(f"[art] saved → {out_path}")

    return out_path


# ---------------------------------------------------------------------------
# CLI for quick local testing
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python generate_art.py <product> <headline> [subheadline]")
        print("Example:")
        print('  python generate_art.py essencial "Sinta-se em casa no seu corpo" "Essencial • Conforto real"')
        sys.exit(1)

    product = sys.argv[1]
    headline = sys.argv[2]
    subheadline = sys.argv[3] if len(sys.argv) > 3 else ""

    path = generate(product, headline, subheadline)
    print(f"\nDone → {path}")
    
