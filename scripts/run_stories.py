"""Stories pipeline: runs right after the feed post. One set of 2-3 frames per run, rotating through set types.

  python scripts/run_stories.py             # live: publishes the frames as Stories
  python scripts/run_stories.py --dry-run   # builds the frames, publishes nothing
  --set auto|novo|mito|escolha|dica|kit     # auto follows the rotation below

Set types: novo (the feed post just published + a product frame), mito (myth-or-truth, 3 frames), escolha (1-or-2 poll
answered by DM/reply, 2 frames), dica (tip card + product frame), kit (kit photo + price card).
The Instagram API cannot add stickers, so there are no poll/link stickers: prompts ask people to reply instead.
"""
import argparse
import io
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from PIL import Image

import catalog
import content
import photos
import publish
import story_art
import story_content

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FEED_HISTORY = DATA_DIR / "history.json"
STORY_HISTORY = DATA_DIR / "stories_history.json"
RECENT_SETS = 12                    # photos used in the last 12 story sets are not reused while others exist
CTA = "LINK NA BIO"

# 50% of sets promote the new feed post; the rest are engagement and conversion sets
SET_CYCLE = ["novo", "mito", "novo", "escolha", "novo", "dica", "novo", "kit"]


def _feed_post_fresh(feed: list[dict]) -> bool:
    """True when the newest feed post is an image/carousel published in the last 6 hours (its cover can be shown)."""
    if not feed:
        return False
    last = feed[-1]
    if last.get("format") == "reel" or not last.get("image_url"):
        return False
    try:
        age = datetime.now(timezone.utc) - datetime.fromisoformat(last["date"])
    except (KeyError, ValueError):
        return False
    return age < timedelta(hours=6)


def pick_set(stories: list[dict], feed: list[dict], wanted: str) -> str:
    chosen = wanted if wanted != "auto" else SET_CYCLE[len(stories) % len(SET_CYCLE)]
    if chosen == "novo" and not _feed_post_fresh(feed):
        return "dica"
    return chosen


def pick_product(set_type: str, stories: list[dict], feed: list[dict]) -> str:
    if set_type == "novo":
        return feed[-1]["product"]

    def last_used(product: str) -> int:
        for i in range(len(stories) - 1, -1, -1):
            if stories[i].get("product") == product:
                return i
        return -1
    return min(content.PRODUCTS, key=last_used)


def build_frames(set_type: str, product: str, entry: dict, data: dict, avoid: set[str], feed: list[dict], stamp: str):
    """-> (frames [(label, path)], photo ids)"""
    frames, ids = [], []

    def product_frame(pillar: str, label: str = "produto"):
        photo = photos.choose(product, pillar, 1, avoid | set(ids), entry)[0]
        ids.append(photo.id)
        closing = data["closing"]
        frames.append((label, story_art.story_photo(photo.image, closing["headline"], closing.get("subheadline", ""),
                                                    CTA, f"story_{stamp}_{len(frames) + 1}")))

    n = lambda: f"story_{stamp}_{len(frames) + 1}"          # noqa: E731  (file name of the next frame)

    if set_type == "novo":
        resp = requests.get(feed[-1]["image_url"], timeout=30)
        resp.raise_for_status()
        frames.append(("novo", story_art.story_feed(Image.open(io.BytesIO(resp.content)), n())))
        product_frame("conforto")
    elif set_type == "mito":
        frames.append(("pergunta", story_art.story_card("Mito ou verdade?", data["statement"], "", n())))
        verdict = "É mito" if data.get("is_myth") else "É verdade"
        frames.append(("resposta", story_art.story_card(verdict, data["explanation"], "", n(), dark=True)))
        product_frame("conforto")
    elif set_type == "escolha":
        pair = photos.choose(product, "educacao", 2, avoid, entry)
        ids.extend(p.id for p in pair)
        frames.append(("escolha", story_art.story_duo(data["question"], data.get("hint") or "Responde aqui com 1 ou 2",
                                                      pair[0].image, pair[1].image, n())))
        product_frame("conforto")
    elif set_type == "dica":
        frames.append(("dica", story_art.story_card("Dica nu.a", data["title"], data["body"], n())))
        product_frame("conforto")
    elif set_type == "kit":
        product_frame("multipack", "kit")
        rows = []
        if entry.get("single"):
            rows.append(("Avulsa", catalog.brl(entry["single"]["price"]), ""))
        for kit in entry["kits"]:
            rows.append((f"Kit com {kit['qty']}", catalog.brl(kit["price"]), f"≈ {catalog.brl(kit['per_piece'])} por peça"))
        frames.append(("precos", story_art.story_list("Compra inteligente", "Quanto mais, melhor o preço", rows,
                                                      "Link na bio", n())))
    else:  # "produto" (also the fallback when a richer set cannot be built)
        product_frame("conforto")
    return frames, ids


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--set", dest="wanted", choices=["auto", "novo", "mito", "escolha", "dica", "kit"], default="auto")
    args = parser.parse_args()

    feed = json.loads(FEED_HISTORY.read_text(encoding="utf-8"))
    stories = json.loads(STORY_HISTORY.read_text(encoding="utf-8")) if STORY_HISTORY.exists() else []
    set_type = pick_set(stories, feed, args.wanted)
    product = pick_product(set_type, stories, feed)
    print(f"[stories] set={set_type} product={product}")

    cat = catalog.get_catalog()
    entry = cat[product]
    if set_type == "kit" and not entry.get("kits"):
        set_type = "dica"
    facts = catalog.facts_for(product, {product: entry})
    recent_texts = [t for s in stories[-RECENT_SETS:] for t in s.get("texts", [])]
    avoid = {pid for s in stories[-RECENT_SETS:] for pid in s.get("photos", [])}
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())

    try:
        data = story_content.create_set(set_type, product, facts, recent_texts)
        frames, ids = build_frames(set_type, product, entry, data, avoid, feed, stamp)
    except Exception as error:   # a richer set failed: fall back to one simple product frame
        if set_type == "produto":
            raise
        print(f"[stories] {set_type} could not be built ({error}); falling back to a single product frame")
        set_type = "produto"
        data = story_content.create_set(set_type, product, facts, recent_texts)
        frames, ids = build_frames(set_type, product, entry, data, avoid, feed, stamp)

    if args.dry_run:
        account = publish.check_token()
        print(f"[dry-run] Instagram token OK (@{account.get('username')})")
        for label, path in frames:
            print(f"[dry-run] frame {label}: {path}")
        print(f"[dry-run] texts: {json.dumps(data, ensure_ascii=False)}")
        return

    published = []
    for label, path in frames:
        try:
            media_id = publish.publish_story(publish.upload_image(path))
            published.append({"frame": label, "media_id": media_id})
            print(f"[stories] published {label}: {media_id}")
        except Exception as error:   # keep going: the remaining frames can still go out
            print(f"::warning::Story frame '{label}' failed: {error}")
        time.sleep(3)

    if published:   # log before anything else can fail
        stories.append({"date": datetime.now(timezone.utc).isoformat(), "set": set_type, "product": product,
                        "frames": published, "photos": ids, "texts": story_content.main_texts(set_type, data)})
        STORY_HISTORY.write_text(json.dumps(stories, ensure_ascii=False, indent=2), encoding="utf-8")
    if len(published) < len(frames):
        sys.exit(f"Only {len(published)} of {len(frames)} story frames were published")


if __name__ == "__main__":
    main()
