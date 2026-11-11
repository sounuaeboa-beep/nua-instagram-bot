"""Which format today's post takes (Reel / carousel / single image) and how a carousel is assembled."""
import generate_art as art

TARGET = {"reel": 4, "carousel": 2, "image": 4}     # out of every 10 posts
WINDOW = 10
CAROUSEL_PILLARS = {"educacao", "multipack"}        # carousels teach or compare, so they fit these two
ORDER = {"reel": 0, "carousel": 1, "image": 2}      # tie-break


def pick_format(history: list[dict], pillar: str) -> str:
    """Steers the mix of the last 10 posts toward 40% Reels, 20% carousels, 40% images; never 3 in a row."""
    recent = [h.get("format", "image") for h in history[-WINDOW:]]
    allowed = ["reel", "image"] + (["carousel"] if pillar in CAROUSEL_PILLARS else [])
    if len(recent) >= 2 and recent[-1] == recent[-2] and len(allowed) > 1:
        allowed = [f for f in allowed if f != recent[-1]] or allowed
    scale = (len(recent) + 1) / WINDOW
    return max(allowed, key=lambda f: (TARGET[f] * scale - recent.count(f), -ORDER[f]))


def build_carousel(cover_image, headline: str, subheadline: str, slides: list[dict], entry: dict, pillar: str,
                   name: str) -> list:
    """Cover (photo + headline), the text slides written by Claude, and a closing card built from store facts."""
    total = len(slides) + 2
    paths = [art.render_post(cover_image, headline, subheadline, f"{name}_1")]
    for i, slide in enumerate(slides, start=2):
        paths.append(art.render_card(slide["title"], slide["body"], i, total, f"{name}_{i}"))
    paths.append(_closing_card(entry, pillar, total, f"{name}_{total}"))
    return paths


def _closing_card(entry: dict, pillar: str, total: int, name: str):
    from catalog import brl
    if pillar == "multipack" and entry.get("kits"):
        rows = []
        if entry.get("single"):
            rows.append(("Avulsa", brl(entry["single"]["price"]), ""))
        for kit in entry["kits"]:
            rows.append((f"Kit com {kit['qty']}", brl(kit["price"]), f"≈ {brl(kit['per_piece'])} por peça"))
        return art.render_list_card("Quanto mais, melhor o preço", rows, "Link na bio", total, total, name)
    colors = ", ".join(entry.get("colors", []))
    body = f"{entry['name']}." + (f" Cores: {colors}." if colors else "") + " Link na bio."
    return art.render_card("Pegou, vestiu, esqueceu", body, total, total, name)
