"""
Pure logic for the travel-graph & locations pipeline — turning a full-city
OTBM dump (+ its map.json objectDefs) and the map editor's NPC export into
the tibia-idle `locations`/`travelGraph` catalog fragment. See
build_travel_fragment.py for the CLI that reads/writes files and
.scratch/travel-graph-and-locations/spec.md for the full design.

Five independent concerns, kept as separate function groups so each is
testable with tiny in-memory fixtures (no real .otbm/map.json/.lua touched):

1. Marker-sign parsing — POIs (HUNT/TEMPLE/DEPOT/QUEST) marked in the OTBM
   with sign item 2016 at a reserved uid (10001+), text = "CIDADE-TIPO-INCREMENTAL".
2. Walkability graph + tile distances — the tileCount between two locations,
   walked over real tiles rather than measured across the coordinates.
3. NPC locations + Canary shop extraction — no sign needed, position/name
   come from <CIDADE>-npc.xml; shop table comes from a same-named .lua.
4. Rejecting nodes with no way in — a destination nobody can travel to never
   reaches the fragment; it leaves in a report with whatever identifies it.
5. Catalog merge — `travelGraph` is *replaced* per city (the fragment is the
   complete edge set), while `locations` upsert by id in hunt_fragment.py's
   mechanical-vs-curated split, per-field rather than per-entry: position and
   shop always take the fresh value, `displayName` is append-only once
   curated, and an entry the fragment dropped is reported, never deleted.
"""

import heapq
import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Sequence, Set, Tuple

import city_ids

# ======================================================
# Marker signs -> POI locations (HUNT/TEMPLE/DEPOT/QUEST)
# ======================================================

SIGN_ITEM_ID = 2016
MARKER_UID_MIN = 10001
POI_TYPES = ("HUNT", "TEMPLE", "DEPOT", "QUEST")

_SIGN_ID_RE = re.compile(
    r"^(?P<city>[A-Z]+)-(?P<type>" + "|".join(POI_TYPES) + r")-(?P<seq>\d{4})$"
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
    doesn't match CIDADE-TIPO-NNNN (exactly 4 digits — a stray digit count,
    like the 5-digit `ROOK-HUNT-00015` typo found live, is rejected instead
    of silently minting an id nothing can ever resolve to) is reported as an
    issue, not silently dropped. Two signs that resolve to the same id (typically a
    copy-pasted sign that kept the old uid — a map-editing mistake) are also
    reported: only the first occurrence becomes a location, so a duplicate
    id can never reach the fragment/catalog and silently collide there."""
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
# overwritten by a later run once the entry is curated (see merge_locations_into_catalog).
# `huntId` only applies to type "HUNT" — it's the mapId a HUNT location's
# sign-based id can't derive on its own, since the two ids come from
# unrelated sources: a sign's CIDADE-TIPO-INCREMENTAL text vs. a hunt map's
# hand-assigned mapId in the `hunts` collection (see hunt_fragment.py).
CURATED_LOCATION_FIELDS = ("displayName", "huntId")


def build_sign_location(sign: Dict) -> Dict:
    """A parsed marker sign -> a draft `locations` entry. `displayName` is a
    placeholder derived from the id; a HUNT location also gets a `huntId`
    placeholder (None) to be pointed at the matching `hunts` entry's mapId —
    both flagged for human curation via `_todo`. merge_locations_into_catalog
    never overwrites either once curated on a later run. `city`/`status` are
    derived from the id on every run — never curated, never stale."""
    city = city_ids.derive_city(sign["id"])
    status = city_ids.derive_status(city)
    entry = {
        "id": sign["id"],
        "type": sign["type"],
        "x": sign["x"],
        "y": sign["y"],
        "z": sign["z"],
        "displayName": _title_from_location_id(sign["id"]),
        "city": city,
    }
    if status is not None:
        entry["status"] = status
    todo = ["confirmar displayName (gerado automaticamente do id)"]
    if sign["type"] == "HUNT":
        entry["huntId"] = None
        todo.append("associar huntId com o mapId da hunt correspondente (coleção hunts)")
    entry["_todo"] = todo
    return entry


# ======================================================
# Walkability graph + tile distances
# ======================================================

_NEIGHBOR_OFFSETS = [(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if (dx, dy) != (0, 0)]

# How far from an NPC the player may stand and still count as having arrived
# at it. Not a movement rule — it's how a shop counter is crossed: most of
# Rookgaard's shopkeepers stand on a tile walled off by an `unpass` counter,
# and without a reach every one of them is an unreachable destination. See
# approach_costs for how the distance stays honest.
#
# 3 because that is where Rookgaard stops changing: 2 and 3 both bring in
# every shopkeeper fully connected to the rest of the city, and 4+ only adds
# one more NPC — by bridging ~5 tiles of solid wall to a single neighbour,
# giving it one artificial edge and hiding a genuinely misplaced NPC from
# the rejection report. A reach wide enough to invent a path is worse than
# a node the report tells you to go fix.
DEFAULT_NPC_REACH = 3

Node = Tuple[int, int, int]

# Where each `floorchange` value takes you, as (dx, dy, dz) from the tile
# carrying it. `down` drops straight through; the four compass values are
# ramps/stairs you *walk up* by moving that way, so they land one tile over
# **and** one floor up — which is exactly the case the same-(x, y) bridge
# below cannot express, and why every cave entered by a ramp used to come out
# islanded.
#
# `southalt`/`eastalt` are the alternate sprite variants of the same two
# movements (Canary's FLOORCHANGE_*_ALT), not different movements.
#
# The graph is undirected, so one entry per value covers both directions:
# walking up the ramp and walking back down it are the same edge.
FLOORCHANGE_DELTAS: Dict[str, Tuple[int, int, int]] = {
    "down": (0, 0, 1),
    "north": (0, -1, -1),
    "south": (0, 1, -1),
    "east": (1, 0, -1),
    "west": (-1, 0, -1),
    "southalt": (0, 1, -1),
    "eastalt": (1, 0, -1),
}

_ITEM_ELEMENT_RE = re.compile(r"<item ([^>]*)>(.*?)</item>", re.S)
_FLOORCHANGE_ATTR_RE = re.compile(r'key="floorchange"\s+value="([a-z]+)"')
_ITEM_ID_RE = re.compile(r'\bid="(\d+)"')
_ITEM_RANGE_RE = re.compile(r'fromid="(\d+)"[^>]*toid="(\d+)"')


def parse_floorchange_items(items_xml: str) -> Dict[int, str]:
    """Canary's `items.xml` -> {item id: floorchange direction}.

    This is the authority on "does walking here change my floor", and it
    replaces guessing from render flags. The previous rule inferred stairs
    from a four-flag combo (`usable`+`forceuse`+`unmove`+`automap`) calibrated
    on four known appearance ids; a ramp carries none of them, so every ramp
    in the map was invisible to the graph — the whole reason hunts sitting in
    ramp-entered caves were reported as unreachable.

    Deliberately *not* a curated id list kept in this repo: the same file the
    map editor reads is the one the server reads, so a new stairs id arrives
    with a Canary bump instead of with somebody remembering to add it here.

    Ranges (`fromid`/`toid`) expand — Canary declares most stair/ramp families
    that way, and reading only the single-`id` form would silently pick up a
    fraction of them.

    **Does not** cover ladders, holes and rope spots: those have no
    `floorchange` because they are *used*, not walked onto (item 1948, the
    ladder, carries none). They keep coming from `isFloorTransition` — see
    `build_walkable_graph`."""
    directions: Dict[int, str] = {}

    for element in _ITEM_ELEMENT_RE.finditer(items_xml):
        attributes, body = element.group(1), element.group(2)
        direction = _FLOORCHANGE_ATTR_RE.search(body)
        if not direction:
            continue

        single = _ITEM_ID_RE.search(attributes)
        span = _ITEM_RANGE_RE.search(attributes)
        if single:
            directions[int(single.group(1))] = direction.group(1)
        elif span:
            for item_id in range(int(span.group(1)), int(span.group(2)) + 1):
                directions[item_id] = direction.group(1)

    return directions


def extract_tile_flags(
    dump: Dict,
    object_defs: Dict[str, Dict],
    floorchange_by_id: Optional[Dict[int, str]] = None,
) -> List[Dict]:
    """Every tile in the dump -> {"x", "y", "z", "unpass", "isFloorTransition",
    "floorchange"}, combining the ground tileid's flags with every item stacked
    on it (each resolved through `object_defs`, keyed by appearanceId — the same
    objectDefs map.json already carries). Marker signs (reserved uid range)
    never contribute — they're stripped from map.json (see build_phaser_map.py)
    and the graph must reflect that same city, not the raw OTBM's extra markup.
    A tile with no metadata for an id (not in object_defs) contributes no flags.

    `floorchange` is the direction from `parse_floorchange_items`, or `None`
    when nothing on the tile changes floors — and `None` for every tile when
    `floorchange_by_id` is omitted, which is what keeps a caller that has no
    `items.xml` behaving exactly as before this existed. The *first* direction
    found on the tile wins: ground first, then items bottom-up, so a ramp that
    someone decorated doesn't lose its movement to the decoration."""
    floorchange_by_id = floorchange_by_id or {}

    def _flags(appearance_id: Optional[int]) -> Dict:
        if appearance_id is None:
            return {}
        return object_defs.get(str(appearance_id), {}).get("flags", {})

    tiles: Dict[Node, Dict] = {}
    for x, y, z, tile in _iter_dump_tiles(dump):
        key = (x, y, z)
        unpass = False
        is_floor_transition = False
        floorchange: Optional[str] = None

        ground_id = tile.get("tileid")
        ground_flags = _flags(ground_id)
        unpass = unpass or ground_flags.get("unpass", False)
        is_floor_transition = is_floor_transition or ground_flags.get("isFloorTransition", False)
        if ground_id is not None:
            floorchange = floorchange_by_id.get(ground_id)

        for raw_item in tile.get("items", []):
            uid = raw_item.get("uid")
            if uid is not None and uid >= MARKER_UID_MIN:
                continue
            item_flags = _flags(raw_item.get("id"))
            unpass = unpass or item_flags.get("unpass", False)
            is_floor_transition = is_floor_transition or item_flags.get("isFloorTransition", False)
            if floorchange is None:
                floorchange = floorchange_by_id.get(raw_item.get("id"))

        tiles[key] = {
            "x": x,
            "y": y,
            "z": z,
            "unpass": unpass,
            "isFloorTransition": is_floor_transition,
            "floorchange": floorchange,
        }

    return list(tiles.values())


def build_walkable_graph(tiles: List[Dict]) -> Dict[Node, Set[Node]]:
    """Walkable tiles -> an undirected adjacency map. Tiles flagged `unpass`
    are excluded entirely (never a node). Same-floor neighbors (orthogonal +
    diagonal) all cost 1 — no diagonal penalty. A tile flagged
    `isFloorTransition` also gets an edge to the same (x, y) on both z-1 and
    z+1 whenever that neighbor is itself walkable (ADR 0002: the true up/down
    direction can't be derived from the flag alone, so both directions get
    an edge rather than guessing).

    A tile carrying a `floorchange` gets the edge that value *names* — one
    tile over and one floor up for a ramp, straight down for a hole (see
    `FLOORCHANGE_DELTAS`). This is the accurate half of the two: it comes from
    Canary's own `items.xml` rather than from a render-flag heuristic, and it
    knows the direction, so a ramp that moves you sideways connects where the
    same-(x, y) bridge above silently could not.

    Both rules stay, and neither is redundant: `floorchange` covers what you
    *walk* onto (stairs, ramps, holes), `isFloorTransition` covers what you
    *use* (ladders, rope spots), which carry no `floorchange` at all."""
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

        delta = FLOORCHANGE_DELTAS.get(t.get("floorchange") or "")
        if delta:
            neighbor = (x + delta[0], y + delta[1], z + delta[2])
            if neighbor in walkable:
                _connect(node, neighbor)

    return graph


def tile_distances(graph: Dict[Node, Set[Node]], sources: Dict[Node, int], targets: Set[Node]) -> Dict[Node, int]:
    """Shortest tile-count from `sources` to every node in `targets` that's
    reachable, stopping as soon as every target has been found (or the graph
    is exhausted) rather than flooding the whole thing.

    `sources` maps a starting tile to the cost of *entering* the graph there
    (0 for a location standing on its own walkable tile; see
    `approach_costs`). Every graph edge still costs 1 — the seed costs are
    the only non-uniform part, which is why this pops the cheapest frontier
    node rather than trusting FIFO order."""
    remaining = set(targets) - {node for node in sources if node in graph}
    found: Dict[Node, int] = {node: cost for node, cost in sources.items()
                              if node in graph and node in targets}
    if not remaining:
        return found

    visited = set()
    frontier = [(cost, node) for node, cost in sources.items() if node in graph]
    heapq.heapify(frontier)
    while frontier and remaining:
        dist, node = heapq.heappop(frontier)
        if node in visited:
            continue
        visited.add(node)
        for neighbor in graph.get(node, ()):
            if neighbor in visited:
                continue
            if neighbor in remaining:
                found[neighbor] = dist + 1
                remaining.discard(neighbor)
            heapq.heappush(frontier, (dist + 1, neighbor))
    return found


def approach_costs(node: Node, graph: Dict[Node, Set[Node]], reach: int) -> Dict[Node, int]:
    """The tiles a location can be reached *from*, mapped to how many tiles
    away from it they are -> what `tile_distances` takes as `sources`.

    With `reach` 0 that's just the location's own tile, when walkable. A
    larger reach exists for NPCs: most of Rookgaard's shopkeepers stand
    behind an `unpass` counter, so their own tile is a two-tile pocket the
    player can never walk into — the player stops on the far side of the
    counter and trades across it. Charging each approach tile its own
    distance (rather than seeding them all at 0) keeps that honest in both
    directions: an NPC standing in the open street still enters at its own
    tile for 0 and its distances are untouched, while a shopkeeper's start
    at the 2 tiles that actually separate the player from the counter."""
    costs: Dict[Node, int] = {}
    x, y, z = node
    for dx in range(-reach, reach + 1):
        for dy in range(-reach, reach + 1):
            candidate = (x + dx, y + dy, z)
            if candidate in graph:
                costs[candidate] = max(abs(dx), abs(dy))
    return costs


def build_travel_graph(
    graph: Dict[Node, Set[Node]], locations: List[Dict], npc_reach: int = DEFAULT_NPC_REACH
) -> List[Dict]:
    """One search per location, reaching every other location (early exit
    once all are found) -> one {from, to, tileCount} edge per reachable pair.
    Distance is computed independently per pair (real tiles walked, never
    inferred through a shared hub, never euclidean), and a pair on
    disconnected regions of the graph simply produces no edge.

    A location is reached at whichever of its approach tiles is cheapest
    (see `approach_costs`) — for everything but an NPC that is its own tile
    and nothing else. Two locations sharing a tile are zero tiles apart, and
    that edge is emitted like any other: since NPCs became travel
    destinations, two of them behind the same tavern counter are two
    destinations the player picks between, not graph noise to collapse.

    Edges are canonical — `from` < `to`, one per unordered pair, never a
    self-edge — and the list is sorted, so re-running against an unchanged
    map produces a byte-identical fragment."""
    approaches: List[Tuple[str, Dict[Node, int]]] = [
        (loc["id"], approach_costs(
            (loc["x"], loc["y"], loc["z"]), graph, npc_reach if loc.get("type") == "NPC" else 0
        ))
        for loc in locations
    ]
    every_approach_tile = {node for _, costs in approaches for node in costs}

    edges: List[Dict] = []
    seen_pairs: Set[frozenset] = set()

    def _emit(a_id: str, b_id: str, dist: int) -> None:
        if a_id == b_id:
            return
        pair = frozenset((a_id, b_id))
        if pair in seen_pairs:
            return
        seen_pairs.add(pair)
        low, high = sorted((a_id, b_id))
        edges.append({"from": low, "to": high, "tileCount": dist})

    for loc_id, costs in approaches:
        if not costs:
            continue
        distances = tile_distances(graph, costs, every_approach_tile)
        for other_id, other_costs in approaches:
            if other_id == loc_id:
                continue
            reachable = [distances[node] + cost for node, cost in other_costs.items()
                         if node in distances]
            if reachable:
                _emit(loc_id, other_id, min(reachable))

    edges.sort(key=lambda e: (e["from"], e["to"]))
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


_OUTFIT_BLOCK_START_RE = re.compile(r"npcConfig\.outfit\s*=\s*\{")

#: `lookType` is the only required key — an NPC with no colours is a valid
#: outfit (the base sprite), and `lookAddons` is absent on most of them.
_OUTFIT_KEYS = ("lookType", "lookHead", "lookBody", "lookLegs", "lookFeet", "lookAddons")


def parse_npc_outfit_lua(lua_text: str) -> Optional[Dict]:
    """A Canary npc .lua file's text -> its `npcConfig.outfit` table, or None
    when the file has none.

    Same file the shop already comes from, and that is the whole point: the
    two facts about an NPC that the game needs to *draw* and *trade with* him
    live side by side in Canary, and reading the file twice to fetch them
    separately would be two passes over the same text.

    `lookType` is what indexes the outfit atlases the client already ships
    (`/assets/outfits/<lookType>.png`); the four colour indices and the addon
    bitmask are what turn the base sprite into *this* NPC. An outfit table
    without `lookType` is not an outfit, and is reported as None rather than
    as a half-filled dict — the consumer would have nothing to draw.
    """
    block_match = _OUTFIT_BLOCK_START_RE.search(lua_text)
    if not block_match:
        return None

    block = _extract_braced_block(lua_text, block_match.end())
    fields = {
        m.group(1): _parse_lua_scalar(m.group(2))
        for m in _SHOP_FIELD_RE.finditer(block)
        if m.group(1) in _OUTFIT_KEYS
    }

    if "lookType" not in fields:
        return None

    return {key: int(fields[key]) for key in _OUTFIT_KEYS if key in fields}


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


def build_npc_location(
    npc: Dict,
    city_prefix: str,
    shop: Optional[List[Dict]],
    outfit: Optional[Dict] = None,
) -> Dict:
    """An NPC (position + name) plus its already-resolved shop (or None) ->
    a `locations` entry. No sign involved, no `displayName` curation — the
    NPC's real in-game name is already a good display name. The id follows
    the same CIDADE-TIPO-slug shape every other POI type uses
    (`ROOK-NPC-obi`), city/type uppercase, slug lowercase — `city`/`status`
    are derived from that same id."""
    city = city_prefix.upper()
    status = city_ids.derive_status(city)
    entry: Dict = {
        "id": f"{city}-NPC-{slugify(npc['name'])}",
        "type": "NPC",
        "x": npc["x"],
        "y": npc["y"],
        "z": npc["z"],
        "displayName": npc["name"],
        "city": city,
    }
    if status is not None:
        entry["status"] = status
    if outfit is not None:
        entry["outfit"] = outfit
    if shop is not None:
        entry["shop"] = shop
    return entry


def build_npc_locations(
    npcs: List[Dict],
    city_prefix: str,
    shops_by_name: Dict[str, Optional[List[Dict]]],
    outfits_by_name: Optional[Dict[str, Optional[Dict]]] = None,
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
        outfit = (outfits_by_name or {}).get(name)
        locations.append(build_npc_location(npc, city_prefix, shop, outfit))
    return locations, unmatched


# ======================================================
# Fragment assembly + catalog merge
# ======================================================


def build_travel_fragment(locations: List[Dict], travel_graph: List[Dict]) -> Dict:
    """The one place the fragment's shape is spelled out. `locations` is
    already both sources combined — sign-marked POIs and NPCs stop being two
    lists the moment they enter the same graph, and re-splitting them here
    just to concatenate them again would be ceremony."""
    return {"locations": locations, "travelGraph": travel_graph}


# ======================================================
# Rejecting nodes with no way in
# ======================================================

def _poi_without_edge_line(rejection: Dict) -> str:
    return (f"  {rejection['id']}  ({rejection['type']})  "
            f"x={rejection['x']} y={rejection['y']} z={rejection['z']}")


def _edge_without_poi_line(rejection: Dict) -> str:
    cited = ", ".join(f"{edge['from']}<->{edge['to']} ({edge['tileCount']} tiles)"
                      for edge in rejection["edges"])
    return f"  {rejection['id']}  sem coordenada  citado por: {cited}"


def _hunt_without_poi_line(rejection: Dict) -> str:
    return f"  {rejection['id']}  {rejection['name']}  sem coordenada de mundo"


# The three ways a node can have no way into the travel graph: the reason,
# what to do about it, and how its line reads — one row per case, because
# the three travel together (the report groups by reason, in this order, and
# each case's line shows different fields, since each has different evidence
# to show). Ordered most actionable (a coordinate to open in the map editor)
# first, vaguest (a hunt whose entrance nobody has marked yet) last.
_REJECTION_CASES = (
    (
        "poi-without-edge",
        "POI com coordenada e sem aresta — a placa existe no OTBM, mas o tile dela não\n"
        "alcança nenhum outro POI da cidade (ilhado por parede/água, ou a placa está num\n"
        "tile intransponível). Abra a coordenada no editor de mapa e mova a placa pra um\n"
        "tile caminhável ligado ao resto da cidade.",
        _poi_without_edge_line,
    ),
    (
        "edge-without-poi",
        "Id citado numa aresta que não é POI — não existe placa com esse id em lugar nenhum,\n"
        "então ele não tem coordenada: é id escrito errado na fonte (ex: um dígito a mais).\n"
        "Corrija o texto da placa no OTBM pro formato CIDADE-TIPO-NNNN, com exatamente 4 dígitos.",
        _edge_without_poi_line,
    ),
    (
        "hunt-without-poi",
        "Hunt sem POI de entrada — o mapa da hunt existe em extractor/maps/, mas nenhuma placa\n"
        "marca por onde se entra nela. A hunt não tem coordenada de mundo (o startPosition dela é\n"
        "posição dentro do próprio mapa da hunt), então só o OTBM sabe onde fica: coloque a placa\n"
        "com esse id na entrada, no editor de mapa.",
        _hunt_without_poi_line,
    ),
)

REJECTION_REASONS = tuple(reason for reason, _, _ in _REJECTION_CASES)


def apply_graph_rejections(
    locations: List[Dict], edges: List[Dict], hunts: Sequence[Dict] = ()
) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    """Splits a freshly built graph into what may be emitted and what has no
    way in -> (kept_locations, kept_edges, rejections).

    A node nobody can travel to is rejected here rather than emitted for a
    downstream gate to drop in silence: while `tileCount` only decorated a
    label, an unreachable destination cost nothing; once travel is
    authoritative it is a hunt the player simply cannot play, with no trace
    of why. Each rejection carries whatever that case actually has to
    identify it (see `_REJECTION_CASES`) — a coordinate is not invented for a
    node that never had one.

    Phantom edges go first, so degree is counted over links that will still
    exist: a POI whose only edge cited a non-existent id is isolated too, and
    is rejected in the same pass. A hunt whose POI exists but was rejected is
    reported once, under that POI's own (more actionable) case.

    `hunts` is [{"id", "name"}] — the hunt maps on disk, whose entrance the
    graph is checked against. Order is by case, then id, so two runs against
    an unchanged map produce identical output."""
    location_ids = {loc["id"] for loc in locations}

    kept_edges: List[Dict] = []
    edges_by_phantom: Dict[str, List[Dict]] = {}
    for edge in edges:
        phantoms = [side for side in (edge["from"], edge["to"]) if side not in location_ids]
        if not phantoms:
            kept_edges.append(edge)
            continue
        for phantom in phantoms:
            edges_by_phantom.setdefault(phantom, []).append(edge)

    degree: Dict[str, int] = {}
    for edge in kept_edges:
        degree[edge["from"]] = degree.get(edge["from"], 0) + 1
        degree[edge["to"]] = degree.get(edge["to"], 0) + 1

    kept_locations = [loc for loc in locations if degree.get(loc["id"], 0) > 0]

    rejections: List[Dict] = []
    for loc in locations:
        if degree.get(loc["id"], 0) == 0:
            rejections.append({
                "reason": "poi-without-edge",
                "id": loc["id"],
                "type": loc.get("type"),
                "x": loc["x"],
                "y": loc["y"],
                "z": loc["z"],
            })
    for phantom_id, citing_edges in edges_by_phantom.items():
        rejections.append({"reason": "edge-without-poi", "id": phantom_id, "edges": citing_edges})
    for hunt in hunts:
        if hunt["id"] not in location_ids:
            rejections.append({"reason": "hunt-without-poi", "id": hunt["id"], "name": hunt["name"]})

    rejections.sort(key=lambda r: (REJECTION_REASONS.index(r["reason"]), r["id"]))
    return kept_locations, kept_edges, rejections


def format_rejection_report(rejections: List[Dict], city: str) -> str:
    """The rejection list -> the text file the user opens next to the map
    editor. Grouped by case, each group stating what to do about it, so a
    line is actionable without reading the spec. Deterministic: same
    rejections in, same bytes out, for a clean diff between runs."""
    lines = [
        f"# Nós sem entrada no grafo de viagem — {city}",
        "#",
        "# Gerado por build_travel_fragment.py. Nada aqui entrou no fragmento: são os nós que",
        "# ninguém consegue alcançar viajando, e o que fazer com cada um.",
        "",
    ]

    if not rejections:
        lines.append("Nenhum nó rejeitado.")
        return "\n".join(lines) + "\n"

    for reason, help_text, format_line in _REJECTION_CASES:
        group = [r for r in rejections if r["reason"] == reason]
        if not group:
            continue
        lines.append(f"## {reason} ({len(group)})")
        lines.append(help_text)
        lines.append("")
        lines.extend(format_line(rejection) for rejection in group)
        lines.append("")

    return "\n".join(lines).rstrip("\n") + "\n"


def merge_locations_into_catalog(
    catalog_locations: List[Dict], fragment_locations: List[Dict], city: str
) -> Dict[str, str]:
    """Upserts each fragment location into catalog_locations in place, by id.
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
    the same db entry instead of duplicating it.

    An entry of `city` already in the db that this run's fragment no longer
    carries (a rejected node, or a sign deleted from the OTBM) is reported as
    `"stale"` but never removed: unlike an edge, a location holds curated
    fields, and a node rejected on one run is often a sign the user is
    halfway through fixing. Edges are the collection that gets replaced
    outright (see merge_travel_graph_into_catalog)."""
    by_id = {entry["id"]: i for i, entry in enumerate(catalog_locations)}
    report: Dict[str, str] = {}

    fragment_ids = {loc["id"] for loc in fragment_locations}
    for entry in catalog_locations:
        if city_ids.derive_city(entry["id"]) == city and entry["id"] not in fragment_ids:
            report[entry["id"]] = "stale"

    for loc in fragment_locations:
        existing_index = by_id.get(loc["id"])
        if existing_index is None:
            catalog_locations.append(dict(loc))
            by_id[loc["id"]] = len(catalog_locations) - 1
            report[loc["id"]] = "added"
            continue

        existing = catalog_locations[existing_index]
        merged = dict(loc)
        if "_todo" not in existing:
            for field in CURATED_LOCATION_FIELDS:
                if field in existing:
                    merged[field] = existing[field]
            merged.pop("_todo", None)
        catalog_locations[existing_index] = merged
        report[loc["id"]] = "updated"

    return report


def merge_travel_graph_into_catalog(
    catalog_travel_graph: List[Dict], fragment_travel_graph: List[Dict], city: str
) -> Dict[str, str]:
    """Replaces `city`'s slice of catalog_travel_graph in place with the fragment's
    edges — the fragment is the complete edge set for that city, so an edge
    missing from it stops existing in the db too.

    This is a replacement and not an upsert on purpose. Upserting is how 23
    edges no BFS ever produced (one of them citing `ROOK-HUNT-00015`, an id
    a digit too long that is not a POI) outlived the map they came from and
    ended up in a versioned catalog nobody could explain. An edge with even
    one foot in `city` belongs to this run's regeneration; edges wholly
    between other cities are left exactly as they are.

    Reports per unordered pair: `"added"`, `"updated"` (in the fragment,
    was already in the db) or `"removed"` (was in the db for this city, the
    fragment doesn't carry it). Always mechanical — no human curation lives
    on an edge, so tileCount is simply overwritten with the fresh value."""

    def _label(edge: Dict) -> str:
        return f"{edge['from']}<->{edge['to']}"

    def _touches_city(edge: Dict) -> bool:
        return city in (city_ids.derive_city(edge["from"]), city_ids.derive_city(edge["to"]))

    existing_pairs = {frozenset((e["from"], e["to"])) for e in catalog_travel_graph}
    fragment_pairs = {frozenset((e["from"], e["to"])) for e in fragment_travel_graph}
    report: Dict[str, str] = {}

    kept: List[Dict] = []
    for edge in catalog_travel_graph:
        if frozenset((edge["from"], edge["to"])) in fragment_pairs:
            continue  # re-appended below, with the fresh tileCount
        if _touches_city(edge):
            report[_label(edge)] = "removed"
            continue
        kept.append(edge)

    for edge in fragment_travel_graph:
        pair = frozenset((edge["from"], edge["to"]))
        report[_label(edge)] = "updated" if pair in existing_pairs else "added"
        kept.append(dict(edge))

    catalog_travel_graph[:] = kept
    return report


def merge_travel_fragment_into_catalog(db: Dict, fragment: Dict, city: str) -> Dict[str, Dict[str, str]]:
    return {
        "locations": merge_locations_into_catalog(db["locations"], fragment["locations"], city),
        "travelGraph": merge_travel_graph_into_catalog(db["travelGraph"], fragment["travelGraph"], city),
    }
