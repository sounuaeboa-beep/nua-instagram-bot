"""Builds the daily post image: a photo from media/<product>/ (or media/lifestyle/) on top, with the headline in a clean
text strip underneath (4:5 portrait, 1080x1350). The text never covers the photo, so the product stays visible.

    generate(product, headline, subheadline="", pillar=None) -> Path
CLI:  python scripts/generate_art.py <product> <headline> [subheadline]
"""
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont

ROOT = Path(__file__).resolve().parent.parent
MEDIA_DIR = ROOT / "media"
OUTPUT_DIR = ROOT / "output"
FONT_BOLD = ROOT / "assets" / "fonts" / "Poppins-Bold.ttf"
FONT_MEDIUM = ROOT / "assets" / "fonts" / "Poppins-Medium.ttf"

WIDTH, PHOTO_H, STRIP_H = 1080, 1080, 270          # 1080x1350 = Instagram 4:5 portrait
STRIP_BG, HEADLINE_COLOR, SUB_COLOR = "#F3EEE8", "#2B2623", "#6B625C"
MARGIN_X = 70
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def _photos(folder: Path) -> list[Path]:
    """Photos in a folder, skipping wide landscape ones: a square crop would cut people off at the sides."""
    found = []
    for p in sorted(folder.glob("*")) if folder.exists() else []:
        if p.suffix.lower() in IMAGE_EXTENSIONS:
            with Image.open(p) as im:
                if im.width / im.height <= 1.1:
                    found.append(p)
    return found


def _pick_photo(product: str, pillar: str | None = None) -> Path:
    """Product close-ups by default. Lifestyle (people) shots on 'aspiracional' days and half of 'conforto' days."""
    product_photos = _photos(MEDIA_DIR / product.lower().strip())
    lifestyle_photos = _photos(MEDIA_DIR / "lifestyle")
    use_lifestyle = pillar == "aspiracional" or (pillar == "conforto" and random.random() < 0.5)
    pool = (lifestyle_photos if use_lifestyle else product_photos) or product_photos or lifestyle_photos
    if not pool:
        raise FileNotFoundError(f"No usable photos for '{product}' in media/")
    return random.choice(pool)


def _cover_crop(img: Image.Image, width: int, height: int) -> Image.Image:
    scale = max(width / img.width, height / img.height)
    img = img.resize((round(img.width * scale), round(img.height * scale)), Image.Resampling.LANCZOS)
    left, top = (img.width - width) // 2, (img.height - height) // 2
    return img.crop((left, top, left + width, top + height))


def _wrap(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    lines, current = [], ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if font.getlength(trial) <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    return lines + [current] if current else lines


def _fit(text: str, font_path: Path, start_size: int, min_size: int, max_lines: int, max_width: int):
    """Largest font size (down to min_size) at which the text fits in max_lines."""
    for size in range(start_size, min_size - 1, -2):
        font = ImageFont.truetype(str(font_path), size)
        lines = _wrap(text, font, max_width)
        if len(lines) <= max_lines:
            return font, lines
    return font, lines


def generate(product: str, headline: str, subheadline: str = "", pillar: str | None = None) -> Path:
    if not headline.strip():
        raise ValueError("headline is required")

    photo_path = _pick_photo(product, pillar)
    print(f"[art] using photo: {photo_path.name}")

    photo = _cover_crop(Image.open(photo_path).convert("RGB"), WIDTH, PHOTO_H)
    photo = ImageEnhance.Color(ImageEnhance.Contrast(photo).enhance(1.03)).enhance(1.05)

    canvas = Image.new("RGB", (WIDTH, PHOTO_H + STRIP_H), STRIP_BG)
    canvas.paste(photo, (0, 0))
    draw = ImageDraw.Draw(canvas)

    text_width = WIDTH - 2 * MARGIN_X
    h_font, h_lines = _fit(headline.upper(), FONT_BOLD, 58, 36, 2, text_width)
    s_font, s_lines = _fit(subheadline, FONT_MEDIUM, 32, 22, 2, text_width) if subheadline.strip() else (None, [])

    h_step, s_step = round(h_font.size * 1.25), (round(s_font.size * 1.35) if s_font else 0)
    block_h = len(h_lines) * h_step + (18 + len(s_lines) * s_step if s_lines else 0)
    y = PHOTO_H + (STRIP_H - block_h) // 2

    for line in h_lines:
        draw.text((WIDTH / 2, y), line, font=h_font, fill=HEADLINE_COLOR, anchor="ma")
        y += h_step
    y += 18
    for line in s_lines:
        draw.text((WIDTH / 2, y), line, font=s_font, fill=SUB_COLOR, anchor="ma")
        y += s_step

    OUTPUT_DIR.mkdir(exist_ok=True)
    out = OUTPUT_DIR / f"post_{product}_{photo_path.stem}.png"
    canvas.save(out, "PNG", optimize=True)
    print(f"[art] saved -> {out}")
    return out


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit('Usage: python scripts/generate_art.py <product> <headline> [subheadline]')
    print(generate(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else ""))
