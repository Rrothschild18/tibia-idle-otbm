"""Joins bake_item_sheets.py (static) + bake_item_sheets_animated.py
(animated) output into a single itemId -> sprite location index
(items-index.json), so a consumer doesn't need to open every sheet to find
one item.

See .scratch/item-sprite-sheets/issues/01-item-sprite-index.md and
.scratch/item-sprite-sheets/issues/03-consolidate-animated-items-into-sheets.md
(animated items moved from one atlas per item, kind "atlas", to shared grid
sheets, kind "animated-sheet" — mirroring what static items already had).
"""

import json
import os
from typing import Dict, List, Tuple

import bake_item_atlas as bia
import bake_item_sheets as bis
import bake_item_sheets_animated as bisa

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
    animated_shard_of: Dict[int, int],
) -> Dict[str, Dict]:
    """Pure: given (item_id, raw metadata dict) pairs for every equipment
    candidate, plus static_shard_of/animated_shard_of item_id -> shard index
    (each only needed for the matching kind of item), returns the itemId ->
    location index.

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
            kind = "animated-sheet"
            shard = animated_shard_of[item_id]
            file = f"items-animated/items-animated-{shard}.json"
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


def _compute_shard_of(
    items: List[Tuple[int, List[str]]],
    columns: int,
    num_sheets: int,
) -> Dict[int, int]:
    """item_id -> shard index, derived from bis.plan_static_sheets's shard
    assignment. Checks membership of an item's first frame key in each
    shard's frame map — safe because plan_static_sheets guarantees an
    item's cells never split across shards. Shared by both static and
    animated items: the packing algorithm is identical, only the (columns,
    num_sheets) config and which items feed it differ."""
    plans = bis.plan_static_sheets(items, columns=columns, num_sheets=num_sheets)
    shard_of: Dict[int, int] = {}
    for item_id, keys in items:
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
    animated_items = [(item_id, list(data.get("spriteId", []))) for item_id, data in all_items if not bis._is_static(data)]
    static_shard_of = _compute_shard_of(static_items, columns=bis.COLUMNS, num_sheets=bis.NUM_SHEETS)
    animated_shard_of = _compute_shard_of(animated_items, columns=bisa.COLUMNS, num_sheets=bisa.NUM_SHEETS)
    return build_item_index(all_items, static_shard_of, animated_shard_of)


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
