"""Art for Instagram Stories: 1080x1920 (9:16). Instagram covers the top ~250 px (profile bar) and the bottom ~340 px
(reply bar), so every piece of text lives between y=270 and y=1580.

    story_photo(image, headline, sub, cta, name)            photo on top, headline panel below
    story_card(kicker, title, body, name, dark=False)       big-text card (tips, myth-or-truth)
    story_duo(question, hint, img1, img2, name)             "1 or 2?" two photos stacked
    story_list(kicker, title, rows, footnote, name)         price card
    story_feed(feed_image, name)                            "new in the feed" teaser around the feed post's picture
"""
import re

from PIL import Image, ImageDraw, ImageFont

from generate_art import (ACCENT, BODY_COLOR, FONT_BOLD, FONT_MEDIUM, HEADLINE_COLOR, MARGIN_X, STRIP_BG, SUB_COLOR,
                          _save, cover_crop, fit, polish)

W, H = 1080, 1920
SAFE_TOP, SAFE_BOTTOM = 270, 1580
_EMOJI = re.compile("[\U0001F000-\U0001FFFF☀-➿️‍]")


def clean(text: str) -> str:
    """Poppins has no emoji glyphs: drop them from on-image text instead of drawing empty boxes."""
    return re.sub(r"\s+", " ", _EMOJI.sub("", text or "")).strip()


def _font(path, size):
    return ImageFont.truetype(str(path), size)


def story_photo(image: Image.Image, headline: str, sub: str, cta: str, name: str):
    photo_h = 1230
    canvas = Image.new("RGB", (W, H), STRIP_BG)
    canvas.paste(polish(cover_crop(image.convert("RGB"), W, photo_h)), (0, 0))
    draw = ImageDraw.Draw(canvas)
    width = W - 2 * MARGIN_X
    h_font, h_lines = fit(clean(headline).upper(), FONT_BOLD, 60, 38, 3, width)
    s_font, s_lines = fit(clean(sub), FONT_MEDIUM, 34, 24, 2, width) if clean(sub) else (None, [])
    h_step, s_step = round(h_font.size * 1.25), (round(s_font.size * 1.35) if s_font else 0)
    y = photo_h + 50
    for line in h_lines:
        draw.text((W / 2, y), line, font=h_font, fill=HEADLINE_COLOR, anchor="ma")
        y += h_step
    y += 16
    for line in s_lines:
        draw.text((W / 2, y), line, font=s_font, fill=SUB_COLOR, anchor="ma")
        y += s_step
    if cta:
        draw.text((W / 2, min(y + 40, SAFE_BOTTOM - 40)), cta, font=_font(FONT_BOLD, 32), fill=ACCENT, anchor="ma")
    return _save(canvas, name)


def story_card(kicker: str, title: str, body: str, name: str, dark: bool = False):
    bg, ink, soft = (ACCENT, "#FFFFFF", "#F6E9E4") if dark else (STRIP_BG, HEADLINE_COLOR, BODY_COLOR)
    mark = "#F3EEE8" if dark else ACCENT
    canvas = Image.new("RGB", (W, H), bg)
    draw = ImageDraw.Draw(canvas)
    width = W - 2 * MARGIN_X
    k_font = _font(FONT_BOLD, 38)
    t_font, t_lines = fit(clean(title), FONT_BOLD, 88, 54, 6, width)
    b_font, b_lines = fit(clean(body), FONT_MEDIUM, 46, 32, 8, width) if clean(body) else (None, [])
    t_step = round(t_font.size * 1.22)
    b_step = round(b_font.size * 1.45) if b_font else 0
    block = 22 + 40 + len(t_lines) * t_step + (40 + len(b_lines) * b_step if b_lines else 0)
    y = max(SAFE_TOP, SAFE_TOP + (SAFE_BOTTOM - SAFE_TOP - block) // 2)
    draw.rectangle([MARGIN_X, y, MARGIN_X + 90, y + 8], fill=mark)
    y += 40
    draw.text((MARGIN_X, y), clean(kicker).upper(), font=k_font, fill=mark)
    y += 62
    for line in t_lines:
        draw.text((MARGIN_X, y), line, font=t_font, fill=ink)
        y += t_step
    y += 40
    for line in b_lines:
        draw.text((MARGIN_X, y), line, font=b_font, fill=soft)
        y += b_step
    draw.text((MARGIN_X, SAFE_BOTTOM - 20), "nu.a", font=_font(FONT_BOLD, 40), fill=mark, anchor="ls")
    return _save(canvas, name)


def story_duo(question: str, hint: str, img1: Image.Image, img2: Image.Image, name: str):
    canvas = Image.new("RGB", (W, H), STRIP_BG)
    draw = ImageDraw.Draw(canvas)
    q_font, q_lines = fit(clean(question), FONT_BOLD, 66, 42, 2, W - 2 * MARGIN_X)
    y = SAFE_TOP
    for line in q_lines:
        draw.text((W / 2, y), line, font=q_font, fill=HEADLINE_COLOR, anchor="ma")
        y += round(q_font.size * 1.22)
    draw.text((W / 2, y + 10), clean(hint), font=_font(FONT_BOLD, 34), fill=ACCENT, anchor="ma")
    top, box_w, box_h, gap = y + 90, 960, 500, 30
    badge = _font(FONT_BOLD, 62)
    for i, img in enumerate((img1, img2)):
        x0, y0 = (W - box_w) // 2, top + i * (box_h + gap)
        tile = polish(cover_crop(img.convert("RGB"), box_w, box_h))
        mask = Image.new("L", (box_w, box_h), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, box_w, box_h], radius=28, fill=255)
        canvas.paste(tile, (x0, y0), mask)
        draw.ellipse([x0 + 24, y0 + 24, x0 + 124, y0 + 124], fill=ACCENT)
        draw.text((x0 + 74, y0 + 77), str(i + 1), font=badge, fill="#FFFFFF", anchor="mm")
    return _save(canvas, name)


def story_list(kicker: str, title: str, rows: list[tuple[str, str, str]], footnote: str, name: str):
    canvas = Image.new("RGB", (W, H), STRIP_BG)
    draw = ImageDraw.Draw(canvas)
    width = W - 2 * MARGIN_X
    t_font, t_lines = fit(clean(title), FONT_BOLD, 84, 52, 3, width)
    label_font, note_font = _font(FONT_BOLD, 52), _font(FONT_MEDIUM, 32)
    t_step = round(t_font.size * 1.22)
    block = 70 + len(t_lines) * t_step + 50 + len(rows) * 170 + 70
    y = max(SAFE_TOP, SAFE_TOP + (SAFE_BOTTOM - SAFE_TOP - block) // 2)
    draw.rectangle([MARGIN_X, y, MARGIN_X + 90, y + 8], fill=ACCENT)
    y += 40
    draw.text((MARGIN_X, y), clean(kicker).upper(), font=_font(FONT_BOLD, 38), fill=ACCENT)
    y += 62
    for line in t_lines:
        draw.text((MARGIN_X, y), line, font=t_font, fill=HEADLINE_COLOR)
        y += t_step
    y += 50
    for label, value, note in rows:
        draw.line([(MARGIN_X, y), (W - MARGIN_X, y)], fill="#D9CFC6", width=2)
        draw.text((MARGIN_X, y + 36), label, font=label_font, fill=HEADLINE_COLOR)
        draw.text((W - MARGIN_X, y + 36), value, font=label_font, fill=ACCENT, anchor="ra")
        if note:
            draw.text((MARGIN_X, y + 106), note, font=note_font, fill=SUB_COLOR)
        y += 170
    draw.text((MARGIN_X, y + 30), footnote, font=note_font, fill=BODY_COLOR)
    return _save(canvas, name)


def story_feed(feed_image: Image.Image, name: str):
    canvas = Image.new("RGB", (W, H), STRIP_BG)
    draw = ImageDraw.Draw(canvas)
    draw.text((W / 2, SAFE_TOP), "NOVO NO FEED", font=_font(FONT_BOLD, 66), fill=ACCENT, anchor="ma")
    draw.text((W / 2, SAFE_TOP + 92), "Acabou de sair. Passa lá e confere!", font=_font(FONT_MEDIUM, 34),
              fill=SUB_COLOR, anchor="ma")
    box_w = 860
    box_h = round(box_w * feed_image.height / feed_image.width)
    box_h = min(box_h, SAFE_BOTTOM - 470)                       # never run into the reply bar
    tile = feed_image.convert("RGB").resize((box_w, box_h), Image.Resampling.LANCZOS)
    mask = Image.new("L", (box_w, box_h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, box_w, box_h], radius=28, fill=255)
    canvas.paste(tile, ((W - box_w) // 2, 470), mask)
    return _save(canvas, name)
