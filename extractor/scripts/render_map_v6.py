"""Render a v6 `map.json` floor to PNG, off-line, the way the Phaser client draws it.

Exists to answer "what does floor z actually look like, and which pixels does
nothing paint?" without a browser: a screenshot only shows the viewport around
the player, and a floor's bugs live at its edges. Everything here mirrors
`libs/phaser-game/src/lib/utils/` in `tibia-idle` — `tile-stack.ts` for the
anchor/elevation math, `constants.ts` for the paint order, `map-loader.ts` for
the ground/item split. Where it deviates the deviation is marked.

Unpainted pixels come out as the scene's own background colour, so a rendered
floor answers "is this hole real?" by eye.

    python extractor/scripts/render_map_v6.py <CIDADE>/<pasta> [--below MODEL]

`--below` picks how floors underneath the rendered one are drawn:

  none    only the floor itself — the raw footprint, nothing behind it
  peek    what ships today: `FloorPeekLayer` — a constant one-tile shift plus
          a hole mask built from `computeHoleTiles`
  client  the Tibia client's model: every visible floor below drawn in full,
          each offset `(k - z)` tiles, no mask, painter's algorithm on top
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parent.parent
READY_V6 = REPO / 'ready-maps'

TILE_SIZE = 32
MAX_STACK_ELEVATION = 24          # constants.ts
BACKGROUND = (2, 107, 198, 255)   # phaser-game.service.ts backgroundColor '#026bc6'

# How deep the client looks below the camera floor (floor-visibility.ts, which
# follows OTClient's calcLastVisibleFloor).
SEA_FLOOR = 7
UNDERGROUND_PEEK = 2


# ── map.json access ─────────────────────────────────────────────────────────

class MapV6:
    def __init__(self, path: Path):
        self.path = path
        self.data = json.loads(path.read_text(encoding='utf-8'))
        self.width = self.data['width']
        self.height = self.data['height']
        self.appearances = self.data['appearances']
        self.sheets = self.data['sheets']
        self.floors = self.data['floors']
        self._images: dict[str, Image.Image] = {}

    def floor_ids(self) -> list[int]:
        return sorted(int(z) for z in self.floors)

    def tiles(self, z: int) -> list[list[int]]:
        key = str(z)
        return self.floors[key]['tiles'] if key in self.floors else []

    def appearance(self, appearance_id: int) -> dict | None:
        return self.appearances.get(str(appearance_id))

    def sheet_image(self, sheet_key: str) -> Image.Image:
        if sheet_key not in self._images:
            img = Image.open(self.path.parent / 'sheets' / f'{sheet_key}.png')
            self._images[sheet_key] = img.convert('RGBA')
        return self._images[sheet_key]

    def ground_sheet_key(self) -> str | None:
        """The sheet whose cells are exactly one tile — the only one the tilemap can serve."""
        for key, sheet in self.sheets.items():
            if sheet['cellWidth'] == TILE_SIZE and sheet['cellHeight'] == TILE_SIZE:
                return key
        return None


def sprite_size(defn: dict) -> tuple[int, int]:
    return defn.get('spriteWidth', TILE_SIZE), defn.get('spriteHeight', TILE_SIZE)


def exceeds_tile(defn: dict) -> bool:
    w, h = sprite_size(defn)
    return w > TILE_SIZE or h > TILE_SIZE


def hash_string(value: str) -> int:
    """Java-style string hash — `hashString` in sprite-resolver.ts, so a random
    appearance picks the same variant here as in the client."""
    h = 0
    for ch in value:
        h = (h << 5) - h + ord(ch)
        h &= 0xFFFFFFFF
    if h >= 0x80000000:
        h -= 0x100000000
    return h


def select_gid(seed: str, tile_x: int, tile_y: int, defn: dict,
               appearance_id: int, slot: int) -> int:
    gids = defn.get('gids') or []
    if not defn.get('random') or len(gids) <= 1:
        return gids[0]
    h = hash_string(f'{seed}:{tile_x}:{tile_y}:{appearance_id}:{slot}')
    return gids[abs(h) % len(gids)]


# ── placement math (tile-stack.ts) ──────────────────────────────────────────

class Placement:
    __slots__ = ('appearance_id', 'slot', 'is_ground', 'defn',
                 'anchor_x', 'anchor_y', 'depth')

    def __init__(self, appearance_id, slot, is_ground, defn, anchor_x, anchor_y, depth):
        self.appearance_id = appearance_id
        self.slot = slot
        self.is_ground = is_ground
        self.defn = defn
        self.anchor_x = anchor_x
        self.anchor_y = anchor_y
        self.depth = depth


def tile_draw_order(tile: list[int]) -> list[int]:
    """`[tileX, tileY, ground, ...stack]` -> the ids in draw order, ground dropped when 0."""
    ground = tile[2]
    rest = tile[3:]
    return ([ground] if ground != 0 else []) + list(rest)


def paint_order_key(tile_x: int, tile_y: int, slot: int) -> tuple[int, int, int]:
    """Anti-diagonal, then column within it, then stack slot — constants.ts."""
    return (tile_x + tile_y, tile_x, slot)


def resolve_tile_stack(tile: list[int], m: MapV6) -> list[Placement]:
    tile_x, tile_y, ground = tile[0], tile[1], tile[2]
    has_ground = ground != 0
    base_x = (tile_x + 1) * TILE_SIZE
    base_y = (tile_y + 1) * TILE_SIZE

    out: list[Placement] = []
    elevation = 0
    for slot, appearance_id in enumerate(tile_draw_order(tile)):
        defn = m.appearance(appearance_id)
        shift = (defn or {}).get('shift') or {}
        out.append(Placement(
            appearance_id=appearance_id,
            slot=slot,
            is_ground=has_ground and slot == 0,
            defn=defn,
            anchor_x=base_x + shift.get('x', 0),
            anchor_y=base_y + shift.get('y', 0) - min(elevation, MAX_STACK_ELEVATION),
            depth=paint_order_key(tile_x, tile_y, slot),
        ))
        elevation += (defn or {}).get('elevation', 0)
    return out


def is_tilemap_ground(p: Placement, m: MapV6) -> bool:
    d = p.defn
    return (p.is_ground and d is not None and d.get('hasSprite') is not False
            and not d.get('animated') and not exceeds_tile(d)
            and d.get('sheet') == m.ground_sheet_key())


# ── drawing ─────────────────────────────────────────────────────────────────

def paste_placement(canvas: Image.Image, m: MapV6, tile: list[int], p: Placement,
                    off_x: int, off_y: int, seed: str) -> None:
    d = p.defn
    if d is None or d.get('hasSprite') is False or not d.get('sheet') or not d.get('gids'):
        return

    sheet_key = d['sheet']
    sheet = m.sheets[sheet_key]
    gid = d['gids'][0] if d.get('animated') else select_gid(
        seed, tile[0], tile[1], d, p.appearance_id, p.slot)

    columns = sheet['columns']
    cell_w, cell_h = sheet['cellWidth'], sheet['cellHeight']
    sx = (gid % columns) * cell_w
    sy = (gid // columns) * cell_h
    cell = m.sheet_image(sheet_key).crop((sx, sy, sx + cell_w, sy + cell_h))

    # `spriteFramePadding` — origin(1,1) anchors the *cell's* corner, so a
    # sprite smaller than its cell is nudged by the leftover space.
    w, h = sprite_size(d)
    pad_x, pad_y = cell_w - w, cell_h - h
    left = p.anchor_x + pad_x - cell_w + off_x
    top = p.anchor_y + pad_y - cell_h + off_y
    canvas.alpha_composite(cell, (left, top))


def draw_floor(canvas: Image.Image, m: MapV6, z: int, off_x: int, off_y: int,
               seed: str) -> None:
    """One floor, in paint order, offset by (off_x, off_y) pixels.

    The tile-sized ground goes down first as a block — the client keeps it in a
    single tilemap layer at `GROUND_TILEMAP_DEPTH`, below every item on the
    plane. A sprite that fits its cell can never draw outside its own tile, so
    hoisting it out of the scan cannot change the result.
    """
    tiles = m.tiles(z)
    resolved = [(t, resolve_tile_stack(t, m)) for t in tiles]

    for tile, placements in resolved:
        for p in placements:
            if is_tilemap_ground(p, m):
                paste_placement(canvas, m, tile, p, off_x, off_y, seed)

    scan = [(p.depth, tile, p)
            for tile, placements in resolved
            for p in placements
            if not is_tilemap_ground(p, m)]
    scan.sort(key=lambda entry: entry[0])
    for _, tile, p in scan:
        paste_placement(canvas, m, tile, p, off_x, off_y, seed)


# ── the floor-below models ──────────────────────────────────────────────────

def last_visible_floor(z: int) -> int:
    """floor-visibility.ts: above ground the view bottoms out at sea level; at or
    below it, two floors down."""
    return SEA_FLOOR if z < SEA_FLOOR else z + UNDERGROUND_PEEK


def occupied(m: MapV6, z: int) -> set[tuple[int, int]]:
    return {(t[0], t[1]) for t in m.tiles(z)}


def hole_tiles(m: MapV6, z: int) -> set[tuple[int, int]]:
    """`computeHoleTiles` — a column is a hole when the floor does not list the
    tile, or lists it with a floor-transition in the stack. Note what it does
    *not* ask: whether the listed tile actually floors the cell."""
    occ = occupied(m, z)
    holes = {(x, y) for y in range(m.height) for x in range(m.width) if (x, y) not in occ}
    for t in m.tiles(z):
        for appearance_id in tile_draw_order(t):
            defn = m.appearance(appearance_id) or {}
            if defn.get('flags', {}).get('isFloorTransition'):
                holes.add((t[0], t[1]))
                break
    return holes


def visible_floors_below(m: MapV6, z: int) -> list[tuple[int, set[tuple[int, int]]]]:
    """`computeVisibleFloorsBelow` — the cumulative hole walk, verbatim."""
    results = []
    max_z = last_visible_floor(z)
    existing = set(m.floor_ids())
    open_tiles = hole_tiles(m, z)

    k = z + 1
    while k <= max_z and open_tiles:
        if k not in existing:
            break
        content = occupied(m, k)
        visible = {t for t in open_tiles if t in content}
        if visible:
            results.append((k, visible))
        holes_at_k = hole_tiles(m, k)
        open_tiles = {t for t in open_tiles if t in holes_at_k}
        k += 1
    return results


def render_peek_below(canvas: Image.Image, m: MapV6, z: int, off_x: int, off_y: int,
                      seed: str) -> None:
    """What ships today: one `FloorPeekLayer` per visible floor below.

    Two things this reproduces on purpose, because they are the bug:
    the pixel offset is a constant one tile whatever `k` is, while the mask
    rects come from the *unshifted* columns.
    """
    for k, tiles in visible_floors_below(m, z):
        layer = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
        draw_floor(layer, m, k, off_x + TILE_SIZE, off_y + TILE_SIZE, seed)

        mask = Image.new('L', canvas.size, 0)
        for (tx, ty) in tiles:
            box = Image.new('L', (TILE_SIZE, TILE_SIZE), 255)
            mask.paste(box, (tx * TILE_SIZE + off_x, ty * TILE_SIZE + off_y))
        layer.putalpha(Image.composite(layer.getchannel('A'),
                                       Image.new('L', canvas.size, 0), mask))
        canvas.alpha_composite(layer)


def render_client_below(canvas: Image.Image, m: MapV6, z: int, off_x: int, off_y: int,
                        seed: str) -> None:
    """The client's model: every visible floor below, drawn whole, each shifted
    `(k - z)` tiles down-right, deepest first. No mask — the floor above covers
    the one below by being painted after it."""
    existing = set(m.floor_ids())
    floors = []
    for k in range(z + 1, last_visible_floor(z) + 1):
        if k not in existing:
            break
        floors.append(k)

    for k in reversed(floors):
        dz = k - z
        draw_floor(canvas, m, k, off_x + dz * TILE_SIZE, off_y + dz * TILE_SIZE, seed)


BELOW_MODELS = {
    'none': lambda *a: None,
    'peek': render_peek_below,
    'client': render_client_below,
}


# ── entry point ─────────────────────────────────────────────────────────────

def render(m: MapV6, z: int, below: str, seed: str) -> Image.Image:
    # Room for what spills outside the grid: sprites reach one tile up-left of
    # their own column, and a peeked floor is pushed down-right by one tile per
    # level below.
    pad = TILE_SIZE
    depth = max(0, last_visible_floor(z) - z)
    canvas = Image.new(
        'RGBA',
        ((m.width + 1 + depth) * TILE_SIZE, (m.height + 1 + depth) * TILE_SIZE),
        BACKGROUND,
    )
    BELOW_MODELS[below](canvas, m, z, pad, pad, seed)
    draw_floor(canvas, m, z, pad, pad, seed)
    return canvas


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('map', help='<CIDADE>/<pasta>, e.g. TEST/TEST-WASPS-DEBUG')
    parser.add_argument('--below', choices=sorted(BELOW_MODELS), default='client')
    parser.add_argument('--floors', help='comma-separated z list (default: all)')
    parser.add_argument('--out', default=None, help='output directory')
    parser.add_argument('--seed', default='tibia-idle')
    args = parser.parse_args()

    path = READY_V6 / args.map / 'map.json'
    if not path.exists():
        print(f'not found: {path}', file=sys.stderr)
        return 1

    m = MapV6(path)
    floors = ([int(z) for z in args.floors.split(',')] if args.floors
              else m.floor_ids())
    out_dir = Path(args.out) if args.out else path.parent / 'render'
    out_dir.mkdir(parents=True, exist_ok=True)

    for z in floors:
        image = render(m, z, args.below, args.seed)
        name = f'{Path(args.map).name}-z{z}-{args.below}.png'
        image.convert('RGB').save(out_dir / name)
        print(f'{out_dir / name}  ({image.width}x{image.height})')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
