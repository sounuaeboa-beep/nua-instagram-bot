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

# A token renewed earlier in the same GitHub job is parked here, so steps that start later use the fresh one
# (secrets are read when the job starts). The file only ever exists inside a running job.
TOKEN_FILE = Path(__file__).resolve().parent.parent / "output" / ".ig_token"
if TOKEN_FILE.exists():
    os.environ["IG_ACCESS_TOKEN"] = TOKEN_FILE.read_text().strip()


def _json(resp: requests.Response) -> dict:
    if not resp.ok:
        raise RuntimeError(f"Instagram API {resp.status_code}: {resp.text}")
    return resp.json()


def _cloudinary_upload(path: str | Path, resource_type: str) -> str:
    cloudinary.config(
        cloud_name=os.environ["CLOUDINARY_CLOUD_NAME"],
        api_key=os.environ["CLOUDINARY_API_KEY"],
        api_secret=os.environ["CLOUDINARY_API_SECRET"],
        secure=True,
    )
    # URL-safe and unique per upload, so a re-used photo can never serve a stale cached file
    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "-", Path(path).stem).strip("-")
    result = cloudinary.uploader.upload(
        str(path), folder="nu-a-instagram", resource_type=resource_type,
        public_id=f"{time.strftime('%Y%m%d-%H%M%S', time.gmtime())}-{safe_name}",
    )
    return result["secure_url"]


def upload_image(image_path: str | Path) -> str:
    """Instagram only fetches public URLs, so host the PNG and return its https URL."""
    return _cloudinary_upload(image_path, "image")


def upload_video(video_path: str | Path) -> str:
    return _cloudinary_upload(video_path, "video")


def check_token() -> dict:
    """Cheap proof that the token and API version are valid (used by --dry-run)."""
    return _json(requests.get(
        f"{GRAPH}/me", params={"fields": "user_id,username", "access_token": os.environ["IG_ACCESS_TOKEN"]},
        timeout=30,
    ))


def _wait(container: str, tries: int, delay: int) -> None:
    token = os.environ["IG_ACCESS_TOKEN"]
    for _ in range(tries):
        status = _json(requests.get(
            f"{GRAPH}/{container}", params={"fields": "status_code", "access_token": token}, timeout=30,
        ))["status_code"]
        if status == "FINISHED":
            return
        if status == "ERROR":
            raise RuntimeError("Instagram failed to process the media container")
        time.sleep(delay)
    raise TimeoutError("Media container not ready in time")


def _publish(media_params: dict, tries: int, delay: int) -> str:
    """Two-step Instagram publishing: create a container, wait until it is processed, then publish it."""
    user_id, token = os.environ["IG_USER_ID"], os.environ["IG_ACCESS_TOKEN"]
    container = _json(requests.post(
        f"{GRAPH}/{user_id}/media", data={**media_params, "access_token": token}, timeout=60,
    ))["id"]
    _wait(container, tries, delay)
    return _json(requests.post(
        f"{GRAPH}/{user_id}/media_publish", data={"creation_id": container, "access_token": token}, timeout=60,
    ))["id"]


def publish_carousel(image_urls: list[str], caption: str) -> str:
    """One container per slide, then a carousel container that holds them."""
    user_id, token = os.environ["IG_USER_ID"], os.environ["IG_ACCESS_TOKEN"]
    children = []
    for url in image_urls:
        child = _json(requests.post(
            f"{GRAPH}/{user_id}/media",
            data={"image_url": url, "is_carousel_item": "true", "access_token": token}, timeout=60,
        ))["id"]
        _wait(child, tries=15, delay=2)
        children.append(child)
    return _publish({"media_type": "CAROUSEL", "children": ",".join(children), "caption": caption}, tries=30, delay=3)


def publish_image(image_url: str, caption: str) -> str:
    return _publish({"image_url": image_url, "caption": caption}, tries=15, delay=2)


def publish_story(image_url: str) -> str:
    """A Story frame (image). The API cannot add stickers (poll, question, link), so text lives on the image."""
    return _publish({"media_type": "STORIES", "image_url": image_url}, tries=15, delay=2)


def publish_reel(video_url: str, caption: str) -> str:
    """Reels take longer to process: wait up to 5 minutes."""
    return _publish(
        {"media_type": "REELS", "video_url": video_url, "caption": caption, "share_to_feed": "true"}, tries=60, delay=5,
    )


def refresh_token() -> bool:
    """Extends the 60-day token and saves the result to the IG_ACCESS_TOKEN repo secret.
    Returns False (instead of raising) if it could not be saved, so a published post is never lost."""
    data = _json(requests.get(
        "https://graph.instagram.com/refresh_access_token",
        params={"grant_type": "ig_refresh_token", "access_token": os.environ["IG_ACCESS_TOKEN"]}, timeout=30,
    ))

    TOKEN_FILE.parent.mkdir(exist_ok=True)
    TOKEN_FILE.write_text(data["access_token"])
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
