"""Consolidated grid sheets for ANIMATED equipment/consumable item icons.

Companion to bake_item_sheets.py, which already does this for STATIC items
(no animation). Animated items (808 in the real data) used to be baked one
small atlas per item by bake_item_atlas.py — fine when that was the only
option, but it's the same "many small requests" problem the static sheets
were built to avoid, just smaller in count (808 files instead of 5083) and
worse per file (each item drags its own PNG+JSON pair even though every
animated equipment/consumable icon is uniformly 32x32, exactly like the
static ones — see .scratch/item-sprite-sheets/spec.md section 4: multi-cell
items only ever show up in DECORATION/OTHERS/CREATURE_PRODUCTS/CONTAINERS,
never in an actual equipment category). So this module folds them into the
same small, fixed number of grid sheets instead, giving a consumer the same
"load N sheets + N JSONs" contract for animated items that it already has
for static ones.

Reuses bake_item_sheets.plan_static_sheets for the packing itself, unchanged
— that function only ever operated on (item_id, spriteKeys) pairs balanced
by cumulative cell count across N shards; "static" in its name describes
where it was first used, not something it enforces. An animated item's
spriteId list is exactly the flat list of animation-frame keys (already
including any multi-cell blocks verbatim, see bake_item_atlas.pack_item_frames
for why that's safe) — packing that list is no different from packing a
static multi-cell item's frame list, so the same "never split an item's
cells across a shard boundary" guarantee applies here too, this time keeping
every frame of an animated item's cycle in the same sheet.

Like the static sheets (and unlike bake_item_atlas.py's individual atlases),
frames here get NO padding between them — same reasoning already applied to
the static sheets: every icon already carries its own transparent margin
inside its 32x32 cell, so nothing bleeds at the shared cell boundary.

bake_item_atlas.py itself isn't retired: its classification helpers
(is_equipment_candidate, _list_item_ids, _resolve_frame_path, ...) are the
shared library both sheet bakers import. Only its per-item bake_item()/main()
entry point — the thing that used to write one atlas per animated item — is
no longer part of the pipeline (see build_items.js).
"""

import json
import os
from typing import Dict, List, Tuple

import bake_item_atlas as bia
import bake_item_sheets as bis

# =========================
# CONFIG
# =========================

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
EXTRACTOR_DIR = os.path.dirname(SCRIPTS_DIR)

ITEMS_SPRITES_DIR = bia.ITEMS_SPRITES_DIR
SHEETS_DIR = os.path.join(EXTRACTOR_DIR, "atlases", "items-animated")

CELL_SIZE = bis.CELL_SIZE
COLUMNS = 32          # sheet width = 32*32 = 1024px, same as items-static
NUM_SHEETS = 8         # animated items pack far more cells/item (one per
                       # animation phase, not one per item) than static ones
                       # do -- 8 shards keeps each sheet well under the
                       # 2048x2048 safe WebGL texture size on real data
                       # (~808 items, several thousand animation-frame cells)


# =========================
# ITEM DISCOVERY (animated equipment/consumable candidates only)
# =========================

def _list_animated_equipment_items() -> List[Tuple[int, List[str]]]:
    """(item_id, spriteKeys) for every equipment/consumable candidate
    (bia.is_equipment_candidate) that HAS animation, sorted by ID for
    determinism. spriteKeys is the item's full spriteId list — every
    animation-phase frame (and every multi-cell block within each phase,
    for the rare multi-cell animated item), in original order."""
    result = []
    for item_id in bia._list_item_ids():
        data = bia._load_item_json(item_id)
        if data is None or not bia.is_equipment_candidate(data) or bis._is_static(data):
            continue
        result.append((item_id, list(data.get("spriteId", []))))
    return result


# =========================
# BAKE
# =========================

def bake_animated_sheets() -> List[Dict]:
    """Bake every animated equipment/consumable item into NUM_SHEETS grid
    sheets, writing items-animated-<i>.png + items-animated-<i>.json to
    SHEETS_DIR. Returns the list of atlas JSON dicts written, in shard
    order."""
    items = _list_animated_equipment_items()
    item_id_by_key = {key: item_id for item_id, keys in items for key in keys}

    plans = bis.plan_static_sheets(items, columns=COLUMNS, num_sheets=NUM_SHEETS)

    os.makedirs(SHEETS_DIR, exist_ok=True)
    atlases = []
    for i, plan in enumerate(plans):
        image_name = f"items-animated-{i}.png"
        canvas = bis._render_sheet(plan, item_id_by_key)
        atlas = bia.build_atlas_json(image_name, canvas.size, {
            key: {"frame": rect} for key, rect in plan["frames"].items()
        })

        canvas.save(os.path.join(SHEETS_DIR, image_name))
        with open(os.path.join(SHEETS_DIR, f"items-animated-{i}.json"), "w", encoding="utf-8") as f:
            json.dump(atlas, f, indent=2, ensure_ascii=False)

        atlases.append(atlas)

    return atlases


# =========================
# ENTRY POINT
# =========================

def main():
    items = _list_animated_equipment_items()
    total_cells = sum(len(keys) for _, keys in items)

    atlases = bake_animated_sheets()

    print(f"[OK] items-animated: {len(items)} itens ({total_cells} celulas) em {NUM_SHEETS} sheets, {SHEETS_DIR}")
    for i, atlas in enumerate(atlases):
        size = atlas["meta"]["size"]
        png_path = os.path.join(SHEETS_DIR, atlas["meta"]["image"])
        kb = os.path.getsize(png_path) / 1024 if os.path.exists(png_path) else 0
        unsafe = " [!] excede 2048px" if max(size["w"], size["h"]) > 2048 else ""
        print(f"  items-animated-{i}: {len(atlas['frames'])} frames, {size['w']}x{size['h']}px, {kb:.0f}KB{unsafe}")


if __name__ == "__main__":
    main()
