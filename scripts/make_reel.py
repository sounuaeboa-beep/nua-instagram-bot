"""Builds a short vertical Reel (1080x1920, 9.5 or 13 s) from 3-4 photos: slow zoom-in, zoom-out or sideways drift per
photo with soft cross-fades, the headline in a clean strip, and a "link na bio" end card. Uses the ffmpeg binary
bundled with imageio-ffmpeg, so nothing needs installing on the machine.

    make_reel(photos, headline, subheadline, cta_label, name) -> Path     (photos = photos.Photo objects)
"""
import random
import subprocess
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw

import generate_art as art

W, H, FPS = 1080, 1920, 25
PHOTO_W, PHOTO_H, PHOTO_Y = 1080, 1350, 140        # 4:5 photo area, same look as the feed post
CLIP_S, FADE_S, CTA_S = 3.5, 0.5, 2.5              # seconds per photo, cross-fade, end-card length
TEXT_Y0, TEXT_Y1 = 1490, 1760                      # headline strip; the bottom ~160 px stay free for Reels buttons
SOURCE_SCALE = 1.2                                 # prepare photos larger than shown so the zoom stays sharp
MOTIONS = ["in", "out", "pan"]


def _motion(kind: str, frames: int) -> str:
    centre_y = "y='ih/2-ih/zoom/2'"
    if kind == "in":
        return f"z='1+0.1*on/{frames}':x='iw/2-iw/zoom/2':{centre_y}"
    if kind == "out":
        return f"z='1.1-0.1*on/{frames}':x='iw/2-iw/zoom/2':{centre_y}"
    return f"z='1.1':x='(iw-iw/zoom)*on/{frames}':{centre_y}"      # slow drift left to right


def _strip_text(draw: ImageDraw.ImageDraw, headline: str, subheadline: str) -> None:
    width = W - 2 * art.MARGIN_X
    h_font, h_lines = art.fit(headline.upper(), art.FONT_BOLD, 62, 40, 2, width)
    s_font, s_lines = art.fit(subheadline, art.FONT_MEDIUM, 34, 24, 2, width) if subheadline.strip() else (None, [])
    h_step, s_step = round(h_font.size * 1.25), (round(s_font.size * 1.35) if s_font else 0)
    block = len(h_lines) * h_step + (18 + len(s_lines) * s_step if s_lines else 0)
    y = TEXT_Y0 + (TEXT_Y1 - TEXT_Y0 - block) // 2
    for line in h_lines:
        draw.text((W / 2, y), line, font=h_font, fill=art.HEADLINE_COLOR, anchor="ma")
        y += h_step
    y += 18
    for line in s_lines:
        draw.text((W / 2, y), line, font=s_font, fill=art.SUB_COLOR, anchor="ma")
        y += s_step


def _overlays(headline: str, subheadline: str, cta_label: str, work: Path) -> tuple[Path, Path]:
    text = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    _strip_text(ImageDraw.Draw(text), headline, subheadline)
    text.save(work / "text.png")

    cta = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(cta)
    draw.rectangle([0, TEXT_Y0 - 30, W, TEXT_Y1 + 30], fill=art.STRIP_BG)           # covers the headline
    big = art.ImageFont.truetype(str(art.FONT_BOLD), 64)
    small = art.ImageFont.truetype(str(art.FONT_MEDIUM), 36)
    mid = (TEXT_Y0 + TEXT_Y1) // 2
    draw.text((W / 2, mid - 20), "LINK NA BIO", font=big, fill=art.ACCENT, anchor="ms")
    draw.text((W / 2, mid + 40), cta_label, font=small, fill=art.SUB_COLOR, anchor="ms")
    cta.save(work / "cta.png")
    return work / "text.png", work / "cta.png"


def make_reel(photos: list, headline: str, subheadline: str, cta_label: str, name: str) -> Path:
    if not headline.strip():
        raise ValueError("headline is required")
    if len(photos) < 2:
        raise RuntimeError("Need at least 2 photos for a Reel")
    art.OUTPUT_DIR.mkdir(exist_ok=True)
    work = art.OUTPUT_DIR / "reel_work"
    work.mkdir(exist_ok=True)

    inputs = []
    for i, photo in enumerate(photos):
        prepared = work / f"photo{i}.png"
        art.polish(art.cover_crop(photo.image.convert("RGB"), round(PHOTO_W * SOURCE_SCALE),
                                  round(PHOTO_H * SOURCE_SCALE))).save(prepared, "PNG")
        inputs.append(prepared)
    text_png, cta_png = _overlays(headline, subheadline, cta_label, work)

    n = len(photos)
    frames = round(CLIP_S * FPS)
    total = n * CLIP_S - (n - 1) * FADE_S
    motions = random.sample(MOTIONS, k=min(n, len(MOTIONS))) + random.choices(MOTIONS, k=max(0, n - len(MOTIONS)))
    parts = [f"[{i}:v]zoompan={_motion(motions[i], frames)}:d={frames}:s={PHOTO_W}x{PHOTO_H}:fps={FPS},setsar=1[v{i}]"
             for i in range(n)]
    last = "v0"
    for i in range(1, n):
        parts.append(f"[{last}][v{i}]xfade=transition=fade:duration={FADE_S}:offset={i * (CLIP_S - FADE_S)}[x{i}]")
        last = f"x{i}"
    parts.append(f"color=c=0xF3EEE8:s={W}x{H}:r={FPS}:d={total}[bg]")
    parts.append(f"[bg][{last}]overlay=0:{PHOTO_Y}[base]")
    parts.append(f"[base][{n}:v]overlay=0:0:format=auto[withtext]")
    parts.append(f"[withtext][{n + 1}:v]overlay=0:0:format=auto:enable='gte(t,{total - CTA_S})',format=yuv420p[out]")

    out = art.OUTPUT_DIR / f"{name}.mp4"
    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error"]
    for path in inputs:
        cmd += ["-i", str(path)]
    cmd += ["-i", str(text_png), "-i", str(cta_png),
            "-f", "lavfi", "-t", str(total), "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
    cmd += ["-filter_complex", ";".join(parts), "-map", "[out]", "-map", f"{n + 2}:a",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-r", str(FPS),
            "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", str(out)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr[-600:]}")
    print(f"[reel] {n} photos, motions={motions}, {total:.1f}s, {out.stat().st_size // 1024} KB")
    return out
