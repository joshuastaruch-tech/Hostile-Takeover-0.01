#!/usr/bin/env python3
"""Export the registry's 60 MYTHOS cards in the Base44 Card shape.

Reads cards/*.yaml and writes:
  exports/base44-cards.json  — array of Base44 Card records
  exports/base44-cards.csv   — same records, flat (for CSV import)

Base44 Card fields (from the 2026-10-12 editor audit): serial_number,
name, card_type, cost, rarity, attributes, art_prompt, art_url,
model_url, audio_url, video_url, token_address, token_id,
arg_fragment, batch_id, in_library.

Mapping choices (deliberate, review before upload):
- Values are the MYTHOS deck values (this is the 60-card deck):
  cost and card_type come from the card's MYTHOS profile/type, NOT
  canon. Canon values ride along inside `attributes` (JSON), so the
  upload is lossless.
- card_type uses the registry type_line head — which equals the
  MYTHOS type for all cards except The Temp, whose curated canon
  type_line says "Creature" while MYTHOS plays it as an Abomination;
  the MYTHOS type wins here and canon is noted in attributes.
- attributes is a JSON string: {slug, title, canon_cost,
  canon_type_line, mythos: {cost, stats, rules_patch, legal},
  rules_text}. If the app renders attributes as plain text this is
  still readable; if it parses JSON, it's structured.
- token_address / token_id are empty: Phase 1 ownership is internal
  (registry ledger) — no chain tokens exist for these cards.
- serial_number is the MYTHOS collector number where known. Only
  The Temp's ("014") is confirmed so far; the rest are filled by
  joining the game's public cards.json during the upload step
  (join key: slug/name). Records missing a serial are listed at the
  end and MUST NOT be uploaded until serials are resolved —
  serial_number is a required field in Base44 and is the registry's
  join key for instances.
"""
import csv
import glob
import json
from pathlib import Path

import yaml

KNOWN_NUMS = {"the-temp": "014"}  # confirmed from the game, 2026-10-10

# Full collector-number map, read from the game's public cards.json
# on 2026-10-12 (num -> name). Joined by NAME below; every registry
# card must match exactly one entry.
GAME_NUMS = {
    "001": "Supreme Worshiper", "002": "Xochitl", "003": "Vex",
    "004": "Somnia", "005": "Plica", "006": "Aletheia",
    "007": "Cinder", "008": "Mothman", "009": "The Intern",
    "010": "Mailroom Mimic", "011": "Coffee Elemental",
    "012": "Reply-All Wisp", "013": "Paper Jam", "014": "The Temp",
    "015": "Cubicle Shambler", "016": "Synergy Hound",
    "017": "Passive-Aggressive Golem", "018": "Overtime Wraith",
    "019": "The Whistleblower", "020": "The Auditor",
    "021": "Meeting Elemental", "022": "Layoff Swarm",
    "023": "The Micromanager", "024": "The Downsizer",
    "025": "Middle Manager", "026": "The Consultant",
    "027": "The Founder", "028": "Performance Reviewer",
    "029": "Non-Compete Clause", "030": "The Glass Cliff",
    "031": "The Restructurer", "032": "The Liquidator",
    "033": "The Board", "034": "Hostile Elemental",
    "035": "Exit Interview", "036": "Shadow IT", "037": "The Mole",
    "038": "The Merger", "039": "Burn Rate", "040": "Tender Offer",
    "041": "Poison Pill", "042": "The Acquisition", "043": "The Altar",
    "044": "The Grove", "045": "Performance Improvement Plan",
    "046": "Reply All", "047": "HR Complaint", "048": "Mandatory Fun",
    "049": "The Red Stapler", "050": "Synergy", "051": "Griselda",
    "052": "Pax", "053": "Marrow", "054": "Tess", "055": "The Pivot",
    "056": "Going Private", "057": "The Full-Timer", "058": "The NDA",
    "059": "Downsizing", "060": "The Break Room",
}
NUM_BY_NAME = {name: num for num, name in GAME_NUMS.items()}
OUT = Path(__file__).resolve().parent.parent / "exports"

FIELDS = ["serial_number", "name", "card_type", "cost", "rarity",
          "attributes", "art_prompt", "art_url", "model_url",
          "audio_url", "video_url", "token_address", "token_id",
          "arg_fragment", "batch_id", "in_library"]


def base44_record(card: dict) -> dict:
    slug = card["slug"]
    mythos = (card.get("games") or {}).get("mythos") or {}
    media = card.get("media") or {}
    type_head = (card.get("type_line") or "").split("·")[0].strip()
    if slug == "the-temp":
        type_head = "Abomination"  # MYTHOS type; canon says Creature
    attributes = {
        "slug": slug,
        "title": card.get("subtitle"),
        "canon_cost": card.get("cost"),
        "canon_type_line": card.get("type_line"),
        "mythos": {
            "cost": mythos.get("cost"),
            "stats": mythos.get("stats") or {},
            "rules_patch": mythos.get("rules_patch"),
            "legal": mythos.get("legal", True),
        },
        "rules_text": card.get("rules_text"),
    }
    return {
        "serial_number": NUM_BY_NAME.get(card["name"])
        or KNOWN_NUMS.get(slug),
        "name": card["name"],
        "card_type": type_head,
        "cost": mythos.get("cost", card.get("cost") or 0),
        "rarity": (card.get("rarity") or "common").title(),
        "attributes": json.dumps(attributes, ensure_ascii=False),
        "art_prompt": "",
        "art_url": media.get("art") or "",
        "model_url": media.get("model_3d") or "",
        "audio_url": media.get("audio") or "",
        "video_url": media.get("video") or "",
        "token_address": "",
        "token_id": "",
        "arg_fragment": card.get("flavor_text") or "",
        "batch_id": "",
        "in_library": False,
    }


def main() -> int:
    records = []
    for path in sorted(glob.glob("cards/*.yaml")):
        records.append(base44_record(
            yaml.safe_load(Path(path).read_text(encoding="utf-8"))))
    records.sort(key=lambda r: (r["serial_number"] is None,
                                r["serial_number"] or r["name"]))
    OUT.mkdir(exist_ok=True)
    (OUT / "base44-cards.json").write_text(
        json.dumps(records, indent=2, ensure_ascii=False),
        encoding="utf-8")
    with (OUT / "base44-cards.csv").open("w", newline="",
                                         encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for r in records:
            w.writerow({k: ("" if r[k] is None else r[k]) for k in FIELDS})
    missing = [r["name"] for r in records if not r["serial_number"]]
    print(f"wrote {len(records)} records to {OUT}/base44-cards.{{json,csv}}")
    print(f"serial_number known for {len(records) - len(missing)}; "
          f"missing for {len(missing)} (resolve from game cards.json "
          f"before upload)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
