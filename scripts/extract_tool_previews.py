"""Extract gallery SVGs verbatim from the locked design mockup.

The source `docs/design/tools.html` embeds one SVG per non-correlation card.
The copies get the XML namespace required when served as image files.
"""
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
MOCKUP = ROOT / "docs/design/tools.html"
OUTPUT = ROOT / "static/tool-previews"
SLUGS = ("backtest", "risk", "optimize", "monte-carlo", "goals", "factors",
         "tactical", "rolling-optimization", "rolling-metrics", "alm", "options",
         "technical", "forecast", "stress", "attribution", "risk-parity",
         "tax", "drawdowns")


def main():
    html = MOCKUP.read_text(encoding="utf-8")
    cards = re.findall(r'<div class="tool-card">(.*?)(?=<div class="tool-card">|</div>\s*</div>\s*<footer)',
                       html, flags=re.S)
    if len(cards) != len(SLUGS):
        raise ValueError(f"Expected {len(SLUGS)} design cards, found {len(cards)}")
    OUTPUT.mkdir(exist_ok=True)
    for slug, card in zip(SLUGS, cards):
        match = re.search(r"<svg\b.*?</svg>", card, flags=re.S)
        if not match:
            raise ValueError(f"Missing signature visual for {slug}")
        svg = match.group(0).replace("<svg ",
                                    '<svg xmlns="http://www.w3.org/2000/svg" ', 1)
        (OUTPUT / f"{slug}.svg").write_text(svg + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
