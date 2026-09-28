"""
CLI: grava a rota do caminho pintado de um mapa de hunt.

Lê o dump do mapa da hunt, monta o grafo andável da mesma forma que o
travel-graph monta (flags versionadas de `appearance-flags/<CIDADE>.json` mais
as regras de troca de andar do `items.xml`), segue o caminho pintado e escreve
`routes/route-anchors.json` ao lado de `monsters/respawn.json` — mesmo lugar,
mesma ideia: um artefato por hunt, derivado do mapa dela.

A entrada é o `start` do `map.json` v6 (o tile com `HUNT_START_ACTION_ID`), que
é o mesmo ponto de onde o jogador entra.

Falha quando um tile pintado é inalcançável, nomeando quais: rota truncada numa
caçada que só acaba com a área limpa é uma quest que nunca fecha.

Run: python build_painted_route.py ROOK-HUNT-0013_copper-shield-quest
"""

import argparse
import json
import os
import sys

import appearance_flags
import map_dirs
import painted_route
import update_canary_data
from travel_graph import build_walkable_graph, extract_tile_flags

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
EXTRACTOR_DIR = os.path.dirname(SCRIPTS_DIR)
RAW_MAPS_DIR = os.path.join(EXTRACTOR_DIR, "raw-maps")
READY_MAPS_DIR = os.path.join(EXTRACTOR_DIR, "ready-maps")
MAPS_DIR = os.path.join(EXTRACTOR_DIR, "maps")
ROUTE_RELPATH = os.path.join("routes", "route-anchors.json")


def _load_json(path: str, what: str):
    if not os.path.exists(path):
        sys.exit(f"error: {what} não encontrado em {path}\n       rode build_map.js antes")
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("folder", help="pasta do mapa, ex: ROOK-HUNT-0013_copper-shield-quest")
    parser.add_argument("--canary-dir")
    args = parser.parse_args()

    map_dir = map_dirs.find_two_level_dir(MAPS_DIR, args.folder)
    if map_dir is None:
        sys.exit(f"error: não achei {args.folder} em nenhuma cidade de {MAPS_DIR}")
    city = os.path.basename(os.path.dirname(map_dir))

    dump = _load_json(os.path.join(RAW_MAPS_DIR, f"{args.folder}.raw.json"), "dump do mapa")
    bundle = _load_json(os.path.join(READY_MAPS_DIR, city, args.folder, "map.json"), "map.json")

    start_raw = bundle.get("start")
    if not start_raw:
        sys.exit(
            "error: o map.json não tem `start` — o tile de entrada não carrega o marcador de "
            "start, e sem ele não há de onde partir"
        )
    bounds = bundle["bounds"]
    start = (start_raw["x"] + bounds["minX"], start_raw["y"] + bounds["minY"], start_raw["z"])

    flags = appearance_flags.load_flags(city)
    floorchange_by_id, ladder_ids = update_canary_data.read_floor_change_rules(args.canary_dir)
    tiles = extract_tile_flags(dump, flags, floorchange_by_id, ladder_ids)
    graph = build_walkable_graph(tiles)

    try:
        route = painted_route.build_painted_route(dump, graph, start)
    except painted_route.UnreachablePaintedTile as failure:
        sys.exit(f"error: {failure}")

    if not route["waypoints"]:
        print(f"{args.folder}: nenhum tile de caminho pintado — nada a gravar")
        return

    out_dir = os.path.join(READY_MAPS_DIR, city, args.folder, "routes")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(READY_MAPS_DIR, city, args.folder, ROUTE_RELPATH)
    document = {
        "mapId": args.folder.split("_", 1)[0],
        "start": {"x": start[0], "y": start[1], "z": start[2]},
        "painted": route["painted"],
        "bridged": route["bridged"],
        "floors": route["floors"],
        "waypoints": route["waypoints"],
    }
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=1)
        handle.write("\n")

    print(f"{args.folder}: {len(route['waypoints'])} waypoints "
          f"({route['painted']} pintados, {route['bridged']} de ponte), andares {route['floors']}")
    print(f"  entrada: {start}")
    print(f"  -> {out_path}")


if __name__ == "__main__":
    main()
