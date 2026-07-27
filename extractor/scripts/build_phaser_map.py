import json
import os
import posixpath
import shutil
import struct
import sys
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Set, Tuple

from PIL import Image

import item_classifier

# ======================================================
# CONFIG
# ======================================================

TILE_SIZE = 32

if len(sys.argv) < 2:
    print("Uso: python build_phaser_map.py <nome-do-mapa> [--dump-baked-preview]")
    print("     <nome-do-mapa> deve ter uma pasta correspondente em extractor/maps/")
    print("     --dump-baked-preview imprime diagnostico por linha bakeada (baked/)")
    sys.exit(1)

MAP_NAME = sys.argv[1]
DUMP_BAKED_PREVIEW = "--dump-baked-preview" in sys.argv

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
EXTRACTOR_DIR = os.path.dirname(SCRIPTS_DIR)

OTBM_FILE = os.path.join(EXTRACTOR_DIR, "raw-maps", f"{MAP_NAME}.raw.json")

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

# Pasta local de saída (dentro de extractor/ready-maps/). O valor de
# ASSETS_ROOT abaixo é independente disso — é o path que o jogo usa em tempo
# de execução para localizar os assets copiados, e mantém o sufixo "-sprites"
# para não quebrar integrações existentes que já leem esse campo do JSON.
OUTPUT_DIR = os.path.abspath(os.path.join(EXTRACTOR_DIR, "ready-maps", MAP_NAME))
SPRITES_OUTPUT_DIR = os.path.join(OUTPUT_DIR, "sprites")
BAKED_OUTPUT_DIR = os.path.join(OUTPUT_DIR, "baked")
ASSETS_ROOT = posixpath.join("assets", f"{MAP_NAME}-sprites")

# Monsters
# O editor de mapas exporta os sidecars com o nome do mapa como prefixo
# (ex: troll-rookguard-monster.xml) — mantemos essa convenção aqui pra não
# exigir renomear arquivo nenhum ao adicionar um mapa novo.
OTSERVBR_MONSTER_XML = os.path.join(EXTRACTOR_DIR, "otservbr-monster.xml")
MONSTER_SPAWN_XML = os.path.join(EXTRACTOR_DIR, "maps", MAP_NAME, f"{MAP_NAME}-monster.xml")
OUTFITS_SPRITES_DIR = os.path.join(EXTRACTOR_DIR, "sprites", "outfits")
MONSTERS_OUTPUT_DIR = os.path.join(OUTPUT_DIR, "monsters")
MONSTERS_ASSETS_ROOT = posixpath.join("assets", f"{MAP_NAME}-sprites", "monsters")

os.makedirs(SPRITES_OUTPUT_DIR, exist_ok=True)

# ======================================================
# GLOBAL STATE
# ======================================================

ITEM_CACHE: Dict[int, Dict] = {}
SPRITE_DIM_CACHE: Dict[str, Tuple[int, int]] = {}
COPIED_SPRITES = set()

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

    phase_count = len(sprite_ids)
    animation_valid = False
    if animation_block:
        phases = animation_block.get("phases")
        if isinstance(phases, list):
            phase_count = len(phases)
        elif isinstance(phases, int):
            phase_count = phases
        sprite_ready = available_count == len(sprite_records) and phase_count == len(sprite_records)
        if sprite_ready:
            frame_duration = animation_block.get("frame_duration") or animation_block.get("frameDuration") or 500
            animation_valid = True
            info["animated"] = True
            info["type"] = "animated"
            info["animation"] = {
                "appearanceId": appearance_id,
                "frameDurationMs": frame_duration,
                "frameRate": max(1, int(1000 / max(frame_duration, 1))),
                "loop": animation_block.get("loop", True),
                "startFrame": animation_block.get("default_phase", 0)
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


def _is_bakeable(analysis: Dict, layer_class: str) -> bool:
    """Determines if an item placement is eligible for offline baking.

    `random` items are excluded even though they're not animated: their
    sprite variant is chosen at runtime from a per-hunt seed (see
    map-loader.ts selectSpriteId), so baking one variant into a shared PNG
    would freeze that variant for every player instead of varying by seed.
    `roof`/`border` are excluded because both already have special
    depth/visibility behavior (absolute depth, visibility toggle) and are
    small sets, so the cost of keeping them dynamic is low (see ADR 0001).
    """
    return (
        analysis.get("animated", False) is False
        and analysis.get("random", False) is False
        and analysis.get("type") != "unknown"
        and analysis.get("appearanceId") not in item_classifier.INTERACTIVE_IDS
        and layer_class not in ("roof", "border")
    )


def _baked_entry_sprite(analysis: Dict) -> Tuple[Optional[str], int, int]:
    """Resolves the (sourcePath, width, height) of a bakeable entry's sprite.

    Falls back to a TILE_SIZE square with no source path when unavailable,
    same as the rest of the pipeline treats missing sprites.
    """
    record = next((r for r in analysis.get("sprites", []) if r.get("available")), None)
    if record is None:
        return None, TILE_SIZE, TILE_SIZE
    return record["sourcePath"], record["width"], record["height"]


def _render_baked_row(tile_y: int, layer_class: str, entries: List[Dict]) -> Tuple[Image.Image, Dict]:
    """Composites one (tileY, layerClass) row of bakeable entries into a
    single RGBA image.

    Each entry anchors at the same bottom-right-of-tile point the runtime
    uses for dynamic sprites (`origin(1,1)`): the right edge of the sprite
    sits at `(tileX + 1) * TILE_SIZE`, the bottom edge of every entry in the
    row sits at `(tileY + 1) * TILE_SIZE`. The canvas is the dynamic bounding
    box of all entries, so a sprite wider/taller than one tile still fits.
    `meta["worldX"/"worldY"]` is the canvas's own top-left corner in the same
    (already-relative) tile coordinate space as the rest of map.json, so a
    consumer drawing the image at that pixel with origin (0,0) reproduces
    the exact per-sprite placement.

    `entries`: dicts of {"tileX": int, "stackIndex": int, "analysis": Dict},
    all sharing the same tile_y/layer_class. Composited in tileX-ascending,
    then stackIndex-ascending order — the same stacking order the dynamic
    renderer uses — so later entries draw on top.
    """
    if not entries:
        raise ValueError("_render_baked_row requires at least one entry")

    ordered = sorted(entries, key=lambda e: (e["tileX"], e["stackIndex"]))
    bottom = (tile_y + 1) * TILE_SIZE

    resolved = []
    for entry in ordered:
        sprite_path, width, height = _baked_entry_sprite(entry["analysis"])
        right_edge = (entry["tileX"] + 1) * TILE_SIZE
        resolved.append({
            "sprite_path": sprite_path,
            "width": width,
            "height": height,
            "right_edge": right_edge,
            "left_edge": right_edge - width,
            "top": bottom - height,
        })

    canvas_min_x = min(r["left_edge"] for r in resolved)
    canvas_max_x = max(r["right_edge"] for r in resolved)
    canvas_top = min(r["top"] for r in resolved)
    canvas_width = canvas_max_x - canvas_min_x
    canvas_height = bottom - canvas_top

    canvas = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
    for r in resolved:
        if not r["sprite_path"]:
            continue
        with Image.open(r["sprite_path"]) as sprite_img:
            sprite_rgba = sprite_img.convert("RGBA")
            paste_x = r["left_edge"] - canvas_min_x
            paste_y = r["top"] - canvas_top
            canvas.alpha_composite(sprite_rgba, (paste_x, paste_y))

    meta = {
        "worldX": canvas_min_x,
        "worldY": canvas_top,
        "width": canvas_width,
        "height": canvas_height,
    }
    return canvas, meta


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


def _build_object_defs(baked_ids: Set[int], dynamic_ids: Set[int]) -> Dict[str, Dict]:
    """Builds the ``objectDefs`` lookup from the global ITEM_CACHE.

    Each entry is keyed by the string appearanceId and contains every
    property that is the *same* for all placements of that appearance.
    The renderer only needs to join objectDefs[id] with the per-tile
    position to fully reconstruct the old verbose entry.

    An appearanceId whose every placement across the map ended up baked
    (present in ``baked_ids`` and never in ``dynamic_ids``) is marked
    ``bakedOnly`` and keeps no ``spriteIds`` — the renderer never needs to
    instantiate that sprite dynamically. The entry itself is kept (rather
    than dropped) for debugging/traceability while the bake pipeline is new
    (see the static-scenery-baking spec).
    """
    defs: Dict[str, Dict] = {}
    for appearance_id, analysis in ITEM_CACHE.items():
        sprite_record = next(
            (r for r in analysis["sprites"] if r["available"]), None
        )
        sprite_width = sprite_record["width"] if sprite_record else TILE_SIZE
        sprite_height = sprite_record["height"] if sprite_record else TILE_SIZE

        baked_only = appearance_id in baked_ids and appearance_id not in dynamic_ids

        entry: Dict = {
            "type": analysis["type"],
            "layerClass": classify_layer(analysis),
        }
        if baked_only:
            entry["bakedOnly"] = True
        else:
            entry["spriteIds"] = [r["spriteId"] for r in analysis["sprites"]]

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
    all_tile_ids = set()
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
            all_zs.add(z)

            for tile in feature.get("tiles", []):
                tx = tile.get("x")
                ty = tile.get("y")
                if tx is None or ty is None:
                    continue

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
                    ensure_sprite_assets(ground_analysis)
                    all_tile_ids.add(tile_ground)

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

                    analysis = analyze_item(appearance_id)
                    all_tile_ids.add(appearance_id)

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

    # Bakeable placements are pulled out of the per-floor objectgroup dicts
    # into their own (tileY, layerClass) groups instead — see ADR 0001. Each
    # group becomes one composited image in the floor's bakedgroup layer.
    floor_baked: Dict[int, Dict[Tuple[int, str], List[Dict]]] = {z: {} for z in all_zs}
    baked_appearance_ids: Set[int] = set()
    dynamic_appearance_ids: Set[int] = set()

    for (x, y, z), items in raw_item_stacks.items():
        objects_for_floor = floor_objects[z]
        tile_x = x - min_x
        tile_y = y - min_y
        for item_index, analysis in items:
            layer_class = classify_layer(analysis)
            appearance_id = analysis["appearanceId"]

            if _is_bakeable(analysis, layer_class):
                floor_baked[z].setdefault((tile_y, layer_class), []).append({
                    "tileX": tile_x,
                    "stackIndex": item_index,
                    "analysis": analysis,
                })
                baked_appearance_ids.add(appearance_id)
                continue

            dynamic_appearance_ids.add(appearance_id)
            entry = _make_object_entry(analysis, appearance_id, item_index)
            target = objects_for_floor.get(layer_class, objects_for_floor["object"])
            target.setdefault((x, y), []).append(entry)

    # appearanceIds whose every placement got baked never need their sprite
    # copied to sprites/ — the baked PNG (composited straight from
    # sourcePath) is all the runtime will ever load for them (see spec.md
    # "Formato de saída": sprites/ é só para objetos ainda dinâmicos).
    baked_only_ids = baked_appearance_ids - dynamic_appearance_ids

    # ── Build tilesets ──
    gid_lookup: Dict[int, int] = {}
    tilesets: List[Dict] = []
    current_gid = 1

    for appearance_id in sorted(all_tile_ids):
        analysis = analyze_item(appearance_id)
        if appearance_id not in baked_only_ids:
            ensure_sprite_assets(analysis)
        sprite = next(
            (r for r in analysis["sprites"] if r["available"]), None
        )
        image_path = sprite["destPath"] if sprite else build_asset_path(
            appearance_id, str(appearance_id)
        )
        image_width = sprite["width"] if sprite else TILE_SIZE
        image_height = sprite["height"] if sprite else TILE_SIZE

        gid_lookup[appearance_id] = current_gid
        tilesets.append({
            "firstgid": current_gid,
            "name": f"tile-{appearance_id}",
            "tilewidth": TILE_SIZE,
            "tileheight": TILE_SIZE,
            "tilecount": 1,
            "columns": 1,
            "image": image_path,
            "imagewidth": image_width,
            "imageheight": image_height,
        })
        current_gid += 1

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

        baked_rows = []
        for (tile_y, layer_class), group_entries in sorted(floor_baked[z].items()):
            depth_offset = next(do for _name, lc, do in layer_configs if lc == layer_class)
            image, meta = _render_baked_row(tile_y, layer_class, group_entries)

            filename = f"row_{tile_y}_{layer_class}.png"
            ensure_directory(BAKED_OUTPUT_DIR)
            image.save(os.path.join(BAKED_OUTPUT_DIR, filename))

            blocked_tiles = sorted(
                f"{entry['tileX']},{tile_y}"
                for entry in group_entries
                if entry["analysis"].get("flags", {}).get("unpass")
            )

            row: Dict = {
                "tileY": tile_y,
                "layerClass": layer_class,
                "image": posixpath.join(ASSETS_ROOT, "baked", filename),
                "worldX": meta["worldX"],
                "worldY": meta["worldY"],
                "width": meta["width"],
                "height": meta["height"],
                "depthOffset": depth_offset,
            }
            if blocked_tiles:
                row["blockedTiles"] = blocked_tiles
            baked_rows.append(row)

        if baked_rows:
            layers.append({
                "id": layer_id,
                "name": "BakedObjects",
                "type": "bakedgroup",
                "visible": True,
                "rows": baked_rows,
                "properties": {},
            })
            layer_id += 1

        floors[str(z)] = {"z": z, "layers": layers}

    # Surface floor is conventionally z=7 in Tibia; fall back to the lowest
    # z present for maps that (unusually) don't include it.
    default_z = 7 if 7 in all_zs else min(all_zs)

    # Build objectDefs: one entry per unique appearanceId
    object_defs = _build_object_defs(baked_appearance_ids, dynamic_appearance_ids)

    return {
        "version": 2,
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


def _print_baked_preview(phaser_map: Dict) -> None:
    """Prints per-row bake diagnostics so a developer can eyeball the
    dimensions/positions before trusting the new pipeline on a map — open
    the referenced PNGs under ``baked/`` alongside this output.
    """
    for z_str, floor in sorted(phaser_map["floors"].items(), key=lambda kv: int(kv[0])):
        baked_layer = next((l for l in floor["layers"] if l["type"] == "bakedgroup"), None)
        if not baked_layer:
            print(f"[BAKE PREVIEW] floor z={z_str}: no baked rows")
            continue
        print(f"[BAKE PREVIEW] floor z={z_str}: {len(baked_layer['rows'])} baked row(s)")
        for row in baked_layer["rows"]:
            blocked = len(row.get("blockedTiles", []))
            print(
                f"  tileY={row['tileY']:<4} layerClass={row['layerClass']:<12} "
                f"{row['width']}x{row['height']} @ ({row['worldX']}, {row['worldY']}) "
                f"depthOffset={row['depthOffset']} blockedTiles={blocked} -> {row['image']}"
            )


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


def _build_outfit_anims(outfit_id: int, data: Dict) -> Dict:
    """Build idle/moving animation data per direction from outfit JSON.

    Layout (see OUTFIT_SPRITES_DOCUMENTATION.md):
      - patternWidth directions in order: south, east, north, west
      - idle:   1 sprite per direction  (indices 0-3)
      - moving: N frames per direction  (indices 4 onward, each dir*N)
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
            result["idle"] = {
                d: frames[0] if frames else str(outfit_id)
                for d, frames in dir_sprites.items()
            }

        elif fg_type == "moving":
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
                if "INFINITE" in anim.get("loopType", ""):
                    loop_type = "infinite"
                else:
                    loop_type = "once"

            result["moving"] = {
                d: {"frames": frames, "frameRate": frame_rate, "loopType": loop_type}
                for d, frames in dir_sprites.items()
            }

    return result


def _copy_outfit_sprites(outfit_id: int, dest_dir: str) -> None:
    """Copy PNG sprites of an outfit to the monster output directory."""
    src_sub = os.path.join(OUTFITS_SPRITES_DIR, str(outfit_id))
    ensure_directory(dest_dir)
    if os.path.isdir(src_sub):
        for fname in os.listdir(src_sub):
            if fname.endswith(".png"):
                dst = os.path.join(dest_dir, fname)
                if not os.path.exists(dst):
                    shutil.copy2(os.path.join(src_sub, fname), dst)
    else:
        src = os.path.join(OUTFITS_SPRITES_DIR, f"{outfit_id}.png")
        if os.path.exists(src):
            dst = os.path.join(dest_dir, f"{outfit_id}.png")
            if not os.path.exists(dst):
                shutil.copy2(src, dst)


def build_monster_respawn(map_bounds: Dict) -> Optional[Dict]:
    """Generate respawn.json for monsters on the current map.

    Returns the dict (also writes it to MONSTERS_OUTPUT_DIR/respawn.json).
    Returns None if no spawn XML is found or no spawns exist.
    """
    monster_lookup = _load_monster_lookup()
    spawns_raw = _parse_spawn_xml()

    if not spawns_raw:
        print("[INFO] Nenhum spawn de monstros encontrado.")
        return None

    min_x = map_bounds.get("minX", 0)
    min_y = map_bounds.get("minY", 0)

    monster_defs: Dict[str, Dict] = {}
    spawns_out: List[Dict] = []
    missing_names: set = set()

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

            _copy_outfit_sprites(
                outfit_id,
                os.path.join(MONSTERS_OUTPUT_DIR, str(outfit_id)),
            )

            monster_defs[outfit_id_str] = {
                "name": name,
                "outfitId": outfit_id,
                "assetsPath": posixpath.join(MONSTERS_ASSETS_ROOT, str(outfit_id)),
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
        "assetsRoot": MONSTERS_ASSETS_ROOT,
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

    if DUMP_BAKED_PREVIEW:
        _print_baked_preview(phaser_map)

    # Write monsters/respawn.json
    build_monster_respawn(phaser_map["bounds"])
