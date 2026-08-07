"""The one place that knows how to walk a raw otbm2json dump.

A dump (`raw-maps/<mapa>.raw.json`, produced by dump_otbm.js) nests tiles
three levels deep — `data.nodes[] -> features[] -> tiles[]` — and stores tile
coordinates *relative to the feature (tile area) that contains them*, so a
tile's real position is only knowable together with its feature's origin.
Every consumer of a dump needs that same walk, and every hand-rolled copy of
it repeats the same two easy-to-get-wrong details: adding `feature.x/y` to
`tile.x/y`, and defaulting a missing `feature.z` to the surface floor. Both
live here now, once.

Two views over the same walk, because floors and tiles are not the same
question:

- `iter_tiles(dump)` — every tile, already resolved to absolute (x, y, z).
- `floor_zs(dump)` — which floors the dump *declares*, whether or not any of
  them ended up carrying a tile.
"""

from typing import Dict, Iterator, Set, Tuple

# A feature with no explicit `z` is on the surface. Real dumps do omit the
# key (it is absent throughout several ROOK hunt maps), so this default is
# load-bearing, not defensive.
DEFAULT_Z = 7

Tile = Tuple[int, int, int, Dict]


def _iter_features(dump: Dict) -> Iterator[Tuple[int, int, int, Dict]]:
    """Yields (base_x, base_y, z, feature) for every tile area in the dump."""
    for node in dump.get("data", {}).get("nodes", []):
        for feature in node.get("features", []):
            yield (
                feature.get("x", 0),
                feature.get("y", 0),
                feature.get("z", DEFAULT_Z),
                feature,
            )


def iter_tiles(dump: Dict) -> Iterator[Tile]:
    """Yields (x, y, z, tile) for every tile in the dump, in dump order, with
    x/y already made absolute (feature origin + tile offset).

    A tile missing either coordinate is skipped: it cannot be placed on the
    map, and a caller that guessed 0 would silently stack it onto the
    feature's corner.
    """
    for base_x, base_y, z, feature in _iter_features(dump):
        for tile in feature.get("tiles", []):
            tx, ty = tile.get("x"), tile.get("y")
            if tx is None or ty is None:
                continue
            yield base_x + tx, base_y + ty, z, tile


def floor_zs(dump: Dict) -> Set[int]:
    """Every z declared by a feature — deliberately *not* derived from
    `iter_tiles`.

    A feature can carry zero placeable tiles (40 of them do across the ROOK
    and TEST maps), and in three of those maps the only feature on floor 7 is
    one of the empty ones. Deriving floors from tiles would drop that floor
    from the map entirely, shifting output for maps nobody edited — so a
    declared floor stays a floor, even when empty.
    """
    return {z for _, _, z, _ in _iter_features(dump)}
