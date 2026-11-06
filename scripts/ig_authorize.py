"""One-time (and every ~60 days if the bot ever misses a refresh) Instagram re-authorization helper.
Run it on your own computer, never in CI:  python scripts/ig_authorize.py

1. Open the authorization URL it prints, log in as @nu.a, click Allow.
2. You land on the redirect page; copy the FULL address from the browser bar and paste it here.
3. Paste the Instagram app secret when asked (hidden).
The long-lived token and the user id go to your clipboard one at a time, so they never show on screen:
paste each into the matching GitHub repo secret (IG_ACCESS_TOKEN, IG_USER_ID)."""
import getpass
import subprocess
import sys
from urllib.parse import parse_qs, urlencode, urlparse

import requests

APP_ID = "1687452435669529"  # Instagram app ID (not the Meta app ID)
REDIRECT = "https://sounuaeboa-beep.github.io/nua-instagram-bot/"
SCOPES = "instagram_business_basic,instagram_business_content_publish"


def to_clipboard(text: str) -> None:
    subprocess.run(["pbcopy"], input=text, text=True, check=True)


def main() -> None:
    query = urlencode({
        "client_id": APP_ID, "redirect_uri": REDIRECT, "response_type": "code", "scope": SCOPES,
    })
    print("1) Open this URL, log in as @nu.a and allow:\n\n   https://www.instagram.com/oauth/authorize?" + query + "\n")
    pasted = input("2) Paste the full address you were redirected to: ").strip()
    code = parse_qs(urlparse(pasted).query).get("code", [pasted])[0].removesuffix("#_")
    secret = getpass.getpass("3) Instagram app secret (hidden): ").strip()

    short = requests.post("https://api.instagram.com/oauth/access_token", data={
        "client_id": APP_ID, "client_secret": secret, "grant_type": "authorization_code",
        "redirect_uri": REDIRECT, "code": code,
    }, timeout=30)
    if not short.ok:
        sys.exit(f"Code exchange failed ({short.status_code}): {short.text}\nCodes work once and expire in minutes: start again.")
    short = short.json()

    long = requests.get("https://graph.instagram.com/access_token", params={
        "grant_type": "ig_exchange_token", "client_secret": secret, "access_token": short["access_token"],
    }, timeout=30)
    if not long.ok:
        sys.exit(f"Long-lived exchange failed ({long.status_code}): {long.text}")
    long = long.json()

    print(f"\nDone. Long-lived token valid {long['expires_in'] // 86400} days (the daily run renews it).")
    to_clipboard(str(short["user_id"]))
    input("IG_USER_ID is on your clipboard. Paste it into the GitHub secret, then press Enter... ")
    to_clipboard(long["access_token"])
    input("IG_ACCESS_TOKEN is on your clipboard. Paste it into the GitHub secret, then press Enter... ")
    to_clipboard("")
    print("Clipboard cleared.")


if __name__ == "__main__":
    main()
