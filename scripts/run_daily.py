"""Orchestrates the full daily pipeline: copy → guardrail → art → Cloudinary → publish → log."""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import generate_copy
import generate_art
from upload_to_cloudinary import upload as upload_image
import publish

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ROTATION_PATH = DATA_DIR / "product_rotation.json"
HISTORY_PATH = DATA_DIR / "history.json"


def run_guardrail(post: dict):
    result = subprocess.run(
        [sys.executable, "guardrail_check.py"],
        input=json.dumps(post),
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parent,
    )
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    if result.returncode != 0:
        raise RuntimeError("Guardrail rejected the caption — aborting run without publishing")


def main():
    # 1. Load rotation state
    with open(ROTATION_PATH) as f:
        rotation = json.load(f)

    # 2. Pick product + generate copy
    product, objetivo = generate_copy.pick_today(rotation)
    post = generate_copy.generate_caption(product, objetivo)
    post["product"] = product
    post["objetivo"] = objetivo

    # 3. Update rotation
    rotation["last_product"] = product
    rotation["last_objetivo"] = objetivo
    with open(ROTATION_PATH, "w") as f:
        json.dump(rotation, f, ensure_ascii=False, indent=2)

    # 4. Safety check
    run_guardrail(post)

    # 5. Generate artwork (Pillow)
    local_path = generate_art.generate(
        product=product,
        headline=post["image_headline"],
        subheadline=post.get("image_subheadline", ""),
    )

    # 6. Upload to Cloudinary → get public URL
    image_url = upload_image(local_path)

    # Optional: remove local file after upload
    try:
        os.remove(local_path)
    except OSError:
        pass

    # 7. Publish to Instagram
    full_caption = post["caption"] + "\n\n" + " ".join(post["hashtags"])
    creation_id = publish.create_container(image_url, full_caption)
    publish.wait_until_ready(creation_id)
    media_id = publish.publish(creation_id)

    # 8. Log to history
    with open(HISTORY_PATH) as f:
        history = json.load(f)

    history.append({
        "date": datetime.now(timezone.utc).isoformat(),
        "product": product,
        "objetivo": objetivo,
        "caption": post["caption"],
        "hashtags": post["hashtags"],
        "image_headline": post["image_headline"],
        "image_subheadline": post.get("image_subheadline", ""),
        "media_id": media_id,
        "image_url": image_url,
    })

    with open(HISTORY_PATH, "w") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    print(f"✅ Published media {media_id} ({product} / {objetivo})")
    print(f"   Image: {image_url}")


if __name__ == "__main__":
    main()
