"""Consolidated grid sheets for STATIC equipment/consumable item icons.

Companion to bake_item_atlas.py, which bakes one small atlas per ANIMATED
item (808 items in the real data) — that's fine as individual files since
each atlas is only a handful of frames. Static items (no animation, 5083
in the real data) are the opposite case: one PNG+JSON per item would mean
5083 individual downloads for icons that never change, which is exactly
the "many small requests" problem the outfit/map sheet work already
solved elsewhere in this pipeline (see OUTFIT_SPRITES_DOCUMENTATION.md and
.scratch/map-sprite-sheets-v4/spec.md) — so instead they're packed into a
small, fixed number of big grid sheets.

Design mirrors sheet_packer.py's model (fixed columns, sequential
placement, no bin-packing) rather than reinventing it, but doesn't reuse
SheetPacker directly: that class buckets by sprite size because map
objectgroups mix many sizes (32/64/128px), while every static item icon
here is uniformly 32x32 — the only free variable is how many items land
in each of the fixed number of output files, not what size bucket they
belong to.
"""

import json
import os
from typing import Dict, List, Optional, Tuple

from PIL import Image

import bake_item_atlas as bia

# =========================
# CONFIG
# =========================

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
EXTRACTOR_DIR = os.path.dirname(SCRIPTS_DIR)

ITEMS_SPRITES_DIR = bia.ITEMS_SPRITES_DIR
SHEETS_DIR = os.path.join(EXTRACTOR_DIR, "atlases", "items-static")

CELL_SIZE = 32
COLUMNS = 32          # sheet width = 32*32 = 1024px
NUM_SHEETS = 4        # ~1603 cells/sheet on real data -> ~1024x1632px, well under
                       # the 2048x2048 texture size guaranteed on every WebGL device


# =========================
# PLANNING (pure function)
# =========================

def plan_static_sheets(
    items: List[Tuple[int, List[str]]],
    columns: int = COLUMNS,
    num_sheets: int = NUM_SHEETS,
) -> List[Dict]:
    """Split (item_id, spriteKeys) pairs into `num_sheets` balanced shards
    by cumulative cell count, then assign each cell a sequential grid
    position within its shard (col = idx % columns, row = idx // columns).

    An item's cells always stay together in the same shard (never split
    across sheets) — items are visited in the given order and a shard is
    closed off (moving to the next one) once it reaches its share of the
    total, so shard boundaries fall on item boundaries, not mid-item.

    Returns one plan dict per shard, in order:
      {"frames": {spriteKey: {"x", "y", "w", "h"}}, "size": (width, height)}
    A shard with no items still gets an entry with an empty frame map and
    size (0, 0), so callers always get exactly `num_sheets` plans back.
    """
    total_cells = sum(len(keys) for _, keys in items)
    target = -(-total_cells // num_sheets) if total_cells else 0  # ceil div

    shards: List[List[Tuple[int, List[str]]]] = [[] for _ in range(num_sheets)]
    shard_cells = [0] * num_sheets
    shard_idx = 0
    for item_id, keys in items:
        if shard_cells[shard_idx] >= target and shard_idx < num_sheets - 1:
            shard_idx += 1
        shards[shard_idx].append((item_id, keys))
        shard_cells[shard_idx] += len(keys)

    plans = []
    for shard in shards:
        frames: Dict = {}
        idx = 0
        for _, keys in shard:
            for key in keys:
                col = idx % columns
                row = idx // columns
                frames[key] = {"x": col * CELL_SIZE, "y": row * CELL_SIZE, "w": CELL_SIZE, "h": CELL_SIZE}
                idx += 1
        if idx:
            rows = -(-idx // columns)
            size = (columns * CELL_SIZE, rows * CELL_SIZE)
        else:
            size = (0, 0)
        plans.append({"frames": frames, "size": size})
    return plans


# =========================
# ITEM DISCOVERY (static equipment/consumable candidates only)
# =========================

def _is_static(data: Dict) -> bool:
    return not data.get("spriteInfo", {}).get("animation")


def _list_static_equipment_items() -> List[Tuple[int, List[str]]]:
    """(item_id, spriteKeys) for every equipment/consumable candidate
    (bia.is_equipment_candidate) that has no animation, sorted by ID for
    determinism."""
    result = []
    for item_id in bia._list_item_ids():
        data = bia._load_item_json(item_id)
        if data is None or not bia.is_equipment_candidate(data) or not _is_static(data):
            continue
        result.append((item_id, list(data.get("spriteId", []))))
    return result


# =========================
# RENDER + WRITE
# =========================

def _render_sheet(plan: Dict, item_id_by_key: Dict[str, int]) -> Image.Image:
    width, height = plan["size"]
    canvas = Image.new("RGBA", (max(width, 1), max(height, 1)), (0, 0, 0, 0))
    for key, rect in plan["frames"].items():
        item_id = item_id_by_key[key]
        path = bia._resolve_frame_path(item_id, key)
        if not os.path.exists(path):
            continue
        with Image.open(path) as sprite_img:
            canvas.paste(sprite_img.convert("RGBA"), (rect["x"], rect["y"]))
    return canvas


def bake_static_sheets() -> List[Dict]:
    """Bake every static equipment/consumable item into NUM_SHEETS grid
    sheets, writing items-static-<i>.png + items-static-<i>.json to
    SHEETS_DIR. Returns the list of atlas JSON dicts written, in shard
    order."""
    items = _list_static_equipment_items()
    item_id_by_key = {key: item_id for item_id, keys in items for key in keys}

    plans = plan_static_sheets(items, columns=COLUMNS, num_sheets=NUM_SHEETS)

    os.makedirs(SHEETS_DIR, exist_ok=True)
    atlases = []
    for i, plan in enumerate(plans):
        image_name = f"items-static-{i}.png"
        canvas = _render_sheet(plan, item_id_by_key)
        atlas = bia.build_atlas_json(image_name, canvas.size, {
            key: {"frame": rect} for key, rect in plan["frames"].items()
        })

        canvas.save(os.path.join(SHEETS_DIR, image_name))
        with open(os.path.join(SHEETS_DIR, f"items-static-{i}.json"), "w", encoding="utf-8") as f:
            json.dump(atlas, f, indent=2, ensure_ascii=False)

        atlases.append(atlas)

    return atlases


# =========================
# ENTRY POINT
# =========================

def main():
    items = _list_static_equipment_items()
    total_cells = sum(len(keys) for _, keys in items)

    atlases = bake_static_sheets()

    print(f"[OK] items-static: {len(items)} itens ({total_cells} celulas) em {NUM_SHEETS} sheets, {SHEETS_DIR}")
    for i, atlas in enumerate(atlases):
        size = atlas["meta"]["size"]
        png_path = os.path.join(SHEETS_DIR, atlas["meta"]["image"])
        kb = os.path.getsize(png_path) / 1024 if os.path.exists(png_path) else 0
        print(f"  items-static-{i}: {len(atlas['frames'])} frames, {size['w']}x{size['h']}px, {kb:.0f}KB")


if __name__ == "__main__":
    main()
