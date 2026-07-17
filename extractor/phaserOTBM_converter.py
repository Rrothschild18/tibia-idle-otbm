import json
import os
import posixpath
import shutil
import struct
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple

import item_classifier

# ======================================================
# CONFIG
# ======================================================

TILE_SIZE = 32
MAP_NAME = "rats-rookguard"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OTBM_FILE = os.path.join(BASE_DIR, f"{MAP_NAME}.raw.json")

_CANDIDATE_ITEM_SOURCES = [
    os.path.abspath(os.path.join(BASE_DIR, "sprites", "items")),
    os.path.abspath(os.path.join(BASE_DIR, "sprites", "missiles")),
    os.path.abspath(os.path.join(BASE_DIR, "sprites")),
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

OUTPUT_DIR = os.path.abspath(os.path.join(BASE_DIR, f"{MAP_NAME}-sprites"))
SPRITES_OUTPUT_DIR = os.path.join(OUTPUT_DIR, "sprites")
ASSETS_ROOT = posixpath.join("assets", f"{MAP_NAME}-sprites")

# Monsters
OTSERVBR_MONSTER_XML = os.path.join(BASE_DIR, "otservbr-monster.xml")
MONSTER_SPAWN_XML = os.path.join(BASE_DIR, "maps", f"{MAP_NAME}-monster.xml")
OUTFITS_SPRITES_DIR = os.path.join(BASE_DIR, "sprites", "outfits")
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
            "isRoof": is_roof,
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


def _get_layer_dict(layer_class: str,
                    border_objects: Dict, bottom_objects: Dict,
                    normal_objects: Dict, top_objects: Dict,
                    roof_objects: Dict,
                    walls_south_objects: Dict,
                    walls_east_objects: Dict) -> Dict:
    """Returns the correct dictionary for a given layer classification."""
    return {
        "border": border_objects,
        "bottom": bottom_objects,
        "object": normal_objects,
        "top": top_objects,
        "roof": roof_objects,
        "walls_south": walls_south_objects,
        "walls_east": walls_east_objects,
    }.get(layer_class, normal_objects)


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


def _build_object_defs() -> Dict[str, Dict]:
    """Builds the ``objectDefs`` lookup from the global ITEM_CACHE.

    Each entry is keyed by the string appearanceId and contains every
    property that is the *same* for all placements of that appearance.
    The renderer only needs to join objectDefs[id] with the per-tile
    position to fully reconstruct the old verbose entry.
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
            "spriteIds": [r["spriteId"] for r in analysis["sprites"]],
        }

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
    ground_tiles: Dict[Tuple[int, int], int] = {}
    raw_item_stacks: Dict[Tuple[int, int], List[Tuple[int, Dict]]] = {}
    animations: Dict[int, Dict] = {}
    all_tile_ids = set()

    min_x = min_y = 10**9
    max_x = max_y = -10**9

    nodes = dump.get("data", {}).get("nodes", [])

    # ── First pass: collect tiles/items, determine map bounds ──
    for node in nodes:
        for feature in node.get("features", []):
            base_x = feature.get("x", 0)
            base_y = feature.get("y", 0)

            for tile in feature.get("tiles", []):
                tx = tile.get("x")
                ty = tile.get("y")
                if tx is None or ty is None:
                    continue

                x = base_x + tx
                y = base_y + ty

                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)

                key = (x, y)

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
                        ground_tiles[key] = tile_ground

                # Collect items for second pass (bounds not yet final)
                items = tile.get("items", [])
                for item_index, raw_item in enumerate(items):
                    appearance_id = raw_item.get("id")
                    if appearance_id is None:
                        continue

                    analysis = analyze_item(appearance_id)
                    ensure_sprite_assets(analysis)
                    all_tile_ids.add(appearance_id)

                    if analysis.get("animated", False) and appearance_id not in animations:
                        animations[appearance_id] = analysis["animation"]

                    raw_item_stacks.setdefault(key, []).append(
                        (item_index, analysis)
                    )

    if min_x == 10**9:
        min_x = min_y = max_x = max_y = 0

    width = max_x - min_x + 1
    height = max_y - min_y + 1

    # ── Second pass: classify items into objectgroup layers ──
    border_objects: Dict[Tuple[int, int], List[Dict]] = {}
    bottom_objects: Dict[Tuple[int, int], List[Dict]] = {}
    normal_objects: Dict[Tuple[int, int], List[Dict]] = {}
    top_objects: Dict[Tuple[int, int], List[Dict]] = {}
    roof_objects: Dict[Tuple[int, int], List[Dict]] = {}
    walls_south_objects: Dict[Tuple[int, int], List[Dict]] = {}
    walls_east_objects: Dict[Tuple[int, int], List[Dict]] = {}

    for (x, y), items in raw_item_stacks.items():
        for item_index, analysis in items:
            layer_class = classify_layer(analysis)
            entry = _make_object_entry(
                analysis, analysis["appearanceId"],
                item_index,
            )
            target = _get_layer_dict(
                layer_class, border_objects, bottom_objects,
                normal_objects, top_objects, roof_objects,
                walls_south_objects, walls_east_objects,
            )
            target.setdefault((x, y), []).append(entry)

    # ── Build tilesets ──
    gid_lookup: Dict[int, int] = {}
    tilesets: List[Dict] = []
    current_gid = 1

    for appearance_id in sorted(all_tile_ids):
        analysis = analyze_item(appearance_id)
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

    # ── Build layers ──
    layers: List[Dict] = []
    layer_id = 1

    # Layer 1: Ground (tilelayer — ALL tileid entries)
    ground_data = [0] * (width * height)
    for (x, y), appearance_id in ground_tiles.items():
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

    # Objectgroup layers with increasing depth offsets
    # WallsSouth: horizontal walls + corners → depthOffset 3 (behind player)
    # WallsEast:  vertical walls             → depthOffset 12 (in front of player)
    layer_configs = [
        ("Borders",    border_objects,       1,   "border"),
        ("Bottom",     bottom_objects,       5,   "bottom"),
        ("WallsSouth", walls_south_objects,  3,   "walls_south"),
        ("WallsEast",  walls_east_objects,   12,  "walls_east"),
        ("Objects",    normal_objects,       10,  "object"),
        ("Top",        top_objects,          50,  "top"),
        ("Roof",       roof_objects,         100, "roof"),
    ]

    for name, obj_dict, depth_offset, layer_class in layer_configs:
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

    # Build objectDefs: one entry per unique appearanceId
    object_defs = _build_object_defs()

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
        "assetsRoot": ASSETS_ROOT,
        "objectDefs": object_defs,
        "layers": layers,
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


def _parse_spawn_xml() -> List[Dict]:
    """Parse {MAP_NAME}-monster.xml → list of spawn dicts."""
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

    # Write monsters/respawn.json
    build_monster_respawn(phaser_map["bounds"])
