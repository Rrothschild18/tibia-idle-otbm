"""Pure grid-sheet packing model for map.json v4.

Groups objectDefs appearances into fixed-column-width sheets by
(layerClass, size bucket) and assigns each appearance sequential gids
within its sheet. No I/O — rendering the actual sheet PNGs happens in
build_phaser_map.py, which consumes the plan this module produces.

Validated against real sprite-size data (see SPRITE_METADATA.md) and edge
cases in a throwaway prototype before being lifted here — see
.scratch/map-sprite-sheets-v4/spec.md.
"""

BUCKET_SIZES = [32, 64, 128]
COLUMNS_BY_BUCKET = {32: 16, 64: 12, 128: 8}


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

    def columns_for_bucket(self, bucket: int) -> int:
        return COLUMNS_BY_BUCKET[bucket]

    def add_appearance(self, appearance_id, layer_class, width, height, frame_count=1):
        cell = bucket_for(width, height)
        sheet_key = f"{layer_class}-{cell}"
        sheet = self.sheets.setdefault(
            sheet_key, {"cellSize": cell, "columns": COLUMNS_BY_BUCKET[cell], "count": 0}
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
