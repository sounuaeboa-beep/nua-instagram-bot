"""One-off import of real-model photos from Google Drive into media/real/<product>/.

Reads data/photo_import.json, downloads each file from its "anyone with the link" Drive URL, shrinks it to a size
that is still sharp for 1080 px posts and Reels (long side 1800 px, JPEG quality 88) and saves it. Files that are
already in media/real are skipped, so running it twice is harmless."""
import io
import json
import sys
from pathlib import Path

import requests
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
LIST = ROOT / "data" / "photo_import.json"
REAL_DIR = ROOT / "media" / "real"
LONG_SIDE = 1800
URL = "https://drive.usercontent.google.com/download?id={id}&export=download&confirm=t"


def main() -> int:
    photos = json.loads(LIST.read_text(encoding="utf-8"))["photos"]
    failed = []
    for item in photos:
        target = REAL_DIR / item["product"] / item["file"]
        if target.exists():
            print(f"skip (already imported): {target.relative_to(ROOT)}")
            continue
        try:
            resp = requests.get(URL.format(id=item["drive_id"]), timeout=120)
            resp.raise_for_status()
            img = ImageOps.exif_transpose(Image.open(io.BytesIO(resp.content))).convert("RGB")
        except Exception as error:  # a Drive HTML page (not shared / quota) also lands here
            print(f"FAILED {item['file']}: {error}")
            failed.append(item["file"])
            continue
        img.thumbnail((LONG_SIDE, LONG_SIDE), Image.LANCZOS)
        target.parent.mkdir(parents=True, exist_ok=True)
        img.save(target, "JPEG", quality=88, optimize=True, progressive=True)
        print(f"ok {target.relative_to(ROOT)} {img.size} {target.stat().st_size // 1024} KB")
    print(f"\n{len(photos) - len(failed)}/{len(photos)} photos in media/real; failed: {failed or 'none'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
