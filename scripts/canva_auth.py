"""Canva Connect API access tokens expire every 4h, and refresh tokens rotate
on every use (the old one is invalidated the instant a new one is issued) —
so each run must refresh once and immediately persist the new refresh token,
or tomorrow's run breaks."""
import base64
import os
import subprocess

import requests

TOKEN_URL = "https://api.canva.com/rest/v1/oauth/token"


def refresh() -> str:
    """Exchanges the stored refresh token for a fresh access token, persists
    the newly-issued refresh token back to GitHub Secrets, and returns the
    access token to use for this run."""
    credentials = f"{os.environ['CANVA_CLIENT_ID']}:{os.environ['CANVA_CLIENT_SECRET']}"
    basic_auth = base64.b64encode(credentials.encode()).decode()

    resp = requests.post(
        TOKEN_URL,
        headers={
            "Authorization": f"Basic {basic_auth}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "refresh_token",
            "refresh_token": os.environ["CANVA_REFRESH_TOKEN"],
        },
        timeout=30,
    )
    resp.raise_for_status()
    tokens = resp.json()

    _persist_new_refresh_token(tokens["refresh_token"])
    return tokens["access_token"]


def _persist_new_refresh_token(new_refresh_token: str):
    repo = os.environ.get("GITHUB_REPOSITORY")
    admin_token = os.environ.get("REPO_ADMIN_TOKEN")
    if not repo or not admin_token:
        # Local/manual run — nothing to persist to, caller is responsible
        # for updating the secret by hand.
        return

    subprocess.run(
        ["gh", "secret", "set", "CANVA_REFRESH_TOKEN", "--body", new_refresh_token, "--repo", repo],
        env={**os.environ, "GH_TOKEN": admin_token},
        check=True,
    )
