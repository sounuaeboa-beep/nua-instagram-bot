"""Autofills the nu.a Canva brand template with today's copy and exports a PNG."""
import json
import os
import sys
import time

import requests

import canva_auth

CANVA_API = "https://api.canva.com/rest/v1"


def _headers(access_token: str):
    return {"Authorization": f"Bearer {access_token}"}


def autofill(access_token: str, headline: str, subheadline: str) -> str:
    resp = requests.post(
        f"{CANVA_API}/autofills",
        headers=_headers(access_token),
        json={
            "type": "create_from_brand_template",
            "brand_template_id": os.environ["CANVA_BRAND_TEMPLATE_ID"],
            "title": f"nu.a daily post - {headline[:30]}",
            "data": {
                "headline": {"type": "text", "text": headline},
                "subheadline": {"type": "text", "text": subheadline},
            },
        },
        timeout=30,
    )
    resp.raise_for_status()
    job_id = resp.json()["job"]["id"]

    for _ in range(30):
        time.sleep(2)
        poll = requests.get(f"{CANVA_API}/autofills/{job_id}", headers=_headers(access_token), timeout=30)
        poll.raise_for_status()
        job = poll.json()["job"]
        if job["status"] == "success":
            return job["result"]["design"]["id"]
        if job["status"] == "failed":
            raise RuntimeError(f"Canva autofill failed: {job.get('error')}")

    raise TimeoutError("Canva autofill job did not finish in time")


def export_png(access_token: str, design_id: str) -> str:
    resp = requests.post(
        f"{CANVA_API}/exports",
        headers=_headers(access_token),
        json={"design_id": design_id, "format": {"type": "png"}},
        timeout=30,
    )
    resp.raise_for_status()
    export_id = resp.json()["job"]["id"]

    for _ in range(30):
        time.sleep(2)
        poll = requests.get(f"{CANVA_API}/exports/{export_id}", headers=_headers(access_token), timeout=30)
        poll.raise_for_status()
        job = poll.json()["job"]
        if job["status"] == "success":
            return job["urls"][0]
        if job["status"] == "failed":
            raise RuntimeError(f"Canva export failed: {job.get('error')}")

    raise TimeoutError("Canva export job did not finish in time")


def generate(headline: str, subheadline: str) -> str:
    access_token = canva_auth.refresh()
    design_id = autofill(access_token, headline, subheadline)
    canva_url = export_png(access_token, design_id)

    # Canva's export URL expires after ~24h, so download the bytes now.
    image_bytes = requests.get(canva_url, timeout=60).content
    local_path = os.path.join(os.path.dirname(__file__), "..", "tmp_post_image.png")
    with open(local_path, "wb") as f:
        f.write(image_bytes)

    return local_path


def main():
    post = json.loads(sys.stdin.read())
    print(generate(post["image_headline"], post["image_subheadline"]))


if __name__ == "__main__":
    main()
