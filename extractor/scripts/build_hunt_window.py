"""Gera a "janela" de uma hunt: um recorte da cidade = bounds da hunt + margem,
renderizado em v6, pra o editor de máscara (tibia-idle-map-editor) mostrar a hunt
E os vizinhos. Sem isso, o editor só tem o recorte da hunt e o brush só apaga —
com a janela, dá pra ADICIONAR SQM que estão em volta.

Lê os bounds/andares/entrada do bundle já publicado da hunt
(apps/tibia-idle-front/public/assets/<pasta>/map.json), recorta a caixa+margem
com `build_curated_hunts.write_hunt_map`, renderiza com build_map.js, e copia o
resultado (map.json + sheets/) pra <pasta>/window/ onde o editor o serve.

Run: uv run python scripts/build_hunt_window.py CARLIN-HUNT-0003 --margin 20
"""

import argparse
import json
import os
import shutil
import subprocess
import sys

import build_curated_hunts as bch
import otbm_stream
import paths
import update_canary_data

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))


def _bundle_folder(assets_dir: str, hunt_id: str) -> str:
    for name in sorted(os.listdir(assets_dir)):
        if name.startswith(f"{hunt_id}_") and name.endswith("-sprites-v6"):
            return name
    sys.exit(f"error: bundle de {hunt_id} não achado em {assets_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("hunt_id", help="ex: CARLIN-HUNT-0003")
    parser.add_argument("--margin", type=int, default=20, help="margem em tiles ao redor (default 20)")
    parser.add_argument("--tibia-idle-dir")
    args = parser.parse_args()

    city = args.hunt_id.split("-")[0]
    tibia_idle = paths.TIBIA_IDLE.require(args.tibia_idle_dir)
    assets_dir = os.path.join(tibia_idle, "apps", "tibia-idle-front", "public", "assets")
    bundle = _bundle_folder(assets_dir, args.hunt_id)

    with open(os.path.join(assets_dir, bundle, "map.json"), encoding="utf-8") as handle:
        bundle_map = json.load(handle)

    b = bundle_map["bounds"]
    m = args.margin
    box = [b["minX"] - m, b["minY"] - m, b["maxX"] + m, b["maxY"] + m]
    floors = {int(z) for z in bundle_map["floors"]}
    start = bundle_map.get("start") or {"x": 0, "y": 0, "z": min(floors)}
    entrance = [b["minX"] + start["x"], b["minY"] + start["y"], start["z"]]

    otbm = os.path.join(bch.FULL_MAPS_DIR, city, f"{city}.otbm")
    if not os.path.exists(otbm):
        sys.exit(f"error: recorte da cidade não encontrado em {otbm} (rode cut_city.py)")
    with open(otbm, "rb") as handle:
        data = handle.read()
    header = otbm_stream.map_header(data)

    hunt = {"id": args.hunt_id, "slug": "window", "folder": f"{args.hunt_id}_window", "name": f"{args.hunt_id} window"}
    result = bch.write_hunt_map(city, hunt, data, header, box, floors, entrance=entrance)
    print(f"[OK] janela recortada: {result['tiles']} tiles, caixa {box}, andares {sorted(floors)}")

    # renderiza v6 com o build_map.js
    build = subprocess.run(["node", "scripts/build_map.js", hunt["folder"]], cwd=os.path.dirname(SCRIPTS_DIR))
    if build.returncode != 0:
        sys.exit(f"error: build_map.js falhou ({build.returncode})")

    ready = os.path.join(os.path.dirname(SCRIPTS_DIR), "ready-maps", city, hunt["folder"])
    dest = os.path.join(assets_dir, bundle, "window")
    shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(dest, exist_ok=True)
    shutil.copy(os.path.join(ready, "map.json"), os.path.join(dest, "map.json"))
    shutil.copytree(os.path.join(ready, "sheets"), os.path.join(dest, "sheets"))
    print(f"[OK] janela publicada em {dest} — reabra a hunt no editor pra adicionar vizinhos")


if __name__ == "__main__":
    main()
