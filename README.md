# nua-instagram-bot

One automatic Instagram post per day for @nu.a.

```
GitHub Actions (09:45 and 17:45 BRT, best effort: GitHub can start scheduled runs hours late)
  -> catalog.py      real prices/kits/links/photos from the store's public product feed (no credentials)
  -> performance.py  reads likes/comments of our own posts -> data/learnings.md (shown to the caption writer)
  -> formats.py      picks the format: about 40% Reels, 20% carousels (education/multipack days), 40% images
  -> content.py      pillar (40/25/25/10 mix) + product; Claude writes the caption using data/playbook.md and the
                     learnings; a second Claude call reviews it; recent headlines are never repeated
  -> photos.py       picks photos: media/ library, media/lifestyle, and the store's own listing photos;
                     photos used in the last 20 posts are skipped
  -> generate_art.py 4:5 feed post (photo + headline strip) and branded carousel cards
  -> make_reel.py    9.5-13 s vertical Reel: 3-4 photos, zoom/drift motions, cross-fades, "link na bio" end card
  -> publish.py      host on Cloudinary (free), publish image / Reel / carousel via the Instagram API, renew the token
  -> data/history.json  one entry per post (format, photos used); also drives rotation and the no-repeat memory
```
Any Reel or carousel problem falls back to a normal image post, so the day's post is never lost.

## Run it

```bash
pip install -r requirements.txt
python scripts/run_daily.py --dry-run      # caption + image + token check, publishes nothing
python scripts/run_daily.py --dry-run --format carousel   # same, forcing a format: image | reel | carousel (also a choice in the workflow form)
python scripts/run_daily.py                # live
```
In GitHub: Actions > "Daily Instagram Post" > Run workflow (dry run is the default for manual runs; the image is
attached to the run as the `dry-run-image` artifact).

## Secrets
See `.env.example`. The scheduled run is live; a failed run makes GitHub email you.

## Changing things
- **Photos:** product close-ups go in `media/essencial|invisible|sculpt/`; people/lifestyle shots in `media/lifestyle/`
  (used on comfort and aspirational days; wide landscape photos are skipped). Posts are 4:5 (1080x1350): photo on top, text strip below.
- **Voice / strategy:** edit `data/playbook.md` and `scripts/content.py`.
- **Model:** one constant, `MODEL` in `scripts/content.py`.
