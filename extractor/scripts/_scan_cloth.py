"""Ad-hoc: lista "green piece of cloth" (item 5910) nos dumps brutos."""
import json
import os
import sys

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
EXTRACTOR_DIR = os.path.dirname(SCRIPTS_DIR)
RAW_MAPS_DIR = os.path.join(EXTRACTOR_DIR, "raw-maps")

CLOTH_ITEM_ID = 5910


def iter_tiles(dump):
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


def main():
    cities = sys.argv[1:] or ["CARLIN", "THAIS", "VENORE", "KAZORDOON"]
    seen = {}
    for city in cities:
        path = os.path.join(RAW_MAPS_DIR, f"{city}.raw.json")
        with open(path, encoding="utf-8") as handle:
            dump = json.load(handle)
        for x, y, z, tile in iter_tiles(dump):
            for item in tile.get("items", []):
                if item.get("id") != CLOTH_ITEM_ID:
                    continue
                seen.setdefault((x, y, z), set()).add(city)

    print(f"{len(seen)} green piece of cloth (id {CLOTH_ITEM_ID}) únicos")
    for (x, y, z), cities_here in sorted(seen.items(), key=lambda kv: (kv[0][2], kv[0][0], kv[0][1])):
        print(f"  z{z:<3} ({x},{y})  [{','.join(sorted(cities_here))}]")


if __name__ == "__main__":
    main()
