"""Pure grid-sheet packing model for map.json v4/v6.

Assigns each appearance sequential gids inside a fixed-column-width sheet. No
I/O — rendering the actual sheet PNGs happens in build_phaser_map.py, which
consumes the plan this module produces.

Two grouping keys, one per map format:

- **v4/v5** groups by `(layerClass, size bucket)` — `"object-32"`, `"ground-64"`.
- **v6** has no render role left to group by, so footprint is the whole key:
  pass `layer_class=None` and get `"sheet-32"`. That collapses the nine-to-twelve
  sheets a map used to emit down to two, which is the point — see
  `.scratch/modelo-render-rme/issues/05-sheets-por-bucket.md`.

Either way the in-sheet contract is the same: square cell, row-major
left-to-right fill, sprite anchored to the cell's top-left corner, index-to-
position as pure arithmetic with no atlas file.

Validated against real sprite-size data (see SPRITE_METADATA.md) and edge
cases in a throwaway prototype before being lifted here — see
.scratch/map-sprite-sheets-v4/spec.md.
"""

BUCKET_SIZES = [32, 64, 128]
COLUMNS_BY_BUCKET = {32: 16, 64: 12, 128: 8}

# The texture size every WebGL 1.0 implementation is required to support, and
# the floor of what any GPU in the wild offers. A sheet is only safe if both
# dimensions stay at or under it.
SAFE_TEXTURE_SIZE = 2048

# v6 packs every appearance of a footprint into one sheet, so a grid that only
# ever grows downward runs out of texture: at 16 columns of 32px, four of the
# 20 maps produced sheets 2240-2688px tall. Filling the safe width first
# (SAFE_TEXTURE_SIZE / cell) keeps each sheet square-ish, and caps its capacity
# at a full 2048x2048 — 4096 cells at 32px, 1024 at 64px, 256 at 128px, all far
# above what any single map uses. The v5 numbers above stay put: changing them
# would renumber the `tilesets` the game reads today.
V6_COLUMNS_BY_BUCKET = {size: SAFE_TEXTURE_SIZE // size for size in BUCKET_SIZES}


def bucket_for(width: int, height: int) -> int:
    """Round a sprite's footprint up to the nearest bucket that fits it."""
    largest = max(width, height)
    for size in BUCKET_SIZES:
        if largest <= size:
            return size
    return BUCKET_SIZES[-1]  # clamp anything bigger than the largest bucket


class SheetPacker:
    """Incrementally assigns appearances to grid sheets, one call at a time."""

    def __init__(self):
        self.sheets = {}       # sheet_key -> {"cellSize", "columns", "count"}
        self.appearances = {}  # appearance_id -> {"sheet", "gids", "width", "height"}

    def columns_for_bucket(self, bucket: int, size_only: bool = False) -> int:
        """Columns in a sheet of this bucket. `size_only=True` asks for the v6
        grid, which is wider — see V6_COLUMNS_BY_BUCKET."""
        table = V6_COLUMNS_BY_BUCKET if size_only else COLUMNS_BY_BUCKET
        return table[bucket]

    def add_appearance(self, appearance_id, layer_class, width, height, frame_count=1):
        """Reserve `frame_count` consecutive cells for an appearance.

        `layer_class=None` selects the v6 sheet — footprint is the whole key,
        and the grid is the wider one.
        """
        cell = bucket_for(width, height)
        size_only = layer_class is None
        sheet_key = f"sheet-{cell}" if size_only else f"{layer_class}-{cell}"
        sheet = self.sheets.setdefault(
            sheet_key,
            {"cellSize": cell, "columns": self.columns_for_bucket(cell, size_only), "count": 0},
        )
        start = sheet["count"]
        gids = list(range(start, start + frame_count))
        sheet["count"] += frame_count

        self.appearances[appearance_id] = {
            "sheet": sheet_key, "gids": gids, "width": width, "height": height,
        }
        return sheet_key, gids

    def sheet_dims(self, sheet_key):
        sheet = self.sheets[sheet_key]
        columns = sheet["columns"]
        rows = -(-sheet["count"] // columns) if sheet["count"] else 0  # ceil div
        cell = sheet["cellSize"]
        return {
            "columns": columns, "rows": rows, "cellSize": cell,
            "pixelWidth": columns * cell, "pixelHeight": rows * cell,
            "occupiedCells": sheet["count"], "totalCells": columns * rows,
        }

    def exceeds_safe_texture_size(self, sheet_key):
        """True when either dimension of the rendered sheet would need a
        texture bigger than every GPU is guaranteed to provide."""
        dims = self.sheet_dims(sheet_key)
        return max(dims["pixelWidth"], dims["pixelHeight"]) > SAFE_TEXTURE_SIZE

    def gid_to_rect(self, sheet_key, gid):
        sheet = self.sheets[sheet_key]
        col = gid % sheet["columns"]
        row = gid // sheet["columns"]
        cell = sheet["cellSize"]
        return {"x": col * cell, "y": row * cell, "w": cell, "h": cell, "row": row, "col": col}

    def gid_owner(self, sheet_key):
        """gid -> appearance_id for a sheet, e.g. for rendering/debugging."""
        owner = {}
        for app_id, data in self.appearances.items():
            if data["sheet"] == sheet_key:
                for gid in data["gids"]:
                    owner[gid] = app_id
        return owner
