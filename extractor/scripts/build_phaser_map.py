import json
import os
import posixpath
import shutil
import struct
import sys
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Set, Tuple

from PIL import Image

import content_export
import item_classifier
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

# Pasta local de saída. Mapas de hunt vão para extractor/ready-maps/ (gerado,
# gitignored). Mapas de cidade inteira (full-maps/) escrevem de volta no
# próprio full-maps/<nome>/ — esse map.json É versionado no Git (artefato de
# inspeção/debug pro travel-graph), diferente do ready-maps/ dos hunts. O
# valor de ASSETS_ROOT abaixo é independente disso — é o path que o jogo usa
# em tempo de execução para localizar os assets copiados, e mantém o sufixo
# "-sprites" para não quebrar integrações existentes que já leem esse campo
# do JSON.
OUTPUT_DIR = os.path.abspath(
    os.path.join(FULL_MAPS_DIR, _RELATIVE_OUTPUT_PATH) if IS_FULL_MAP
    else os.path.join(EXTRACTOR_DIR, "ready-maps", _RELATIVE_OUTPUT_PATH)
)
SPRITES_OUTPUT_DIR = os.path.join(OUTPUT_DIR, "sprites")
SHEETS_OUTPUT_DIR = os.path.join(OUTPUT_DIR, "sheets")
ASSETS_ROOT = posixpath.join("assets", f"{MAP_NAME}-sprites")

# map.json v6 is written to a parallel tree — `ready-maps-v6/`, same relative
# path under a different root — so the directory the game consumes today stays
# byte-identical while the Phaser side migrates. The two formats also get
# distinct asset roots, so both can sit in the front's assets/ at once.
# See docs/adr/0006 and .scratch/modelo-render-rme/spec.md.
#
# Hunt spots only. A full-city map.json is never rendered — it exists so
# build_travel_fragment.py can read its objectDefs — and packing a whole city's
# ~2000 appearances into footprint sheets would need textures past what any GPU
# guarantees (512×7936 for ROOK). The v5 tree keeps serving that pipeline.
V6_OUTPUT_DIR = os.path.abspath(
    os.path.join(EXTRACTOR_DIR, "ready-maps-v6", _RELATIVE_OUTPUT_PATH)
)
V6_SHEETS_OUTPUT_DIR = os.path.join(V6_OUTPUT_DIR, "sheets")
V6_MONSTERS_OUTPUT_DIR = os.path.join(V6_OUTPUT_DIR, "monsters")
# Same folder name hunt_fragment.py writes into a hunt's `mapUrl` — one
# definition, since a mismatch means the catalog points at a bundle the front
# doesn't serve, and the import rejects the hunt.
V6_ASSETS_ROOT = content_export.map_bundle_root(MAP_NAME)


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
MONSTERS_OUTPUT_DIR = os.path.join(OUTPUT_DIR, "monsters")
# Reference file built once by build_monster_loot_index.py from a local Canary
# install (see monster_loot.py) — the real pipeline only ever reads this, never
# the Canary install itself.
MONSTER_LOOT_INDEX_PATH = os.path.join(EXTRACTOR_DIR, "monster-loot.json")

# Outfit atlases are baked once, globally, by bake_outfit_atlas.py — shared
# and cached across every map that uses a given outfit, instead of each map
# copying its own set of per-frame PNGs (see .scratch/outfit-sprite-atlas/).
OUTFITS_ATLAS_DIR = os.path.join(EXTRACTOR_DIR, "atlases", "outfits")
OUTFITS_ATLAS_ASSETS_ROOT = posixpath.join("assets", "outfits")

os.makedirs(SPRITES_OUTPUT_DIR, exist_ok=True)

# ======================================================
# GLOBAL STATE
# ======================================================

ITEM_CACHE: Dict[int, Dict] = {}
SPRITE_DIM_CACHE: Dict[str, Tuple[int, int]] = {}
COPIED_SPRITES = set()

# map.json v4: objectDefs sprites are packed into grid sheets instead of
# copied as individual PNGs — see .scratch/map-sprite-sheets-v4/spec.md.
SHEET_PACKER = SheetPacker()
SHEET_FRAME_SOURCES: Dict[str, Dict[int, str]] = {}

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

def build_asset_path(appearance_id: int, sprite_id: str) -> str:
    return posixpath.join(ASSETS_ROOT, "sprites", str(appearance_id), f"{sprite_id}.png")

def ensure_sprite_assets(analysis: Dict) -> None:
    for sprite in analysis.get("sprites", []):
        if not sprite["available"]:
            continue
        key = (analysis["appearanceId"], sprite["spriteId"])
        if key in COPIED_SPRITES:
            continue
        ensure_directory(os.path.dirname(sprite["destAbsPath"]))
        shutil.copy2(sprite["sourcePath"], sprite["destAbsPath"])
        COPIED_SPRITES.add(key)

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

    # Extract hook direction for wall orientation
    hook_raw = flags.get("hook", {})
    if isinstance(hook_raw, dict):
        hook_direction = hook_raw.get("direction", None)
    else:
        hook_direction = None

    # Extract sprite info for bounding calculations
    pattern_width = sprite_info.get("patternWidth", 1)
    pattern_height = sprite_info.get("patternHeight", 1)
    pattern_depth = sprite_info.get("patternDepth", 1)

    # Calculate bounding square (width * height * 32 pixels per tile)
    bounding_square = pattern_width * pattern_height * TILE_SIZE
    has_bounding_box_per_direction = pattern_depth >= 1

    # Roof items must have:
    # - Required flags: unpass, unmove, unsight, automap, bank
    # - Optional flags: fullbank (can be present or not)
    # - boundingSquare >= 64 (pattern area >= 2 tiles)
    # - boundingBoxPerDirection (patternDepth >= 1)
    is_roof = (
        has_unmove and
        has_unpass and
        has_unsight and
        has_automap and
        has_bank and
        bounding_square >= 64 and
        has_bounding_box_per_direction
    )

    # Floor-transition tiles (stairs/holes) have no dedicated OTBM flag —
    # this is the heuristic combo observed on every known stairs/hole
    # appearance ID across the current map set (386, 421, 1948, 12202; see
    # ADR 0002). `bank` is deliberately NOT required: item 1948 (the actual
    # staircase in skeletons-rookguard) lacks it, and across every item
    # placed in the 8 existing maps, no non-transition item shares this
    # exact 4-flag combo — so dropping `bank` adds no false positives.
    is_floor_transition = (
        has_usable and
        has_forceuse and
        has_unmove and
        has_automap
    )

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
            "sourcePath": sprite_path,
            "destPath": build_asset_path(appearance_id, sprite_id),
            "destAbsPath": os.path.join(SPRITES_OUTPUT_DIR, str(appearance_id), f"{sprite_id}.png"),
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
                "startFrame": animation_block.get("default_phase", 0),
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

def _is_wall_auto(analysis: Dict) -> bool:
    """Auto-detect wall items by their metadata flags.

    A wall has ALL of: bottom + unpass + unmove + unsight + automap.
    This matches Tibia's wall definition (stone/brick/wood walls).
    Items with 'top' flag are NOT walls (they are ceilings/overhangs).
    """
    flags = analysis.get("flags", {})
    return (
        flags.get("bottom", False) and
        flags.get("unpass", False) and
        flags.get("unmove", False) and
        flags.get("unsight", False) and
        flags.get("automap", False) and
        not flags.get("top", False) and
        not flags.get("isRoof", False)
    )


def _get_wall_orientation(analysis: Dict) -> str:
    """Determine wall orientation from hook direction.

    Returns:
        "east"    – HOOK_TYPE_EAST  → vertical wall (west edge of room)
        "south"   – HOOK_TYPE_SOUTH → horizontal wall (north edge of room)
        "corner"  – no hook → corner piece / pillar
    """
    hook = analysis.get("flags", {}).get("hookDirection")
    if hook == "HOOK_TYPE_EAST":
        return "east"
    elif hook == "HOOK_TYPE_SOUTH":
        return "south"
    return "corner"


def classify_layer(analysis: Dict) -> str:
    """
    Classifies an item into a rendering layer.

    Decision tree (evaluated in order):
        1. item_classifier manual      -> forced category (roof, border, walls_east, walls_south, walls — manual only)
        2. auto-detect walls           -> walls_east / walls_south / walls_south (corner)
        3. top flag                    -> "top"
        4. bottom flag                 -> "bottom"
        5. fallback                    -> "object"

    Wall sub-layers:
        - "walls_east"  → vertical walls (HOOK_TYPE_EAST) — high depth, renders OVER player
        - "walls_south" → horizontal walls + corners (HOOK_TYPE_SOUTH / no hook) — low depth, renders BEHIND player
    """
    appearance_id = analysis.get("appearanceId", 0)

    # Rule 0: Manual classification (item_classifier.py) — overrides everything
    manual = item_classifier.classify(appearance_id)
    if manual is not None:
        # Manual "walls" without sub-type: resolve via hook direction
        if manual == "walls":
            orientation = _get_wall_orientation(analysis)
            if orientation == "east":
                return "walls_east"
            return "walls_south"  # south + corner → same layer
        return manual

    # Rule 1: Auto-detect walls by flags
    if _is_wall_auto(analysis):
        orientation = _get_wall_orientation(analysis)
        if orientation == "east":
            return "walls_east"
        return "walls_south"

    flags = analysis.get("flags", {})

    has_top = flags.get("top", False)
    has_bottom = flags.get("bottom", False)

    # Rule 2: Explicit top/ceiling flag
    if has_top:
        return "top"

    # Rule 3: Bottom decorations (above ground, below creatures)
    if has_bottom:
        return "bottom"

    # Rule 4: Everything else
    return "object"


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


def _is_roof_tile(analysis: Dict) -> bool:
    """Determines if a tileid should be treated as roof instead of ground.

    A tileid is reclassified as roof when:
      - It has all three blocking flags: unpass + unmove + unsight
      - Its sprite occupies more than 1x1 tile (patternWidth > 1 or patternHeight > 1)

    Tiles that are 1x1 (like void/black ID 101) stay in the ground tilelayer
    even if they have blocking flags, since they render correctly at 32x32.
    """
    flags = analysis.get("flags", {})
    sprite_info = analysis.get("spriteInfo", {})
    has_unpass = flags.get("unpass", False)
    has_unmove = flags.get("unmove", False)
    has_unsight = flags.get("unsight", False)
    pw = sprite_info.get("patternWidth", 1)
    ph = sprite_info.get("patternHeight", 1)
    is_multitile = pw > 1 or ph > 1
    return has_unpass and has_unmove and has_unsight and is_multitile


def _make_object_entry(analysis: Dict, appearance_id: int,
                       stack_index: int) -> List:
    """Creates a compact [appearanceId, stackIndex] entry.

    All static properties (type, layerClass, spriteIds, flags, etc.)
    are stored once in the top-level ``objectDefs`` dictionary keyed
    by appearanceId. The renderer resolves them at load time.

    worldX / worldY are derived from the parent tile's tileX / tileY:
        worldX = (tileX + 1) * tilewidth
        worldY = (tileY + 1) * tileheight
    """
    return [appearance_id, stack_index]


def _build_object_defs(dynamic_ids: Set[int]) -> Dict[str, Dict]:
    """Builds the ``objectDefs`` lookup from the global ITEM_CACHE.

    Each entry is keyed by the string appearanceId and contains every
    property that is the *same* for all placements of that appearance.
    The renderer only needs to join objectDefs[id] with the per-tile
    position to fully reconstruct the old verbose entry.

    An appearanceId that never shows up in ``dynamic_ids`` (i.e. it was only
    ever seen as a ground ``tileid``, never placed via an objectgroup) gets
    no sprite reference: nothing ever looks up an objectDefs entry for a
    ground tile (rendering goes through ``tilesets`` instead), so packing it
    into a v4 sheet would just be wasted space.

    Appearances that ARE placed dynamically get ``sheet`` + ``gids``
    (map.json v4 — see .scratch/map-sprite-sheets-v4/spec.md): their frames
    are packed into a shared grid sheet via the module-level
    ``SHEET_PACKER``. This used to also cover appearances baked offline into
    a composited row image (see docs/adr/0001, superseded by ADR 0004) —
    that split was removed once sheets made per-appearance loading cheap
    enough that baking's runtime-instantiation win no longer justified its
    much higher request count (see ADR 0004).
    """
    defs: Dict[str, Dict] = {}
    for appearance_id, analysis in ITEM_CACHE.items():
        sprite_record = next(
            (r for r in analysis["sprites"] if r["available"]), None
        )
        sprite_width = sprite_record["width"] if sprite_record else TILE_SIZE
        sprite_height = sprite_record["height"] if sprite_record else TILE_SIZE

        entry: Dict = {
            "type": analysis["type"],
            "layerClass": classify_layer(analysis),
        }
        if appearance_id in dynamic_ids:
            sheet_key, gids = SHEET_PACKER.add_appearance(
                appearance_id, entry["layerClass"], sprite_width, sprite_height,
                frame_count=len(analysis["sprites"]),
            )
            entry["sheet"] = sheet_key
            entry["gids"] = gids
            sources = SHEET_FRAME_SOURCES.setdefault(sheet_key, {})
            for gid, sprite in zip(gids, analysis["sprites"]):
                if sprite["available"]:
                    sources[gid] = sprite["sourcePath"]

        # Add wall orientation for wall items
        layer_class = entry["layerClass"]
        if layer_class in ("walls_east", "walls_south"):
            entry["wallOrientation"] = _get_wall_orientation(analysis)

        # Only include dimensions when they differ from default 32×32
        if sprite_width != TILE_SIZE:
            entry["spriteWidth"] = sprite_width
        if sprite_height != TILE_SIZE:
            entry["spriteHeight"] = sprite_height

        if not analysis["hasSprite"]:
            entry["hasSprite"] = False
        if analysis.get("random", False):
            entry["random"] = True
        if analysis.get("animated", False):
            entry["animated"] = True

        flags_true = {k: v for k, v in analysis.get("flags", {}).items() if v}
        if flags_true:
            entry["flags"] = flags_true

        if analysis["issues"]:
            entry["issues"] = list(analysis["issues"])

        defs[str(appearance_id)] = entry
    return defs


# ======================================================
# MAP BUILDER
# ======================================================

def build_phaser_map(dump: Dict) -> Dict:
    # Ground tiles are bucketed per floor (z) from the start — two floors
    # occupying the same (x, y) column (e.g. a dungeon directly beneath the
    # surface) must never merge into one entry. See ADR 0002.
    ground_tiles: Dict[int, Dict[Tuple[int, int], int]] = {}
    raw_item_stacks: Dict[Tuple[int, int, int], List[Tuple[int, Dict]]] = {}
    animations: Dict[int, Dict] = {}
    all_zs: Set[int] = set()

    min_x = min_y = 10**9
    max_x = max_y = -10**9

    nodes = dump.get("data", {}).get("nodes", [])

    # ── First pass: collect tiles/items per floor, determine map bounds ──
    for node in nodes:
        for feature in node.get("features", []):
            base_x = feature.get("x", 0)
            base_y = feature.get("y", 0)
            z = feature.get("z", 7)

            for tile in feature.get("tiles", []):
                tx = tile.get("x")
                ty = tile.get("y")
                if tx is None or ty is None:
                    continue

                # Only count this floor toward `defaultZ` once it actually
                # contributes a tile — a feature with no `z` and no tiles
                # (an empty/container node) used to default to z=7 and get
                # counted anyway, making `defaultZ` pick a phantom floor 7
                # even on maps whose real content lives entirely elsewhere
                # (e.g. a tower cut at z=1..5, a dungeon cut at z=8).
                all_zs.add(z)

                x = base_x + tx
                y = base_y + ty

                # Bounds are a union across all floors — every floor shares
                # the same (tileX, tileY) coordinate space, so a transition
                # tile lines up with the same column on the floor below/above
                # without needing explicit destination metadata (ADR 0002).
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)

                key = (x, y, z)

                # tileid — usually goes to ground tilelayer, but large
                # blocking tiles (unpass+unmove+unsight with sprite > 1×1)
                # are redirected to the roof objectgroup to avoid rendering
                # 64×64+ sprites in a 32×32 tilelayer (which causes black
                # lines and incorrect overlap with clip/border sprites).
                tile_ground = tile.get("tileid")
                if tile_ground is not None:
                    ground_analysis = analyze_item(tile_ground)

                    if _is_roof_tile(ground_analysis):
                        # Redirect to item stacks so classify_layer sends
                        # it to the Roof objectgroup. stackIndex = -1 so
                        # it renders below any real items on this position.
                        raw_item_stacks.setdefault(key, []).insert(
                            0, (-1, ground_analysis)
                        )
                    else:
                        ground_tiles.setdefault(z, {})[(x, y)] = tile_ground

                # Collect items for second pass (bounds not yet final)
                items = tile.get("items", [])
                for item_index, raw_item in enumerate(items):
                    appearance_id = raw_item.get("id")
                    if appearance_id is None:
                        continue

                    # Marker signs (reserved uid range) are travel-graph
                    # tooling input, never a renderable map object.
                    uid = raw_item.get("uid")
                    if uid is not None and uid >= MARKER_UID_MIN:
                        continue

                    analysis = analyze_item(appearance_id)

                    if analysis.get("animated", False) and appearance_id not in animations:
                        animations[appearance_id] = analysis["animation"]

                    raw_item_stacks.setdefault(key, []).append(
                        (item_index, analysis)
                    )

    if min_x == 10**9:
        min_x = min_y = max_x = max_y = 0
        all_zs.add(7)

    width = max_x - min_x + 1
    height = max_y - min_y + 1

    # ── Second pass: classify items into per-floor objectgroup layers ──
    # Each floor gets its own independent set of the 7 layer-class dicts.
    # Floors never share stack entries even when they occupy the same
    # (x, y) column — that's precisely the bug this rewrite fixes.
    floor_objects: Dict[int, Dict[str, Dict[Tuple[int, int], List[Dict]]]] = {
        z: {
            "border": {}, "bottom": {}, "object": {}, "top": {},
            "roof": {}, "walls_south": {}, "walls_east": {},
        }
        for z in all_zs
    }

    dynamic_appearance_ids: Set[int] = set()

    for (x, y, z), items in raw_item_stacks.items():
        objects_for_floor = floor_objects[z]
        for item_index, analysis in items:
            layer_class = classify_layer(analysis)
            appearance_id = analysis["appearanceId"]

            dynamic_appearance_ids.add(appearance_id)
            entry = _make_object_entry(analysis, appearance_id, item_index)
            target = objects_for_floor.get(layer_class, objects_for_floor["object"])
            target.setdefault((x, y), []).append(entry)

    # ── Pack ground appearances into grid sheets (map.json v5) ──
    # Reuses the same SheetPacker as objectDefs (layerClass "ground"), so the
    # Ground tilelayer needs only 1-3 tileset entries (one per size bucket in
    # use) instead of one legacy single-tile tileset per unique appearance —
    # see docs/adr/0005-map-json-v5-ground-sheets.md.
    ground_appearance_ids: Set[int] = {
        appearance_id
        for tiles in ground_tiles.values()
        for appearance_id in tiles.values()
    }

    ground_local_gid: Dict[int, Tuple[str, int]] = {}
    for appearance_id in sorted(ground_appearance_ids):
        analysis = analyze_item(appearance_id)
        sprite = next((r for r in analysis["sprites"] if r["available"]), None)
        sprite_width = sprite["width"] if sprite else TILE_SIZE
        sprite_height = sprite["height"] if sprite else TILE_SIZE

        sheet_key, gids = SHEET_PACKER.add_appearance(appearance_id, "ground", sprite_width, sprite_height)
        local_gid = gids[0]
        ground_local_gid[appearance_id] = (sheet_key, local_gid)
        if sprite:
            SHEET_FRAME_SOURCES.setdefault(sheet_key, {})[local_gid] = sprite["sourcePath"]

    ground_by_sheet: Dict[str, List[Tuple[int, int]]] = {}
    for appearance_id, (sheet_key, local_gid) in ground_local_gid.items():
        ground_by_sheet.setdefault(sheet_key, []).append((appearance_id, local_gid))

    gid_lookup: Dict[int, int] = {}
    tilesets: List[Dict] = []
    current_gid = 1

    for sheet_key in sorted(ground_by_sheet):
        dims = SHEET_PACKER.sheet_dims(sheet_key)
        tilesets.append({
            "firstgid": current_gid,
            "name": sheet_key,
            "tilewidth": dims["cellSize"],
            "tileheight": dims["cellSize"],
            "tilecount": dims["totalCells"],
            "columns": dims["columns"],
            "image": posixpath.join(ASSETS_ROOT, "sheets", f"{sheet_key}.png"),
            "imagewidth": dims["pixelWidth"],
            "imageheight": dims["pixelHeight"],
        })
        for appearance_id, local_gid in ground_by_sheet[sheet_key]:
            gid_lookup[appearance_id] = current_gid + local_gid
        current_gid += dims["totalCells"]

    # ── Build layers, once per floor ──
    # Objectgroup layers with increasing depth offsets
    # WallsSouth: horizontal walls + corners → depthOffset 3 (behind player)
    # WallsEast:  vertical walls             → depthOffset 12 (in front of player)
    layer_configs = [
        ("Borders",    "border",       1),
        ("Bottom",     "bottom",       5),
        ("WallsSouth", "walls_south",  3),
        ("WallsEast",  "walls_east",   12),
        ("Objects",    "object",       10),
        ("Top",        "top",          50),
        ("Roof",       "roof",         100),
    ]

    floors: Dict[str, Dict] = {}

    for z in sorted(all_zs):
        layers: List[Dict] = []
        layer_id = 1

        # Layer 1: Ground (tilelayer — ALL tileid entries on this floor).
        # Sized to the union bounds like every floor, so a column with no
        # tile on this floor stays zero rather than shifting coordinates.
        ground_data = [0] * (width * height)
        for (x, y), appearance_id in ground_tiles.get(z, {}).items():
            ix = x - min_x
            iy = y - min_y
            index = iy * width + ix
            ground_data[index] = gid_lookup.get(appearance_id, 0)

        layers.append({
            "id": layer_id,
            "name": "Ground",
            "type": "tilelayer",
            "visible": True,
            "opacity": 1,
            "width": width,
            "height": height,
            "data": ground_data,
            "properties": {"depthOffset": 0, "layerClass": "ground"},
        })
        layer_id += 1

        objects_for_floor = floor_objects[z]
        for name, layer_class, depth_offset in layer_configs:
            obj_dict = objects_for_floor[layer_class]
            if not obj_dict:
                continue
            object_list = []
            for (x, y), stack in obj_dict.items():
                tile_x = x - min_x
                tile_y = y - min_y
                # Compact: [tileX, tileY, ...stack_entries]
                # Each stack entry is [appearanceId, stackIndex]
                object_list.append([tile_x, tile_y] + stack)
            layers.append({
                "id": layer_id,
                "name": name,
                "type": "objectgroup",
                "visible": True,
                "objects": object_list,
                "properties": {
                    "depthOffset": depth_offset,
                    "layerClass": layer_class,
                },
            })
            layer_id += 1

        floors[str(z)] = {"z": z, "layers": layers}

    # Surface floor is conventionally z=7 in Tibia; fall back to the lowest
    # z present for maps that (unusually) don't include it.
    default_z = 7 if 7 in all_zs else min(all_zs)

    # Build objectDefs: one entry per unique appearanceId. This is also
    # where dynamic appearances get packed into SHEET_PACKER (v4 sheets).
    object_defs = _build_object_defs(dynamic_appearance_ids)

    # Render one PNG per sheet the packer accumulated above.
    sheets_manifest: Dict[str, Dict] = {}
    if SHEET_PACKER.sheets:
        ensure_directory(SHEETS_OUTPUT_DIR)
    for sheet_key in SHEET_PACKER.sheets:
        dims = SHEET_PACKER.sheet_dims(sheet_key)
        image = _render_sheet(SHEET_PACKER, sheet_key, SHEET_FRAME_SOURCES.get(sheet_key, {}))
        filename = f"{sheet_key}.png"
        image.save(os.path.join(SHEETS_OUTPUT_DIR, filename))
        sheets_manifest[sheet_key] = {
            "image": posixpath.join(ASSETS_ROOT, "sheets", filename),
            "cellWidth": dims["cellSize"],
            "cellHeight": dims["cellSize"],
            "columns": dims["columns"],
        }

    return {
        "version": 5,
        "orientation": "orthogonal",
        "renderorder": "right-down",
        "tilewidth": TILE_SIZE,
        "tileheight": TILE_SIZE,
        "width": width,
        "height": height,
        "bounds": {
            "minX": min_x,
            "minY": min_y,
            "maxX": max_x,
            "maxY": max_y,
        },
        "defaultZ": default_z,
        "assetsRoot": ASSETS_ROOT,
        "objectDefs": object_defs,
        "sheets": sheets_manifest,
        "floors": floors,
        "tilesets": tilesets,
        "animations": animations,
    }

# ======================================================
# MAIN
# ======================================================

def _build_metadata_index() -> Dict:
    """Build a metadata.json with per-appearance-id entries from ITEM_CACHE."""
    metadata: Dict[str, Dict] = {}
    for appearance_id, analysis in ITEM_CACHE.items():
        entry: Dict = {}
        if analysis.get("metadataFound"):
            entry["metadata"] = analysis["metadataFound"]
        if analysis.get("spriteInfo"):
            entry["spriteInfo"] = analysis["spriteInfo"]
        # Only true flags
        flags_true = {k: v for k, v in analysis.get("flags", {}).items() if v}
        if flags_true:
            entry["flags"] = flags_true
        if analysis.get("animation"):
            entry["animation"] = analysis["animation"]
        if entry:
            metadata[str(appearance_id)] = entry
    return metadata




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
    """Parse monster-loot.json -> {monster name: {"loot": [...], "issues": [...]}}."""
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

            monster_defs[outfit_id_str] = {
                "name": name,
                "outfitId": outfit_id,
                "atlas": _outfit_atlas_ref(outfit_id),
                "loot": loot_entry["loot"] if loot_entry else [],
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

def write_map_v6(dump: Dict, respawn: Optional[Dict]) -> Dict:
    """Build and write the v6 tree for this map, returning the document.

    Its own SheetPacker: v6 groups sheets by footprint alone, while the v5 pass
    above groups by (layerClass, footprint). Sharing one packer would merge the
    two key spaces and corrupt both.

    `respawn` is the dict `build_monster_respawn` already produced — copied in
    so the v6 tree is self-contained for the game to consume, not regenerated.
    """
    packer = SheetPacker()
    # `MAP_NAME` up to its first underscore is the hunt's own hand-chosen id
    # (see `hunt_fragment.map_id_from_folder`) — what a start-marker sign's
    # text must equal for `build_map_v6` to trust it over the defaultZ
    # heuristic.
    map_id = MAP_NAME.split("_", 1)[0]
    document, frame_sources = map_v6.build_map_v6(
        dump, analyze_item, packer, V6_ASSETS_ROOT, map_id=map_id
    )

    if packer.sheets:
        ensure_directory(V6_SHEETS_OUTPUT_DIR)
    for sheet_key in sorted(packer.sheets):
        image = _render_sheet(packer, sheet_key, frame_sources.get(sheet_key, {}))
        image.save(os.path.join(V6_SHEETS_OUTPUT_DIR, f"{sheet_key}.png"))

    oversized = [key for key in sorted(packer.sheets) if packer.exceeds_safe_texture_size(key)]
    if oversized:
        print(f"[WARN] v6: folha acima do limite seguro de textura: {', '.join(oversized)}")

    ensure_directory(V6_OUTPUT_DIR)
    output_path = os.path.join(V6_OUTPUT_DIR, "map.json")
    with open(output_path, "w", encoding="utf-8") as output_file:
        json.dump(document, output_file, indent=2)

    if respawn is not None:
        ensure_directory(V6_MONSTERS_OUTPUT_DIR)
        with open(os.path.join(V6_MONSTERS_OUTPUT_DIR, "respawn.json"), "w",
                  encoding="utf-8") as monsters_file:
            json.dump(respawn, monsters_file, indent=2, ensure_ascii=False)

    tile_count = sum(len(floor["tiles"]) for floor in document["floors"].values())
    print(f"[OK] Mapa v6 gerado em {output_path}")
    print(f"     {tile_count} tiles | {len(document['appearances'])} aparências "
          f"| {len(document['sheets'])} folhas")
    return document


# ======================================================
# MAIN
# ======================================================

if __name__ == "__main__":
    with open(OTBM_FILE, "r", encoding="utf-8") as file_handler:
        dump = json.load(file_handler)

    phaser_map = build_phaser_map(dump)

    # Write optimized map.json
    output_path = os.path.join(OUTPUT_DIR, "map.json")
    ensure_directory(os.path.dirname(output_path))
    with open(output_path, "w", encoding="utf-8") as output_file:
        json.dump(phaser_map, output_file, indent=2)

    # Write separate metadata.json (keyed by appearance id)
    metadata_path = os.path.join(OUTPUT_DIR, "metadata.json")
    metadata_index = _build_metadata_index()
    with open(metadata_path, "w", encoding="utf-8") as meta_file:
        json.dump(metadata_index, meta_file, indent=2)

    print(f"[OK] Mapa Phaser gerado em {output_path}")
    print(f"[OK] Metadata gerado em {metadata_path} ({len(metadata_index)} entries)")

    # Write monsters/respawn.json
    respawn = build_monster_respawn(phaser_map["bounds"])

    # ── map.json v6, into its own tree ──
    # Runs after the v5 pass on purpose: ITEM_CACHE is already warm, so this is
    # a second walk over the dump, not a second round of metadata resolution.
    if IS_FULL_MAP:
        print("[INFO] Mapa de cidade inteira: v6 não se aplica (ver V6_OUTPUT_DIR)")
    else:
        write_map_v6(dump, respawn)
