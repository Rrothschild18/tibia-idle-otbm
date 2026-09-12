import json
import os
import posixpath
import shutil
import struct
import sys
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Set, Tuple

from PIL import Image

import appearance_derivation
import content_export
import map_dirs
import map_v6
from sheet_packer import SheetPacker

# ======================================================
# CONFIG
# ======================================================

TILE_SIZE = 32

if len(sys.argv) < 2:
    print("Uso: python build_phaser_map.py <nome-do-mapa>")
    print("     <nome-do-mapa> deve ter uma pasta correspondente em extractor/maps/")
    sys.exit(1)

MAP_NAME = sys.argv[1]

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
EXTRACTOR_DIR = os.path.dirname(SCRIPTS_DIR)

OTBM_FILE = os.path.join(EXTRACTOR_DIR, "raw-maps", f"{MAP_NAME}.raw.json")

# A hunt map lives two levels deep — maps/<CIDADE>/<pasta>/ — the city is
# always the physical parent folder, never guessed from MAP_NAME (see
# extractor/README.md, "Convenção de pastas"). A full-city OTBM
# (extractor/full-maps/<CIDADE>/) feeds the travel-graph pipeline instead of
# a single hunt spot — same converter, different source tree, one level deep
# (folder = city code itself), and a versioned output dir
# (full-maps/<CIDADE>/map.json) instead of the gitignored
# ready-maps/<CIDADE>/<pasta>/ used for hunt spots. maps/ is tried first so
# an ordinary hunt map name never resolves to full-maps/.
FULL_MAPS_DIR = os.path.join(EXTRACTOR_DIR, "full-maps")
_MAPS_DIR = os.path.join(EXTRACTOR_DIR, "maps")

_hunt_dir = map_dirs.find_two_level_dir(_MAPS_DIR, MAP_NAME)
if _hunt_dir is not None:
    IS_FULL_MAP = False
    SOURCE_MAP_DIR = _hunt_dir
    # Mirrors maps/ 1:1 into ready-maps/ — same relative path, different root.
    _RELATIVE_OUTPUT_PATH = os.path.relpath(_hunt_dir, _MAPS_DIR)
elif os.path.isdir(os.path.join(FULL_MAPS_DIR, MAP_NAME)):
    IS_FULL_MAP = True
    SOURCE_MAP_DIR = os.path.join(FULL_MAPS_DIR, MAP_NAME)
    _RELATIVE_OUTPUT_PATH = MAP_NAME
else:
    raise FileNotFoundError(
        f'Mapa "{MAP_NAME}" não encontrado em nenhuma cidade sob {_MAPS_DIR} nem em {FULL_MAPS_DIR}'
    )

# Marker signs (item 2016) used by the travel-graph tooling to mark POIs use
# a reserved uid range starting at 10001 — see .scratch/travel-graph-and-locations.
# They must never leak into a generated map.json (player-facing or the
# full-city inspection artifact alike). Defined next to the v6 model so both
# emitters read one value.
MARKER_UID_MIN = map_v6.MARKER_UID_MIN

_CANDIDATE_ITEM_SOURCES = [
    os.path.abspath(os.path.join(EXTRACTOR_DIR, "sprites", "items")),
    os.path.abspath(os.path.join(EXTRACTOR_DIR, "sprites", "missiles")),
    os.path.abspath(os.path.join(EXTRACTOR_DIR, "sprites")),
]

ITEMS_SOURCES: List[str] = []
_seen = set()
for candidate in _CANDIDATE_ITEM_SOURCES:
    normalized = os.path.normpath(candidate)
    if normalized in _seen:
        continue
    _seen.add(normalized)
    if os.path.isdir(normalized):
        ITEMS_SOURCES.append(normalized)

if not ITEMS_SOURCES:
    raise FileNotFoundError("Nenhuma pasta de sprites encontrada.")

# Uma árvore só, formato v6. O `ready-maps-v6/` paralelo existia para o
# `ready-maps/` v5 ficar intocado enquanto o front migrava; o front migrou, e
# `map-definition.ts:62-71` lança exceção em qualquer coisa que não seja v6 —
# a árvore v5 era bakeada todo run para ninguém. Ver docs/adr/0006.
#
# Só mapas de hunt. Um mapa de cidade inteira não é renderizado, e desde que o
# travel-graph passou a ler `appearance-flags/<CIDADE>.json` ele não tem
# consumidor de mapa nenhum. Empacotar as ~2000 aparências de uma cidade em
# folhas por footprint também exigiria textura além do que qualquer GPU
# garante (512×7936 no ROOK).
OUTPUT_DIR = os.path.abspath(
    os.path.join(FULL_MAPS_DIR, _RELATIVE_OUTPUT_PATH) if IS_FULL_MAP
    else os.path.join(EXTRACTOR_DIR, "ready-maps", _RELATIVE_OUTPUT_PATH)
)
SHEETS_OUTPUT_DIR = os.path.join(OUTPUT_DIR, "sheets")
MONSTERS_OUTPUT_DIR = os.path.join(OUTPUT_DIR, "monsters")
# Mesmo nome de pasta que hunt_fragment.py grava no `mapUrl` de um hunt — uma
# definição só, porque divergir significa o catálogo apontar para um bundle que
# o front não serve, e o import rejeitar o hunt.
ASSETS_ROOT = content_export.map_bundle_root(MAP_NAME)


def _find_sidecar(directory: str, suffix: str) -> str:
    """First (sorted) filename ending in `suffix` inside `directory`, or ""
    if none — found by suffix, not by assuming the exact basename, since a
    hunt map's folder name (the id) is deliberately allowed to differ from
    the .otbm/xml basenames the map editor originally exported (see
    extractor/README.md)."""
    matches = sorted(name for name in os.listdir(directory) if name.endswith(suffix))
    return os.path.join(directory, matches[0]) if matches else ""


# Monsters
OTSERVBR_MONSTER_XML = os.path.join(EXTRACTOR_DIR, "otservbr-monster.xml")
MONSTER_SPAWN_XML = _find_sidecar(SOURCE_MAP_DIR, "-monster.xml")
OUTFITS_SPRITES_DIR = os.path.join(EXTRACTOR_DIR, "sprites", "outfits")
# Reference file built once by build_monster_loot_index.py from a local Canary
# install (see monster_loot.py) — the real pipeline only ever reads this, never
# the Canary install itself.
MONSTER_LOOT_INDEX_PATH = os.path.join(EXTRACTOR_DIR, "monster-loot.json")

# Outfit atlases are baked once, globally, by bake_outfit_atlas.py — shared
# and cached across every map that uses a given outfit, instead of each map
# copying its own set of per-frame PNGs (see .scratch/outfit-sprite-atlas/).
OUTFITS_ATLAS_DIR = os.path.join(EXTRACTOR_DIR, "atlases", "outfits")
OUTFITS_ATLAS_ASSETS_ROOT = posixpath.join("assets", "outfits")

# ======================================================
# GLOBAL STATE
# ======================================================

ITEM_CACHE: Dict[int, Dict] = {}
SPRITE_DIM_CACHE: Dict[str, Tuple[int, int]] = {}

# ======================================================
# HELPERS
# ======================================================

def ensure_directory(path: str) -> None:
    os.makedirs(path, exist_ok=True)

def _candidate_paths(root: str, identifier: str, filename: str) -> List[str]:
    ident = str(identifier)
    return [
        os.path.join(root, filename),
        os.path.join(root, ident, filename),
        os.path.join(root, "items", filename),
        os.path.join(root, "items", ident, filename),
        os.path.join(root, "missiles", filename),
        os.path.join(root, "missiles", ident, filename),
    ]

def resolve_item_json_path(appearance_id: int) -> Optional[str]:
    filename = f"{appearance_id}.json"
    for root in ITEMS_SOURCES:
        for candidate in _candidate_paths(root, str(appearance_id), filename):
            if os.path.exists(candidate):
                return candidate
    return None

def resolve_sprite_path(sprite_id: str, appearance_id: Optional[int] = None) -> Optional[str]:
    filename = f"{sprite_id}.png"
    for root in ITEMS_SOURCES:
        search_id = str(appearance_id) if appearance_id is not None else sprite_id
        for candidate in _candidate_paths(root, search_id, filename):
            if os.path.exists(candidate):
                return candidate
    return None

def load_item_json(appearance_id: int) -> Optional[Dict]:
    path = resolve_item_json_path(appearance_id)
    if not path:
        return None
    with open(path, "r", encoding="utf-8") as handler:
        return json.load(handler)

def get_png_dimensions(sprite_id: str, sprite_path: Optional[str]) -> Tuple[int, int]:
    if sprite_id in SPRITE_DIM_CACHE:
        return SPRITE_DIM_CACHE[sprite_id]
    width = height = TILE_SIZE
    if sprite_path:
        try:
            with open(sprite_path, "rb") as handler:
                header = handler.read(24)
                if len(header) >= 24 and header[:8] == b"\x89PNG\r\n\x1a\n":
                    width, height = struct.unpack(">II", header[16:24])
        except OSError:
            pass
    SPRITE_DIM_CACHE[sprite_id] = (width, height)
    return width, height

def _normalize_sprite_ids(raw_ids: Optional[List]) -> List[str]:
    if raw_ids is None:
        return []
    if isinstance(raw_ids, (int, str)):
        raw_ids = [raw_ids]
    normalized: List[str] = []
    for entry in raw_ids:
        sid = str(entry)
        if sid not in normalized:
            normalized.append(sid)
    return normalized

def _extract_sprite_payload(appearance_id: int, data: Optional[Dict]) -> Tuple[List[str], Dict, Optional[Dict]]:
    if not data:
        return [str(appearance_id)], {}, None
    sprite_ids: List[str] = []
    sprite_info: Dict = {}
    animation: Optional[Dict] = None

    frame_groups = data.get("frame_group") or data.get("frameGroups")
    if isinstance(frame_groups, list) and frame_groups:
        sprite_info = frame_groups[0].get("sprite_info") or frame_groups[0].get("spriteInfo") or {}
        sprite_ids = _normalize_sprite_ids(
            sprite_info.get("sprite_id") or sprite_info.get("spriteId")
        )
        animation = sprite_info.get("animation")
    if not sprite_ids:
        sprite_info = data.get("sprite_info") or data.get("spriteInfo") or sprite_info
        sprite_ids = _normalize_sprite_ids(
            data.get("sprite_id") or data.get("spriteId") or sprite_info.get("sprite_id")
        )
        animation = animation or data.get("animation") or sprite_info.get("animation")
    if not sprite_ids:
        sprite_ids = [str(appearance_id)]
    return sprite_ids, sprite_info, animation

def _strip_sprite_ids(payload):
    if payload is None:
        return None
    if isinstance(payload, dict):
        return {
            key: _strip_sprite_ids(value)
            for key, value in payload.items()
            if key not in {"sprite_id", "spriteId"}
        }
    if isinstance(payload, list):
        return [_strip_sprite_ids(item) for item in payload]
    return payload

def _frame_durations_ms(phase_list) -> List[int]:
    """Per-phase duration in ms from a CIP `spritePhase` list.

    Each phase carries `durationMin`/`durationMax` (equal unless the client is
    meant to pick a random duration in the range); we take the average, which
    is what the outfit path (`_animation_timing`) already does. Returns an empty
    list when the data is absent or malformed, so the caller falls back to a
    scalar rather than emitting garbage.
    """
    if not isinstance(phase_list, list) or not phase_list:
        return []
    out: List[int] = []
    for phase in phase_list:
        if not isinstance(phase, dict):
            return []
        dmin = phase.get("durationMin")
        dmax = phase.get("durationMax", dmin)
        if dmin is None and dmax is None:
            return []
        dmin = dmin if dmin is not None else dmax
        dmax = dmax if dmax is not None else dmin
        out.append(int(round((dmin + dmax) / 2)))
    return out

def analyze_item(appearance_id: int) -> Dict:
    if appearance_id in ITEM_CACHE:
        return ITEM_CACHE[appearance_id]

    metadata = load_item_json(appearance_id)
    metadata_payload = _strip_sprite_ids(metadata) if metadata else None
    sprite_ids, sprite_info, animation_block = _extract_sprite_payload(appearance_id, metadata)

    # Extract flags from metadata
    flags = metadata.get("flags", {}) if metadata else {}
    has_fullbank = flags.get("fullbank", False)
    has_unmove = flags.get("unmove", False)
    has_unpass = flags.get("unpass", False)
    has_unsight = flags.get("unsight", False)
    has_automap = flags.get("automap") is not None
    has_bank = flags.get("bank") is not None
    has_clip = flags.get("clip", False)
    has_bottom = flags.get("bottom", False)
    has_top = flags.get("top", False)
    has_hang = flags.get("hang", False)
    has_usable = flags.get("usable", False)
    has_forceuse = flags.get("forceuse", False)

    # Positioning, not classification: `shift` moves this sprite's own pixels
    # and does not accumulate; `elevation` (the appearances' `height` flag)
    # offsets every item drawn AFTER this one on the same tile, and does. Both
    # are emitted per appearance by map.json v6 — see CONTEXT.md and
    # .scratch/modelo-render-rme/issues/06-emitir-shift-e-elevacao.md. They stay
    # out of the `flags` dict below because v5 serializes that wholesale.
    shift_raw = flags.get("shift")
    shift = (
        {"x": shift_raw.get("x", 0), "y": shift_raw.get("y", 0)}
        if isinstance(shift_raw, dict) else None
    )
    height_raw = flags.get("height")
    elevation = height_raw.get("elevation", 0) if isinstance(height_raw, dict) else 0

    # Extract sprite info for bounding calculations
    pattern_width = sprite_info.get("patternWidth", 1)
    pattern_height = sprite_info.get("patternHeight", 1)
    pattern_depth = sprite_info.get("patternDepth", 1)

    # Calculate bounding square (width * height * 32 pixels per tile)
    bounding_square = pattern_width * pattern_height * TILE_SIZE
    has_bounding_box_per_direction = pattern_depth >= 1

    # As duas flags derivadas (isRoof, isFloorTransition) e o hookDirection
    # vêm de `appearance_derivation`, a mesma definição que
    # `build_appearance_flags` usa para montar a tabela do travel-graph.
    # Duas cópias divergiriam em silêncio — foi exatamente o que aconteceu
    # quando a tabela nasceu dumpando as flags cruas: `isFloorTransition` saiu
    # zerada, o BFS perdeu as escadas e uma location sumiu do grafo sem erro.
    _derived = appearance_derivation.derived_flags(flags, sprite_info)
    is_roof = _derived["isRoof"]
    is_floor_transition = _derived["isFloorTransition"]
    hook_direction = _derived["hookDirection"]

    info = {
        "appearanceId": appearance_id,
        "type": "unknown" if metadata is None else "static",
        "hasSprite": False,
        "animated": False,
        "random": False,
        "animation": None,
        "metadataFound": metadata_payload,
        "flags": {
            "fullbank": has_fullbank,
            "unmove": has_unmove,
            "unpass": has_unpass,
            "unsight": has_unsight,
            "automap": has_automap,
            "bank": has_bank,
            "clip": has_clip,
            "bottom": has_bottom,
            "top": has_top,
            "hang": has_hang,
            "usable": has_usable,
            "forceuse": has_forceuse,
            "isRoof": is_roof,
            "isFloorTransition": is_floor_transition,
            "hookDirection": hook_direction,
        },
        "spriteInfo": {
            "patternWidth": pattern_width,
            "patternHeight": pattern_height,
            "patternDepth": pattern_depth,
            "boundingSquare": bounding_square
        },
        "shift": shift,
        "elevation": elevation,
        "sprites": [],
        "maxSpriteHeight": TILE_SIZE,
        "issues": []
    }

    sprite_records = []
    available_count = 0

    for sprite_id in sprite_ids:
        sprite_path = resolve_sprite_path(sprite_id, appearance_id)
        available = sprite_path is not None
        if not available:
            info["issues"].append(f"missing_sprite:{sprite_id}")
        width, height = get_png_dimensions(sprite_id, sprite_path)
        sprite_records.append({
            "spriteId": sprite_id,
            # `sourcePath` é o único que sobrevive ao v5: `map_v6.py:95` o usa
            # para alimentar o packer. `destPath`/`destAbsPath` endereçavam a
            # cópia por mapa de PNGs individuais, que as folhas aposentaram.
            "sourcePath": sprite_path,
            "width": width,
            "height": height,
            "available": available
        })
        if available:
            available_count += 1

    if metadata is None:
        info["issues"].append("metadata_missing")

    info["sprites"] = sprite_records
    info["hasSprite"] = available_count > 0
    info["maxSpriteHeight"] = max((record["height"] for record in sprite_records), default=TILE_SIZE)

    # An appearance's sprite list is `phases x patterns`, phase-major: the
    # client indexes it as `phase * pattern_count + pattern` (OTClient's
    # `ThingType::getSpriteIndex`), where the pattern comes from the tile's own
    # position. So the phase count is the list divided by the pattern count —
    # NOT its length. Reading the whole list as phases is what made a 3-variant
    # shore border (id 4633: 3x1x1 patterns, 14 phases, 42 sprites) animate
    # through all three shapes instead of animating the one belonging to its
    # column. See ADR 0014 in `tibia-idle`.
    pattern_count = pattern_width * pattern_height * pattern_depth
    phase_count = len(sprite_ids) // pattern_count if pattern_count else len(sprite_ids)
    animation_valid = False
    if animation_block:
        # CIP stores the phase list under `spritePhase`, each phase carrying a
        # `durationMin`/`durationMax` in ms. The old code read `phases` /
        # `frame_duration` — keys that don't exist in this metadata — so EVERY
        # animated appearance fell to the 500ms default and rendered at a flat
        # 2fps regardless of its real cadence (water, fire, teleporters, and
        # effects all move at different speeds). The outfit path
        # (`_animation_timing`) already reads `spritePhase`; this brings the map
        # path in line with it.
        phase_list = animation_block.get("spritePhase")
        if not isinstance(phase_list, list):
            legacy = animation_block.get("phases")
            phase_list = legacy if isinstance(legacy, list) else None
        if isinstance(phase_list, list):
            phase_count = len(phase_list)
        elif isinstance(animation_block.get("phases"), int):
            phase_count = animation_block["phases"]
        sprite_ready = (
            available_count == len(sprite_records)
            and phase_count * pattern_count == len(sprite_records)
        )
        if sprite_ready:
            frame_durations = _frame_durations_ms(phase_list)
            if frame_durations:
                avg_ms = sum(frame_durations) / len(frame_durations)
            else:
                scalar = (
                    animation_block.get("frame_duration")
                    or animation_block.get("frameDuration")
                    or 500
                )
                frame_durations = [int(scalar)] * phase_count
                avg_ms = scalar
            loop_type = str(animation_block.get("loopType", ""))
            loop = ("INFINITE" in loop_type) if loop_type else bool(animation_block.get("loop", True))
            animation_valid = True
            info["animated"] = True
            info["type"] = "animated"
            info["animation"] = {
                "appearanceId": appearance_id,
                # Real per-frame cadence, one entry per phase and aligned with a
                # variant's phase-major strided gids (frame i of a variant uses
                # frameDurations[i]). This is what the renderer honours.
                "frameDurations": frame_durations,
                # Scalar average kept as a coarse fallback / back-compat.
                "frameDurationMs": int(round(avg_ms)),
                "frameRate": max(1, round(1000 / max(avg_ms, 1), 2)),
                "loop": loop,
                # CIP's `synchronized`: True => every tile of this appearance
                # animates on one shared clock (water, most decor); False =>
                # each tile free-runs. The renderer aligns phase to a global
                # clock when True (see `map-loader` playInStep) so a streamed
                # map doesn't show the same water at different frames.
                "synchronized": bool(animation_block.get("synchronized", True)),
                # CIP names this `default_start_phase` (camelCase `defaultStartPhase`
                # in this protobuf-JSON); the old `default_phase` matched neither
                # key, so every startFrame silently defaulted to 0.
                "startFrame": animation_block.get("defaultStartPhase")
                or animation_block.get("default_start_phase")
                or animation_block.get("default_phase")
                or 0,
            }
        else:
            info["issues"].append("invalid_animation")

    if not animation_valid:
        if len(sprite_records) > 1:
            info["random"] = True
            info["type"] = "random"
        elif metadata_payload is not None:
            info["type"] = "static"

    ITEM_CACHE[appearance_id] = info

    if info["issues"]:
        print(f"[WARN] appearance {appearance_id}: {', '.join(info['issues'])}")

    return info

# ======================================================
# LAYER CLASSIFICATION
# ======================================================







def _render_sheet(packer: SheetPacker, sheet_key: str, frame_sources: Dict[int, str]) -> Image.Image:
    """Composites a v4 grid sheet: one appearance frame per gid cell.

    `frame_sources`: {gid: sourcePath}. A gid with no entry (sprite
    unavailable) stays a transparent cell rather than failing the build.
    """
    dims = packer.sheet_dims(sheet_key)
    canvas = Image.new("RGBA", (dims["pixelWidth"], dims["pixelHeight"]), (0, 0, 0, 0))
    for gid, source_path in frame_sources.items():
        if not source_path:
            continue
        rect = packer.gid_to_rect(sheet_key, gid)
        with Image.open(source_path) as sprite_img:
            canvas.paste(sprite_img.convert("RGBA"), (rect["x"], rect["y"]))
    return canvas








# ======================================================
# MAP BUILDER
# ======================================================


# ======================================================
# MAIN
# ======================================================





# ======================================================
# MONSTERS
# ======================================================

_DIRECTIONS = ["south", "east", "north", "west"]


def _load_monster_lookup() -> Dict[str, int]:
    """Parse otservbr-monster.xml → {lowercase_name: looktype}."""
    if not os.path.exists(OTSERVBR_MONSTER_XML):
        print(f"[WARN] {OTSERVBR_MONSTER_XML} não encontrado")
        return {}
    tree = ET.parse(OTSERVBR_MONSTER_XML)
    lookup: Dict[str, int] = {}
    for monster in tree.getroot().iter("monster"):
        name = monster.get("name")
        looktype = monster.get("looktype")
        if name and looktype:
            lookup[name.lower()] = int(looktype)
    return lookup


def _load_monster_loot_index() -> Dict[str, Dict]:
    """Parse monster-loot.json -> {monster name: {"loot": [...], "issues": [...], "corpse": {...}, "race": "blood"}}."""
    if not os.path.exists(MONSTER_LOOT_INDEX_PATH):
        print(f"[WARN] {MONSTER_LOOT_INDEX_PATH} não encontrado — rode build_monster_loot_index.py")
        return {}
    with open(MONSTER_LOOT_INDEX_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _parse_spawn_xml() -> List[Dict]:
    """Parse maps/{MAP_NAME}/monster.xml → list of spawn dicts."""
    if not os.path.exists(MONSTER_SPAWN_XML):
        print(f"[WARN] {MONSTER_SPAWN_XML} não encontrado")
        return []
    tree = ET.parse(MONSTER_SPAWN_XML)
    spawns: List[Dict] = []
    for area in tree.getroot().iter("monster"):
        cx = area.get("centerx")
        if cx is None:
            continue  # skip inner <monster> tags
        centerx = int(cx)
        centery = int(area.get("centery", 0))
        centerz = int(area.get("centerz", 7))
        radius = int(area.get("radius", 1))
        for mob in area:
            name = mob.get("name")
            if not name:
                continue
            spawns.append({
                "name": name,
                "worldX": centerx + int(mob.get("x", 0)),
                "worldY": centery + int(mob.get("y", 0)),
                "worldZ": int(mob.get("z", centerz)),
                "radius": radius,
                "spawntime": int(mob.get("spawntime", 60)),
            })
    return spawns


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


def _animation_timing(sprite_info: Dict) -> Tuple[float, str]:
    """(frameRate, loopType) derived from a frame group's animation block,
    falling back to a sane default (6 fps, infinite) when absent."""
    frame_rate = 6.0
    loop_type = "infinite"
    anim = sprite_info.get("animation")
    if anim:
        phases = anim.get("spritePhase", [])
        if phases:
            avg_ms = sum(
                (p.get("durationMin", 300) + p.get("durationMax", 300)) / 2
                for p in phases
            ) / len(phases)
            frame_rate = round(1000 / max(avg_ms, 1), 2)
        loop_type = "infinite" if "INFINITE" in anim.get("loopType", "") else "once"
    return frame_rate, loop_type


def _build_outfit_anims(outfit_id: int, data: Dict) -> Dict:
    """Build idle/moving animation data per direction from outfit JSON.

    Layout (see OUTFIT_SPRITES_DOCUMENTATION.md):
      - patternWidth directions in order: south, east, north, west
      - idle:   usually 1 static sprite per direction, BUT some creature
        outfits (Wasp, Ghost, Fire Elemental — see outfit_has_addons_or_mounts
        in extract_sprites.py) loop an animation while idle too (wings,
        flicker, flame), so their idle frame group carries multiple frames
        per direction just like moving does.
      - moving: N frames per direction  (indices 4 onward, each dir*N)

    `idle` is a dict per direction whose value is either a plain sprite-key
    string (static outfits — the common case) or, when the idle frame group
    itself has more than one frame per direction, an object shaped exactly
    like `moving`'s: `{frames, frameRate, loopType}`. See PHASER_MONSTERS.md
    for how the Phaser side should tell the two apart.
    """
    result: Dict = {}
    frame_groups = data.get("frameGroups")

    if not frame_groups:
        # Single frame group (no idle/moving split)
        sprite_ids: List[str] = data.get("spriteId", [])
        result["idle"] = {"south": sprite_ids[0] if sprite_ids else str(outfit_id)}
        result["moving"] = {"south": {"frames": sprite_ids, "frameRate": 6, "loopType": "infinite"}}
        return result

    for fg in frame_groups:
        fg_type = fg.get("frameGroup")  # "idle" or "moving"
        sprite_ids = fg.get("spriteId", [])
        sprite_info = fg.get("spriteInfo", {})
        n_dirs = min(sprite_info.get("patternWidth", 1), len(_DIRECTIONS))
        total = len(sprite_ids)
        frames_per_dir = total // n_dirs if n_dirs else total

        dir_sprites = {
            _DIRECTIONS[d]: sprite_ids[d * frames_per_dir:(d + 1) * frames_per_dir]
            for d in range(n_dirs)
        }

        if fg_type == "idle":
            idle_animates = frames_per_dir > 1
            if idle_animates:
                frame_rate, loop_type = _animation_timing(sprite_info)
                result["idle"] = {
                    d: {"frames": frames, "frameRate": frame_rate, "loopType": loop_type}
                    for d, frames in dir_sprites.items()
                }
            else:
                result["idle"] = {
                    d: frames[0] if frames else str(outfit_id)
                    for d, frames in dir_sprites.items()
                }

        elif fg_type == "moving":
            frame_rate, loop_type = _animation_timing(sprite_info)
            result["moving"] = {
                d: {"frames": frames, "frameRate": frame_rate, "loopType": loop_type}
                for d, frames in dir_sprites.items()
            }

    return result


def _outfit_atlas_ref(outfit_id: int) -> Optional[Dict]:
    """Reference to the shared, globally-baked atlas for this outfit.

    Atlases are baked once by bake_outfit_atlas.py, independent of any
    specific map. Returns None (with a warning) if that step hasn't run yet
    for this outfit — the map build doesn't need to fail on it.
    """
    png_path = os.path.join(OUTFITS_ATLAS_DIR, f"{outfit_id}.png")
    json_path = os.path.join(OUTFITS_ATLAS_DIR, f"{outfit_id}.json")
    if not (os.path.exists(png_path) and os.path.exists(json_path)):
        print(f"[WARN] Atlas do outfit {outfit_id} não encontrado em {OUTFITS_ATLAS_DIR} "
              f"— rode bake_outfit_atlas.py")
        return None

    return {
        "image": posixpath.join(OUTFITS_ATLAS_ASSETS_ROOT, f"{outfit_id}.png"),
        "json": posixpath.join(OUTFITS_ATLAS_ASSETS_ROOT, f"{outfit_id}.json"),
    }


def build_monster_respawn(map_bounds: Dict) -> Optional[Dict]:
    """Generate respawn.json for monsters on the current map.

    Returns the dict (also writes it to MONSTERS_OUTPUT_DIR/respawn.json).
    Returns None if no spawn XML is found or no spawns exist.
    """
    monster_lookup = _load_monster_lookup()
    loot_index = _load_monster_loot_index()
    spawns_raw = _parse_spawn_xml()

    if not spawns_raw:
        print("[INFO] Nenhum spawn de monstros encontrado.")
        return None

    min_x = map_bounds.get("minX", 0)
    min_y = map_bounds.get("minY", 0)

    monster_defs: Dict[str, Dict] = {}
    spawns_out: List[Dict] = []
    missing_names: set = set()
    missing_loot_names: set = set()

    for spawn in spawns_raw:
        name = spawn["name"]
        name_key = name.lower()
        outfit_id = monster_lookup.get(name_key)

        if outfit_id is None:
            if name_key not in missing_names:
                print(f"[WARN] Outfit ID não encontrado para monstro: '{name}'")
                missing_names.add(name_key)
            outfit_id = 0

        outfit_id_str = str(outfit_id)

        # Build monster def once per outfit
        if outfit_id_str not in monster_defs and outfit_id:
            outfit_data = _load_outfit_json(outfit_id)
            if outfit_data is None:
                print(f"[WARN] JSON do outfit {outfit_id} ({name}) não encontrado em sprites/outfits/")

            anims = _build_outfit_anims(outfit_id, outfit_data) if outfit_data else {}

            loot_entry = loot_index.get(name)
            if loot_entry is None and name not in missing_loot_names:
                print(f"[WARN] Loot não encontrado para monstro: '{name}' — rode build_monster_loot_index.py")
                missing_loot_names.add(name)

            # corpse só existe pra monstro que deixa corpo, race pra quem
            # declara uma — sem elas as chaves somem do def, igual ao
            # monster-loot.json
            corpse = loot_entry.get("corpse") if loot_entry else None
            race = loot_entry.get("race") if loot_entry else None

            monster_defs[outfit_id_str] = {
                "name": name,
                "outfitId": outfit_id,
                "atlas": _outfit_atlas_ref(outfit_id),
                "loot": loot_entry["loot"] if loot_entry else [],
                **({"corpse": corpse} if corpse else {}),
                **({"race": race} if race else {}),
                **anims,
            }

        spawns_out.append({
            "name": name,
            "outfitId": outfit_id,
            "tileX": spawn["worldX"] - min_x,
            "tileY": spawn["worldY"] - min_y,
            "worldX": spawn["worldX"],
            "worldY": spawn["worldY"],
            "worldZ": spawn["worldZ"],
            "radius": spawn["radius"],
            "spawntime": spawn["spawntime"],
        })

    respawn = {
        "mapBoundsRef": map_bounds,
        "monsterDefs": monster_defs,
        "spawns": spawns_out,
    }

    ensure_directory(MONSTERS_OUTPUT_DIR)
    out_path = os.path.join(MONSTERS_OUTPUT_DIR, "respawn.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(respawn, f, indent=2, ensure_ascii=False)

    print(f"[OK] respawn.json gerado em {out_path}")
    print(f"     {len(monster_defs)} defs de monstros | {len(spawns_out)} spawns")
    return respawn


# ======================================================
# MAP.JSON V6
# ======================================================

def write_map_v6(dump: Dict) -> Dict:
    """Constrói e escreve a árvore do mapa, devolvendo o documento.

    Um `SheetPacker` por mapa: o v6 agrupa folhas por footprint.

    O `respawn.json` sai **daqui**, do `bounds` que o próprio documento calcula
    (`map_v6.py`). Antes ele vinha do documento v5, o que fazia o respawn
    depender de um formato que ninguém mais consome.
    """
    packer = SheetPacker()
    # `MAP_NAME` up to its first underscore is the hunt's own hand-chosen id
    # (see `hunt_fragment.map_id_from_folder`) — what a start-marker sign's
    # text must equal for `build_map_v6` to trust it over the defaultZ
    # heuristic.
    map_id = MAP_NAME.split("_", 1)[0]
    document, frame_sources = map_v6.build_map_v6(
        dump, analyze_item, packer, ASSETS_ROOT, map_id=map_id
    )

    if packer.sheets:
        ensure_directory(SHEETS_OUTPUT_DIR)
    for sheet_key in sorted(packer.sheets):
        image = _render_sheet(packer, sheet_key, frame_sources.get(sheet_key, {}))
        image.save(os.path.join(SHEETS_OUTPUT_DIR, f"{sheet_key}.png"))

    oversized = [key for key in sorted(packer.sheets) if packer.exceeds_safe_texture_size(key)]
    if oversized:
        print(f"[WARN] folha acima do limite seguro de textura: {', '.join(oversized)}")

    ensure_directory(OUTPUT_DIR)
    output_path = os.path.join(OUTPUT_DIR, "map.json")
    with open(output_path, "w", encoding="utf-8") as output_file:
        json.dump(document, output_file, indent=2)

    respawn = build_monster_respawn(document["bounds"])
    if respawn is not None:
        ensure_directory(MONSTERS_OUTPUT_DIR)
        with open(os.path.join(MONSTERS_OUTPUT_DIR, "respawn.json"), "w",
                  encoding="utf-8") as monsters_file:
            json.dump(respawn, monsters_file, indent=2, ensure_ascii=False)

    tile_count = sum(len(floor["tiles"]) for floor in document["floors"].values())
    print(f"[OK] Mapa gerado em {output_path}")
    print(f"     {tile_count} tiles | {len(document['appearances'])} aparências "
          f"| {len(document['sheets'])} folhas")
    return document


# ======================================================
# MAIN
# ======================================================

if __name__ == "__main__":
    with open(OTBM_FILE, "r", encoding="utf-8") as file_handler:
        dump = json.load(file_handler)

    # O mapa de cidade inteira não é renderizado e não tem consumidor de mapa:
    # o travel-graph lê `appearance-flags/<CIDADE>.json`, gerado por
    # build_appearance_flags.py. Dele sai só o respawn.json, que sempre foi a
    # outra saída deste caminho.
    if IS_FULL_MAP:
        respawn = build_monster_respawn(map_v6.map_bounds(dump))
        if respawn is not None:
            ensure_directory(MONSTERS_OUTPUT_DIR)
            with open(os.path.join(MONSTERS_OUTPUT_DIR, "respawn.json"), "w",
                      encoding="utf-8") as monsters_file:
                json.dump(respawn, monsters_file, indent=2, ensure_ascii=False)
        print("[INFO] Mapa de cidade inteira: nenhum map.json é gerado.")
        print("       As flags que o travel-graph consome vêm de "
              f"appearance-flags/{MAP_NAME}.json — regere com build_appearance_flags.py.")
    else:
        write_map_v6(dump)
