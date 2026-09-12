"""Pure grid-sheet packing model for map.json v6.

Assigns each appearance sequential gids inside a fixed-column-width sheet. No
I/O — rendering the actual sheet PNGs happens in build_phaser_map.py, which
consumes the plan this module produces.

**Footprint é a chave inteira**: `"sheet-32"`, `"sheet-64"`. O v5 agrupava por
`(layerClass, bucket)` — `"object-32"`, `"ground-64"` — e emitia de nove a doze
folhas por mapa; sem papel de render para agrupar, sobram duas, que é o ponto
(ver `.scratch/modelo-render-rme/issues/05-sheets-por-bucket.md`). O agrupamento
v5 saiu junto com o formato.

O contrato dentro da folha é o mesmo: square cell, row-major
left-to-right fill, sprite anchored to the cell's top-left corner, index-to-
position as pure arithmetic with no atlas file.

Validated against real sprite-size data (see SPRITE_METADATA.md) and edge
cases in a throwaway prototype before being lifted here — see
.scratch/map-sprite-sheets-v4/spec.md.
"""

BUCKET_SIZES = [32, 64, 128]

# The texture size every WebGL 1.0 implementation is required to support, and
# the floor of what any GPU in the wild offers. A sheet is only safe if both
# dimensions stay at or under it.
SAFE_TEXTURE_SIZE = 2048

# Cada footprint vira uma folha só, então uma grade que só cresce para baixo
# estoura a textura: a 16 colunas de 32px, quatro dos 20 mapas produziam folhas
# de 2240-2688px de altura. Preencher primeiro a largura segura
# (SAFE_TEXTURE_SIZE / cell) mantém a folha quase quadrada e limita a
# capacidade a 2048x2048 — 4096 células a 32px, 1024 a 64px, 256 a 128px, bem
# acima do que qualquer mapa usa.
COLUMNS_BY_BUCKET = {size: SAFE_TEXTURE_SIZE // size for size in BUCKET_SIZES}


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
        """Colunas numa folha desse bucket."""
        return COLUMNS_BY_BUCKET[bucket]

    def add_appearance(self, appearance_id, width, height, frame_count=1):
        """Reserve `frame_count` consecutive cells for an appearance."""
        cell = bucket_for(width, height)
        sheet_key = f"sheet-{cell}"
        sheet = self.sheets.setdefault(
            sheet_key,
            {"cellSize": cell, "columns": self.columns_for_bucket(cell), "count": 0},
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
