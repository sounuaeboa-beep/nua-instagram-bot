"""Art engine: the 4:5 feed post (photo on top, headline strip below, so text never covers the product) and the
branded text cards used in carousels.

    render_post(image, headline, subheadline, name) -> Path
    render_card(title, body, index, total, name) -> Path
    render_list_card(title, rows, footnote, index, total, name) -> Path
CLI:  python scripts/generate_art.py <product> <headline> [subheadline]   (random library photo, for a quick look)
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output"
FONT_BOLD = ROOT / "assets" / "fonts" / "Poppins-Bold.ttf"
FONT_MEDIUM = ROOT / "assets" / "fonts" / "Poppins-Medium.ttf"

WIDTH, PHOTO_H, STRIP_H = 1080, 1080, 270          # 1080x1350 = Instagram 4:5 portrait
CARD_H = PHOTO_H + STRIP_H
STRIP_BG, HEADLINE_COLOR, SUB_COLOR = "#F3EEE8", "#2B2623", "#6B625C"
ACCENT, BODY_COLOR = "#A9685F", "#4A423D"
MARGIN_X = 70


def cover_crop(img: Image.Image, width: int, height: int) -> Image.Image:
    scale = max(width / img.width, height / img.height)
    img = img.resize((round(img.width * scale), round(img.height * scale)), Image.Resampling.LANCZOS)
    left, top = (img.width - width) // 2, (img.height - height) // 2
    return img.crop((left, top, left + width, top + height))


def polish(img: Image.Image) -> Image.Image:
    return ImageEnhance.Color(ImageEnhance.Contrast(img).enhance(1.03)).enhance(1.05)


def wrap(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    lines, current = [], ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if font.getlength(trial) <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    return lines + [current] if current else lines


def fit(text: str, font_path: Path, start_size: int, min_size: int, max_lines: int, max_width: int):
    """Largest font size (down to min_size) at which the text fits in max_lines."""
    for size in range(start_size, min_size - 1, -2):
        font = ImageFont.truetype(str(font_path), size)
        lines = wrap(text, font, max_width)
        if len(lines) <= max_lines:
            return font, lines
    return font, lines


def _save(img: Image.Image, name: str) -> Path:
    OUTPUT_DIR.mkdir(exist_ok=True)
    out = OUTPUT_DIR / f"{name}.png"
    img.convert("RGB").save(out, "PNG", optimize=True)
    return out


def render_post(image: Image.Image, headline: str, subheadline: str, name: str) -> Path:
    if not headline.strip():
        raise ValueError("headline is required")
    canvas = Image.new("RGB", (WIDTH, CARD_H), STRIP_BG)
    canvas.paste(polish(cover_crop(image.convert("RGB"), WIDTH, PHOTO_H)), (0, 0))
    draw = ImageDraw.Draw(canvas)

    text_width = WIDTH - 2 * MARGIN_X
    h_font, h_lines = fit(headline.upper(), FONT_BOLD, 58, 36, 2, text_width)
    s_font, s_lines = fit(subheadline, FONT_MEDIUM, 32, 22, 2, text_width) if subheadline.strip() else (None, [])
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
    return _save(canvas, name)


def _card_frame(index: int, total: int):
    canvas = Image.new("RGB", (WIDTH, CARD_H), STRIP_BG)
    draw = ImageDraw.Draw(canvas)
    draw.rectangle([MARGIN_X, 110, MARGIN_X + 90, 118], fill=ACCENT)
    brand = ImageFont.truetype(str(FONT_BOLD), 40)
    draw.text((MARGIN_X, CARD_H - 110), "nu.a", font=brand, fill=ACCENT, anchor="ls")
    small = ImageFont.truetype(str(FONT_MEDIUM), 30)
    draw.text((WIDTH - MARGIN_X, CARD_H - 110), f"{index}/{total}", font=small, fill=SUB_COLOR, anchor="rs")
    return canvas, draw


def render_card(title: str, body: str, index: int, total: int, name: str) -> Path:
    canvas, draw = _card_frame(index, total)
    width = WIDTH - 2 * MARGIN_X
    t_font, t_lines = fit(title, FONT_BOLD, 84, 52, 4, width)
    b_font, b_lines = fit(body, FONT_MEDIUM, 46, 32, 9, width)
    t_step, b_step = round(t_font.size * 1.22), round(b_font.size * 1.45)
    block = len(t_lines) * t_step + 40 + len(b_lines) * b_step
    y = max(190, (CARD_H - block) // 2 - 40)           # centre the text block on the card
    for line in t_lines:
        draw.text((MARGIN_X, y), line, font=t_font, fill=HEADLINE_COLOR)
        y += t_step
    y += 40
    for line in b_lines:
        draw.text((MARGIN_X, y), line, font=b_font, fill=BODY_COLOR)
        y += b_step
    return _save(canvas, name)


def render_list_card(title: str, rows: list[tuple[str, str, str]], footnote: str, index: int, total: int,
                     name: str) -> Path:
    """rows = (label, value, small note). Used for the price card of multipack carousels."""
    canvas, draw = _card_frame(index, total)
    width = WIDTH - 2 * MARGIN_X
    t_font, t_lines = fit(title, FONT_BOLD, 84, 52, 3, width)
    label_font = ImageFont.truetype(str(FONT_BOLD), 48)
    note_font = ImageFont.truetype(str(FONT_MEDIUM), 30)
    y = 190
    for line in t_lines:
        draw.text((MARGIN_X, y), line, font=t_font, fill=HEADLINE_COLOR)
        y += round(t_font.size * 1.22)
    y += 50
    for label, value, note in rows:
        draw.line([(MARGIN_X, y), (WIDTH - MARGIN_X, y)], fill="#D9CFC6", width=2)
        draw.text((MARGIN_X, y + 36), label, font=label_font, fill=HEADLINE_COLOR)
        draw.text((WIDTH - MARGIN_X, y + 36), value, font=label_font, fill=ACCENT, anchor="ra")
        if note:
            draw.text((MARGIN_X, y + 100), note, font=note_font, fill=SUB_COLOR)
        y += 160
    draw.text((MARGIN_X, y + 30), footnote, font=note_font, fill=BODY_COLOR)
    return _save(canvas, name)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("Usage: python scripts/generate_art.py <product> <headline> [subheadline]")
    import photos
    photo = photos.choose(sys.argv[1], None, 1, set(), None)[0]
    print(render_post(photo.image, sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "", f"post_{sys.argv[1]}"))
