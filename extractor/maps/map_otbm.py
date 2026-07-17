import json
import math

TILE_SIZE = 32
TILES_PER_ROW = 50   # controla o formato do mapa
DEFAULT_TILE_GID = 1

# ======================
# Load tiles
# ======================

with open("out.json", "r") as f:
    tiles = json.load(f)

tile_count = len(tiles)

if tile_count == 0:
    raise RuntimeError("out.json vazio")

# ======================
# Build artificial grid
# ======================

width = TILES_PER_ROW
height = math.ceil(tile_count / width)

print(f"Tiles: {tile_count}")
print(f"Mapa artificial: {width}x{height}")

data = [0] * (width * height)

for i in range(tile_count):
    data[i] = DEFAULT_TILE_GID

# ======================
# Phaser map
# ======================

phaser_map = {
    "version": 1,
    "orientation": "orthogonal",
    "width": width,
    "height": height,
    "tilewidth": TILE_SIZE,
    "tileheight": TILE_SIZE,
    "layers": [
        {
            "id": 1,
            "name": "Tiles",
            "type": "tilelayer",
            "visible": True,
            "opacity": 1,
            "x": 0,
            "y": 0,
            "width": width,
            "height": height,
            "data": data
        }
    ],
    "tilesets": [
        {
            "firstgid": 1,
            "name": "debug",
            "tilewidth": TILE_SIZE,
            "tileheight": TILE_SIZE,
            "spacing": 0,
            "margin": 0,
            "image": "assets/debug.png",
            "imagewidth": TILE_SIZE,
            "imageheight": TILE_SIZE
        }
    ]
}

with open("out_phaser.json", "w") as f:
    json.dump(phaser_map, f, indent=2)

print("✔ Tilemap compacto gerado")