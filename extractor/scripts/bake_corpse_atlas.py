"""Single atlas for monster corpses — the body item plus every decay stage.

A corpse item has no home in any sheet the pipeline already writes, which is
why the game had nothing to draw:

- **map.json sheets** only carry the appearances a map actually places on a
  tile, and a corpse is never *on* a tile in the OTBM — it's spawned at
  runtime when something dies. Measured: the intersection between the corpse
  itemIds and the `appearances` of all 21 map.json files is empty.
- **items-static/items-animated** are the market catalogue, and
  `bia.is_equipment_candidate` deliberately rejects the `corpse` flag.

So corpses get their own atlas, keyed by **itemId** (`"5964"`), because the
itemId is what the client already has in hand: `MonsterCorpse.stages[i].itemId`
straight out of monster-loot.json. Every stage of the chain is packed, not just
the body — a decay tick that swaps to a stage with no texture would blank the
corpse mid-rot.

Unlike bake_effect_atlas.py/bake_item_atlas.py this packs a **grid**, not a
single row: 63 frames of up to 64x64 in one row is 4158px, already past the
texture size. The grid model is bake_item_sheets.py's (fixed columns,
row-major, no bin-packing), with the cell sized from the widest/tallest sprite
in the set instead of a hardcoded 32 — corpse sprites come in 32x32, 64x32,
32x64 and 64x64. Frame ordering, padding and the `{frames, meta}` shape are
the shared bake_item_atlas helpers, imported rather than copied like both item
sheet bakers already do.

**Which corpses.** Not all of them. monster-loot.json has 1391 monsters with a
corpse chain, 2688 distinct itemIds (2667 of which have an extracted PNG); at
a 66px cell that grid is 31 columns x 87 rows = 2046x5742px, and even a
perfect size-aware packing needs ~7.35M px2 against the ~4.19M a 2048x2048
texture holds — the full set simply does not fit in one texture. The scope is
therefore the monsters the built maps actually spawn: every `monsterDefs` name
in `ready-maps*/<CIDADE>/<pasta>/monsters/respawn.json`, the same files
build_hunt_fragment.py reads. Today that's 16 monsters / 63 itemIds, and the
atlas grows on its own when a map with a new monster is built — no allow-list
to maintain.

Requires `node build_map.js <pasta>` (for respawn.json) and
`python extract_sprites.py` (for sprites/items/<id>.png) to have run.
"""

import json
import os
from typing import Dict, List, Set, Tuple

from PIL import Image

import bake_item_atlas as bia
import map_dirs
from sheet_packer import SAFE_TEXTURE_SIZE

# =========================
# CONFIG
# =========================

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
EXTRACTOR_DIR = os.path.dirname(SCRIPTS_DIR)

MONSTER_LOOT_PATH = os.path.join(EXTRACTOR_DIR, "monster-loot.json")
CORPSES_ATLAS_DIR = os.path.join(EXTRACTOR_DIR, "atlases", "corpses")

# Both map roots: v6 is the current format, v5 is still shipped alongside it,
# and a monster that only spawns on one of them still dies and leaves a body.
READY_MAPS_DIRS = (
    os.path.join(EXTRACTOR_DIR, "ready-maps"),
    os.path.join(EXTRACTOR_DIR, "ready-maps-v6"),
)

RESPAWN_RELPATH = os.path.join("monsters", "respawn.json")

ATLAS_NAME = "corpses"


# =========================
# PACKING (pure function)
# =========================

def pack_corpse_frames(frames: List[Tuple[str, str]]) -> Tuple[Image.Image, Dict]:
    """Pack ordered (key, png_path) frames into a row-major grid atlas.

    Frames keep the exact order given (a monster's chain stays contiguous —
    see _corpse_frame_list) and each gets a `bia.PADDING_PX` transparent
    border, same as the single-row packers. The cell is square-ish rather
    than fixed: it's the widest and tallest sprite in the set plus padding,
    so a set that happens to be all 32x32 doesn't pay for the 64x64 corpses.

    Column count fills the safe texture width first, the way
    sheet_packer.V6_COLUMNS_BY_BUCKET does, so the sheet grows in both axes
    instead of only downward.
    """
    if not frames:
        return Image.new("RGBA", (0, 0), (0, 0, 0, 0)), {}

    images = [(key, Image.open(path).convert("RGBA")) for key, path in frames]
    cell_w = max(img.width for _, img in images) + 2 * bia.PADDING_PX
    cell_h = max(img.height for _, img in images) + 2 * bia.PADDING_PX

    columns = max(1, SAFE_TEXTURE_SIZE // cell_w)
    rows = -(-len(images) // columns)  # ceil div

    canvas = Image.new(
        "RGBA",
        (cell_w * min(columns, len(images)), cell_h * rows),
        (0, 0, 0, 0),
    )
    frame_map: Dict = {}

    for index, (key, img) in enumerate(images):
        x = (index % columns) * cell_w + bia.PADDING_PX
        y = (index // columns) * cell_h + bia.PADDING_PX
        canvas.paste(img, (x, y))
        frame_map[key] = {"frame": {"x": x, "y": y, "w": img.width, "h": img.height}}

    return canvas, frame_map


# =========================
# CORPSE DISCOVERY
# =========================

def _load_monster_loot() -> Dict:
    """monster-loot.json, the checked-in corpse/loot reference. Missing file
    means the index was never generated — see build_monster_loot_index.py."""
    if not os.path.exists(MONSTER_LOOT_PATH):
        return {}
    with open(MONSTER_LOOT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def spawned_monster_names() -> List[str]:
    """Every monster name any built map spawns, sorted, deduplicated across
    the two map roots. Reads the `monsterDefs` of each
    `<root>/<CIDADE>/<pasta>/monsters/respawn.json` — the map's own digested
    spawn list, so a monster nobody can meet never costs a cell."""
    names: Set[str] = set()

    for root in READY_MAPS_DIRS:
        for map_name in map_dirs.discover_two_level_names(root, RESPAWN_RELPATH):
            map_dir = map_dirs.find_two_level_dir(root, map_name)
            with open(os.path.join(map_dir, RESPAWN_RELPATH), "r", encoding="utf-8") as f:
                respawn = json.load(f)
            for definition in (respawn.get("monsterDefs") or {}).values():
                name = definition.get("name")
                if name:
                    names.add(name)

    return sorted(names)


def corpse_item_ids(names: List[str], monster_loot: Dict) -> List[int]:
    """Body itemId + every decay stage's itemId, for each named monster, in
    first-seen order with a monster's chain contiguous. A monster with no
    corpse block is skipped silently — plenty of them (summons, glyphs) never
    leave a body."""
    ids: List[int] = []
    seen: Set[int] = set()

    for name in names:
        corpse = (monster_loot.get(name) or {}).get("corpse")
        if not corpse:
            continue
        chain = [corpse["itemId"]] + [stage["itemId"] for stage in corpse.get("stages", [])]
        for item_id in chain:
            if item_id not in seen:
                seen.add(item_id)
                ids.append(item_id)

    return ids


def _corpse_frame_list(ids: List[int]) -> Tuple[List[Tuple[str, str]], List[int]]:
    """(key, png_path) per itemId plus the ids that had no PNG.

    The key is the itemId as a string, not the sprite's own id: a corpse
    appearance carries exactly one spriteId (verified across all 2667
    extracted ones), so there is no frame to disambiguate, and keying by
    itemId is what lets the client look a stage up directly.
    """
    frames: List[Tuple[str, str]] = []
    missing: List[int] = []

    for item_id in ids:
        data = bia._load_item_json(item_id)
        item_frames = bia._item_frame_list(item_id, data) if data else []
        if not item_frames or not os.path.exists(item_frames[0][1]):
            missing.append(item_id)
            continue
        frames.append((str(item_id), item_frames[0][1]))

    return frames, missing


# =========================
# BAKE
# =========================

def bake_corpse_atlas() -> Dict:
    """Bake the corpse chains of every monster the built maps spawn into one
    atlas, writing corpses.png + corpses.json to CORPSES_ATLAS_DIR. Returns
    the atlas JSON dict. Nothing is written when there is nothing to pack —
    same tolerance as the other bakes."""
    monster_loot = _load_monster_loot()
    if not monster_loot:
        print(f"  [!] monster-loot.json não encontrado em {MONSTER_LOOT_PATH} — "
              f"rode build_monster_loot_index.py primeiro")
        return bia.build_atlas_json(f"{ATLAS_NAME}.png", (0, 0), {})

    names = spawned_monster_names()
    if not names:
        print("  [!] nenhum monsters/respawn.json em ready-maps — rode build_map.js primeiro")
        return bia.build_atlas_json(f"{ATLAS_NAME}.png", (0, 0), {})

    frames, missing = _corpse_frame_list(corpse_item_ids(names, monster_loot))
    for item_id in missing:
        print(f"  [skip] corpse {item_id}: PNG não extraído em {bia.ITEMS_SPRITES_DIR}")

    if not frames:
        print("  [!] nenhum sprite de corpse extraído — rode extract_sprites.py primeiro")
        return bia.build_atlas_json(f"{ATLAS_NAME}.png", (0, 0), {})

    canvas, frame_map = pack_corpse_frames(frames)
    image_name = f"{ATLAS_NAME}.png"
    atlas = bia.build_atlas_json(image_name, canvas.size, frame_map)

    if canvas.width > SAFE_TEXTURE_SIZE or canvas.height > SAFE_TEXTURE_SIZE:
        print(f"  [!] {canvas.width}x{canvas.height}px passa do limite seguro de "
              f"{SAFE_TEXTURE_SIZE}x{SAFE_TEXTURE_SIZE} — as hunts já não cabem num "
              f"atlas só, hora de shardear como bake_item_sheets.py")

    os.makedirs(CORPSES_ATLAS_DIR, exist_ok=True)
    canvas.save(os.path.join(CORPSES_ATLAS_DIR, image_name))
    with open(os.path.join(CORPSES_ATLAS_DIR, f"{ATLAS_NAME}.json"), "w", encoding="utf-8") as f:
        json.dump(atlas, f, indent=2, ensure_ascii=False)

    return atlas


# =========================
# ENTRY POINT
# =========================

def main():
    atlas = bake_corpse_atlas()
    size = atlas["meta"]["size"]

    print(f"[OK] corpses: {len(atlas['frames'])} itemIds de "
          f"{len(spawned_monster_names())} monstro(s) spawnado(s), "
          f"{size['w']}x{size['h']}px em {CORPSES_ATLAS_DIR}")


if __name__ == "__main__":
    main()
