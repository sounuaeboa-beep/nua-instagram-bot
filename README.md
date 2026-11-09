# nua-instagram-bot

One automatic Instagram post per day for @nu.a.

```
GitHub Actions (10:00 BRT)
  -> catalog.py      real prices/kits/links from the store's public product feed (no credentials)
  -> content.py      pick pillar (40/25/25/10 mix) + product, Claude writes the caption using data/playbook.md,
                     a second Claude call reviews it against the facts and brand rules
  -> generate_art.py Pillow: photo from media/ + headline text strip (4:5)
  -> publish.py      host on Cloudinary (free), publish via Instagram API, refresh the 60-day token
  -> data/history.json  one entry per post; also drives the rotation
```

## Run it

```bash
pip install -r requirements.txt
python scripts/run_daily.py --dry-run      # caption + image + token check, publishes nothing
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
