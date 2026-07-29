"""
Loot table extraction for Canary monster definitions.

Parses raw Canary `data/items/items.xml` and `data-otservbr-global/monster/**/*.lua`
files into a resolved, per-monster loot index. See build_monster_loot_index.py for
the CLI entry point that writes it to extractor/monster-loot.json — the checked-in
reference file so the real pipeline (build_phaser_map.py) never needs to read a
Canary install directly.

Promoted from prototype/loot-extraction (prototype_loot_extraction.py) once its
id-resolution/duplicate-merge model was validated against real monster.loot tables.
"""

import glob
import os
import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple

# ======================================================
# items.xml -> name/id resolution
# ======================================================


def load_items_index(items_xml_path: str) -> Tuple[Dict[str, int], Dict[int, str]]:
    """Parse items.xml -> (name.lower() -> id, id -> name.lower()).

    Handles both single `id="N"` and ranged `fromid="A" toid="B"` entries
    (ranges top out at ~750 ids in this dataset, cheap to expand). On a name
    collision, the first entry encountered wins.
    """
    name_to_id: Dict[str, int] = {}
    id_to_name: Dict[int, str] = {}
    if not os.path.exists(items_xml_path):
        return name_to_id, id_to_name

    tree = ET.parse(items_xml_path)
    for item in tree.getroot().iter("item"):
        name = item.get("name")
        if not name:
            continue
        name_key = name.lower()

        single_id = item.get("id")
        if single_id is not None:
            item_id = int(single_id)
            name_to_id.setdefault(name_key, item_id)
            id_to_name.setdefault(item_id, name_key)
            continue

        from_id, to_id = item.get("fromid"), item.get("toid")
        if from_id is not None and to_id is not None:
            first_id = int(from_id)
            name_to_id.setdefault(name_key, first_id)
            for item_id in range(first_id, int(to_id) + 1):
                id_to_name.setdefault(item_id, name_key)

    return name_to_id, id_to_name


# ======================================================
# monster .lua -> (name, raw loot rows)
# ======================================================

_MONSTER_NAME_RE = re.compile(r'Game\.createMonsterType\(\s*"([^"]+)"\s*\)')
_LOOT_BLOCK_START_RE = re.compile(r"monster\.loot\s*=\s*\{")
_LOOT_ENTRY_RE = re.compile(r"\{([^{}]*)\}")
_LOOT_FIELD_RE = re.compile(r'(\w+)\s*=\s*("(?:[^"\\]|\\.)*"|-?\d+(?:\.\d+)?|true|false)')


def _extract_braced_block(text: str, start: int) -> str:
    """Text between a `{` (already consumed — `start` points just past it)
    and its matching `}`, honouring nested braces so this also works for a
    same-line empty table (`monster.loot = {}`)."""
    depth = 1
    i = start
    while i < len(text) and depth > 0:
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
        i += 1
    return text[start : i - 1]


def _strip_lua_comment(line: str) -> str:
    idx = line.find("--")
    return line if idx == -1 else line[:idx]


def _parse_lua_value(raw: str):
    raw = raw.strip()
    if raw.startswith('"'):
        return raw[1:-1]
    if raw == "true":
        return True
    if raw == "false":
        return False
    return float(raw) if "." in raw else int(raw)


def parse_monster_loot_lua(lua_path: str) -> Tuple[Optional[str], List[Dict]]:
    """One Canary monster .lua file -> (monster name, raw loot rows).

    Raw rows keep source field names/casing as-is — this install mixes
    `maxCount`/`maxcount`/`minCount`/`mincount`, so normalize_loot_entry
    resolves that, not this parser.
    """
    with open(lua_path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()

    name_match = _MONSTER_NAME_RE.search(text)
    monster_name = name_match.group(1) if name_match else None

    block_match = _LOOT_BLOCK_START_RE.search(text)
    if not block_match:
        return monster_name, []

    block = _extract_braced_block(text, block_match.end())

    raw_rows: List[Dict] = []
    for line in block.splitlines():
        line = _strip_lua_comment(line).strip()
        if not line.startswith("{"):
            continue
        entry_match = _LOOT_ENTRY_RE.search(line)
        if not entry_match:
            continue
        row: Dict = {}
        for field_match in _LOOT_FIELD_RE.finditer(entry_match.group(1)):
            row[field_match.group(1)] = _parse_lua_value(field_match.group(2))
        if row:
            raw_rows.append(row)

    return monster_name, raw_rows


# ======================================================
# LOGIC — raw rows -> resolved loot.json shape
# (ported from prototype_loot_extraction.py, validated there against real
# Rat/Rotworm tables and synthetic edge cases: unresolved names, duplicate
# rows, monsters with no loot)
# ======================================================

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


def _first_present(raw: Dict, *names):
    for name in names:
        if name in raw:
            return raw[name]
    return None


def normalize_loot_entry(raw: Dict, name_to_id: Dict[str, int], id_to_name: Dict[int, str]):
    """One raw `monster.loot` row -> (entry, issue). Exactly one is None.

    Mirrors the "flag, don't silently skip" precedent already established
    for missing outfit ids in build_monster_respawn().
    """
    item_id = raw.get("id")
    name = raw.get("name")

    if item_id is None and name:
        item_id = name_to_id.get(name.lower())

    if item_id is None:
        return None, {"reason": "unresolved-item", "raw": raw}

    if name is None:
        name = id_to_name.get(item_id)  # resolve display name for id-only rows too

    chance_raw = raw.get("chance")
    if chance_raw is None:
        return None, {"reason": "missing-chance", "raw": raw}

    count_fixed = _first_present(raw, "count")
    count_min = _first_present(raw, "minCount", "mincount") or 1
    count_max = _first_present(raw, "maxCount", "maxcount") or count_fixed or count_min

    entry = {
        "itemId": item_id,
        "itemName": name,
        "dropChance": round(chance_raw / 100000, 5),
        "rarity": _rarity_for_chance(chance_raw),
        "countMin": count_min,
        "countMax": count_max,
    }
    return entry, None


def merge_duplicate_loot_entries(entries: list) -> list:
    """Same item rolled independently more than once -> one combined display
    line. Sums dropChance (capped at 1.0) and widens the count range."""
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


def build_monster_loot(raw_loot_rows: list, name_to_id: Dict[str, int], id_to_name: Dict[int, str]) -> Dict:
    """All raw rows for one monster -> the candidate loot.json shape."""
    entries = []
    issues = []
    for raw in raw_loot_rows:
        entry, issue = normalize_loot_entry(raw, name_to_id, id_to_name)
        if entry is not None:
            entries.append(entry)
        if issue is not None:
            issues.append(issue)
    entries = merge_duplicate_loot_entries(entries)
    entries.sort(key=lambda e: e["dropChance"], reverse=True)
    return {"loot": entries, "issues": issues}


# ======================================================
# Whole-install index
# ======================================================


def build_monster_loot_index(canary_dir: str) -> Dict[str, Dict]:
    """Every monster .lua file in a local Canary install -> {monster name:
    {"loot": [...], "issues": [...]}}. Monsters with no `monster.loot` table
    at all are omitted (trainers/dummies); monsters with an empty table are
    kept with `"loot": []` — the index is meant to be a complete reference,
    not filtered to what tibia-idle currently uses."""
    items_xml_path = os.path.join(canary_dir, "data", "items", "items.xml")
    name_to_id, id_to_name = load_items_index(items_xml_path)

    monster_glob = os.path.join(canary_dir, "data-otservbr-global", "monster", "**", "*.lua")
    index: Dict[str, Dict] = {}
    for lua_path in sorted(glob.glob(monster_glob, recursive=True)):
        monster_name, raw_rows = parse_monster_loot_lua(lua_path)
        if monster_name is None:
            continue
        index[monster_name] = build_monster_loot(raw_rows, name_to_id, id_to_name)
    return index
