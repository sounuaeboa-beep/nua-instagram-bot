"""Reads how our own posts performed (likes and comments from the Instagram API) and writes short learnings that the
caption writer sees before every post. Best effort: any failure here is reported but never blocks a post."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import requests

import publish

DATA = Path(__file__).resolve().parent.parent / "data"
PERF_PATH, LEARNINGS_PATH = DATA / "performance.json", DATA / "learnings.md"
REFRESH_DAYS = 14                      # counts keep growing for a while; older posts are frozen


def _age_days(iso: str) -> float:
    return (datetime.now(timezone.utc) - datetime.fromisoformat(iso)).total_seconds() / 86400


def update(history: list[dict]) -> dict:
    perf = json.loads(PERF_PATH.read_text()) if PERF_PATH.exists() else {}
    token = os.environ["IG_ACCESS_TOKEN"]
    for post in history:
        media_id = str(post.get("media_id", ""))
        if not media_id or (media_id in perf and _age_days(post["date"]) > REFRESH_DAYS):
            continue
        data = publish._json(requests.get(
            f"{publish.GRAPH}/{media_id}",
            params={"fields": "like_count,comments_count", "access_token": token}, timeout=30,
        ))
        perf[media_id] = {"likes": data.get("like_count", 0), "comments": data.get("comments_count", 0),
                          "read_at": datetime.now(timezone.utc).isoformat()}
    PERF_PATH.write_text(json.dumps(perf, indent=2), encoding="utf-8")
    return perf


def write_learnings(history: list[dict], perf: dict) -> str:
    rows = []
    for post in history:
        p = perf.get(str(post.get("media_id", "")))
        if p:
            rows.append({**post, "score": p["likes"] + 2 * p["comments"]})      # a comment says more than a like
    if len(rows) < 4:
        LEARNINGS_PATH.write_text("", encoding="utf-8")
        return ""
    lines = [f"Resultados dos nossos últimos {len(rows)} posts (pontos = curtidas + 2 x comentários):"]
    for key, label in (("format", "formato"), ("pillar", "pilar"), ("product", "linha")):
        groups: dict[str, list[int]] = {}
        for r in rows:
            groups.setdefault(r.get(key, "image"), []).append(r["score"])
        ranked = sorted(groups.items(), key=lambda kv: -sum(kv[1]) / len(kv[1]))
        lines.append(f"- Média por {label}: " + "; ".join(f"{k} {sum(v) / len(v):.0f} ({len(v)} posts)" for k, v in ranked))
    best = sorted(rows, key=lambda r: -r["score"])[:3]
    lines.append("- Mais engajados: " + " | ".join(f"\"{r.get('image_headline', '')}\" ({r['score']})" for r in best))
    lines.append("Use como pista do que funciona; não é regra e nunca repita os mesmos textos.")
    text = "\n".join(lines)
    LEARNINGS_PATH.write_text(text, encoding="utf-8")
    return text
