"""Single atlas for the fluid pools combat leaves on the ground.

Same gap the corpse atlas closes, one step further: a splash item is spawned
at runtime, never placed on an OTBM tile, so no `map.json` sheet carries it;
and `bia.is_equipment_candidate` rejects it too (`liquidpool` items have no
`market`/`clothes` flag and no `take`, only `bottom`/`unmove`). Hence its own
atlas, sibling of `bake_effect_atlas.py`/`bake_corpse_atlas.py`.

**What the server actually spawns** (conferido no Canary 3.2.1):

- a hit only splashes on **physical** damage, with `ITEM_SMALLSPLASH = 2889`
  (`Game::combatGetTypeInfo`, src/game/game.cpp:6957);
- a death splashes with `ITEM_FULLSPLASH = 2886` (`Creature::dropCorpse`,
  src/creatures/creature.cpp:668);
- and both decay down a fixed chain (data/items/items.xml):
  2889 -> 2890 -> 2891 -> gone, 2886 -> 2887 -> 2888 -> gone.

Which **fluid** it is comes from the monster's `race`: `blood` -> sangue,
`venom` -> slime, `ink` -> ink; `undead`, `fire` and `energy` splash nothing
at all (only a visual effect), so those three need no frame here.

That maps onto the sprites because a splash appearance is a 4x3 pattern grid
of 12 fluid colours — one appearance, twelve cells, one per fluid the client
knows. The three the game can ask for were confirmed by pixel: cell **2** is
RGB(255,13,13) vermelho, cell **4** RGB(45,229,39) verde, cell **8**
RGB(39,39,39) preto. 6 items x 3 fluids = 18 frames of 32x32, which is why
this packs a single row (`bia.pack_item_frames`, 612px) instead of the grid
`bake_corpse_atlas.py` needed for its 63 frames of up to 64x64.

Requires `python extract_sprites.py` to have run (sprites/items/<id>/).
"""

import json
import os
from typing import Dict, List, Tuple

import bake_item_atlas as bia

# =========================
# CONFIG
# =========================

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
EXTRACTOR_DIR = os.path.dirname(SCRIPTS_DIR)

POOLS_ATLAS_DIR = os.path.join(EXTRACTOR_DIR, "atlases", "pools")

ATLAS_NAME = "pools"

# As duas cadeias de decay, cada uma na ordem em que o item apodrece. A "full"
# é a da morte (ITEM_FULLSPLASH), a "small" é a do hit físico
# (ITEM_SMALLSPLASH) — ver o docstring do módulo.
POOL_DECAY_CHAINS = (
    ("full", (2886, 2887, 2888)),
    ("small", (2889, 2890, 2891)),
)

# Índice da célula no grid 4x3 de cores do fluido, por raça de monstro. As
# raças que não aparecem aqui (undead, fire, energy) não deixam poça nenhuma.
FLUID_VARIANTS = (
    ("blood", 2),
    ("venom", 4),
    ("ink", 8),
)


# =========================
# FRAME DISCOVERY
# =========================

def pool_frame_keys() -> List[Tuple[int, int]]:
    """Ordered (itemId, variant) pairs to pack, fluid-major.

    Um fluido de cada vez, e dentro dele as duas cadeias inteiras na ordem do
    decay — mesma razão pela qual a cadeia de um monstro fica contígua em
    `bake_corpse_atlas.py`: o que se lê seguido no atlas é a sequência que o
    cliente vai percorrer conforme a poça seca.
    """
    return [
        (item_id, variant)
        for _, variant in FLUID_VARIANTS
        for _, chain in POOL_DECAY_CHAINS
        for item_id in chain
    ]


def _pool_frame_list(
    pairs: List[Tuple[int, int]],
) -> Tuple[List[Tuple[str, str]], List[Tuple[int, int]]]:
    """(key, png_path) per (itemId, variant) plus the pairs that had no PNG.

    A chave é `"<itemId>_<variante>"` (ex.: `"2889_2"`) porque o cliente tem
    as duas metades em mãos e nenhuma sozinha basta: o itemId vem do estágio
    de decay, a variante da raça do monstro que sangrou. Coincide com o nome
    do PNG extraído — `extract_sprites.py` nomeia cada célula do pattern como
    `<itemId>_<índice>` —, então o `spriteId` do JSON do item serve de
    validação: uma variante fora da lista dele é pulada com aviso em vez de
    virar um frame quebrado.
    """
    frames: List[Tuple[str, str]] = []
    missing: List[Tuple[int, int]] = []

    for item_id, variant in pairs:
        data = bia._load_item_json(item_id)
        keys = [key for key, _ in bia._item_frame_list(item_id, data)] if data else []
        key = f"{item_id}_{variant}"
        path = bia._resolve_frame_path(item_id, key)
        if key not in keys or not os.path.exists(path):
            missing.append((item_id, variant))
            continue
        frames.append((key, path))

    return frames, missing


# =========================
# BAKE
# =========================

def bake_pool_atlas() -> Dict:
    """Bake every (chain item, fluid) pair into one atlas, writing pools.png
    + pools.json to POOLS_ATLAS_DIR. Returns the atlas JSON dict. Nothing is
    written when there is nothing to pack — same tolerance as the other
    bakes."""
    frames, missing = _pool_frame_list(pool_frame_keys())
    for item_id, variant in missing:
        print(f"  [skip] pool {item_id} variante {variant}: PNG não extraído em "
              f"{bia.ITEMS_SPRITES_DIR}")

    if not frames:
        print("  [!] nenhum sprite de poça extraído — rode extract_sprites.py primeiro")
        return bia.build_atlas_json(f"{ATLAS_NAME}.png", (0, 0), {})

    canvas, frame_map = bia.pack_item_frames(frames)
    image_name = f"{ATLAS_NAME}.png"
    atlas = bia.build_atlas_json(image_name, canvas.size, frame_map)

    os.makedirs(POOLS_ATLAS_DIR, exist_ok=True)
    canvas.save(os.path.join(POOLS_ATLAS_DIR, image_name))
    with open(os.path.join(POOLS_ATLAS_DIR, f"{ATLAS_NAME}.json"), "w", encoding="utf-8") as f:
        json.dump(atlas, f, indent=2, ensure_ascii=False)

    return atlas


# =========================
# ENTRY POINT
# =========================

def main():
    atlas = bake_pool_atlas()
    size = atlas["meta"]["size"]

    print(f"[OK] pools: {len(atlas['frames'])} frames de {len(FLUID_VARIANTS)} fluido(s) "
          f"x {sum(len(chain) for _, chain in POOL_DECAY_CHAINS)} estágio(s), "
          f"{size['w']}x{size['h']}px em {POOLS_ATLAS_DIR}")


if __name__ == "__main__":
    main()
