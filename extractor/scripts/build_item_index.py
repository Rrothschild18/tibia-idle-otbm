"""Joins bake_item_atlas.py + bake_item_sheets.py output into a single
itemId -> sprite location index (items-index.json), so a consumer doesn't
need to open every individual atlas or static sheet to find one item.

See .scratch/item-sprite-sheets/issues/01-item-sprite-index.md.
"""

import json
import os
from typing import Dict, List, Optional, Tuple

import bake_item_atlas as bia
import bake_item_sheets as bis

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
EXTRACTOR_DIR = os.path.dirname(SCRIPTS_DIR)
ATLASES_DIR = os.path.join(EXTRACTOR_DIR, "atlases")
INDEX_PATH = os.path.join(ATLASES_DIR, "items-index.json")


# =========================
# PLANNING (pure)
# =========================

def _cell_count(sprite_info: Dict) -> int:
    return (
        sprite_info.get("patternWidth", 1)
        * sprite_info.get("patternHeight", 1)
        * sprite_info.get("patternDepth", 1)
    )


def build_item_index(
    items: List[Tuple[int, Dict]],
    static_shard_of: Dict[int, int],
) -> Dict[str, Dict]:
    """Pure: given (item_id, raw metadata dict) pairs for every equipment
    candidate, plus a static_shard_of item_id -> shard index (only needed
    for items with no animation), returns the itemId -> location index.

    spriteCount is always the item's CELL count (patternWidth * patternHeight
    * patternDepth), never the total sprite/frame count — for an animated
    item those differ (see test for item 9058: 8 cells * 13 frames = 104
    sprites, spriteCount is 8). stackable reflects flags.cumulative,
    independent of spriteCount (an item can be cumulative with a single
    sprite, no visual variation by quantity).
    """
    index: Dict[str, Dict] = {}
    for item_id, data in items:
        flags = data.get("flags", {})
        sprite_info = data.get("spriteInfo", {})
        frame_keys = list(data.get("spriteId", []))
        stackable = bool(flags.get("cumulative"))

        if sprite_info.get("animation"):
            kind = "atlas"
            file = f"items/{item_id}.json"
            sprite_count = _cell_count(sprite_info)
        else:
            kind = "static-sheet"
            shard = static_shard_of[item_id]
            file = f"items-static/items-static-{shard}.json"
            sprite_count = len(frame_keys)

        index[str(item_id)] = {
            "kind": kind,
            "file": file,
            "frameKeys": frame_keys,
            "stackable": stackable,
            "spriteCount": sprite_count,
        }
    return index


def _compute_static_shard_of(
    static_items: List[Tuple[int, List[str]]],
    columns: int = bis.COLUMNS,
    num_sheets: int = bis.NUM_SHEETS,
) -> Dict[int, int]:
    """item_id -> shard index, derived from bis.plan_static_sheets's shard
    assignment. Checks membership of an item's first frame key in each
    shard's frame map — safe because plan_static_sheets guarantees an
    item's cells never split across shards."""
    plans = bis.plan_static_sheets(static_items, columns=columns, num_sheets=num_sheets)
    shard_of: Dict[int, int] = {}
    for item_id, keys in static_items:
        if not keys:
            continue
        first_key = keys[0]
        for shard_idx, plan in enumerate(plans):
            if first_key in plan["frames"]:
                shard_of[item_id] = shard_idx
                break
    return shard_of


# =========================
# ORCHESTRATION (I/O)
# =========================

def _load_all_candidates() -> List[Tuple[int, Dict]]:
    result = []
    for item_id in bia._list_item_ids():
        data = bia._load_item_json(item_id)
        if data is None or not bia.is_equipment_candidate(data):
            continue
        result.append((item_id, data))
    return result


def generate_item_index() -> Dict[str, Dict]:
    all_items = _load_all_candidates()
    static_items = [(item_id, list(data.get("spriteId", []))) for item_id, data in all_items if bis._is_static(data)]
    static_shard_of = _compute_static_shard_of(static_items, columns=bis.COLUMNS, num_sheets=bis.NUM_SHEETS)
    return build_item_index(all_items, static_shard_of)


# =========================
# ENTRY POINT
# =========================

def main():
    index = generate_item_index()

    os.makedirs(os.path.dirname(INDEX_PATH), exist_ok=True)
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)

    print(f"[OK] items-index: {len(index)} itens em {INDEX_PATH}")


if __name__ == "__main__":
    main()
