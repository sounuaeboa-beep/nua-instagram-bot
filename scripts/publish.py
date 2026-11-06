"""Publishing: host the image on Cloudinary (free tier), publish through the
Instagram API (Instagram Login flow, graph.instagram.com), keep the token alive."""
import os
import re
import subprocess
import time
from pathlib import Path

import cloudinary
import cloudinary.uploader
import requests

GRAPH = "https://graph.instagram.com/v26.0"


def _json(resp: requests.Response) -> dict:
    if not resp.ok:
        raise RuntimeError(f"Instagram API {resp.status_code}: {resp.text}")
    return resp.json()


def upload_image(image_path: str | Path) -> str:
    """Instagram only fetches public URLs, so host the PNG and return its https URL."""
    cloudinary.config(
        cloud_name=os.environ["CLOUDINARY_CLOUD_NAME"],
        api_key=os.environ["CLOUDINARY_API_KEY"],
        api_secret=os.environ["CLOUDINARY_API_SECRET"],
        secure=True,
    )
    # URL-safe and unique per upload, so a re-used photo can never serve a stale cached image
    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "-", Path(image_path).stem).strip("-")
    result = cloudinary.uploader.upload(
        str(image_path), folder="nu-a-instagram",
        public_id=f"{time.strftime('%Y%m%d-%H%M%S', time.gmtime())}-{safe_name}", resource_type="image",
    )
    return result["secure_url"]


def check_token() -> dict:
    """Cheap proof that the token and API version are valid (used by --dry-run)."""
    return _json(requests.get(
        f"{GRAPH}/me", params={"fields": "user_id,username", "access_token": os.environ["IG_ACCESS_TOKEN"]},
        timeout=30,
    ))


def publish_image(image_url: str, caption: str) -> str:
    user_id, token = os.environ["IG_USER_ID"], os.environ["IG_ACCESS_TOKEN"]

    container = _json(requests.post(
        f"{GRAPH}/{user_id}/media",
        data={"image_url": image_url, "caption": caption, "access_token": token}, timeout=30,
    ))["id"]

    for _ in range(15):
        status = _json(requests.get(
            f"{GRAPH}/{container}", params={"fields": "status_code", "access_token": token}, timeout=30,
        ))["status_code"]
        if status == "FINISHED":
            break
        if status == "ERROR":
            raise RuntimeError("Instagram failed to process the media container")
        time.sleep(2)
    else:
        raise TimeoutError("Media container not ready in time")

    return _json(requests.post(
        f"{GRAPH}/{user_id}/media_publish",
        data={"creation_id": container, "access_token": token}, timeout=30,
    ))["id"]


def refresh_token() -> bool:
    """Extends the 60-day token and saves the result to the IG_ACCESS_TOKEN repo secret.
    Returns False (instead of raising) if it could not be saved, so a published post is never lost."""
    data = _json(requests.get(
        "https://graph.instagram.com/refresh_access_token",
        params={"grant_type": "ig_refresh_token", "access_token": os.environ["IG_ACCESS_TOKEN"]}, timeout=30,
    ))

    repo, pat = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("REPO_ADMIN_TOKEN")
    if not (repo and pat):
        print("[token] refreshed, but REPO_ADMIN_TOKEN/GITHUB_REPOSITORY missing: new token NOT saved")
        return False

    subprocess.run(
        ["gh", "secret", "set", "IG_ACCESS_TOKEN", "--repo", repo],
        input=data["access_token"], text=True, env={**os.environ, "GH_TOKEN": pat}, check=True,
    )
    print(f"[token] refreshed and saved (valid {data['expires_in'] // 86400} days)")
    return True
