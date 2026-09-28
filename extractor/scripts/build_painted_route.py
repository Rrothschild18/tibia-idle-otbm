"""
CLI: grava a rota do caminho pintado de um mapa de hunt.

Lê o dump do mapa da hunt, monta o grafo andável da mesma forma que o
travel-graph monta (flags versionadas de `appearance-flags/<CIDADE>.json` mais
as regras de troca de andar do `items.xml`), segue o caminho pintado e escreve
`routes/route-anchors.json` ao lado de `monsters/respawn.json` — mesmo lugar,
mesma ideia: um artefato por hunt, derivado do mapa dela.

A entrada é o `start` do `map.json` v6 (o tile com `HUNT_START_ACTION_ID`), que
é o mesmo ponto de onde o jogador entra.

A entrada desce para um vizinho andável quando o tile marcado não é (o autor põe
o marcador sobre mobília, e em ROOK-HUNT-0014 sobre uma lápide de verdade); o
artefato registra de onde desceu.

Falha — exit 1 — quando um **spawn** fica fora do alcance da rota, nomeando
quais: "todos os monstros precisam morrer" é a promessa da quest, e uma que não
dá para cumprir não deve passar calada. Tile pintado inalcançável sem spawn atrás
é aviso, não reprovação: no mapa da Katana são 9, todos atrás de porta trancada e
sem monstro nenhum, e parar por causa deles seria parar por decoração.

O artefato é escrito nos dois casos. Ele é a evidência de onde está o furo, e
quem lê o exit code é o pipeline.

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
RESPAWN_RELPATH = os.path.join("monsters", "respawn.json")


def _fmt(point) -> str:
    return f"({point['x']},{point['y']},{point['z']})"


def _spawn_tiles(path: str):
    """Os spawns do bundle em coordenada de mundo, ou nada se o arquivo não existe.

    Ausência não é erro: mapa sem respawn.json é mapa sem monstro, e a rota dele
    continua fazendo sentido. O que não pode é a cobertura mentir — por isso o
    contador de spawn sai de `respawn.json`, o mesmo arquivo que o jogo lê, e não
    de uma segunda contagem sobre o dump."""
    if not os.path.exists(path):
        return []

    with open(path, encoding="utf-8") as handle:
        document = json.load(handle)

    return [
        (spawn["worldX"], spawn["worldY"], spawn["worldZ"])
        for spawn in document.get("spawns") or []
    ]


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

    respawn_path = os.path.join(READY_MAPS_DIR, city, args.folder, RESPAWN_RELPATH)
    spawns = _spawn_tiles(respawn_path)

    try:
        route = painted_route.build_painted_route(dump, graph, start, spawns)
    except painted_route.EntranceUnreachable as failure:
        sys.exit(f"error: {failure}")

    if not route["waypoints"]:
        print(f"{args.folder}: nenhum tile de caminho pintado — nada a gravar")
        return

    out_dir = os.path.join(READY_MAPS_DIR, city, args.folder, "routes")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(READY_MAPS_DIR, city, args.folder, ROUTE_RELPATH)
    document = {
        "mapId": args.folder.split("_", 1)[0],
        # `start` é o tile marcado; `entrance` é de onde se parte de verdade. Os
        # dois só diferem quando o marcador caiu sobre coisa que bloqueia, e
        # guardar ambos é o que deixa a diferença auditável depois.
        "start": {"x": start[0], "y": start[1], "z": start[2]},
        "entrance": route["entrance"],
        "entranceSnappedFrom": route["entranceSnappedFrom"],
        "painted": route["painted"],
        "bridged": route["bridged"],
        "floors": route["floors"],
        "paintedTotal": route["paintedTotal"],
        "unreachablePainted": route["unreachablePainted"],
        "spawnsTotal": route["spawnsTotal"],
        "unreachableSpawns": route["unreachableSpawns"],
        "waypoints": route["waypoints"],
    }
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=1)
        handle.write("\n")

    print(f"{args.folder}: {len(route['waypoints'])} waypoints "
          f"({route['painted']} pintados, {route['bridged']} de ponte), andares {route['floors']}")
    if route["entranceSnappedFrom"] is None:
        print(f"  entrada: {start}")
    else:
        print(f"  entrada: {_fmt(route['entrance'])} (o tile marcado {start} não é andável)")
    print(f"  pintados: {route['painted']} de {route['paintedTotal']} alcançados")
    print(f"  spawns:   {route['spawnsTotal'] - len(route['unreachableSpawns'])} "
          f"de {route['spawnsTotal']} alcançados")
    print(f"  -> {out_path}")

    for tile in route["unreachablePainted"]:
        print(f"  aviso: tile pintado sem alcance e sem spawn atrás: {_fmt(tile)}")

    if route["unreachableSpawns"]:
        addresses = ", ".join(_fmt(tile) for tile in route["unreachableSpawns"])
        sys.exit(
            f"error: {len(route['unreachableSpawns'])} spawn(s) que a rota não alcança: "
            f"{addresses}\n"
            "       a quest promete matar todos; ou o mapa liga esse trecho, ou a quest "
            "baixa o `requiredKillPercent`"
        )


if __name__ == "__main__":
    main()
