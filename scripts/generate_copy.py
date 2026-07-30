"""Generates today's caption + art brief via the Claude API."""
import json
import os
import random

from anthropic import Anthropic

from brand_voice import SYSTEM_PROMPT

ROTATION_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "product_rotation.json")


def pick_today(rotation):
    products = rotation["products"]
    objetivos = rotation["objetivos"]

    choices = [p for p in products if p != rotation["last_product"]] or products
    product = random.choice(choices)

    obj_choices = [o for o in objetivos if o != rotation["last_objetivo"]] or objetivos
    objetivo = random.choice(obj_choices)

    return product, objetivo


def generate_caption(product: str, objetivo: str) -> dict:
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    message = client.messages.create(
        model="claude-opus-4-5-20251101",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": (
                f"Modelo: {product}\nFormato: Feed/Carrossel\nObjetivo: {objetivo}\n\n"
                "Gere UMA versão final (não A/B) pronta para postar hoje."
            ),
        }],
    )

    text = message.content[0].text.strip()
    return json.loads(text)


def main():
    with open(ROTATION_PATH) as f:
        rotation = json.load(f)

    product, objetivo = pick_today(rotation)
    result = generate_caption(product, objetivo)
    result["product"] = product
    result["objetivo"] = objetivo

    rotation["last_product"] = product
    rotation["last_objetivo"] = objetivo
    with open(ROTATION_PATH, "w") as f:
        json.dump(rotation, f, ensure_ascii=False, indent=2)

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
