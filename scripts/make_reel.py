"""Builds a short vertical Reel (1080x1920, about 9.5 s) from library photos: slow zoom on three photos with soft
cross-fades, the headline in a clean strip below. Uses the ffmpeg binary bundled with imageio-ffmpeg, so nothing
needs installing on the machine.

    make_reel(product, headline, subheadline="", pillar=None) -> Path
CLI:  python scripts/make_reel.py <product> <headline> [subheadline]
"""
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageEnhance

import generate_art as art

W, H, FPS = 1080, 1920, 25
PHOTO_W, PHOTO_H, PHOTO_Y = 1080, 1350, 140        # 4:5 photo area, same look as the feed post
CLIP_S, FADE_S, PHOTOS = 3.5, 0.5, 3               # seconds per photo, cross-fade, number of photos
TEXT_Y0, TEXT_Y1 = 1490, 1760                      # headline strip; the bottom ~160 px stay free for Reels buttons
SOURCE_SCALE = 1.2                                 # prepare photos larger than shown so the zoom stays sharp


def _prepare_photo(path: Path, out: Path) -> None:
    img = art._cover_crop(Image.open(path).convert("RGB"), round(PHOTO_W * SOURCE_SCALE), round(PHOTO_H * SOURCE_SCALE))
    ImageEnhance.Color(ImageEnhance.Contrast(img).enhance(1.03)).enhance(1.05).save(out, "PNG")


def _text_overlay(headline: str, subheadline: str, out: Path) -> None:
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    width = W - 2 * art.MARGIN_X
    h_font, h_lines = art._fit(headline.upper(), art.FONT_BOLD, 62, 40, 2, width)
    s_font, s_lines = art._fit(subheadline, art.FONT_MEDIUM, 34, 24, 2, width) if subheadline.strip() else (None, [])
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
    img.save(out, "PNG")


def make_reel(product: str, headline: str, subheadline: str = "", pillar: str | None = None) -> Path:
    if not headline.strip():
        raise ValueError("headline is required")
    photos = art.pick_photos(product, pillar, PHOTOS)
    print(f"[reel] photos: {', '.join(p.name for p in photos)}")
    if len(photos) < 2:
        raise RuntimeError("Need at least 2 photos for a Reel")

    art.OUTPUT_DIR.mkdir(exist_ok=True)
    work = art.OUTPUT_DIR / "reel_work"
    work.mkdir(exist_ok=True)
    inputs = []
    for i, photo in enumerate(photos):
        prepared = work / f"photo{i}.png"
        _prepare_photo(photo, prepared)
        inputs.append(prepared)
    text_png = work / "text.png"
    _text_overlay(headline, subheadline, text_png)

    frames = round(CLIP_S * FPS)
    total = len(photos) * CLIP_S - (len(photos) - 1) * FADE_S
    zoom = f"zoompan=z='1+0.1*on/{frames}':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d={frames}:s={PHOTO_W}x{PHOTO_H}:fps={FPS},setsar=1"
    parts = [f"[{i}:v]{zoom}[v{i}]" for i in range(len(photos))]
    last = "v0"
    for i in range(1, len(photos)):
        offset = i * (CLIP_S - FADE_S)
        parts.append(f"[{last}][v{i}]xfade=transition=fade:duration={FADE_S}:offset={offset}[x{i}]")
        last = f"x{i}"
    n = len(photos)
    parts.append(f"color=c=0xF3EEE8:s={W}x{H}:r={FPS}:d={total}[bg]")
    parts.append(f"[bg][{last}]overlay=0:{PHOTO_Y}[base]")
    parts.append(f"[base][{n}:v]overlay=0:0:format=auto,format=yuv420p[out]")

    out = art.OUTPUT_DIR / f"reel_{product}_{photos[0].stem}.mp4"
    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error"]
    for path in inputs:
        cmd += ["-i", str(path)]
    cmd += ["-i", str(text_png), "-f", "lavfi", "-t", str(total), "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
    cmd += ["-filter_complex", ";".join(parts), "-map", "[out]", "-map", f"{n + 1}:a",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-r", str(FPS),
            "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", str(out)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr[-600:]}")
    print(f"[reel] saved -> {out} ({out.stat().st_size // 1024} KB, {total:.1f}s)")
    return out


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("Usage: python scripts/make_reel.py <product> <headline> [subheadline]")
    print(make_reel(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else ""))
