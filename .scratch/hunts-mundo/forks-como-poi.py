"""Põe as hunts nascidas de fork no `curated-hunts.json` da região.

Fork de andar nasce no editor: ele tem máscara, recorte e bundle publicado, mas
nunca passou pelo `build_curated_hunts.py` — então não está no
`curated-hunts.json`, que é de onde o `build_travel_fragment.py` tira os POIs de
hunt curada. Sem POI, o `hunt-add` recusa a hunt (e com razão: seria uma hunt
que ninguém alcança).

Aqui cada fork publicado entra nesse manifesto com o mínimo que o POI pede: id,
nome, pasta, andares que a máscara mantém e a entrada. A entrada é a da máscara
quando existe; senão o `start` que o próprio recorte gravou no `map.json`.

Uso: uv run python .scratch/hunts-mundo/forks-como-poi.py ZAO [--write]
"""

import argparse
import glob
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
EXTRACTOR = os.path.join(HERE, "..", "..", "extractor")
ASSETS = "/home/rroth/Projects/tibia-idle/apps/tibia-idle-front/public/assets"


def read(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("city")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    path = os.path.join(EXTRACTOR, "full-maps", args.city, "curated-hunts.json")
    doc = read(path)
    conhecidos = {hunt["id"] for hunt in doc["hunts"]}
    novos = []

    for bundle in sorted(glob.glob(f"{ASSETS}/{args.city}-HUNT-*-sprites-v6")):
        folder = os.path.basename(bundle)[: -len("-sprites-v6")]
        hunt_id = folder.split("_")[0]
        if hunt_id in conhecidos or folder.endswith("_window"):
            continue
        conhecidos.add(hunt_id)
        mask_path = os.path.join(EXTRACTOR, "hunt-masks", f"{hunt_id}.json")
        if not os.path.isfile(mask_path):
            print(f"[--] {hunt_id}: sem máscara, não é fork — pulado")
            continue
        mask = read(mask_path)
        excluded = {int(z) for z in (mask.get("excludedFloors") or [])}
        floors = sorted(
            int(z) for z, cells in mask["floors"].items() if cells and int(z) not in excluded
        )
        if not floors:
            print(f"[--] {hunt_id}: descartada (todo andar excluído)")
            continue

        entrance = mask.get("entrance")
        if entrance:
            entrance = {"x": entrance[0], "y": entrance[1], "z": entrance[2]}
        else:
            bundle_map = read(os.path.join(bundle, "map.json"))
            start = bundle_map.get("start")
            if not start:
                print(f"[!!] {hunt_id}: sem entrada na máscara e sem start no bundle")
                continue
            bounds = bundle_map["bounds"]
            entrance = {
                "x": bounds["minX"] + start["x"],
                "y": bounds["minY"] + start["y"],
                "z": start["z"],
            }

        novos.append(
            {
                "id": hunt_id,
                "type": "HUNT",
                "name": (mask.get("name") or hunt_id).strip(),
                "slug": folder.split("_", 1)[1],
                "folder": folder,
                "floors": floors,
                "cropFloors": floors,
                "candidateIds": [],
                "creatures": None,
                "extent": None,
                "subareaId": None,
                "entrance": entrance,
                "walkTilesFromTemple": None,
            }
        )
        print(f"[OK] {hunt_id:<22} {novos[-1]['name'][:34]:<34} z{floors} entrada {entrance['x']},{entrance['y']},{entrance['z']}")

    if args.write and novos:
        doc["hunts"].extend(novos)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(doc, handle, ensure_ascii=False, indent=2)
    print(f"{args.city}: {len(novos)} fork(s){' gravado(s)' if args.write and novos else ''}")


if __name__ == "__main__":
    main()
