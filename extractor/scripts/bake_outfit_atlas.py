import contextlib
import glob
import json
import os
import tempfile
from typing import Dict, List, Optional, Set, Tuple

from PIL import Image

import outfit_colors

# =========================
# CONFIG
# =========================

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
EXTRACTOR_DIR = os.path.dirname(SCRIPTS_DIR)

OUTFITS_SPRITES_DIR = os.path.join(EXTRACTOR_DIR, "sprites", "outfits")

# A camada base, sem addon, de um outfit de jogador. Serve de duas coisas:
# é o frame que `bake_outfit` empacota, e é a lista de posições
# (4 direções x 9 fases) sobre a qual `bake_monster_appearance` empilha os
# addons — as outras camadas têm o mesmo nome com `a0` trocado.
BASE_LAYER_MARKER = "_base_a0_"
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

def _appearance_layers(outfit_id: int, position_key: str, addons: int) -> List[Tuple[str, str]]:
    """Os `(base, mask)` de cada camada ligada daquela posição, de baixo para cima.

    Uma camada que não existe no disco é pulada em vez de derrubar o atlas: o
    monstro fica sem aquele acessório, e não sem sprite nenhum.
    """
    layers = []
    for addon in outfit_colors.enabled_addons(addons):
        base_key = position_key.replace(BASE_LAYER_MARKER, f"_base_a{addon}_")
        base_path = _resolve_frame_path(outfit_id, base_key)
        mask_path = _resolve_frame_path(outfit_id, base_key.replace("_base_", "_mask_"))
        if os.path.exists(base_path) and os.path.exists(mask_path):
            layers.append((base_path, mask_path))
    return layers


def bake_monster_appearance(appearance: Dict) -> Optional[Dict]:
    """Bakeia o atlas de criatura de **uma aparência** — outfit, as quatro
    cores do monstro e os addons —, recolorindo base pela máscara.

    Um atlas por outfit não bastaria: 78 looktypes são usados por monstros de
    cores diferentes, e o 137 por quatro (Amazon, e mais três). O nome do
    arquivo é a chave da aparência, e é o mesmo nome que
    `build_phaser_map._outfit_atlas_ref` escreve no `respawn.json`.

    O addon entra empilhado por cima da base, tingido pelas mesmas cores —
    porque a máscara da camada de addon também pinta região. Sem isso os cinco
    do culto de Carlin saíam com a chave prometendo addon e o pixel sem ele.
    """
    outfit_id = int(appearance["looktype"])
    data = _load_outfit_json(outfit_id)
    if data is None or "axes" not in data:
        return None

    frames = _outfit_frame_list(outfit_id, data)
    colors = outfit_colors.region_colors(appearance)
    key = outfit_colors.appearance_key(appearance)
    addons = int(appearance.get("addons", 0))

    with tempfile.TemporaryDirectory(prefix=f"outfit-{key}-") as staging:
        tinted = []
        for index, position_key in enumerate(
            [frame_key for frame_key, _ in frames if BASE_LAYER_MARKER in frame_key]
        ):
            layers = _appearance_layers(outfit_id, position_key, addons)
            if not layers:
                continue
            with contextlib.ExitStack() as open_layers:
                painted = outfit_colors.compose_frame(
                    [
                        (
                            open_layers.enter_context(Image.open(base_path)),
                            open_layers.enter_context(Image.open(mask_path)),
                        )
                        for base_path, mask_path in layers
                    ],
                    colors,
                )
            staged = os.path.join(staging, f"{key}_{index}.png")
            painted.save(staged)
            tinted.append((f"{outfit_id}_{index}", staged))

        if not tinted:
            return None

        canvas, frame_map = pack_outfit_frames(tinted)

    image_name = f"{key}.png"
    atlas = build_atlas_json(image_name, canvas.size, frame_map)
    os.makedirs(OUTFITS_ATLAS_DIR, exist_ok=True)
    canvas.save(os.path.join(OUTFITS_ATLAS_DIR, image_name))
    with open(os.path.join(OUTFITS_ATLAS_DIR, f"{key}.json"), "w", encoding="utf-8") as handler:
        json.dump(atlas, handler, indent=2, ensure_ascii=False)
    return atlas


def bake_outfit(outfit_id: int, as_monster: bool = False) -> Optional[Dict]:
    """Bake one outfit's atlas, writing <id>.png + <id>.json to
    OUTFITS_ATLAS_DIR. Returns the atlas JSON dict, or None if the outfit
    has no extracted JSON (mirrors the tolerant missing-outfit handling in
    build_phaser_map.py) or is a player outfit.

    Player outfits belong to bake_player_outfit_sheet.py: they have an addon
    and a layer axis, and packing them into this single row of `<id>_<n>`
    frames would produce an atlas that loads and animates wrong. They are
    recognised by the `axes` block their extraction declares — not by an id
    list, so neither baker has to know the other's.

    `as_monster` é a exceção, e ela existe porque **monstro humanoide usa
    outfit de jogador**: Amazon, Valkyrie e os quatro do culto de Carlin caem
    todos aí, e sem atlas o mapa da hunt sai com aviso e o jogo desenha nada.
    Nesse modo só a camada base sem addon entra (`_base_a0_`), que é
    exatamente 4 direções x 9 fases — a mesma contagem e a mesma ordem de um
    outfit de monstro."""
    data = _load_outfit_json(outfit_id)
    if data is None:
        return None
    if "axes" in data and not as_monster:
        return None

    frames = _outfit_frame_list(outfit_id, data)
    if "axes" in data:
        # A chave também é renomeada para `<id>_<n>`: quem lê um atlas de
        # criatura ordena pelo índice no fim da chave, e `137_base_a0_north_0`
        # e `137_base_a0_east_0` colidiriam no índice 0, embaralhando as
        # direções. A ordem da lista já é a do outfit, então numerar em
        # sequência preserva exatamente ela.
        base = [path for key, path in frames if BASE_LAYER_MARKER in key]
        frames = [(f"{outfit_id}_{index}", path) for index, path in enumerate(base)]
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

def monster_outfit_ids() -> Set[int]:
    """Os outfits que algum spawn usa, lidos dos `respawn.json` construídos."""
    ids: Set[int] = set()
    pattern = os.path.join(EXTRACTOR_DIR, "ready-maps", "*", "*", "monsters", "respawn.json")
    for path in glob.glob(pattern):
        with open(path, "r", encoding="utf-8") as handler:
            for spawn in json.load(handler).get("spawns", []):
                outfit_id = spawn.get("outfitId")
                if isinstance(outfit_id, int):
                    ids.add(outfit_id)
    return ids


def monster_appearances() -> List[Dict]:
    """As aparências que precisam de atlas próprio (cor ou addon), sem repetir."""
    seen: Dict[str, Dict] = {}
    pattern = os.path.join(EXTRACTOR_DIR, "ready-maps", "*", "*", "monsters", "respawn.json")
    for path in glob.glob(pattern):
        with open(path, "r", encoding="utf-8") as handler:
            for monster in json.load(handler).get("monsterDefs", {}).values():
                appearance = monster.get("appearance")
                if appearance and outfit_colors.needs_appearance_atlas(appearance):
                    seen[outfit_colors.appearance_key(appearance)] = appearance
    return [seen[key] for key in sorted(seen)]


def main():
    ids = _list_outfit_ids()
    baked = 0
    skipped = []

    for outfit_id in ids:
        if bake_outfit(outfit_id) is not None:
            baked += 1
        else:
            skipped.append(outfit_id)

    humanoids = sorted(set(skipped) & monster_outfit_ids())
    for outfit_id in humanoids:
        if bake_outfit(outfit_id, as_monster=True) is not None:
            baked += 1

    colored = 0
    for appearance in monster_appearances():
        if bake_monster_appearance(appearance) is not None:
            colored += 1

    print(f"[OK] outfits: {baked} atlases gerados em {OUTFITS_ATLAS_DIR}")
    if humanoids:
        print(f"  [OK] {len(humanoids)} de outfit de jogador, usados por monstro: {humanoids}")
    if colored:
        print(f"  [OK] {colored} atlas por aparência (outfit + cores e addons do monstro)")
    remaining = len(skipped) - len(humanoids)
    if remaining:
        print(f"  [skip] {remaining} outfits ignorados (sem JSON, ou de jogador sem monstro que os use)")


if __name__ == "__main__":
    main()
