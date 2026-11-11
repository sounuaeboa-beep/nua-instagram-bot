"""Copy for Stories (Claude call + independent review). Stories carry no caption: all text is drawn on the images,
so it is short, has no emojis and no URLs ("link na bio" is added by the art code)."""
import json

import content

CLOSING = '"closing": {"headline": "máx. 6 palavras", "subheadline": "máx. 10 palavras"}'

# set type -> what Claude must return (besides the common "closing" text shown over a product photo)
SPECS = {
    "mito": (
        'MITO OU VERDADE. Devolva {"statement": "afirmação que muita gente acredita sobre calcinha, tamanho, tecido ou '
        'conforto, máx. 14 palavras", "is_myth": true|false, "explanation": "resposta curta e verdadeira, máx. 26 '
        f'palavras", {CLOSING}}}. Só use afirmações que os FATOS confirmam ou desmentem, ou dicas de uso inofensivas '
        "(escolher tamanho, lavar, tecido). Nada de saúde, medicina ou promessa de resultado no corpo."
    ),
    "escolha": (
        'ESCOLHA 1 OU 2. Duas fotos serão mostradas. Devolva {"question": "pergunta leve que se responde com 1 ou 2, '
        f'máx. 8 palavras, sem citar cor ou modelo específico", "hint": "máx. 5 palavras, ex: Responde aqui com 1 ou 2", {CLOSING}}}.'
    ),
    "dica": (
        'DICA RÁPIDA. Devolva {"title": "máx. 7 palavras", "body": "máx. 28 palavras, ensina UMA coisa útil e concreta '
        f'usando só os FATOS", {CLOSING}}}.'
    ),
    "kit": f"KIT. Devolva só {{{CLOSING}}}: o texto da foto do kit, ligado a economia de comprar mais de uma.",
    "novo": f"NOVO NO FEED. Devolva só {{{CLOSING}}}: texto de uma foto do produto que apareceu no post de hoje.",
    "produto": f"PRODUTO. Devolva só {{{CLOSING}}}: texto de uma foto do produto, foco em conforto no dia a dia.",
}

STORY_RULES = """
FORMATO STORIES: todo o texto vai escrito em cima da imagem. Sem emojis, sem hashtags, sem URL, sem preços
inventados. Frases curtíssimas. Responda APENAS com JSON válido, sem markdown."""

REVIEW = """Você é o revisor de marca e conformidade da nu.a. Avalie os textos de Stories contra os FATOS.
Responda APENAS com JSON: {"approved": true|false, "reason": "..."}

REJEITE se algum texto:
- cita preço, kit, desconto, frete, prazo, material ou cor que NÃO consta nos FATOS
- afirma algo falso ou duvidoso como verdade (principalmente no mito ou verdade)
- fala de saúde, doença, emagrecimento, ou promete resultado no corpo
- menciona política, religião ou polêmica
- cria insegurança corporal ou comparação negativa, ou é vulgar / excessivamente sensual
- não está no feminino ou usa "tu"
- contém URL"""


def _system() -> str:
    base = content.SYSTEM_PROMPT.split("SAÍDA:")[0].strip()
    playbook = content.PLAYBOOK_PATH.read_text(encoding="utf-8") if content.PLAYBOOK_PATH.exists() else ""
    return f"{base}\n{STORY_RULES}\n\nPLAYBOOK:\n{playbook}"


def _texts(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False)


def create_set(set_type: str, product: str, facts: str, recent_texts: list[str]) -> dict:
    """Text for one Stories set. Up to 3 attempts; the reviewer's feedback is sent back to the writer."""
    feedback, verdict = "", {"reason": ""}
    for _ in range(3):
        user = (
            f"CONJUNTO DE STORIES: {SPECS[set_type]}\nLINHA: {product}\n\nFATOS:\n{facts}\n\n"
            f"Textos recentes de stories (não repita nem parafraseie): {recent_texts or 'nenhum'}\n{feedback}\n"
            "Gere o conjunto de hoje."
        )
        data = content._ask(_system(), user, max_tokens=4000)
        if not isinstance(data.get("closing"), dict) or not data["closing"].get("headline"):
            feedback = 'Faltou o campo "closing" com headline e subheadline.'
            continue
        verdict = content._ask(REVIEW, f"FATOS:\n{facts}\n\nTEXTOS:\n{_texts(data)}", max_tokens=2000)
        if verdict["approved"]:
            return data
        feedback = f"A versão anterior foi REJEITADA pelo revisor: {verdict['reason']} Corrija isso."
    raise RuntimeError(f"Story copy not approved: {verdict['reason']}")


def main_texts(set_type: str, data: dict) -> list[str]:
    """The distinctive texts of a set, stored in history so later sets do not repeat them."""
    keys = {"mito": ["statement"], "escolha": ["question"], "dica": ["title"]}.get(set_type, [])
    return [data[k] for k in keys if data.get(k)] + [data["closing"]["headline"]]
