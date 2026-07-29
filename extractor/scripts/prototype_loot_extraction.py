"""
PROTOTYPE — throwaway, not wired into the real pipeline.

Question this answers: does an id-based loot JSON shape (matching ADR 0003's
"derive, don't store" convention already used for map tiles and monster
outfits) actually survive contact with real Canary `monster.loot` tables —
name-only entries needing item-name -> item-id resolution, unresolved/typo'd
names, duplicate rows for the same item, and monsters with zero loot — before
wiring a real parser into build_phaser_map.py's build_monster_respawn() and a
`loot` field into db.json's `monsters` collection (served today by
MonsterService.getMonstersByMapId, see tibia-idle ticket 02)?

The two `raw_loot_rows` samples below (Rat, Rotworm) are transcribed verbatim
from C:\\canary-3.2.1\\data-otservbr-global\\monster\\{mammals/rat,vermins/rotworm}.lua
monster.loot tables. The rest are synthetic edge cases. The item-name index
below is illustrative (a handful of ids copied from that install's
items.xml) — the real integration would parse items.xml in full, the way
_load_monster_lookup() already parses otservbr-monster.xml for outfits.

Run: python extractor/scripts/prototype_loot_extraction.py
"""

import sys

# ======================================================
# LOGIC — pure, portable. This is the part worth keeping.
# ======================================================

# name.lower() -> item id. Illustrative subset only (see docstring). The real
# integration parses items.xml in full, both directions, the way
# _load_monster_lookup() already parses otservbr-monster.xml for outfits.
ITEM_NAME_INDEX = {
    "gold coin": 3031,
    "cheese": 3607,
    "sword": 3264,
    "mace": 3308,
    "meat": 2666,
    "ham": 2671,
    "worm": 3687,
    "lump of dirt": 3730,
    "legion helmet": 2495,
}

# id -> name.lower(), decided in review: even loot rows given only as `{id:
# ...}` (no `name`) should still resolve a display name from items.xml,
# rather than showing `itemName: null` to the player.
ITEM_ID_TO_NAME = {item_id: name for name, item_id in ITEM_NAME_INDEX.items()}

# Canary chance is out of 100000. Buckets follow the informal tiers the
# Tibia wiki uses for "how rare is this drop" — a labeling convenience for
# display, not a game-logic threshold.
_RARITY_THRESHOLDS = [
    (100000, "always"),
    (25000, "common"),
    (5000, "semi-rare"),
    (500, "rare"),
    (0, "very-rare"),
]


def _rarity_for_chance(chance_raw: int) -> str:
    for threshold, label in _RARITY_THRESHOLDS:
        if chance_raw >= threshold:
            return label
    return "very-rare"


def normalize_loot_entry(raw: dict, item_name_index: dict, item_id_to_name: dict):
    """One raw `monster.loot` row -> (entry, issue). Exactly one is None.

    Mirrors the "flag, don't silently skip" precedent already established
    for missing outfit ids in build_monster_respawn().
    """
    item_id = raw.get("id")
    name = raw.get("name")

    if item_id is None and name:
        item_id = item_name_index.get(name.lower())

    if item_id is None:
        return None, {"reason": "unresolved-item", "raw": raw}

    if name is None:
        name = item_id_to_name.get(item_id)  # resolve display name for id-only rows too

    chance_raw = raw["chance"]
    entry = {
        "itemId": item_id,
        "itemName": name,
        "dropChance": round(chance_raw / 100000, 5),
        "rarity": _rarity_for_chance(chance_raw),
        "countMin": 1,
        "countMax": raw.get("maxCount", 1),
    }
    return entry, None


def merge_duplicate_loot_entries(entries: list) -> list:
    """Same item rolled independently more than once (e.g. two `worm` rows
    at different chance/count bands) -> one combined display line, decided
    in review over keeping them as separate rows. Sums dropChance (capped at
    1.0 — an approximation of the true independent-events probability, judged
    good enough for a display table) and widens the count range."""
    merged_by_id = {}
    order = []
    for entry in entries:
        item_id = entry["itemId"]
        if item_id not in merged_by_id:
            merged_by_id[item_id] = dict(entry)
            order.append(item_id)
            continue
        existing = merged_by_id[item_id]
        existing["dropChance"] = round(min(1.0, existing["dropChance"] + entry["dropChance"]), 5)
        existing["countMin"] = min(existing["countMin"], entry["countMin"])
        existing["countMax"] = max(existing["countMax"], entry["countMax"])
        existing["rarity"] = _rarity_for_chance(round(existing["dropChance"] * 100000))
    return [merged_by_id[item_id] for item_id in order]


def build_monster_loot(monster_name: str, raw_loot_rows: list, item_name_index: dict, item_id_to_name: dict) -> dict:
    """All raw rows for one monster -> the candidate `loot.json` shape."""
    entries = []
    issues = []
    for raw in raw_loot_rows:
        entry, issue = normalize_loot_entry(raw, item_name_index, item_id_to_name)
        if entry is not None:
            entries.append(entry)
        if issue is not None:
            issues.append(issue)
    entries = merge_duplicate_loot_entries(entries)
    entries.sort(key=lambda e: e["dropChance"], reverse=True)
    return {"monster": monster_name, "loot": entries, "issues": issues}


def merge_loot_into_monster_def(monster_def: dict, loot_result: dict) -> dict:
    """Simulates attaching loot onto build_monster_respawn()'s monsterDefs[id]."""
    merged = dict(monster_def)
    merged["loot"] = loot_result["loot"]
    return merged


def project_hunts_endpoint_view(map_id: str, monster_defs_with_loot: dict) -> dict:
    """What MonsterService.getMonstersByMapId(mapId) hands the frontend,
    once db.json's `monsters` collection carries `loot` per def. Still just
    ids + numbers — the frontend resolves item icon paths by convention,
    same as it does for tile/outfit sprites (ADR 0003)."""
    return {
        "id": map_id,
        "mapId": map_id,
        "monsterDefs": monster_defs_with_loot,
    }


# ======================================================
# SAMPLE DATA — the cases being pushed through the model
# ======================================================

SAMPLES = [
    {
        "monster_name": "Rat",
        "monster_def": {"name": "Rat", "outfitId": 21, "assetsPath": "assets/.../monsters/21"},
        "raw_loot_rows": [
            {"name": "gold coin", "chance": 100000, "maxCount": 4},
            {"id": 3607, "chance": 39410},  # cheese
        ],
    },
    {
        "monster_name": "Rotworm",
        "monster_def": {"name": "Rotworm", "outfitId": 26, "assetsPath": "assets/.../monsters/26"},
        "raw_loot_rows": [
            {"name": "gold coin", "chance": 71760, "maxCount": 17},
            {"id": 3264, "chance": 3000},  # sword
            {"name": "mace", "chance": 4500},
            {"name": "meat", "chance": 20000},
            {"name": "ham", "chance": 20120},
            {"name": "worm", "chance": 3000, "maxCount": 3},
            {"name": "lump of dirt", "chance": 10000},
            {"name": "legion helmet", "chance": 1890},
        ],
    },
    {
        "monster_name": "Typo Ghoul (synthetic)",
        "monster_def": {"name": "Typo Ghoul", "outfitId": 999, "assetsPath": "assets/.../monsters/999"},
        "raw_loot_rows": [
            {"name": "gold coin", "chance": 90000, "maxCount": 10},
            {"name": "rotten shmeat", "chance": 15000},  # typo/unknown name
        ],
    },
    {
        "monster_name": "Duplicate Imp (synthetic)",
        "monster_def": {"name": "Duplicate Imp", "outfitId": 998, "assetsPath": "assets/.../monsters/998"},
        "raw_loot_rows": [
            {"name": "worm", "chance": 3000, "maxCount": 1},
            {"name": "worm", "chance": 500, "maxCount": 5},  # same item, 2nd independent roll
        ],
    },
    {
        "monster_name": "Empty Slime (synthetic)",
        "monster_def": {"name": "Empty Slime", "outfitId": 997, "assetsPath": "assets/.../monsters/997"},
        "raw_loot_rows": [],
    },
]


# ======================================================
# TUI — throwaway shell. Nothing above this line should import from here.
# ======================================================

BOLD = "\x1b[1m"
DIM = "\x1b[2m"
RESET = "\x1b[0m"


def _clear():
    print("\x1b[2J\x1b[H", end="")


def _print_json(label, obj):
    import json
    print(f"{BOLD}{label}{RESET}")
    print(json.dumps(obj, indent=2, ensure_ascii=False))
    print()


def render(index: int):
    _clear()
    sample = SAMPLES[index]
    monster_name = sample["monster_name"]
    monster_def = sample["monster_def"]
    raw_rows = sample["raw_loot_rows"]

    print(f"{BOLD}=== [{index + 1}/{len(SAMPLES)}] {monster_name} ==={RESET}")
    print(f"{DIM}(raw monster.loot rows, as a lua-table parser would hand them back){RESET}")
    _print_json("1. raw_loot_rows", raw_rows)

    loot_result = build_monster_loot(monster_name, raw_rows, ITEM_NAME_INDEX, ITEM_ID_TO_NAME)
    _print_json("2. build_monster_loot() -> candidate loot.json shape", loot_result)

    if loot_result["issues"]:
        print(f"{DIM}^ issues are surfaced, not silently dropped (same precedent as{RESET}")
        print(f"{DIM}  missing outfit ids in build_monster_respawn()){RESET}\n")

    merged_def = merge_loot_into_monster_def(monster_def, loot_result)
    _print_json("3. merge_loot_into_monster_def() -> respawn.json monsterDefs[id]", merged_def)

    hunts_view = project_hunts_endpoint_view(
        "ROOK-0001", {str(monster_def["outfitId"]): merged_def}
    )
    _print_json("4. project_hunts_endpoint_view() -> what MonsterService returns", hunts_view)

    print(f"{BOLD}[n]{RESET}{DIM}ext monster  {RESET}"
          f"{BOLD}[p]{RESET}{DIM}rev monster  {RESET}"
          f"{BOLD}[q]{RESET}{DIM}uit{RESET}")


def main():
    index = 0
    render(index)
    while True:
        key = input("> ").strip().lower()
        if key == "q":
            break
        elif key == "n":
            index = (index + 1) % len(SAMPLES)
        elif key == "p":
            index = (index - 1) % len(SAMPLES)
        else:
            continue
        render(index)


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        sys.exit(0)
