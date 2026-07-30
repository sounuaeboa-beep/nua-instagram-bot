"""Orchestrates the full daily pipeline: copy -> guardrail -> art -> hosting -> publish -> log."""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

import generate_copy
import generate_art
import upload_to_shopify
import publish

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
ROTATION_PATH = os.path.join(DATA_DIR, "product_rotation.json")
HISTORY_PATH = os.path.join(DATA_DIR, "history.json")


def run_guardrail(post: dict):
    result = subprocess.run(
        [sys.executable, "guardrail_check.py"],
        input=json.dumps(post),
        capture_output=True,
        text=True,
        cwd=os.path.dirname(__file__),
    )
    print(result.stderr, file=sys.stderr)
    if result.returncode != 0:
        raise RuntimeError("Guardrail rejected the caption — aborting run without publishing")


def main():
    with open(ROTATION_PATH) as f:
        rotation = json.load(f)

    product, objetivo = generate_copy.pick_today(rotation)
    post = generate_copy.generate_caption(product, objetivo)
    post["product"] = product
    post["objetivo"] = objetivo

    rotation["last_product"] = product
    rotation["last_objetivo"] = objetivo
    with open(ROTATION_PATH, "w") as f:
        json.dump(rotation, f, ensure_ascii=False, indent=2)

    run_guardrail(post)

    local_path = generate_art.generate(post["image_headline"], post["image_subheadline"])

    size = os.path.getsize(local_path)
    target = upload_to_shopify.staged_upload(os.path.basename(local_path), size)
    upload_to_shopify.upload_bytes(target, local_path)
    file_id = upload_to_shopify.create_file(target["resourceUrl"])
    cdn_url = upload_to_shopify.poll_cdn_url(file_id)
    os.remove(local_path)

    full_caption = post["caption"] + "\n\n" + " ".join(post["hashtags"])
    creation_id = publish.create_container(cdn_url, full_caption)
    publish.wait_until_ready(creation_id)
    media_id = publish.publish(creation_id)

    with open(HISTORY_PATH) as f:
        history = json.load(f)
    history.append({
        "date": datetime.now(timezone.utc).isoformat(),
        "product": product,
        "objetivo": objetivo,
        "caption": post["caption"],
        "media_id": media_id,
        "cdn_url": cdn_url,
    })
    with open(HISTORY_PATH, "w") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    print(f"Published media {media_id} ({product} / {objetivo})")


if __name__ == "__main__":
    main()
