import struct
import json

NODE_START = 0xFE
NODE_END = 0xFF
ESCAPE = 0xFD

# ======================
# Binary parsing
# ======================

def read_node(f):
    data = []
    children = []

    while True:
        b = f.read(1)
        if not b:
            break

        b = b[0]

        if b == NODE_END:
            break

        if b == NODE_START:
            children.append(read_node(f))
            continue

        if b == ESCAPE:
            data.append(f.read(1)[0])
        else:
            data.append(b)

    return {"data": data, "children": children}

def parse_otbm(path):
    with open(path, "rb") as f:
        f.read(4)  # OTBM
        f.read(4)  # version
        return read_node(f)

# ======================
# Extract real tiles
# ======================

def extract_tiles(node, tiles=None):
    if tiles is None:
        tiles = []

    data = node["data"]

    # Tile node marker
    if len(data) >= 6 and data[0] == 0x05:
        x = data[1] | (data[2] << 8)
        y = data[3] | (data[4] << 8)
        z = data[5]

        # Extract ItemNodes
        items = []
        for child in node["children"]:
            cdata = child["data"]
            if len(cdata) >= 3 and cdata[0] == 0x06:
                item_id = cdata[1] | (cdata[2] << 8)
                items.append(item_id)

        # Tile válido precisa de ground
        if items:
            tiles.append({
                "x": x,
                "y": y,
                "z": z,
                "ground": items[0],
                "top": items[-1] if len(items) > 1 else None
            })

    for child in node["children"]:
        extract_tiles(child, tiles)

    return tiles

# ======================
# Build Phaser map
# ======================

def build_phaser_map(tiles):
    min_x = min(t["x"] for t in tiles)
    min_y = min(t["y"] for t in tiles)
    max_x = max(t["x"] for t in tiles)
    max_y = max(t["y"] for t in tiles)

    width = max_x - min_x + 1
    height = max_y - min_y + 1

    ground = [0] * (width * height)
    items = [0] * (width * height)

    gid_map = {}
    next_gid = 1

    def gid(item_id):
        nonlocal next_gid
        if item_id not in gid_map:
            gid_map[item_id] = next_gid
            next_gid += 1
        return gid_map[item_id]

    def idx(x, y):
        return y * width + x

    for t in tiles:
        x = t["x"] - min_x
        y = t["y"] - min_y
        i = idx(x, y)

        ground[i] = gid(t["ground"])

        if t["top"]:
            items[i] = gid(t["top"])

    tileset = {
        "firstgid": 1,
        "name": "tibia",
        "tilewidth": 32,
        "tileheight": 32,
        "spacing": 0,
        "margin": 0,
        "image": "assets/tileset.png",
        "imagewidth": 32,
        "imageheight": 32
    }

    return {
        "version": 1,
        "orientation": "orthogonal",
        "width": width,
        "height": height,
        "tilewidth": 32,
        "tileheight": 32,
        "layers": [
            {
                "id": 1,
                "name": "Ground",
                "type": "tilelayer",
                "visible": True,
                "opacity": 1,
                "x": 0,
                "y": 0,
                "width": width,
                "height": height,
                "data": ground
            },
            {
                "id": 2,
                "name": "Items",
                "type": "tilelayer",
                "visible": True,
                "opacity": 1,
                "x": 0,
                "y": 0,
                "width": width,
                "height": height,
                "data": items
            }
        ],
        "tilesets": [tileset]
    }

# ======================
# Main
# ======================

if __name__ == "__main__":
    root = parse_otbm("rats.otbm")
    tiles = extract_tiles(root)

    print("Tiles válidos:", len(tiles))

    tilemap = build_phaser_map(tiles)

    with open("map_phaser.json", "w") as f:
        json.dump(tilemap, f, indent=2)

    print("✔ JSON do Phaser gerado corretamente")