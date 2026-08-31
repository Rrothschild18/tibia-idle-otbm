"""Single atlas for the magic effects the game plays (today: teleport only).

Simplified sibling of bake_item_atlas.py: same single-row packing, same
`{frames, meta}` atlas shape, minus the equipment/consumable classifier —
`is_equipment_candidate` reads item flags (market/clothes/usable+take) that
an effect appearance simply doesn't carry, so there is nothing to classify
here. The packing and JSON helpers are imported from bake_item_atlas rather
than copied, the same way both item sheet bakers already import them —
"item" in `pack_item_frames`'s name describes where it was first used, not
something it enforces.

What it does NOT do is bake every effect in effects.aec. The extraction
writes all 169 of them (2240 frames, up to 64x64 each); one atlas holding
all of that would land around 3100x3100px, past the 2048x2048 texture size
the item/map sheets are explicitly sized to stay under. Since the only
effect the game asks for is the birth/respawn one, ATLAS_EFFECT_IDS is an
explicit allow-list — add an id to it when the game needs another effect,
and the same atlas grows.
"""

import json
import os
from typing import Dict, List, Optional, Tuple

import bake_item_atlas as bia

# =========================
# CONFIG
# =========================

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
EXTRACTOR_DIR = os.path.dirname(SCRIPTS_DIR)

EFFECTS_SPRITES_DIR = os.path.join(EXTRACTOR_DIR, "sprites", "effects")
EFFECTS_ATLAS_DIR = os.path.join(EXTRACTOR_DIR, "atlases", "effects")

ATLAS_NAME = "effects"

# CONST_ME_TELEPORT (11 no enum MagicEffectClasses do Canary): o redemoinho
# usado quando algo é teleportado, e o efeito de nascimento de monstro.
ATLAS_EFFECT_IDS = (11,)


# =========================
# EFFECT LOADING
# =========================

def _load_effect_json(effect_id: int) -> Optional[Dict]:
    """Load JSON metadata for an effect from sprites/effects/{id}/."""
    for path in [
        os.path.join(EFFECTS_SPRITES_DIR, str(effect_id), f"{effect_id}.json"),
        os.path.join(EFFECTS_SPRITES_DIR, f"{effect_id}.json"),
    ]:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    return None


def _resolve_frame_path(effect_id: int, key: str) -> str:
    """Resolve a frame's PNG path, trying the effect's subdirectory first.

    Same split-location quirk documented in bake_item_atlas.py: an effect
    with a single sprite is written flat (sprites/effects/{id}.png), an
    animated one into sprites/effects/{id}/.
    """
    for base in (os.path.join(EFFECTS_SPRITES_DIR, str(effect_id)), EFFECTS_SPRITES_DIR):
        path = os.path.join(base, f"{key}.png")
        if os.path.exists(path):
            return path
    return os.path.join(EFFECTS_SPRITES_DIR, str(effect_id), f"{key}.png")


def _effect_frame_list(effect_id: int, data: Dict) -> List[Tuple[str, str]]:
    """Ordered (key, png_path) list for an effect, following its JSON's
    spriteId order — which for an effect is exactly the animation phase
    order, since every effect keeps patternWidth/Height/Depth at 1."""
    frame_groups = data.get("frameGroups")
    if frame_groups:
        keys = [key for fg in frame_groups for key in fg.get("spriteId", [])]
    else:
        keys = data.get("spriteId", [])

    return [(key, _resolve_frame_path(effect_id, key)) for key in keys]


# =========================
# BAKE
# =========================

def bake_effect_atlas() -> Dict:
    """Bake every effect in ATLAS_EFFECT_IDS into one atlas, writing
    effects.png + effects.json to EFFECTS_ATLAS_DIR. Returns the atlas
    JSON dict. Effects with no extracted JSON are skipped (tolerant, like
    the other bakes) — run extract_sprites.py --group effects first."""
    frames: List[Tuple[str, str]] = []

    for effect_id in ATLAS_EFFECT_IDS:
        data = _load_effect_json(effect_id)
        if data is None:
            print(f"  [skip] effect {effect_id}: JSON não encontrado em {EFFECTS_SPRITES_DIR}")
            continue
        frames.extend(_effect_frame_list(effect_id, data))

    if not frames:
        print("  [!] nenhum effect extraido — rode extract_sprites.py --group effects primeiro")
        return bia.build_atlas_json(f"{ATLAS_NAME}.png", (0, 0), {})

    canvas, frame_map = bia.pack_item_frames(frames)
    image_name = f"{ATLAS_NAME}.png"
    atlas = bia.build_atlas_json(image_name, canvas.size, frame_map)

    os.makedirs(EFFECTS_ATLAS_DIR, exist_ok=True)
    canvas.save(os.path.join(EFFECTS_ATLAS_DIR, image_name))
    with open(os.path.join(EFFECTS_ATLAS_DIR, f"{ATLAS_NAME}.json"), "w", encoding="utf-8") as f:
        json.dump(atlas, f, indent=2, ensure_ascii=False)

    return atlas


# =========================
# ENTRY POINT
# =========================

def main():
    atlas = bake_effect_atlas()
    size = atlas["meta"]["size"]

    print(f"[OK] effects: {len(atlas['frames'])} frames de {len(ATLAS_EFFECT_IDS)} efeito(s), "
          f"{size['w']}x{size['h']}px em {EFFECTS_ATLAS_DIR}")


if __name__ == "__main__":
    main()
