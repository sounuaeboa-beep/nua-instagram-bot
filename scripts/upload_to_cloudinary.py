"""
upload_to_cloudinary.py
Uploads the generated PNG to Cloudinary and returns a public URL
that Instagram can fetch.
"""

from __future__ import annotations

import os
import cloudinary
import cloudinary.uploader
from pathlib import Path


def upload(image_path: str | Path) -> str:
    """
    Upload a local image to Cloudinary and return the secure public URL.
    """
    image_path = Path(image_path)

    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    # Configure from environment variables
    cloudinary.config(
        cloud_name=os.environ["CLOUDINARY_CLOUD_NAME"],
        api_key=os.environ["CLOUDINARY_API_KEY"],
        api_secret=os.environ["CLOUDINARY_API_SECRET"],
        secure=True,
    )

    # Upload
    result = cloudinary.uploader.upload(
        str(image_path),
        folder="nu-a-instagram",          # keeps things organized
        public_id=image_path.stem,        # uses the filename without extension
        overwrite=True,
        resource_type="image",
    )

    url = result["secure_url"]
    print(f"[cloudinary] uploaded → {url}")
    return url


if __name__ == "__main__":
    # Quick local test
    import sys
    if len(sys.argv) < 2:
        print("Usage: python upload_to_cloudinary.py path/to/image.png")
        sys.exit(1)

    print(upload(sys.argv[1]))
