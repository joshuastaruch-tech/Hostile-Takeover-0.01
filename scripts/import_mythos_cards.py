#!/usr/bin/env python3
"""Import MYTHOS cards.json into registry card-definition YAML files.

Usage:
    python import_mythos_cards.py cards.json --out ../cards --game mythos

For each card in the game's cards.json, writes cards/<slug>.yaml conforming
to schemas/card-definition.schema.json. If the YAML already exists (e.g.
the-temp.yaml from the CARDREALM viewer), its canonical fields are preserved
and only the games.<game> profile is (re)written from the game data — so the
collectible canon and the game adaptation never clobber each other.
"""

import argparse
import json
import re
import sys
from pathlib import Path

# MYTHOS per-card numeric stats -> registry game-profile `stats` map.
STAT_KEYS = ("control", "sanity", "power", "flesh", "leash", "upkeep")


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return re.sub(r"-+", "-", s)


def load_existing(path: Path) -> dict:
    import yaml
    if path.exists():
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {}


def build_profile(card: dict, existing: dict) -> dict:
    stats = {k: card[k] for k in STAT_KEYS if card.get(k) is not None}
    profile = {"cost": card.get("cost"), "legal": True}
    if stats:
        profile["stats"] = stats
    # Game rules differ from the canonical text -> record as a patch,
    # never rewrite the canon.
    if existing.get("rules_text") and existing["rules_text"] != card.get("rules"):
        profile["rules_patch"] = card.get("rules")
    return profile


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cards_json", help="MYTHOS cards.json (a JSON array)")
    ap.add_argument("--out", default="cards")
    ap.add_argument("--game", default="mythos")
    args = ap.parse_args()

    import yaml

    cards = json.loads(Path(args.cards_json).read_text(encoding="utf-8"))
    if not isinstance(cards, list):
        print("expected a JSON array of cards", file=sys.stderr)
        return 1

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    seen = set()
    for card in cards:
        slug = slugify(card["name"])
        if slug in seen:  # defensive: keep filenames unique
            slug = f"{slug}-{card.get('id', 'x')}"
        seen.add(slug)
        path = out / f"{slug}.yaml"
        existing = load_existing(path)
        games = dict(existing.get("games") or {})
        games[args.game] = build_profile(card, existing)
        doc = {
            "slug": slug,
            "name": existing.get("name", card["name"]),
            "type_line": existing.get("type_line", card.get("type")),
            "cost": existing.get("cost", card.get("cost")),
            "rules_text": existing.get("rules_text", card.get("rules")),
            "flavor_text": existing.get("flavor_text", card.get("flavor")),
            "rarity": existing.get("rarity", "common"),
            "serial_scheme": existing.get("serial_scheme", "open"),
            "version": existing.get("version", 1),
            "media": existing.get("media", {
                "art": None, "model_3d": None, "audio": None, "video": None,
            }),
            "games": games,
        }
        subtitle = existing.get("subtitle", card.get("title"))
        if subtitle:
            # keep subtitle right after name for readability
            doc = {"slug": doc["slug"], "name": doc["name"],
                   "subtitle": subtitle,
                   **{k: v for k, v in doc.items() if k not in ("slug", "name")}}
        path.write_text(
            yaml.safe_dump(doc, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
    print(f"wrote {len(seen)} card files to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
