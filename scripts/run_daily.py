"""Daily pipeline: pick pillar + product + format -> caption (+ independent review) -> media -> host -> publish -> log.

  python scripts/run_daily.py             # live: publishes to Instagram
  python scripts/run_daily.py --dry-run   # builds caption + media and checks the IG token; publishes nothing
  --format auto|image|reel|carousel       # auto steers the mix toward 40% Reels, 20% carousels, 40% images
"""
import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import catalog
import content
import formats
import generate_art
import make_reel
import performance
import photos
import publish

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
HISTORY_PATH = DATA_DIR / "history.json"
TOKEN_STATE_PATH = DATA_DIR / "token_state.json"   # when the Instagram token was last renewed
TOKEN_REFRESH_EVERY_DAYS = 7                       # Instagram allows renewal only after 24h; the token lasts 60 days
RECENT_POSTS = 20                                  # photos used in the last 20 posts are not reused while others exist


def _token_refresh_due() -> bool:
    try:
        last = datetime.fromisoformat(json.loads(TOKEN_STATE_PATH.read_text())["refreshed_at"])
    except (FileNotFoundError, KeyError, ValueError):
        return True
    age = datetime.now(timezone.utc) - last
    print(f"[token] last renewed {age.days}d ago")
    return age.days >= TOKEN_REFRESH_EVERY_DAYS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--pillar", choices=sorted(content.PILLARS))
    parser.add_argument("--product", choices=content.PRODUCTS)
    parser.add_argument("--format", choices=["auto", "image", "reel", "carousel"], default="auto")
    args = parser.parse_args()

    history = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    pillar, product = content.pick_today(history)
    pillar, product = args.pillar or pillar, args.product or product
    fmt = formats.pick_format(history, pillar) if args.format == "auto" else args.format
    print(f"[plan] pillar={pillar} product={product} format={fmt}")

    try:  # learn from our own results; never blocks the post
        performance.write_learnings(history, performance.update(history))
    except Exception as error:
        print(f"[performance] skipped ({error})")

    entry = catalog.get_catalog()[product]
    post = content.create_post(
        pillar, product, catalog.facts_for(product, {product: entry}),
        [h.get("hook", "") for h in history[-7:]], [h.get("image_headline", "") for h in history[-20:]], fmt,
    )
    caption = post["caption"] + "\n\n" + " ".join(post["hashtags"])
    headline, subheadline = post["image_headline"], post.get("image_subheadline", "")
    avoid = {pid for h in history[-RECENT_POSTS:] for pid in h.get("photos", [])}
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())

    def build(kind: str):
        """-> (kind, files, photo ids)"""
        if kind == "reel":
            chosen = photos.choose(product, pillar, 3 + (int(stamp[-1]) % 2), avoid, entry)   # 3 or 4 photos
            label = entry["name"].split(" (")[0]
            return kind, [make_reel.make_reel(chosen, headline, subheadline, label, f"reel_{stamp}")], [p.id for p in chosen]
        chosen = photos.choose(product, pillar, 1, avoid, entry)
        if kind == "carousel":
            files = formats.build_carousel(chosen[0].image, headline, subheadline, post["slides"], entry, pillar,
                                           f"carousel_{stamp}")
            return kind, files, [chosen[0].id]
        return "image", [generate_art.render_post(chosen[0].image, headline, subheadline, f"post_{stamp}")], [chosen[0].id]

    kind, files, ids = "image", None, []
    if fmt != "image":
        try:
            kind, files, ids = build(fmt)
        except Exception as error:  # extra formats are a bonus: never let them block the day's post
            print(f"[{fmt}] could not build it ({error}); posting an image instead")
    if files is None:
        kind, files, ids = build("image")

    if args.dry_run:
        account = publish.check_token()
        print(f"[dry-run] Instagram token OK (@{account.get('username')})")
        print(f"[dry-run] {kind}: {[str(f) for f in files]}\n[dry-run] photos: {ids}\n[dry-run] caption:\n{caption}")
        return

    def publish_media(media_kind: str, media_files: list):
        if media_kind == "reel":
            url = publish.upload_video(media_files[0])
            return publish.publish_reel(url, caption), url
        urls = [publish.upload_image(f) for f in media_files]
        if media_kind == "carousel":
            return publish.publish_carousel(urls, caption), urls[0]
        return publish.publish_image(urls[0], caption), urls[0]

    media_id = media_url = None
    if kind != "image":
        try:
            media_id, media_url = publish_media(kind, files)
        except Exception as error:  # nothing was published yet, so falling back cannot double-post
            print(f"[{kind}] publishing failed ({error}); posting an image instead")
            kind, files, ids = build("image")
    if media_id is None:
        media_id, media_url = publish_media("image", files)

    # Log before anything else can fail, so a published post is never lost from history.
    history.append({
        "date": datetime.now(timezone.utc).isoformat(), "pillar": pillar, "product": product, "format": kind,
        "hook": post["hook"], "caption": post["caption"], "hashtags": post["hashtags"],
        "image_headline": headline, "image_subheadline": subheadline, "slides": post.get("slides", []),
        "photos": ids, "media_id": media_id, "image_url": media_url,
    })
    HISTORY_PATH.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Published {kind} {media_id} ({pillar} / {product})\n{media_url}")

    if _token_refresh_due():
        if not publish.refresh_token():
            sys.exit("Post published, but the Instagram token could not be refreshed/saved. Fix before it expires.")
        TOKEN_STATE_PATH.write_text(json.dumps({"refreshed_at": datetime.now(timezone.utc).isoformat()}), encoding="utf-8")


if __name__ == "__main__":
    main()
