import json
import os
from typing import Dict, List, Optional, Tuple

from PIL import Image

# =========================
# CONFIG
# =========================

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
EXTRACTOR_DIR = os.path.dirname(SCRIPTS_DIR)

ITEMS_SPRITES_DIR = os.path.join(EXTRACTOR_DIR, "sprites", "items")
ITEMS_ATLAS_DIR = os.path.join(EXTRACTOR_DIR, "atlases", "items")

# Transparent pixels added around each packed frame so the client scaling
# or filtering the atlas texture doesn't bleed neighboring frames together.
PADDING_PX = 1


# =========================
# PACKING (pure functions)
# =========================

def pack_item_frames(frames: List[Tuple[str, str]]) -> Tuple[Image.Image, Dict]:
    """Pack ordered (key, png_path) frames into a single-row atlas.

    Frames keep the exact order given (the item's spriteId order straight
    from the extracted metadata) — not sorted by key. This order already
    covers both plain animation (one cell, N phases) and the rarer
    multi-cell items (patternWidth/Height/Depth > 1, e.g. stack-count
    variants or hook-direction variants): the sprite_id list is emitted in
    contiguous per-frame blocks of patternWidth*patternHeight*patternDepth
    cells (verified against real data, item 9058), so packing it verbatim
    keeps every cell individually addressable without needing to interpret
    what each axis means — the same "preserve everything, let the client
    pick" approach used for outfit direction/frame selection. Each frame
    gets a PADDING_PX transparent border on every side to avoid texture
    bleeding.
    """
    if not frames:
        return Image.new("RGBA", (0, 0), (0, 0, 0, 0)), {}

    images = [(key, Image.open(path).convert("RGBA")) for key, path in frames]
    frame_w = max(img.width for _, img in images)
    frame_h = max(img.height for _, img in images)
    cell_w = frame_w + 2 * PADDING_PX
    cell_h = frame_h + 2 * PADDING_PX

    canvas = Image.new("RGBA", (cell_w * len(images), cell_h), (0, 0, 0, 0))
    frame_map: Dict = {}

    for index, (key, img) in enumerate(images):
        x = index * cell_w + PADDING_PX
        y = PADDING_PX
        canvas.paste(img, (x, y))
        frame_map[key] = {"frame": {"x": x, "y": y, "w": img.width, "h": img.height}}

    return canvas, frame_map


def build_atlas_json(image_name: str, canvas_size: Tuple[int, int], frame_map: Dict) -> Dict:
    return {
        "frames": frame_map,
        "meta": {"image": image_name, "size": {"w": canvas_size[0], "h": canvas_size[1]}},
    }


# =========================
# CLASSIFICATION
# =========================
#
# Three independent signals, any one of which marks an item as
# equipment/consumable (inventory-relevant) rather than map scenery:
#
#   1. flags.market present — the item is listed for trade. The clearest,
#      least ambiguous signal (4564 items in the real data).
#   2. flags.clothes present but no market — wearable items that were
#      never listed on the market (quest/event rewards, often with
#      `expire`/`wearout`). ~479 items.
#   3. (flags.usable or flags.cumulative) + flags.take, with none of the
#      scenery-ish flags below — portable consumables/utilities (potions,
#      runes, tools) and pure stackables (currency: gold/platinum/crystal
#      coin, ammo without a `usable` flag) that aren't on the market
#      either. ~1146 items.
#
# The scenery-ish flags in (3) matter because "usable + take" alone is
# dominated by false positives: corpses (lootable but not equipment),
# world containers, and world objects marked `take` that are still
# fixed/decorative (bottom/top overlays, automap-colored scenery, wall
# hooks). Excluding items carrying any of those flags is what separates
# the real consumables from the ~7476 raw "usable" items in the extracted
# data. `cumulative` alone (without `usable`) is included too — currency
# items like gold coin (id 3031: `cumulative` + `take`, no `usable`) would
# otherwise be excluded entirely despite being one of the most important
# item categories in the game (found by tracing a real 404 for gold coin's
# sprite in the client after this classifier shipped without it).

_SCENERY_FLAGS = (
    "corpse", "container", "unpass", "bottom", "top",
    "automap", "hang", "lying_object",
)


def is_market_item(data: Dict) -> bool:
    return bool(data.get("flags", {}).get("market"))


def is_wearable_without_market(data: Dict) -> bool:
    flags = data.get("flags", {})
    return bool(flags.get("clothes")) and not flags.get("market")


def is_portable_consumable_without_market(data: Dict) -> bool:
    flags = data.get("flags", {})
    if flags.get("market") or not flags.get("take"):
        return False
    if not (flags.get("usable") or flags.get("cumulative")):
        return False
    return not any(flags.get(f) for f in _SCENERY_FLAGS)


def is_equipment_candidate(data: Dict) -> bool:
    return (
        is_market_item(data)
        or is_wearable_without_market(data)
        or is_portable_consumable_without_market(data)
    )


# =========================
# ITEM DISCOVERY / LOADING
# =========================

def _list_item_ids() -> List[int]:
    """List every item ID with extracted sprites, sorted ascending."""
    if not os.path.isdir(ITEMS_SPRITES_DIR):
        return []

    ids = set()
    for name in os.listdir(ITEMS_SPRITES_DIR):
        path = os.path.join(ITEMS_SPRITES_DIR, name)
        if os.path.isdir(path):
            ids.add(int(name))
        elif name.endswith(".json"):
            ids.add(int(name[: -len(".json")]))

    return sorted(ids)


def _load_item_json(item_id: int) -> Optional[Dict]:
    """Load JSON metadata for an item from sprites/items/{id}/."""
    for path in [
        os.path.join(ITEMS_SPRITES_DIR, str(item_id), f"{item_id}.json"),
        os.path.join(ITEMS_SPRITES_DIR, f"{item_id}.json"),
    ]:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    return None


def _resolve_frame_path(item_id: int, key: str) -> str:
    """Resolve a frame's PNG path, trying the item's subdirectory first.

    Mirrors the same split-location quirk documented in
    bake_outfit_atlas.py: extract_sprites.py writes single-sprite items
    flat (sprites/items/{id}.json + {id}.png) and multi-sprite items into
    a subdirectory, but defends against the two disagreeing anyway.
    """
    for base in (os.path.join(ITEMS_SPRITES_DIR, str(item_id)), ITEMS_SPRITES_DIR):
        path = os.path.join(base, f"{key}.png")
        if os.path.exists(path):
            return path
    return os.path.join(ITEMS_SPRITES_DIR, str(item_id), f"{key}.png")


def _item_frame_list(item_id: int, data: Dict) -> List[Tuple[str, str]]:
    """Ordered (key, png_path) list for an item, following its JSON's
    existing spriteId order (see pack_item_frames for why that order is
    safe to pack verbatim)."""
    frame_groups = data.get("frameGroups")
    if frame_groups:
        keys = [key for fg in frame_groups for key in fg.get("spriteId", [])]
    else:
        keys = data.get("spriteId", [])

    return [(key, _resolve_frame_path(item_id, key)) for key in keys]


# =========================
# BAKE
# =========================
#
# bake_item()/main() below are no longer part of the wired pipeline
# (build_items.js) — items-index.json never points at their output anymore,
# static and animated items both bake into shared grid sheets now
# (bake_item_sheets.py / bake_item_sheets_animated.py, which import this
# module for classification and frame-path resolution). Kept because it's
# still handy standalone for inspecting a single item's frames without
# baking/opening a full shared sheet — not run automatically.

def bake_item(item_id: int) -> Optional[Dict]:
    """Bake one item's atlas, writing <id>.png + <id>.json to
    ITEMS_ATLAS_DIR. Returns the atlas JSON dict, or None if the item has
    no extracted JSON or fails the equipment/consumable classification
    (see is_equipment_candidate)."""
    data = _load_item_json(item_id)
    if data is None or not is_equipment_candidate(data):
        return None

    frames = _item_frame_list(item_id, data)
    canvas, frame_map = pack_item_frames(frames)
    image_name = f"{item_id}.png"
    atlas = build_atlas_json(image_name, canvas.size, frame_map)

    os.makedirs(ITEMS_ATLAS_DIR, exist_ok=True)
    canvas.save(os.path.join(ITEMS_ATLAS_DIR, image_name))
    with open(os.path.join(ITEMS_ATLAS_DIR, f"{item_id}.json"), "w", encoding="utf-8") as f:
        json.dump(atlas, f, indent=2, ensure_ascii=False)

    return atlas


# =========================
# ENTRY POINT
# =========================

def main():
    ids = _list_item_ids()
    baked = 0
    skipped = 0

    for item_id in ids:
        if bake_item(item_id) is not None:
            baked += 1
        else:
            skipped += 1

    print(f"[OK] items: {baked} atlases gerados em {ITEMS_ATLAS_DIR}")
    if skipped:
        print(f"  [skip] {skipped} itens ignorados (fora do classificador de equipamento/consumível)")


if __name__ == "__main__":
    main()
