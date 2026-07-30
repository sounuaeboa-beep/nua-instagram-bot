# nua-instagram-bot

Fully autonomous daily Instagram post pipeline for @nu.a.

## Pipeline

```
GitHub Actions (daily cron)
  -> Claude API        generate_copy.py    caption + art brief, brand voice baked in
  -> Claude API        guardrail_check.py  brand/legal safety pass (no human review)
  -> Canva Connect API generate_art.py     autofill brand template, export PNG
  -> Shopify Files API  upload_to_shopify.py  host the PNG, get a public CDN URL
  -> Instagram Graph API publish.py        create media container, publish
  -> data/history.json                     append log, committed back by the workflow
```

Product/objective rotation state lives in `data/product_rotation.json` so the bot
doesn't repeat the same product or angle two days in a row.

## One-time setup

### 1. GitHub secrets

Repo → Settings → Secrets and variables → Actions → add:

| Secret | Where to get it |
|---|---|
| `ANTHROPIC_API_KEY` | console.anthropic.com |
| `CANVA_CLIENT_ID` / `CANVA_CLIENT_SECRET` | Canva Developer Portal → your Connect API integration |
| `CANVA_REFRESH_TOKEN` | One-time OAuth flow (see below) — **rotates on every run**, the pipeline updates this secret itself |
| `CANVA_BRAND_TEMPLATE_ID` | The brand template ID from the nu.a daily-post design in Canva |
| `SHOPIFY_STORE_DOMAIN` | e.g. `your-store.myshopify.com` |
| `SHOPIFY_ADMIN_ACCESS_TOKEN` | Shopify Admin → Settings → Apps → Develop apps → create an app with `write_files` scope |
| `IG_ACCESS_TOKEN` | Long-lived token from the Instagram Login OAuth flow (see below) |
| `IG_USER_ID` | From `GET https://graph.instagram.com/me?fields=id,username` |
| `REPO_ADMIN_TOKEN` | A GitHub Personal Access Token (fine-grained, `secrets:write` on this repo) — needed for **both** the Instagram token-refresh workflow and every daily run (to persist Canva's rotated refresh token) |

**Important:** Canva access tokens expire every 4 hours, and refresh tokens rotate on
every use — the old one is invalidated the instant a new one is issued. `canva_auth.py`
handles this automatically each run, but if a run ever fails *after* the Canva refresh
step but *before* `REPO_ADMIN_TOKEN` successfully updates the secret, the next run will
fail too (the stored refresh token would be stale). Check the Actions log if that happens
— you'd need to redo the Canva OAuth flow once to get a fresh refresh token.

### 2. Canva brand template

The template must have two autofill text fields named exactly `headline` and `subheadline`
(rename Canva's placeholder field names to match, or update `generate_art.py` if you prefer
different names).

### 3. Instagram Login token

Already covered in our setup conversation — Instagram App ID `1687452435669529`,
scopes `instagram_business_basic,instagram_business_content_publish`. Store the
resulting long-lived token as `IG_ACCESS_TOKEN`.

## Running locally

```bash
cd scripts
pip install -r ../requirements.txt
export ANTHROPIC_API_KEY=... CANVA_ACCESS_TOKEN=... CANVA_BRAND_TEMPLATE_ID=... \
       SHOPIFY_STORE_DOMAIN=... SHOPIFY_ADMIN_ACCESS_TOKEN=... IG_ACCESS_TOKEN=... IG_USER_ID=...
python run_daily.py
```

## Manual trigger

Actions tab → "Daily Instagram Post" → Run workflow (uses `workflow_dispatch`), useful
for testing without waiting for the 10:00 BRT cron.
