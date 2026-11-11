"""Caption + art brief for today's post (Claude call #1) and an independent
brand/legal review of it (Claude call #2). Replaces brand_voice.py,
generate_copy.py and guardrail_check.py."""
import json
import re
import unicodedata
from pathlib import Path

from anthropic import Anthropic

MODEL = "claude-sonnet-5-5"
PLAYBOOK_PATH = Path(__file__).resolve().parent.parent / "data" / "playbook.md"
LEARNINGS_PATH = Path(__file__).resolve().parent.parent / "data" / "learnings.md"

PRODUCTS = ["essencial", "invisible", "sculpt"]

# Content mix: 40% comfort/lifestyle, 25% education, 25% multipacks, 10% aspirational.
# A 20-slot cycle gives that split exactly, with the pillars spread out.
PILLAR_CYCLE = [
    "conforto", "educacao", "multipack", "conforto", "educacao",
    "conforto", "multipack", "aspiracional", "conforto", "educacao",
    "multipack", "conforto", "educacao", "conforto", "multipack",
    "aspiracional", "conforto", "educacao", "multipack", "conforto",
]

PILLARS = {
    "conforto": "Conforto e lifestyle do dia a dia: mulheres reais, rotina, 'pegar e usar sem pensar'. "
                "Identificação e leveza, benefício prático em primeiro lugar.",
    "educacao": "Educação de produto: explique UM benefício concreto (sem costura/corte a laser, não marca sob a roupa, "
                "microfibra, cós alto, forro de algodão) de forma simples e informativa.",
    "multipack": "Multipacks e conversão: valor pela compra inteligente. Use SOMENTE os kits e preços dos FATOS "
                 "(preço por peça do kit vs. avulso). CTA claro de compra.",
    "aspiracional": "Visual aspiracional: minimalista, elegante, luz natural. Poucas palavras, sem apelo sensual e "
                    "sem sinais de luxo ou preço alto.",
}

SYSTEM_PROMPT = """Você é a redatora de copy da nu.a, marca brasileira de moda íntima feminina de preço justo.

IDENTIDADE: conforto real, preço justo, design que entende o corpo real, simplicidade que funciona todo dia.
VOZ: português do Brasil, amigável, confiante, direta, sem frescura. Fala como uma amiga que entende de roupa
íntima. Nunca condescendente, nunca formal. Enfatize compra inteligente e conforto diário.

NUNCA: política, religião, polêmica; insegurança corporal ou comparação negativa; linguagem triste,
constrangedora ou vulgar; apelo excessivamente sensual; prometer o que o produto não entrega.

FATOS: use SOMENTE os preços, kits, cores e benefícios listados em FATOS. Nunca invente desconto, frete,
prazo, promoção, material ou número de avaliações. Não coloque URL na legenda: diga "link na bio".

REGRAS DE ESCRITA: "você" (nunca "tu"); contrações naturais ("tá", "pra"); toda a copy no feminino; frases
curtas, parágrafos de 1-2 linhas; 1-3 emojis por bloco; sem anglicismos desnecessários.
TÉCNICA: abra com um gancho que ative uma emoção antes de falar do produto; use linguagem sensorial
(faça a leitora sentir, não só descreva); feche com um CTA que reforce esse estado emocional.

REGRA DE REFERÊNCIA: o PLAYBOOK traz padrões aprendidos com outras marcas. Aprenda ganchos, composição e
estrutura; jamais reproduza textos, fotos, marcas ou campanhas de terceiros.

SAÍDA: responda APENAS com JSON válido, sem markdown:
{"hook": "...", "caption": "legenda completa pronta para postar (gancho + corpo + CTA, quebras de linha \\n)",
 "hashtags": ["#nua", ...] (6 a 10),
 "image_headline": "máx. 6 palavras", "image_subheadline": "máx. 10 palavras"}"""

REVIEW_PROMPT = """Você é o revisor de marca e conformidade da nu.a. Avalie a legenda contra os FATOS e as regras.
Responda APENAS com JSON: {"approved": true|false, "reason": "..."}

REJEITE se a legenda:
- cita preço, kit, desconto, frete, prazo, material ou cor que NÃO consta nos FATOS
- menciona política, religião ou polêmica
- cria insegurança corporal ou comparação negativa
- usa linguagem triste, constrangedora, vulgar ou excessivamente sensual
- promete algo que o produto não entrega (milagre, emagrecimento, cura)
- não está no feminino, usa "tu", ou não tem CTA claro
- contém URL (deve dizer "link na bio")"""


def pick_today(history: list[dict]) -> tuple[str, str]:
    """(pillar, product) for today: fixed content-mix cycle, least-recently-used product."""
    pillar = PILLAR_CYCLE[len(history) % len(PILLAR_CYCLE)]

    def last_used(product: str) -> int:
        for i in range(len(history) - 1, -1, -1):
            if history[i].get("product") == product:
                return i
        return -1

    return pillar, min(PRODUCTS, key=last_used)


def _parse_json(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON object in model reply: {text[:200]}")
    return json.loads(text[start:end + 1])


def _ask(system: str, user: str, max_tokens: int) -> dict:
    message = Anthropic().messages.create(  # reads ANTHROPIC_API_KEY
        model=MODEL, max_tokens=max_tokens, system=system,
        messages=[{"role": "user", "content": user}],
        # Sonnet 5.5 thinks by default and thinking tokens count toward max_tokens: keep it light
        extra_body={"output_config": {"effort": "low"}},
    )
    # The reply can start with a "thinking" block: read only the text blocks
    text = "".join(block.text for block in message.content if block.type == "text")
    if not text:
        raise RuntimeError(f"Model returned no text (stop_reason={message.stop_reason}); raise max_tokens?")
    return _parse_json(text)


def _system_prompt() -> str:
    playbook = PLAYBOOK_PATH.read_text(encoding="utf-8") if PLAYBOOK_PATH.exists() else ""
    learnings = LEARNINGS_PATH.read_text(encoding="utf-8").strip() if LEARNINGS_PATH.exists() else ""
    prompt = f"{SYSTEM_PROMPT}\n\nPLAYBOOK:\n{playbook}" if playbook else SYSTEM_PROMPT
    return f"{prompt}\n\nAPRENDIZADOS DOS NOSSOS POSTS:\n{learnings}" if learnings else prompt


FORMAT_BRIEFS = {
    "image": "Publicação de feed (imagem única).",
    "reel": "REEL: vídeo curto de ~10 s sem fala. O image_headline é o texto que aparece no vídeo: gancho forte e curto.",
    "carousel": (
        "CARROSSEL: além dos campos acima, devolva \"slides\": lista de 2 ou 3 itens "
        '{"title": "máx. 6 palavras", "body": "máx. 22 palavras"}. Cada slide ensina ou mostra UMA ideia, usando '
        "SOMENTE os FATOS. O image_headline é a capa; a legenda convida a deslizar."
    ),
}


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _slides_ok(post: dict) -> bool:
    slides = post.get("slides")
    return (isinstance(slides, list) and 2 <= len(slides) <= 3
            and all(isinstance(x, dict) and x.get("title") and x.get("body") for x in slides))


def create_post(pillar: str, product: str, facts: str, recent_hooks: list[str],
                recent_headlines: list[str] = (), fmt: str = "image") -> dict:
    """Generate, then have a second call review it. Up to 3 attempts: a reviewer rejection, a headline that repeats a
    recent one, or a malformed carousel each send the model back with feedback. A repeated headline on the last
    attempt is accepted rather than blocking the day's post."""
    seen = {_norm(h) for h in recent_headlines}
    feedback, verdict = "", {"reason": ""}
    for attempt in range(3):
        last = attempt == 2
        user = (
            f"PILAR DE HOJE: {pillar} — {PILLARS[pillar]}\nLINHA: {product}\nFORMATO: {FORMAT_BRIEFS[fmt]}\n\n"
            f"FATOS:\n{facts}\n\nGanchos recentes (não repita): {recent_hooks or 'nenhum'}\n"
            f"Textos de imagem recentes (não repita nem parafraseie): {list(recent_headlines) or 'nenhum'}\n{feedback}\n"
            "Gere UMA publicação pronta para postar hoje."
        )
        post = _ask(_system_prompt(), user, max_tokens=6000)

        if fmt == "carousel" and not _slides_ok(post):
            feedback = "Faltaram os slides: devolva 2 ou 3 itens com title e body."
            if last:
                raise RuntimeError("Model did not return valid carousel slides")
            continue
        if _norm(post["image_headline"]) in seen and not last:
            feedback = f"O image_headline \"{post['image_headline']}\" repete um texto recente. Crie um novo."
            continue

        text = post["caption"] + "".join(f"\n[slide] {x['title']}: {x['body']}" for x in post.get("slides", []))
        verdict = _ask(REVIEW_PROMPT, f"FATOS:\n{facts}\n\nLEGENDA:\n{text}", max_tokens=2000)
        if verdict["approved"]:
            return post
        feedback = f"A versão anterior foi REJEITADA pelo revisor: {verdict['reason']} Corrija isso."

    raise RuntimeError(f"Reviewer rejected the post: {verdict['reason']}")
