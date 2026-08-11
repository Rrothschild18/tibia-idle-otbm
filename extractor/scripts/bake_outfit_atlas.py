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
OUTFITS_ATLAS_DIR = os.path.join(EXTRACTOR_DIR, "atlases", "outfits")

# Transparent pixels added around each packed frame so the client scaling
# or filtering the atlas texture doesn't bleed neighboring frames together.
PADDING_PX = 1


# =========================
# PACKING (pure functions)
# =========================

def pack_outfit_frames(frames: List[Tuple[str, str]]) -> Tuple[Image.Image, Dict]:
    """Pack ordered (key, png_path) frames into a single-row atlas.

    Frames keep the exact order given (the outfit's documented idle/moving
    direction+index order) — not sorted by key. Each frame gets a
    PADDING_PX transparent border on every side to avoid texture bleeding.
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
# OUTFIT DISCOVERY / LOADING
# =========================

def _list_outfit_ids() -> List[int]:
    """List every outfit ID with extracted sprites, sorted ascending."""
    if not os.path.isdir(OUTFITS_SPRITES_DIR):
        return []

    ids = set()
    for name in os.listdir(OUTFITS_SPRITES_DIR):
        path = os.path.join(OUTFITS_SPRITES_DIR, name)
        if os.path.isdir(path):
            ids.add(int(name))
        elif name.endswith(".json"):
            ids.add(int(name[: -len(".json")]))

    return sorted(ids)


def _load_outfit_json(outfit_id: int) -> Optional[Dict]:
    """Load JSON metadata for an outfit from sprites/outfits/{id}/."""
    for path in [
        os.path.join(OUTFITS_SPRITES_DIR, str(outfit_id), f"{outfit_id}.json"),
        os.path.join(OUTFITS_SPRITES_DIR, f"{outfit_id}.json"),
    ]:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    return None


def _resolve_frame_path(outfit_id: int, key: str) -> str:
    """Resolve a frame's PNG path, trying the outfit's subdirectory first.

    extract_sprites.py normally writes every frame of a multi-frame-group
    outfit into sprites/outfits/<id>/, but when a frame group has exactly
    one sprite it writes that single PNG to the top-level sprites/outfits/
    directory instead (its "SPRITE ÚNICA" branch), even though the JSON for
    the same outfit still lives in the subdirectory. Outfits with one idle
    sprite + one moving sprite (no walk-cycle) hit this split-location case
    in real extracted data.
    """
    for base in (os.path.join(OUTFITS_SPRITES_DIR, str(outfit_id)), OUTFITS_SPRITES_DIR):
        path = os.path.join(base, f"{key}.png")
        if os.path.exists(path):
            return path
    return os.path.join(OUTFITS_SPRITES_DIR, str(outfit_id), f"{key}.png")


def _outfit_frame_list(outfit_id: int, data: Dict) -> List[Tuple[str, str]]:
    """Ordered (key, png_path) list for an outfit, following its JSON's
    existing frame order (already idle-then-moving, direction-then-index —
    see OUTFIT_SPRITES_DOCUMENTATION.md — because extract_sprites.py writes
    spriteId arrays in that order)."""
    frame_groups = data.get("frameGroups")
    if frame_groups:
        keys = [key for fg in frame_groups for key in fg.get("spriteId", [])]
    else:
        keys = data.get("spriteId", [])

    return [(key, _resolve_frame_path(outfit_id, key)) for key in keys]


# =========================
# BAKE
# =========================

def bake_outfit(outfit_id: int) -> Optional[Dict]:
    """Bake one outfit's atlas, writing <id>.png + <id>.json to
    OUTFITS_ATLAS_DIR. Returns the atlas JSON dict, or None if the outfit
    has no extracted JSON (mirrors the tolerant missing-outfit handling in
    build_phaser_map.py) or is a player outfit.

    Player outfits belong to bake_player_outfit_sheet.py: they have an addon
    and a layer axis, and packing them into this single row of `<id>_<n>`
    frames would produce an atlas that loads and animates wrong. They are
    recognised by the `axes` block their extraction declares — not by an id
    list, so neither baker has to know the other's."""
    data = _load_outfit_json(outfit_id)
    if data is None or "axes" in data:
        return None

    frames = _outfit_frame_list(outfit_id, data)
    canvas, frame_map = pack_outfit_frames(frames)
    image_name = f"{outfit_id}.png"
    atlas = build_atlas_json(image_name, canvas.size, frame_map)

    os.makedirs(OUTFITS_ATLAS_DIR, exist_ok=True)
    canvas.save(os.path.join(OUTFITS_ATLAS_DIR, image_name))
    with open(os.path.join(OUTFITS_ATLAS_DIR, f"{outfit_id}.json"), "w", encoding="utf-8") as f:
        json.dump(atlas, f, indent=2, ensure_ascii=False)

    return atlas


# =========================
# ENTRY POINT
# =========================

def main():
    ids = _list_outfit_ids()
    baked = 0
    skipped = 0

    for outfit_id in ids:
        if bake_outfit(outfit_id) is not None:
            baked += 1
        else:
            skipped += 1

    print(f"[OK] outfits: {baked} atlases gerados em {OUTFITS_ATLAS_DIR}")
    if skipped:
        print(f"  [skip] {skipped} outfits ignorados (JSON não encontrado)")


if __name__ == "__main__":
    main()
