"""Bake one sheet per player outfit from the frames extract_sprites.py wrote.

Separate from bake_outfit_atlas.py on purpose. That one packs a creature into
a single row of `<id>_<n>` frames and knows nothing about addons, layers or
mounts; this one packs a 24-column grid of explicitly named frames and carries
the `axes` block through to the consumer. The two never touch the same output
directory, and a JSON without `axes` is left alone here.

Layout: 216 frames (4 directions x 3 addons x 2 layers x 9 phases — the mount
axis is dropped upstream), 64x64 cells pitched one pixel apart, 24 columns.
That comes out at 1561x586, ~92 KB per outfit — times however many ids
extract_sprites.py wrote to sprites/outfits/ (the full catalogue in
outfit_names.json, not just the 22 classics).

Twenty-four columns is not arbitrary: one phase is exactly 3 addons x 4
directions x 2 layers = 24 frames, so **row N of the sheet is phase N**. The
grid is readable by eye against the documented axes, which is the same reason
the frame keys spell themselves out instead of being numbered — see the
correction note at the top of OUTFIT_SPRITES_DOCUMENTATION.md.

Run: python bake_player_outfit_sheet.py
"""

import json
import os
from typing import Dict, List, Optional, Tuple

from PIL import Image

# =========================
# CONFIG
# =========================

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
EXTRACTOR_DIR = os.path.dirname(SCRIPTS_DIR)

OUTFITS_SPRITES_DIR = os.path.join(EXTRACTOR_DIR, "sprites", "outfits")
SHEETS_DIR = os.path.join(EXTRACTOR_DIR, "atlases", "player-outfits")

# One transparent pixel between neighbouring cells (and around the grid) so
# scaling or filtering the texture doesn't bleed one frame into the next.
# Shared between neighbours rather than given to each cell: cells are pitched
# frame+1 apart, and the sheet is one pixel bigger than the last cell's edge.
PADDING_PX = 1
COLUMNS = 24


# =========================
# PACKING (pure functions)
# =========================

def pack_player_frames(frames: List[Tuple[str, str]],
                       columns: int = COLUMNS) -> Tuple[Image.Image, Dict]:
    """Pack ordered (key, png_path) frames into a `columns`-wide grid.

    Frames keep the order given — the index law's order, which is what makes
    row N come out as phase N — and are never sorted by key.
    """
    if not frames:
        return Image.new("RGBA", (0, 0), (0, 0, 0, 0)), {}

    images = [(key, Image.open(path).convert("RGBA")) for key, path in frames]
    frame_w = max(img.width for _, img in images)
    frame_h = max(img.height for _, img in images)
    pitch_x = frame_w + PADDING_PX
    pitch_y = frame_h + PADDING_PX
    rows = -(-len(images) // columns)  # ceil div

    canvas = Image.new(
        "RGBA",
        (PADDING_PX + columns * pitch_x, PADDING_PX + rows * pitch_y),
        (0, 0, 0, 0),
    )
    frame_map: Dict = {}

    for index, (key, img) in enumerate(images):
        x = PADDING_PX + (index % columns) * pitch_x
        y = PADDING_PX + (index // columns) * pitch_y
        canvas.paste(img, (x, y))
        frame_map[key] = {"frame": {"x": x, "y": y, "w": img.width, "h": img.height}}

    return canvas, frame_map


def build_sheet_json(image_name: str, canvas_size: Tuple[int, int],
                     frame_map: Dict, axes: Dict, name: str = "") -> Dict:
    """The shape Phaser reads directly, plus the `axes` block the client needs
    so it never has to deduce the axes from the frame count."""
    return {
        "frames": frame_map,
        "axes": axes,
        "name": name,
        "meta": {"image": image_name, "size": {"w": canvas_size[0], "h": canvas_size[1]}},
    }


def frames_declared_by(axes: Dict) -> int:
    return (axes["directions"] * axes["addons"] * axes["mounts"]
            * axes["layers"] * axes["phases"])


# =========================
# LOADING
# =========================

def _load_extracted(outfit_id: int) -> Optional[Dict]:
    """Load the JSON extract_sprites.py wrote, or None if this outfit isn't a
    player outfit — the absence of `axes` is what says so, so the two bakers
    stay decoupled from each other's id lists."""
    path = os.path.join(OUTFITS_SPRITES_DIR, str(outfit_id), f"{outfit_id}.json")
    if not os.path.exists(path):
        return None

    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)

    return data if "axes" in data else None


def extracted_player_outfit_ids() -> List[int]:
    """Every outfit id under sprites/outfits/ whose JSON declares `axes`."""
    if not os.path.isdir(OUTFITS_SPRITES_DIR):
        return []

    ids = []
    for name in sorted(os.listdir(OUTFITS_SPRITES_DIR)):
        if not name.isdigit():
            continue
        if not os.path.isdir(os.path.join(OUTFITS_SPRITES_DIR, name)):
            continue
        if _load_extracted(int(name)) is not None:
            ids.append(int(name))

    return ids


# =========================
# BAKE
# =========================

def bake_player_outfit(outfit_id: int) -> Optional[Dict]:
    """Bake one outfit's sheet, writing <id>.png + <id>.json to SHEETS_DIR.

    Returns None — without writing anything — when the outfit wasn't extracted
    by the player path, or when its frame count contradicts the axes it
    declares. The second case is the whole reason the axes are declared: a
    sheet whose frames don't multiply out is a sheet somebody will read with
    the wrong stride later.
    """
    data = _load_extracted(outfit_id)
    if data is None:
        return None

    axes = data["axes"]
    keys = data.get("spriteId", [])

    if len(keys) != frames_declared_by(axes):
        print(f"  [!] outfit {outfit_id}: {len(keys)} frames, "
              f"os eixos declaram {frames_declared_by(axes)} — pulado")
        return None

    outfit_dir = os.path.join(OUTFITS_SPRITES_DIR, str(outfit_id))
    frames = [(key, os.path.join(outfit_dir, f"{key}.png")) for key in keys]

    canvas, frame_map = pack_player_frames(frames)
    image_name = f"{outfit_id}.png"
    sheet = build_sheet_json(image_name, canvas.size, frame_map, axes, data.get("name", ""))

    os.makedirs(SHEETS_DIR, exist_ok=True)
    canvas.save(os.path.join(SHEETS_DIR, image_name))
    with open(os.path.join(SHEETS_DIR, f"{outfit_id}.json"), "w", encoding="utf-8") as handle:
        json.dump(sheet, handle, indent=2, ensure_ascii=False)

    return sheet


# =========================
# ENTRY POINT
# =========================

def main():
    ids = extracted_player_outfit_ids()
    baked = 0

    for outfit_id in ids:
        if bake_player_outfit(outfit_id) is not None:
            baked += 1

    print(f"[OK] player outfits: {baked} sheets gerados em {SHEETS_DIR}")
    if not ids:
        print("  [!] nenhum outfit de jogador extraido — rode extract_sprites.py primeiro")


if __name__ == "__main__":
    main()
