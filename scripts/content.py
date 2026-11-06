"""Caption + art brief for today's post (Claude call #1) and an independent
brand/legal review of it (Claude call #2). Replaces brand_voice.py,
generate_copy.py and guardrail_check.py."""
import json
from pathlib import Path

from anthropic import Anthropic

MODEL = "claude-sonnet-5-5"
PLAYBOOK_PATH = Path(__file__).resolve().parent.parent / "data" / "playbook.md"

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
    )
    return _parse_json(message.content[0].text)


def _system_prompt() -> str:
    playbook = PLAYBOOK_PATH.read_text(encoding="utf-8") if PLAYBOOK_PATH.exists() else ""
    return f"{SYSTEM_PROMPT}\n\nPLAYBOOK:\n{playbook}" if playbook else SYSTEM_PROMPT


def create_post(pillar: str, product: str, facts: str, recent_hooks: list[str]) -> dict:
    """Generate, then have a second call review it; one retry with the reviewer's feedback."""
    feedback = ""
    for _ in range(2):
        user = (
            f"PILAR DE HOJE: {pillar} — {PILLARS[pillar]}\nLINHA: {product}\n\nFATOS:\n{facts}\n\n"
            f"Ganchos recentes (não repita): {recent_hooks or 'nenhum'}\n{feedback}\n"
            "Gere UMA publicação de feed pronta para postar hoje."
        )
        post = _ask(_system_prompt(), user, max_tokens=1500)

        verdict = _ask(REVIEW_PROMPT, f"FATOS:\n{facts}\n\nLEGENDA:\n{post['caption']}", max_tokens=300)
        if verdict["approved"]:
            return post
        feedback = f"A versão anterior foi REJEITADA pelo revisor: {verdict['reason']} Corrija isso."

    raise RuntimeError(f"Reviewer rejected the caption twice: {verdict['reason']}")
