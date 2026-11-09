"""Daily pipeline: pick pillar+product -> caption (+ independent review) -> image -> host -> publish -> log.

  python scripts/run_daily.py             # live: publishes to Instagram
  python scripts/run_daily.py --dry-run   # builds caption + image and checks the IG token; publishes nothing
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import catalog
import content
import generate_art
import make_reel
import publish

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
HISTORY_PATH = DATA_DIR / "history.json"
TOKEN_STATE_PATH = DATA_DIR / "token_state.json"   # when the Instagram token was last renewed
REEL_EVERY = 4                                     # auto mode: every 4th post is a Reel
TOKEN_REFRESH_EVERY_DAYS = 7                       # Instagram allows renewal only after 24h; the token lasts 60 days


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
    parser.add_argument("--format", choices=["auto", "image", "reel"], default="auto",
                        help="auto = every 4th post is a Reel")
    args = parser.parse_args()

    history = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    pillar, product = content.pick_today(history)
    pillar, product = args.pillar or pillar, args.product or product
    print(f"[plan] pillar={pillar} product={product}")

    facts = catalog.facts_for(product, catalog.get_catalog())
    post = content.create_post(pillar, product, facts, [h.get("hook", "") for h in history[-7:]])
    caption = post["caption"] + "\n\n" + " ".join(post["hashtags"])

    headline, subheadline = post["image_headline"], post.get("image_subheadline", "")
    want_reel = args.format == "reel" or (args.format == "auto" and (len(history) + 1) % REEL_EVERY == 0)

    def build_image() -> Path:
        return generate_art.generate(product=product, headline=headline, subheadline=subheadline, pillar=pillar)

    kind, media_path = "image", None
    if want_reel:
        try:
            media_path, kind = make_reel.make_reel(product, headline, subheadline, pillar), "reel"
        except Exception as error:  # a Reel is a bonus: never let it block the day's post
            print(f"[reel] could not build the Reel ({error}); posting an image instead")
    if media_path is None:
        media_path = build_image()

    if args.dry_run:
        account = publish.check_token()
        print(f"[dry-run] Instagram token OK (@{account.get('username')})")
        print(f"[dry-run] {kind}: {media_path}\n[dry-run] caption:\n{caption}")
        return

    media_id = media_url = None
    if kind == "reel":
        try:
            media_url = publish.upload_video(media_path)
            media_id = publish.publish_reel(media_url, caption)
        except Exception as error:  # nothing was published yet, so falling back cannot double-post
            print(f"[reel] publishing the Reel failed ({error}); posting an image instead")
            kind, media_path = "image", build_image()
    if media_id is None:
        media_url = publish.upload_image(media_path)
        media_id = publish.publish_image(media_url, caption)

    # Log before anything else can fail, so a published post is never lost from history.
    history.append({
        "date": datetime.now(timezone.utc).isoformat(), "pillar": pillar, "product": product,
        "hook": post["hook"], "caption": post["caption"], "hashtags": post["hashtags"],
        "image_headline": post["image_headline"], "image_subheadline": post.get("image_subheadline", ""),
        "format": kind, "media_id": media_id, "image_url": media_url,
    })
    HISTORY_PATH.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Published {kind} {media_id} ({pillar} / {product})\n{media_url}")

    if _token_refresh_due():
        if not publish.refresh_token():
            sys.exit("Post published, but the Instagram token could not be refreshed/saved. Fix before it expires.")
        TOKEN_STATE_PATH.write_text(json.dumps({"refreshed_at": datetime.now(timezone.utc).isoformat()}), encoding="utf-8")


if __name__ == "__main__":
    main()
