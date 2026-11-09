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
import publish

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
HISTORY_PATH = DATA_DIR / "history.json"
TOKEN_STATE_PATH = DATA_DIR / "token_state.json"   # when the Instagram token was last renewed
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
    args = parser.parse_args()

    history = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    pillar, product = content.pick_today(history)
    pillar, product = args.pillar or pillar, args.product or product
    print(f"[plan] pillar={pillar} product={product}")

    facts = catalog.facts_for(product, catalog.get_catalog())
    post = content.create_post(pillar, product, facts, [h.get("hook", "") for h in history[-7:]])
    caption = post["caption"] + "\n\n" + " ".join(post["hashtags"])

    image_path = generate_art.generate(
        product=product, headline=post["image_headline"], subheadline=post.get("image_subheadline", ""), pillar=pillar,
    )

    if args.dry_run:
        account = publish.check_token()
        print(f"[dry-run] Instagram token OK (@{account.get('username')})")
        print(f"[dry-run] image: {image_path}\n[dry-run] caption:\n{caption}")
        return

    image_url = publish.upload_image(image_path)
    media_id = publish.publish_image(image_url, caption)

    # Log before anything else can fail, so a published post is never lost from history.
    history.append({
        "date": datetime.now(timezone.utc).isoformat(), "pillar": pillar, "product": product,
        "hook": post["hook"], "caption": post["caption"], "hashtags": post["hashtags"],
        "image_headline": post["image_headline"], "image_subheadline": post.get("image_subheadline", ""),
        "media_id": media_id, "image_url": image_url,
    })
    HISTORY_PATH.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Published media {media_id} ({pillar} / {product})\n{image_url}")

    if _token_refresh_due():
        if not publish.refresh_token():
            sys.exit("Post published, but the Instagram token could not be refreshed/saved. Fix before it expires.")
        TOKEN_STATE_PATH.write_text(json.dumps({"refreshed_at": datetime.now(timezone.utc).isoformat()}), encoding="utf-8")


if __name__ == "__main__":
    main()
