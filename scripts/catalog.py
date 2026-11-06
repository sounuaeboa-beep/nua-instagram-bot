"""Reads nu.a's real product facts (prices, kits, links) from the store's public
product feed. No credentials needed, and it keeps Claude from inventing offers."""
import html
import os
import re

import requests

STORE_DOMAIN = os.environ.get("STORE_DOMAIN", "lojamomo.com.br")

# SKU family -> product line used across the project
LINES = {"CLT100": "essencial", "CLF200": "invisible", "CMF300": "sculpt"}
LINE_NAMES = {"essencial": "nu.a Essencial (tanga)", "invisible": "nu.a Invisible (fio dental)",
              "sculpt": "nu.a Sculpt (cós alto fio dental, microfibra)"}


def _fetch_products() -> list[dict]:
    resp = requests.get(f"https://{STORE_DOMAIN}/products.json", params={"limit": 250}, timeout=30)
    resp.raise_for_status()
    return resp.json()["products"]


def _line_of(product: dict) -> str | None:
    tags = {t.upper() for t in product.get("tags", [])}
    if "NU.A" not in tags:
        return None
    for sku_family, line in LINES.items():
        if sku_family in tags:
            return line
    return None


def _kit_size(title: str) -> int:
    match = re.match(r"\s*Kit\s+(\d+)", title, re.IGNORECASE)
    return int(match.group(1)) if match else 1


def brl(value: float) -> str:
    return f"R$ {value:.2f}".replace(".", ",")


def _clean(text: str, limit: int = 400) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()[:limit]


def get_catalog() -> dict[str, dict]:
    """Returns {line: {name, single, kits[], colors, description}}; prices in BRL."""
    catalog: dict[str, dict] = {}
    for product in _fetch_products():
        line = _line_of(product)
        if not line:
            continue
        entry = catalog.setdefault(line, {"name": LINE_NAMES[line], "single": None, "kits": [], "colors": set()})
        prices = [float(v["price"]) for v in product["variants"]]
        url = f"https://{STORE_DOMAIN}/products/{product['handle']}"
        size = _kit_size(product["title"])
        for variant in product["variants"]:
            color = variant["title"].split("/")[-1].strip()
            if size == 1 and color:
                entry["colors"].add(color)

        if size == 1:
            entry["single"] = {"price": min(prices), "url": url, "description": _clean(product["body_html"])}
        else:
            entry["kits"].append({"qty": size, "price": min(prices),
                                  "per_piece": round(min(prices) / size, 2), "url": url})

    for entry in catalog.values():
        entry["colors"] = sorted(entry["colors"])
        entry["kits"].sort(key=lambda k: k["qty"])
    return catalog


def facts_for(line: str, catalog: dict[str, dict]) -> str:
    """Plain-text fact sheet handed to Claude: the only prices/offers it may mention."""
    entry = catalog[line]
    lines = [f"Produto: {entry['name']}"]
    if entry["single"]:
        lines.append(f"Preço avulso: {brl(entry['single']['price'])} | {entry['single']['url']}")
        lines.append(f"Descrição da loja: {entry['single']['description']}")
    for kit in entry["kits"]:
        lines.append(f"Kit com {kit['qty']}: {brl(kit['price'])} (≈ {brl(kit['per_piece'])} por peça) | {kit['url']}")
    if entry["colors"]:
        lines.append("Cores: " + ", ".join(entry["colors"]))
    return "\n".join(lines)


if __name__ == "__main__":
    cat = get_catalog()
    for line in cat:
        print(facts_for(line, cat), "\n")
