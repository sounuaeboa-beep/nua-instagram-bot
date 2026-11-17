"""Comment engagement: auto-reply to comments and "Comente QUERO" (send the product link by private message).

Runs every ~20 minutes from GitHub Actions (.github/workflows/engage.yml):
  1. reads new comments on our recent posts (graph.instagram.com, permission instagram_business_manage_comments)
  2. a comment with the keyword (QUERO) gets a private message with the product and kit links, built only from the
     store feed (no AI, so prices and links are always right), plus a short public reply ("te mandei no direct")
  3. any other comment is read by Claude: reply (questions, compliments), reply + flag for a human (complaints,
     orders, delivery, exchanges, anything it cannot answer from the store facts), or ignore (spam, emoji-only
     from other brands, offensive). Every reply goes through a second review call before it is posted.
  4. data/engagement.json remembers every comment handled, so nothing is answered twice.

Switches live in data/settings.json, so they can be turned off without touching code.
Until the Instagram token has the comments permission, the run says so and exits without error."""
import argparse
import json
import os
import random
import sys
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import catalog  # noqa: E402
import content  # noqa: E402
from publish import GRAPH  # noqa: E402  (also loads a token renewed earlier in the same job)

DATA = Path(__file__).resolve().parent.parent / "data"
STATE_PATH = DATA / "engagement.json"
SETTINGS_PATH = DATA / "settings.json"
HISTORY_PATH = DATA / "history.json"
ALERTS_PATH = Path(__file__).resolve().parent.parent / "output" / "engagement_alerts.txt"

RECENT_POSTS = 12              # comments are read on our last N posts
MAX_AGE = timedelta(days=7)    # Instagram only allows a private reply within 7 days of the comment
MAX_ACTIONS_PER_RUN = 25       # safety cap: a flood of comments is handled over several runs
PRODUCT_NAMES = {"essencial": "Essencial (tanga)", "invisible": "Invisible (fio dental)", "sculpt": "Sculpt (cós alto)"}

DM_PUBLIC_REPLIES = [
    "Te mandei no direct! 💌", "Já te chamei no direct 🤍", "Corre no direct que o link tá lá ✨",
    "Mandei no direct pra você! 💌", "Olha o direct 🤍",
]
PERMISSION_HINTS = ("permission", "OAuthException", "(#10)", "(#200)", "(#3)")


class MissingPermission(RuntimeError):
    pass


# ---------- small helpers ----------

def _load(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def settings() -> dict:
    return {"auto_reply": True, "comment_to_dm": True, "dm_keyword": "QUERO", **_load(SETTINGS_PATH, {})}


def _norm(text: str) -> str:
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().upper()


def has_keyword(text: str, keyword: str) -> bool:
    """QUERO, quero!, "Quero 🙋", "eu quero" all count; "querosene" does not."""
    words = "".join(c if c.isalnum() else " " for c in _norm(text)).split()
    return _norm(keyword) in words


def _api(method: str, path: str, **kwargs) -> dict:
    token = os.environ["IG_ACCESS_TOKEN"]
    if method == "GET":
        resp = requests.get(f"{GRAPH}/{path}", params={**kwargs.get("params", {}), "access_token": token}, timeout=30)
    else:
        resp = requests.post(f"{GRAPH}/{path}", headers={"Authorization": f"Bearer {token}"},
                             timeout=30, **kwargs)
    if not resp.ok:
        if resp.status_code in (400, 403) and any(h in resp.text for h in PERMISSION_HINTS):
            raise MissingPermission(resp.text)
        raise RuntimeError(f"Instagram API {resp.status_code}: {resp.text}")
    return resp.json()


# ---------- reading ----------

def recent_posts(history: list[dict]) -> list[dict]:
    """Our last posts that have an Instagram id, newest first, with the product line they were about."""
    posts = [h for h in history if h.get("media_id")]
    return [{"media_id": h["media_id"], "product": h.get("product")} for h in posts[-RECENT_POSTS:]][::-1]


def comments_of(media_id: str) -> list[dict]:
    data = _api("GET", f"{media_id}/comments", params={"fields": "id,text,username,timestamp", "limit": 50})
    return data.get("data", [])


# ---------- writing (one place each, so dry runs never touch Instagram) ----------

def post_reply(comment_id: str, text: str) -> str:
    return _api("POST", f"{comment_id}/replies", data={"message": text})["id"]


def send_private_reply(comment_id: str, text: str) -> str:
    body = {"recipient": {"comment_id": comment_id}, "message": {"text": text}}
    return _api("POST", f"{os.environ['IG_USER_ID']}/messages", json=body).get("message_id", "")


# ---------- content ----------

def dm_text(product: str | None, cat: dict) -> str:
    """Private message with real links and prices only (no AI)."""
    lines = ["Oi! Que bom que você quer conhecer a nu.a 🤍"]
    for line in ([product] if product in cat else list(PRODUCT_NAMES)):
        entry = cat.get(line, {})
        single = entry.get("single")
        if single:
            lines.append(f"\n{PRODUCT_NAMES[line]}: avulsa por {catalog.brl(single['price'])}\n{single['url']}")
        for kit in sorted(entry.get("kits", []), key=lambda k: k["qty"]):
            lines.append(f"Kit com {kit['qty']}: {catalog.brl(kit['price'])} (≈ {catalog.brl(kit['per_piece'])} por peça)"
                         f"\n{kit['url']}")
    lines.append("\nQualquer dúvida sobre tamanho ou cor, é só responder aqui 💛")
    return "\n".join(lines)


REPLY_PROMPT = """Você responde comentários no Instagram da nu.a, marca brasileira de moda íntima feminina de preço justo.
VOZ: amiga que entende de roupa íntima; português do Brasil, feminino, "você", curto (1-2 frases, máx. 200
caracteres), caloroso, 0-2 emojis. Nunca formal, nunca vendedora insistente.

FATOS: use SOMENTE os FATOS (preços, kits, cores, benefícios). Nunca invente frete, prazo de entrega, estoque,
promoção, cupom, tamanho que não está nos FATOS. Nunca coloque URL: diga "link na bio" ou convide a comentar QUERO
para receber o link no direct (só se COMENTE_QUERO estiver ativo).

DECIDA a ação:
- "reply": elogio, pergunta que os FATOS respondem (cor, preço, kit, tecido, modelo), comentário simpático, marcação
  de amiga (responda à pessoa de forma leve).
- "reply_and_flag": reclamação, problema com pedido, entrega, troca, defeito, tamanho que você não consegue
  confirmar, ou qualquer pergunta que os FATOS não respondem. Responda com empatia e convide para o direct
  ("me chama no direct que a gente resolve"), sem prometer nada.
- "ignore": spam, golpe, divulgação de outras contas, ofensa, conteúdo sexual, ou comentário sem sentido.

Responda APENAS com JSON: {"action": "reply"|"reply_and_flag"|"ignore", "reply": "...", "why": "motivo curto"}"""

REPLY_REVIEW_PROMPT = """Você revisa uma resposta pública da nu.a a um comentário no Instagram.
Responda APENAS com JSON: {"approved": true|false, "reason": "..."}
REJEITE se a resposta: cita preço, kit, desconto, frete, prazo, estoque, material, tamanho ou cor que NÃO consta
nos FATOS; promete algo (troca, reembolso, entrega) ; contém URL; é rude, sensual, vulgar ou cria insegurança
corporal; fala de política/religião; não está no feminino ou usa "tu"; passa de 220 caracteres."""


def write_reply(comment: dict, product: str | None, facts: str, dm_on: bool, keyword: str) -> dict:
    user = (f"COMENTE_QUERO: {'ativo, palavra ' + keyword if dm_on else 'desligado'}\n"
            f"POST SOBRE: {PRODUCT_NAMES.get(product, 'linha nu.a em geral')}\n\nFATOS:\n{facts}\n\n"
            f"COMENTÁRIO de @{comment.get('username', '?')}: {comment.get('text', '')}")
    decision = content._ask(REPLY_PROMPT, user, max_tokens=1500)
    if decision.get("action") not in ("reply", "reply_and_flag"):
        return {"action": "ignore", "why": decision.get("why", "")}
    verdict = content._ask(REPLY_REVIEW_PROMPT, f"FATOS:\n{facts}\n\nCOMENTÁRIO: {comment.get('text', '')}\n\n"
                                                f"RESPOSTA: {decision.get('reply', '')}", max_tokens=1000)
    if not verdict.get("approved") or not decision.get("reply"):
        return {"action": "flag", "why": f"reply rejected by reviewer: {verdict.get('reason', '')}"}
    return decision


# ---------- main ----------

def _set_status(state: dict, value: str, now: datetime) -> None:
    """Saved only when it changes, so the state file (and the repo) is not rewritten every 20 minutes."""
    if state.get("status", {}).get("value") != value:
        state["status"] = {"value": value, "since": now.isoformat()}


def run(dry_run: bool) -> int:
    cfg = settings()
    if not cfg["auto_reply"] and not cfg["comment_to_dm"]:
        print("[engage] both switches are off in data/settings.json: nothing to do")
        return 0

    history = _load(HISTORY_PATH, [])
    state = _load(STATE_PATH, {"handled": {}})
    handled = state["handled"]
    now = datetime.now(timezone.utc)
    me = _api("GET", "me", params={"fields": "username"})["username"]
    cat, alerts, actions = None, [], 0

    try:
        for post in recent_posts(history):
            for comment in comments_of(post["media_id"]):
                cid = comment["id"]
                if cid in handled or comment.get("username") == me:
                    continue
                created = datetime.fromisoformat(comment["timestamp"].replace("+0000", "+00:00"))
                if now - created > MAX_AGE:
                    handled[cid] = {"action": "skipped_old"}
                    continue
                if actions >= MAX_ACTIONS_PER_RUN:
                    break
                actions += 1
                cat = cat or catalog.get_catalog()
                product = post["product"]
                record = {"media_id": post["media_id"], "username": comment.get("username"),
                          "text": comment.get("text", "")[:300], "at": now.isoformat()}

                if cfg["comment_to_dm"] and has_keyword(comment.get("text", ""), cfg["dm_keyword"]):
                    message, public = dm_text(product, cat), random.choice(DM_PUBLIC_REPLIES)
                    print(f"[dm] @{record['username']}: {record['text']!r} -> private link message + {public!r}")
                    if not dry_run:
                        send_private_reply(cid, message)
                        post_reply(cid, public)
                    record.update(action="dm", reply=public)
                elif cfg["auto_reply"]:
                    facts = catalog.facts_for(product, cat) if product in cat else "\n\n".join(
                        catalog.facts_for(p, cat) for p in PRODUCT_NAMES if p in cat)
                    decision = write_reply(comment, product, facts, cfg["comment_to_dm"], cfg["dm_keyword"])
                    print(f"[{decision['action']}] @{record['username']}: {record['text']!r} -> "
                          f"{decision.get('reply', '')!r} ({decision.get('why', '')})")
                    if decision["action"] in ("reply", "reply_and_flag") and not dry_run:
                        post_reply(cid, decision["reply"])
                    if decision["action"] in ("reply_and_flag", "flag"):
                        alerts.append(f"@{record['username']} on post {post['media_id']}: {record['text']}\n"
                                      f"   bot: {decision.get('reply') or '(no reply posted)'} | {decision.get('why', '')}")
                    record.update(action=decision["action"], reply=decision.get("reply", ""), why=decision.get("why", ""))
                else:
                    continue
                handled[cid] = record
                time.sleep(2)   # gentle pace: replies look natural and stay far from rate limits
        _set_status(state, "ok", now)
    except MissingPermission:
        _set_status(state, "missing_permission", now)
        raise
    finally:
        if not dry_run:
            STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")

    if alerts:
        ALERTS_PATH.parent.mkdir(exist_ok=True)
        ALERTS_PATH.write_text("\n".join(alerts), encoding="utf-8")
        print("\n[engage] NEEDS A HUMAN:\n" + "\n".join(alerts))
    print(f"[engage] done: {actions} comment(s) handled{' (dry run, nothing posted)' if dry_run else ''}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="decide and print, but post nothing")
    args = parser.parse_args()
    try:
        return run(args.dry_run)
    except MissingPermission as error:
        print("[engage] The Instagram token does not have the comments permission yet "
              "(instagram_business_manage_comments). Nothing was done. Re-authorize with scripts/ig_authorize.py.\n"
              f"         API said: {str(error)[:300]}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
