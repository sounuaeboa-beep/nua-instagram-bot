"""Uploads the generated image to Shopify Files and returns its public CDN URL."""
import os
import sys
import time

import requests


def _shopify_url():
    return f"https://{os.environ['SHOPIFY_STORE_DOMAIN']}/admin/api/2025-01/graphql.json"


def _headers():
    return {
        "X-Shopify-Access-Token": os.environ["SHOPIFY_ADMIN_ACCESS_TOKEN"],
        "Content-Type": "application/json",
    }


def staged_upload(filename: str, size: int) -> dict:
    query = """
    mutation stagedUploadsCreate($input: [StagedUploadInput!]!) {
      stagedUploadsCreate(input: $input) {
        stagedTargets { url resourceUrl parameters { name value } }
        userErrors { field message }
      }
    }"""
    variables = {
        "input": [{
            "resource": "FILE",
            "filename": filename,
            "mimeType": "image/png",
            "fileSize": str(size),
            "httpMethod": "POST",
        }]
    }
    resp = requests.post(_shopify_url(), headers=_headers(),
                          json={"query": query, "variables": variables}, timeout=30)
    resp.raise_for_status()
    data = resp.json()["data"]["stagedUploadsCreate"]
    if data["userErrors"]:
        raise RuntimeError(data["userErrors"])
    return data["stagedTargets"][0]


def upload_bytes(target: dict, image_path: str):
    form = {p["name"]: p["value"] for p in target["parameters"]}
    with open(image_path, "rb") as f:
        files = {"file": (os.path.basename(image_path), f, "image/png")}
        resp = requests.post(target["url"], data=form, files=files, timeout=60)
    resp.raise_for_status()


def create_file(resource_url: str) -> str:
    query = """
    mutation fileCreate($files: [FileCreateInput!]!) {
      fileCreate(files: $files) {
        files { id fileStatus ... on MediaImage { image { url } } }
        userErrors { field message }
      }
    }"""
    variables = {"files": [{"originalSource": resource_url, "contentType": "IMAGE"}]}
    resp = requests.post(_shopify_url(), headers=_headers(),
                          json={"query": query, "variables": variables}, timeout=30)
    resp.raise_for_status()
    data = resp.json()["data"]["fileCreate"]
    if data["userErrors"]:
        raise RuntimeError(data["userErrors"])
    return data["files"][0]["id"]


def poll_cdn_url(file_id: str) -> str:
    query = """
    query($id: ID!) {
      node(id: $id) { ... on MediaImage { fileStatus image { url } } }
    }"""
    for _ in range(30):
        time.sleep(2)
        resp = requests.post(_shopify_url(), headers=_headers(),
                              json={"query": query, "variables": {"id": file_id}}, timeout=30)
        resp.raise_for_status()
        node = resp.json()["data"]["node"]
        if node["fileStatus"] == "READY":
            return node["image"]["url"]
        if node["fileStatus"] == "FAILED":
            raise RuntimeError("Shopify file processing failed")
    raise TimeoutError("Shopify file did not become READY in time")


def main():
    image_path = sys.argv[1]
    size = os.path.getsize(image_path)
    target = staged_upload(os.path.basename(image_path), size)
    upload_bytes(target, image_path)
    file_id = create_file(target["resourceUrl"])
    cdn_url = poll_cdn_url(file_id)
    print(cdn_url)


if __name__ == "__main__":
    main()
