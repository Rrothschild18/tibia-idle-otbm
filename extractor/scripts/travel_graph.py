"""
Pure logic for the travel-graph & locations pipeline — turning a full-city
OTBM dump (+ its map.json objectDefs) and the map editor's NPC export into
the tibia-idle db.json `locations`/`travelGraph` fragment. See
build_travel_fragment.py for the CLI that reads/writes files and
.scratch/travel-graph-and-locations/spec.md for the full design.

Four independent concerns, kept as separate function groups so each is
testable with tiny in-memory fixtures (no real .otbm/map.json/.lua touched):

1. Marker-sign parsing — POIs (HUNT/TEMPLE/DEPOT/QUEST) marked in the OTBM
   with sign item 2016 at a reserved uid (10001+), text = "CIDADE-TIPO-INCREMENTAL".
2. Walkability graph + BFS — tileCount distances between POIs.
3. NPC locations + Canary shop extraction — no sign needed, position/name
   come from <region>-npc.xml; shop table comes from a same-named .lua.
4. Fragment assembly + db.json merge — mirrors hunt_fragment.py's
   mechanical-vs-curated split, but per-field (not per-entry): position/
   shop/tileCount always upsert, `displayName` is append-only once curated.
"""

import re
import xml.etree.ElementTree as ET
from collections import deque
from typing import Deque, Dict, List, Optional, Set, Tuple

# ======================================================
# Marker signs -> POI locations (HUNT/TEMPLE/DEPOT/QUEST)
# ======================================================

SIGN_ITEM_ID = 2016
MARKER_UID_MIN = 10001
POI_TYPES = ("HUNT", "TEMPLE", "DEPOT", "QUEST")

_SIGN_ID_RE = re.compile(
    r"^(?P<city>[A-Z]+)-(?P<type>" + "|".join(POI_TYPES) + r")-(?P<seq>\d+)$"
)


def _iter_dump_tiles(dump: Dict):
    """Yields (x, y, z, tile) for every tile in a raw otbm2json dump — same
    node/feature/tile walk build_phaser_map.py uses."""
    for node in dump.get("data", {}).get("nodes", []):
        for feature in node.get("features", []):
            base_x = feature.get("x", 0)
            base_y = feature.get("y", 0)
            z = feature.get("z", 7)
            for tile in feature.get("tiles", []):
                tx, ty = tile.get("x"), tile.get("y")
                if tx is None or ty is None:
                    continue
                yield base_x + tx, base_y + ty, z, tile


def parse_marker_signs(dump: Dict) -> Tuple[List[Dict], List[Dict]]:
    """Every sign item (id 2016) with a uid in the reserved range -> a
    (locations, issues) pair. A sign whose uid falls outside the reserved
    range isn't a marker at all and is silently skipped (it's an ordinary
    in-game sign, not travel-graph input). A reserved-uid sign whose text
    doesn't match CIDADE-TIPO-INCREMENTAL is reported as an issue, not
    silently dropped. Two signs that resolve to the same id (typically a
    copy-pasted sign that kept the old uid — a map-editing mistake) are also
    reported: only the first occurrence becomes a location, so a duplicate
    id can never reach the fragment/db.json and silently collide there."""
    locations: List[Dict] = []
    issues: List[Dict] = []
    seen_ids: Set[str] = set()

    for x, y, z, tile in _iter_dump_tiles(dump):
        for raw_item in tile.get("items", []):
            if raw_item.get("id") != SIGN_ITEM_ID:
                continue
            uid = raw_item.get("uid")
            if uid is None or uid < MARKER_UID_MIN:
                continue

            text = raw_item.get("text", "")
            match = _SIGN_ID_RE.match(text)
            if not match:
                issues.append({"reason": "invalid-sign-format", "uid": uid, "text": text, "x": x, "y": y, "z": z})
                continue

            if text in seen_ids:
                issues.append({"reason": "duplicate-sign-id", "uid": uid, "text": text, "x": x, "y": y, "z": z})
                continue
            seen_ids.add(text)

            locations.append({
                "id": text,
                "type": match.group("type"),
                "x": x,
                "y": y,
                "z": z,
            })

    return locations, issues


def _title_from_location_id(location_id: str) -> str:
    return " ".join(word.capitalize() for word in location_id.split("-"))


# Fields on a `locations` entry that need a human decision and are never
# overwritten by a later run once the entry is curated (see merge_locations_into_db).
# `huntId` only applies to type "HUNT" — it's the mapId a HUNT location's
# sign-based id can't derive on its own, since the two ids come from
# unrelated sources: a sign's CIDADE-TIPO-INCREMENTAL text vs. a hunt map's
# hand-assigned mapId in the `hunts` collection (see hunt_fragment.py).
CURATED_LOCATION_FIELDS = ("displayName", "huntId")


def build_sign_location(sign: Dict) -> Dict:
    """A parsed marker sign -> a draft `locations` entry. `displayName` is a
    placeholder derived from the id; a HUNT location also gets a `huntId`
    placeholder (None) to be pointed at the matching `hunts` entry's mapId —
    both flagged for human curation via `_todo`. merge_locations_into_db
    never overwrites either once curated on a later run."""
    entry = {
        "id": sign["id"],
        "type": sign["type"],
        "x": sign["x"],
        "y": sign["y"],
        "z": sign["z"],
        "displayName": _title_from_location_id(sign["id"]),
    }
    todo = ["confirmar displayName (gerado automaticamente do id)"]
    if sign["type"] == "HUNT":
        entry["huntId"] = None
        todo.append("associar huntId com o mapId da hunt correspondente (coleção hunts)")
    entry["_todo"] = todo
    return entry


# ======================================================
# Walkability graph + BFS
# ======================================================

_NEIGHBOR_OFFSETS = [(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if (dx, dy) != (0, 0)]

Node = Tuple[int, int, int]


def extract_tile_flags(dump: Dict, object_defs: Dict[str, Dict]) -> List[Dict]:
    """Every tile in the dump -> {"x", "y", "z", "unpass", "isFloorTransition"},
    combining the ground tileid's flags with every item stacked on it (each
    resolved through `object_defs`, keyed by appearanceId — the same
    objectDefs map.json already carries). Marker signs (reserved uid range)
    never contribute — they're stripped from map.json (see build_phaser_map.py)
    and the graph must reflect that same city, not the raw OTBM's extra markup.
    A tile with no metadata for an id (not in object_defs) contributes no flags."""

    def _flags(appearance_id: Optional[int]) -> Dict:
        if appearance_id is None:
            return {}
        return object_defs.get(str(appearance_id), {}).get("flags", {})

    tiles: Dict[Node, Dict] = {}
    for x, y, z, tile in _iter_dump_tiles(dump):
        key = (x, y, z)
        unpass = False
        is_floor_transition = False

        ground_flags = _flags(tile.get("tileid"))
        unpass = unpass or ground_flags.get("unpass", False)
        is_floor_transition = is_floor_transition or ground_flags.get("isFloorTransition", False)

        for raw_item in tile.get("items", []):
            uid = raw_item.get("uid")
            if uid is not None and uid >= MARKER_UID_MIN:
                continue
            item_flags = _flags(raw_item.get("id"))
            unpass = unpass or item_flags.get("unpass", False)
            is_floor_transition = is_floor_transition or item_flags.get("isFloorTransition", False)

        tiles[key] = {"x": x, "y": y, "z": z, "unpass": unpass, "isFloorTransition": is_floor_transition}

    return list(tiles.values())


def build_walkable_graph(tiles: List[Dict]) -> Dict[Node, Set[Node]]:
    """Walkable tiles -> an undirected adjacency map. Tiles flagged `unpass`
    are excluded entirely (never a node). Same-floor neighbors (orthogonal +
    diagonal) all cost 1 — no diagonal penalty. A tile flagged
    `isFloorTransition` also gets an edge to the same (x, y) on both z-1 and
    z+1 whenever that neighbor is itself walkable (ADR 0002: the true up/down
    direction can't be derived from the flag alone, so both directions get
    an edge rather than guessing)."""
    walkable = {(t["x"], t["y"], t["z"]) for t in tiles if not t["unpass"]}
    graph: Dict[Node, Set[Node]] = {node: set() for node in walkable}

    def _connect(a: Node, b: Node) -> None:
        graph[a].add(b)
        graph[b].add(a)

    for t in tiles:
        if t["unpass"]:
            continue
        x, y, z = t["x"], t["y"], t["z"]
        node = (x, y, z)

        for dx, dy in _NEIGHBOR_OFFSETS:
            neighbor = (x + dx, y + dy, z)
            if neighbor in walkable:
                _connect(node, neighbor)

        if t["isFloorTransition"]:
            for nz in (z - 1, z + 1):
                neighbor = (x, y, nz)
                if neighbor in walkable:
                    _connect(node, neighbor)

    return graph


def bfs_distances(graph: Dict[Node, Set[Node]], start: Node, targets: Set[Node]) -> Dict[Node, int]:
    """Shortest tile-count from `start` to every node in `targets` that's
    reachable, stopping as soon as every target has been found (or the graph
    is exhausted) rather than flooding the whole thing."""
    remaining = set(targets) - {start}
    found: Dict[Node, int] = {}
    if start not in graph or not remaining:
        return found

    visited = {start}
    queue: Deque[Tuple[Node, int]] = deque([(start, 0)])
    while queue and remaining:
        node, dist = queue.popleft()
        for neighbor in graph.get(node, ()):
            if neighbor in visited:
                continue
            visited.add(neighbor)
            if neighbor in remaining:
                found[neighbor] = dist + 1
                remaining.discard(neighbor)
            queue.append((neighbor, dist + 1))
    return found


def build_travel_graph(graph: Dict[Node, Set[Node]], locations: List[Dict]) -> List[Dict]:
    """One BFS per location, reaching every other location in `locations`
    (early exit once all are found) -> one {from, to, tileCount} edge per
    reachable pair. Distance is computed independently per pair (real BFS,
    never inferred through a shared hub), and a pair on disconnected regions
    of the graph simply produces no edge."""
    edges: List[Dict] = []
    seen_pairs: Set[frozenset] = set()

    for loc in locations:
        start = (loc["x"], loc["y"], loc["z"])
        targets_by_node = {
            (other["x"], other["y"], other["z"]): other["id"]
            for other in locations
            if other["id"] != loc["id"]
        }
        distances = bfs_distances(graph, start, set(targets_by_node))

        for node, dist in distances.items():
            other_id = targets_by_node[node]
            pair = frozenset((loc["id"], other_id))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            edges.append({"from": loc["id"], "to": other_id, "tileCount": dist})

    return edges


# ======================================================
# NPC locations + Canary shop extraction
# ======================================================


def slugify(name: str) -> str:
    """"Lee'Delle" -> "lee-delle". Used both for the NPC location id and for
    matching a Canary npc/*.lua filename (which follows the same convention)."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug


def parse_npc_xml(xml_text: str) -> List[Dict]:
    """<region>-npc.xml -> [{"name", "x", "y", "z"}, ...]. Position is the
    outer <npc centerx/centery/centerz> plus the inner <npc name="..." x="0"
    y="0" z="..."> offset (0,0 in every placement seen so far, but the offset
    is honoured rather than assumed away)."""
    root = ET.fromstring(xml_text)
    npcs: List[Dict] = []
    for outer in root.findall("npc"):
        center_x = int(outer.get("centerx", 0))
        center_y = int(outer.get("centery", 0))
        center_z = int(outer.get("centerz", 7))
        for inner in outer.findall("npc"):
            name = inner.get("name")
            if not name:
                continue
            npcs.append({
                "name": name,
                "x": center_x + int(inner.get("x", 0)),
                "y": center_y + int(inner.get("y", 0)),
                "z": int(inner.get("z", center_z)),
            })
    return npcs


def match_npc_lua_filename(npc_name: str, lua_filenames: List[str]) -> Optional[str]:
    """The NPC's name, slugified, matched against a same-named .lua filename
    (case-insensitive stem match — Canary's own filenames are lowercase and
    use "_" as a word separator, e.g. "An Orc Guard" -> an_orc_guard.lua,
    while `slugify`/location ids use "-"; both sides are normalized to "-"
    for the comparison only). None if nothing matches."""
    slug = slugify(npc_name)
    for filename in lua_filenames:
        stem = filename[:-4] if filename.lower().endswith(".lua") else filename
        if stem.lower().replace("_", "-") == slug:
            return filename
    return None


_SHOP_BLOCK_START_RE = re.compile(r"npcConfig\.shop\s*=\s*\{")
_SHOP_ENTRY_RE = re.compile(r"\{([^{}]*)\}")
_SHOP_FIELD_RE = re.compile(r'(\w+)\s*=\s*("(?:[^"\\]|\\.)*"|-?\d+(?:\.\d+)?)')


def _extract_braced_block(text: str, start: int) -> str:
    depth = 1
    i = start
    while i < len(text) and depth > 0:
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
        i += 1
    return text[start:i - 1]


def _parse_lua_scalar(raw: str):
    raw = raw.strip()
    if raw.startswith('"'):
        return raw[1:-1]
    return int(raw) if re.fullmatch(r"-?\d+", raw) else float(raw)


def parse_npc_shop_lua(lua_text: str) -> Optional[List[Dict]]:
    """A Canary npc .lua file's text -> its `npcConfig.shop` table, or None
    if the NPC has no shop at all (a trainer/quest NPC). `clientId` is used
    directly as `itemId` — verified against Canary's own npc_functions.cpp
    and items.xml, no id-translation table needed (see spec's Further Notes)."""
    block_match = _SHOP_BLOCK_START_RE.search(lua_text)
    if not block_match:
        return None

    block = _extract_braced_block(lua_text, block_match.end())
    entries: List[Dict] = []
    for line in block.splitlines():
        line = line.split("--", 1)[0].strip()
        if not line.startswith("{"):
            continue
        entry_match = _SHOP_ENTRY_RE.search(line)
        if not entry_match:
            continue
        fields = {m.group(1): _parse_lua_scalar(m.group(2)) for m in _SHOP_FIELD_RE.finditer(entry_match.group(1))}
        if "itemName" not in fields or "clientId" not in fields:
            continue
        entry = {"itemName": fields["itemName"], "itemId": int(fields["clientId"])}
        if "buy" in fields:
            entry["buy"] = int(fields["buy"])
        if "sell" in fields:
            entry["sell"] = int(fields["sell"])
        entries.append(entry)
    return entries


def build_npc_location(npc: Dict, city_prefix: str, shop: Optional[List[Dict]]) -> Dict:
    """An NPC (position + name) plus its already-resolved shop (or None) ->
    a `locations` entry. No sign involved, no `displayName` curation — the
    NPC's real in-game name is already a good display name."""
    entry: Dict = {
        "id": f"{city_prefix.lower()}-npc-{slugify(npc['name'])}",
        "type": "NPC",
        "x": npc["x"],
        "y": npc["y"],
        "z": npc["z"],
        "displayName": npc["name"],
    }
    if shop is not None:
        entry["shop"] = shop
    return entry


def build_npc_locations(
    npcs: List[Dict], city_prefix: str, shops_by_name: Dict[str, Optional[List[Dict]]]
) -> Tuple[List[Dict], List[str]]:
    """Every NPC -> its Location, plus the list of NPC names with no matching
    `.lua` file at all (still get a Location — position/name — just no
    `shop` field, and the run should warn about these). A name that IS a key
    in `shops_by_name` matched a file — its value may still be None (a
    trainer/quest NPC with no `npcConfig.shop` table), which is expected and
    not warning-worthy, unlike a genuinely missing file."""
    locations: List[Dict] = []
    unmatched: List[str] = []
    for npc in npcs:
        name = npc["name"]
        if name not in shops_by_name:
            unmatched.append(name)
        shop = shops_by_name.get(name)
        locations.append(build_npc_location(npc, city_prefix, shop))
    return locations, unmatched


# ======================================================
# Fragment assembly + db.json merge
# ======================================================


def build_travel_fragment(sign_locations: List[Dict], npc_locations: List[Dict], travel_graph: List[Dict]) -> Dict:
    return {"locations": [*sign_locations, *npc_locations], "travelGraph": travel_graph}


def merge_locations_into_db(db_locations: List[Dict], fragment_locations: List[Dict]) -> Dict[str, str]:
    """Upserts each fragment location into db_locations in place, by id.
    Mechanical fields (position, type, shop) always take the fragment's
    fresh value. Once a human edit removes `_todo` from an existing entry,
    it's considered fully curated: every field in CURATED_LOCATION_FIELDS
    (`displayName`, `huntId`) is preserved from then on, never overwritten
    by a later run's placeholder, and `_todo` stays gone. While `_todo` is
    still present (still a draft nobody's reviewed yet), the entry is fully
    regenerated from the fresh fragment instead — including `_todo` itself,
    so a code change that adds a new curation note (e.g. `huntId`) reaches
    every not-yet-curated draft on its next run, not just brand-new ones.
    `by_id` is kept up to date as entries are appended, so two fragment
    locations sharing an id (should never happen — see parse_marker_signs'
    duplicate-id check — but this function doesn't trust that) upsert into
    the same db entry instead of duplicating it."""
    by_id = {entry["id"]: i for i, entry in enumerate(db_locations)}
    report: Dict[str, str] = {}

    for loc in fragment_locations:
        existing_index = by_id.get(loc["id"])
        if existing_index is None:
            db_locations.append(dict(loc))
            by_id[loc["id"]] = len(db_locations) - 1
            report[loc["id"]] = "added"
            continue

        existing = db_locations[existing_index]
        merged = dict(loc)
        if "_todo" not in existing:
            for field in CURATED_LOCATION_FIELDS:
                if field in existing:
                    merged[field] = existing[field]
            merged.pop("_todo", None)
        db_locations[existing_index] = merged
        report[loc["id"]] = "updated"

    return report


def merge_travel_graph_into_db(db_travel_graph: List[Dict], fragment_travel_graph: List[Dict]) -> Dict[str, str]:
    """Upserts each fragment edge into db_travel_graph in place, matched by
    the unordered {from, to} pair — always mechanical, no human curation
    involved, so every run just overwrites tileCount with the fresh value."""
    by_pair = {frozenset((e["from"], e["to"])): i for i, e in enumerate(db_travel_graph)}
    report: Dict[str, str] = {}

    for edge in fragment_travel_graph:
        pair = frozenset((edge["from"], edge["to"]))
        label = f"{edge['from']}<->{edge['to']}"
        existing_index = by_pair.get(pair)
        if existing_index is None:
            db_travel_graph.append(dict(edge))
            by_pair[pair] = len(db_travel_graph) - 1
            report[label] = "added"
        else:
            db_travel_graph[existing_index] = dict(edge)
            report[label] = "updated"

    return report


def merge_travel_fragment_into_db(db: Dict, fragment: Dict) -> Dict[str, Dict[str, str]]:
    return {
        "locations": merge_locations_into_db(db["locations"], fragment["locations"]),
        "travelGraph": merge_travel_graph_into_db(db["travelGraph"], fragment["travelGraph"]),
    }
