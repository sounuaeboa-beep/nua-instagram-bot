"""Publishes the image + caption to Instagram via the Instagram Graph API
(Instagram Login / Business Login for Instagram flow -> graph.instagram.com host)."""
import os
import sys
import time

import requests

GRAPH_API = "https://graph.instagram.com/v21.0"


def create_container(image_url: str, caption: str) -> str:
    resp = requests.post(
        f"{GRAPH_API}/{os.environ['IG_USER_ID']}/media",
        data={
            "image_url": image_url,
            "caption": caption,
            "access_token": os.environ["IG_ACCESS_TOKEN"],
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def wait_until_ready(creation_id: str):
    for _ in range(15):
        resp = requests.get(
            f"{GRAPH_API}/{creation_id}",
            params={"fields": "status_code", "access_token": os.environ["IG_ACCESS_TOKEN"]},
            timeout=30,
        )
        resp.raise_for_status()
        status = resp.json()["status_code"]
        if status == "FINISHED":
            return
        if status == "ERROR":
            raise RuntimeError("Instagram failed to process the media container")
        time.sleep(2)
    raise TimeoutError("Media container not ready in time")


def publish(creation_id: str) -> str:
    resp = requests.post(
        f"{GRAPH_API}/{os.environ['IG_USER_ID']}/media_publish",
        data={"creation_id": creation_id, "access_token": os.environ["IG_ACCESS_TOKEN"]},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def main():
    image_url = sys.argv[1]
    caption = sys.argv[2]

    creation_id = create_container(image_url, caption)
    wait_until_ready(creation_id)
    media_id = publish(creation_id)

    print(media_id)


if __name__ == "__main__":
    main()
