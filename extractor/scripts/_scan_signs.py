"""Ad-hoc: lista toda placa numerica (id=2017, texto so digitos) do usuario,
deduplicada por posicao (x,y,z) entre os dumps de cidades vizinhas que se
sobrepoem no recorte quadrado."""
import json
import os
import sys

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
EXTRACTOR_DIR = os.path.dirname(SCRIPTS_DIR)
RAW_MAPS_DIR = os.path.join(EXTRACTOR_DIR, "raw-maps")

SIGN_ITEM_ID = 2017


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
    by_pos = {}

    for city in cities:
        path = os.path.join(RAW_MAPS_DIR, f"{city}.raw.json")
        with open(path, encoding="utf-8") as handle:
            dump = json.load(handle)
        for x, y, z, tile in iter_tiles(dump):
            for item in tile.get("items", []):
                if item.get("id") != SIGN_ITEM_ID:
                    continue
                text = item.get("text", "")
                if not text.strip().isdigit():
                    continue
                key = (x, y, z)
                by_pos.setdefault(key, {"x": x, "y": y, "z": z, "text": text, "cities": set()})
                by_pos[key]["cities"].add(city)

    groups = {}
    for entry in by_pos.values():
        groups.setdefault(entry["text"], []).append(entry)

    total = len(by_pos)
    print(f"{total} placas numericas unicas (dedup por x,y,z), {len(groups)} IDs distintos\n")
    for text, entries in sorted(groups.items(), key=lambda kv: int(kv[0])):
        floors = sorted({e["z"] for e in entries})
        cities = sorted({c for e in entries for c in e["cities"]})
        print(f"ID {text}: {len(entries)} placa(s), z={floors}, cidades={cities}")
        for e in sorted(entries, key=lambda e: e["z"]):
            print(f"    z{e['z']:<3} ({e['x']},{e['y']})  [{','.join(sorted(e['cities']))}]")


if __name__ == "__main__":
    main()
