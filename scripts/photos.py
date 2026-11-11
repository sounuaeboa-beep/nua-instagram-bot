"""Where post photos come from: the local library (media/) and the store's own listing photos (public feed).
Every photo has a stable id, so the pipeline can avoid reusing the same picture within a few weeks."""
import io
import random
from dataclasses import dataclass
from pathlib import Path

import requests
from PIL import Image

MEDIA_DIR = Path(__file__).resolve().parent.parent / "media"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
STORE_WIDTH = 1600                      # store photos are 2000x2000; this is plenty for a 1080 px post

# pillar -> {pool: weight}. Pools: product close-ups (library), people shots (lifestyle),
# store photos of the single product / of its kits.
POOL_WEIGHTS = {
    "conforto": {"lifestyle": 0.30, "library": 0.35, "store_single": 0.35},
    "educacao": {"library": 0.45, "store_single": 0.55},
    "multipack": {"store_kit": 0.65, "library": 0.35},
    "aspiracional": {"lifestyle": 1.0},
}


@dataclass
class Photo:
    id: str            # e.g. "lib:invisible/2 CLF200 - RED.jpg" or "store:12345678"
    image: Image.Image
    pool: str


def classify(img: Image.Image) -> str:
    """'chart' (size table), 'product' (item on a white background) or 'model' (person photo)."""
    small = img.convert("RGB").resize((96, 96))
    px = small.load()
    edge = [px[i, j] for i in range(96) for j in (0, 1, 94, 95)] + [px[j, i] for i in range(96) for j in (0, 1, 94, 95)]
    border_light = sum(sum(c) / 3 for c in edge) / len(edge)
    saturation = sum(small.convert("HSV").resize((32, 32)).getdata(1)) / (32 * 32)
    if border_light > 238:
        return "chart" if saturation < 22 else "product"
    return "model"


def _library_ids(folder: Path) -> list[Path]:
    """Photos in a library folder, skipping wide landscape ones (a square crop would cut people at the sides)."""
    found = []
    for p in sorted(folder.glob("*")) if folder.exists() else []:
        if p.suffix.lower() in IMAGE_EXTENSIONS:
            with Image.open(p) as im:
                if im.width / im.height <= 1.1:
                    found.append(p)
    return found


def _store_candidates(entry: dict, kits: bool) -> list[dict]:
    if kits:
        return [img for kit in entry.get("kits", []) for img in kit.get("images", [])]
    return (entry.get("single") or {}).get("images", [])


def _download(src: str) -> Image.Image:
    url = src.split("?")[0] + f"?width={STORE_WIDTH}"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return Image.open(io.BytesIO(resp.content)).convert("RGB")


def choose(product: str, pillar: str | None, count: int, avoid: set[str], catalog_entry: dict | None) -> list[Photo]:
    """`count` different photos for this post. Photos in `avoid` (recently used) are skipped while others exist."""
    weights = dict(POOL_WEIGHTS.get(pillar or "", {"library": 1.0}))
    chosen: list[Photo] = []
    tried: set[str] = set()
    for _ in range(count * 12):
        if len(chosen) == count:
            break
        pool = random.choices(list(weights), weights=list(weights.values()))[0]
        photo = _try_pool(pool, product, catalog_entry, avoid | tried | {p.id for p in chosen}, tried)
        if photo:
            chosen.append(photo)
    if len(chosen) < count:  # everything recent was skipped: relax the avoid list rather than fail
        if avoid:
            return choose(product, pillar, count, set(), catalog_entry)
        raise RuntimeError(f"Could not find {count} usable photos for {product}/{pillar}")
    return chosen


def _try_pool(pool: str, product: str, entry: dict | None, skip: set[str], tried: set[str]) -> Photo | None:
    if pool in ("library", "lifestyle"):
        folder = MEDIA_DIR / ("lifestyle" if pool == "lifestyle" else product)
        options = [p for p in _library_ids(folder) if f"lib:{folder.name}/{p.name}" not in skip]
        if not options:
            return None
        path = random.choice(options)
        pid = f"lib:{folder.name}/{path.name}"
        tried.add(pid)
        return Photo(pid, Image.open(path).convert("RGB"), pool)
    if not entry:
        return None
    options = [i for i in _store_candidates(entry, kits=(pool == "store_kit")) if f"store:{i['id']}" not in skip]
    random.shuffle(options)
    for item in options[:6]:
        pid = f"store:{item['id']}"
        tried.add(pid)
        try:
            image = _download(item["src"])
        except requests.RequestException:
            continue
        if classify(image) == "chart":      # the size table is not a post visual
            continue
        return Photo(pid, image, pool)
    return None
