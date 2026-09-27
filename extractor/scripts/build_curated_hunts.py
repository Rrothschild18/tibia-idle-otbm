"""Transforma a curadoria da tela `new-hunts` nas pastas de mapa de hunt.

    extractor/maps/<CIDADE>/<ID>_<slug>/<slug>.otbm  (+ os 4 xmls irmãos)
    extractor/full-maps/<CIDADE>/curated-hunts.json  (ids, entradas, membros)

Entrada: `full-maps/<CIDADE>/curation.json` — o arquivo que a tela baixa, com a
cidade, as subáreas ligadas e as hunts escolhidas. Nada fora de `extractor/` é
tocado.

Cada hunt vira um recorte do mapa da cidade: a extensão das candidatas que ela
juntou, com folga, **só nos andares escolhidos**. A coordenada de mundo é
preservada aqui também, então o mapa de uma hunt sabe de onde veio — é o que
permite conferir depois que o roster do recorte bate com o da cidade naquela
região.

Ordem: `cut_city.py` -> `dump_otbm.js` -> `build_appearance_flags.py` ->
`build_hunt_candidates.py` -> (curadoria na tela) -> este -> `build_map.js`.

Run: uv run python extractor/scripts/build_curated_hunts.py CARLIN
"""

import argparse
import json
import os
import sys
import xml.etree.ElementTree as ElementTree

import appearance_flags
import curated_hunts
import hunt_candidates
import otbm_stream
import update_canary_data
from travel_graph import build_walkable_graph, extract_tile_flags, tile_distances_and_prev

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
EXTRACTOR_DIR = os.path.dirname(SCRIPTS_DIR)
RAW_MAPS_DIR = os.path.join(EXTRACTOR_DIR, "raw-maps")
FULL_MAPS_DIR = os.path.join(EXTRACTOR_DIR, "full-maps")
MAPS_DIR = os.path.join(EXTRACTOR_DIR, "maps")

# O mesmo action id que Rookgaard usa na tile de entrada, colocado à mão no
# editor (ver map_v6.HUNT_START_ACTION_ID). Sem ele o bundle sai sem `start`, e
# tanto o Phaser quanto o gerador de waypoints caem no `startPosition` antigo,
# em pixel — que num mapa de coordenada de mundo aponta para fora do mapa.
HUNT_START_ACTION_ID = 3366
HUNT_START_ITEM_ID = 352

CURATION_FILE_NAME = "curation.json"
CURATED_HUNTS_FILE_NAME = "curated-hunts.json"

EMPTY_XML = {
    "npc": "<?xml version='1.0' encoding='UTF-8'?>\n<npcs>\n</npcs>\n",
    "house": "<?xml version='1.0' encoding='UTF-8'?>\n<houses>\n</houses>\n",
    "zones": "<?xml version='1.0' encoding='UTF-8'?>\n<zones>\n</zones>\n",
}


def _load_json(path: str, what: str):
    if not os.path.isfile(path):
        sys.exit(f"error: {what} não encontrado: {path}")
    with open(path, encoding="utf-8") as handler:
        return json.load(handler)


def crop_spawns(source: str, destination: str, bounds, floors) -> int:
    min_x, min_y, max_x, max_y = bounds
    tree = ElementTree.parse(source)
    root = tree.getroot()
    kept = 0

    for group in list(root):
        center_x = int(group.get("centerx"))
        center_y = int(group.get("centery"))
        inside = [
            entry
            for entry in group
            if min_x <= center_x + int(entry.get("x")) <= max_x
            and min_y <= center_y + int(entry.get("y")) <= max_y
            and int(entry.get("z", group.get("centerz"))) in floors
        ]
        if not inside:
            root.remove(group)
            continue
        for entry in list(group):
            if entry not in inside:
                group.remove(entry)
        kept += len(inside)

    ElementTree.indent(tree, space="\t")
    tree.write(destination, encoding="UTF-8", xml_declaration=True)
    return kept


def write_hunt_map(
    city: str, hunt: dict, data: bytes, header: dict, bounds, floors, entrance=None
) -> dict:
    folder = os.path.join(MAPS_DIR, city, hunt["folder"])
    os.makedirs(folder, exist_ok=True)
    slug = hunt["slug"]

    min_x, min_y, max_x, max_y = bounds
    areas = [
        (origin, nodes)
        for origin, nodes in otbm_stream.crop_tiles(
            data,
            lambda x, y: min_x <= x <= max_x and min_y <= y <= max_y,
            bounds=bounds,
        )
        if origin[2] in floors
    ]

    marked = False
    if entrance is not None:
        marker = otbm_stream.item_node(HUNT_START_ITEM_ID, HUNT_START_ACTION_ID)
        for origin, nodes in areas:
            if origin[2] != entrance[2]:
                continue
            for index, node in enumerate(nodes):
                offset_x, offset_y = otbm_stream.tile_offsets(node, 0)
                if (origin[0] + offset_x, origin[1] + offset_y) == entrance[:2]:
                    nodes[index] = otbm_stream.with_extra_item(node, marker)
                    marked = True
                    break
            if marked:
                break

    tiles = otbm_stream.write_map(
        os.path.join(folder, f"{slug}.otbm"),
        header,
        f"{hunt['id']} {hunt['name'].strip()} — recortado de {city}.otbm por build_curated_hunts.py",
        f"{slug}-monster.xml",
        f"{slug}-house.xml",
        areas,
        [],
    )

    spawns = crop_spawns(
        os.path.join(FULL_MAPS_DIR, city, f"{city}-monster.xml"),
        os.path.join(folder, f"{slug}-monster.xml"),
        bounds,
        floors,
    )
    for kind, content in EMPTY_XML.items():
        with open(os.path.join(folder, f"{slug}-{kind}.xml"), "w", encoding="utf-8") as handler:
            handler.write(content)

    return {"tiles": tiles, "spawns": spawns, "folder": folder, "marked": marked}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("city")
    parser.add_argument("--margin", type=int, default=curated_hunts.DEFAULT_MARGIN_TILES)
    parser.add_argument("--canary-dir")
    args = parser.parse_args()

    city = args.city
    city_dir = os.path.join(FULL_MAPS_DIR, city)
    curation = _load_json(os.path.join(city_dir, CURATION_FILE_NAME), "curadoria")
    candidates_doc = _load_json(os.path.join(city_dir, "candidates.json"), "candidatas")
    candidates_by_id = {c["id"]: c for c in candidates_doc["candidates"]}

    hunts = curated_hunts.assign(city, curation["hunts"])
    shared = curated_hunts.duplicated_candidates(curation["hunts"])
    for candidate_id, names in sorted(shared.items()):
        print(f"[WARN] {candidate_id} está em {len(names)} hunts: {', '.join(names)}")

    dump = _load_json(os.path.join(RAW_MAPS_DIR, f"{city}.raw.json"), "dump OTBM")
    flags_by_id = appearance_flags.load_flags(city)
    floorchange_by_id, ladder_ids = update_canary_data.read_floor_change_rules(args.canary_dir)
    tiles = extract_tile_flags(dump, flags_by_id, floorchange_by_id, ladder_ids)
    graph = build_walkable_graph(tiles)
    walkable = set(graph)

    source = _load_json(os.path.join(city_dir, "source.json"), "manifesto do recorte")
    temple = (source.get("towns") or [None])[0]
    distances = {}
    if temple:
        anchor = hunt_candidates.anchor_tile(temple, walkable, reach=3)
        if anchor is None:
            print(f"[WARN] templo {temple['name']} não encosta em tile caminhável")
        else:
            # Os alvos são todos os tiles de spawn das hunts curadas: a busca
            # para quando o último deles é aceito, e uma lista de alvos vazia
            # faria ela parar antes do primeiro passo.
            targets = {
                node
                for hunt in hunts
                for member in curated_hunts.members_of(hunt, candidates_by_id)
                for node in (
                    hunt_candidates.anchor_tile(spawn, walkable)
                    for spawn in member["spawns"]
                )
                if node is not None
            }
            distances, _ = tile_distances_and_prev(graph, {anchor: 0}, targets)

    with open(os.path.join(city_dir, f"{city}.otbm"), "rb") as handler:
        data = handler.read()
    header = otbm_stream.map_header(data)

    written = []
    for hunt in hunts:
        members = curated_hunts.members_of(hunt, candidates_by_id)
        if not members:
            print(f"[WARN] {hunt['id']} {hunt['name']}: nenhuma candidata encontrada, pulando")
            continue

        floors = set(hunt["floors"])
        bounds = curated_hunts.crop_bounds(hunt["extent"], args.margin)

        anchor_of = lambda spawn: hunt_candidates.anchor_tile(spawn, walkable)
        entrance, cost = curated_hunts.entrance_of(members, distances, anchor_of)
        if entrance is None:
            # Sem rota, a entrada vira um tile andável qualquer da hunt. A
            # location existe de propósito: assim ela cai no relatório de
            # rejeição como `poi-without-edge`, com coordenada para abrir no
            # editor, em vez de sumir como "hunt sem placa".
            entrance = next(
                (
                    node
                    for node in (
                        anchor_of(spawn) for spawn in curated_hunts.spawns_of(members)
                    )
                    if node is not None
                ),
                None,
            )

        result = write_hunt_map(city, hunt, data, header, bounds, floors, entrance)
        if entrance is not None and not result["marked"]:
            print(f"[WARN] {hunt['id']}: tile de entrada {entrance} ficou fora do recorte")
        written.append(
            {
                "id": hunt["id"],
                "name": hunt["name"].strip(),
                "slug": hunt["slug"],
                "folder": hunt["folder"],
                "floors": sorted(floors),
                "candidateIds": hunt["candidateIds"],
                "creatures": sum(member["creatures"] for member in members),
                "extent": hunt["extent"],
                "subareaId": hunt.get("subareaId"),
                "entrance": (
                    {"x": entrance[0], "y": entrance[1], "z": entrance[2]}
                    if entrance
                    else None
                ),
                "walkTilesFromTemple": cost,
                "tiles": result["tiles"],
                "spawns": result["spawns"],
            }
        )
        reach = f"templo+{cost}" if cost is not None else "SEM CAMINHO"
        print(
            f"[OK] {hunt['id']:<18} {result['tiles']:>6} tiles, {result['spawns']:>3} bichos, "
            f"z{sorted(floors)} {reach:>12}  {hunt['name'].strip()}"
        )

    destination = os.path.join(city_dir, CURATED_HUNTS_FILE_NAME)
    with open(destination, "w", encoding="utf-8") as handler:
        json.dump(
            {"city": city, "area": curation.get("area"), "hunts": written},
            handler,
            indent=2,
            ensure_ascii=False,
        )
        handler.write("\n")

    unreachable = [hunt for hunt in written if hunt["entrance"] is None]
    print(f"\n[OK] {len(written)} hunts -> {destination}")
    print(f"     pastas de mapa em {os.path.join(MAPS_DIR, city)}")
    if unreachable:
        print(
            f"[!!] {len(unreachable)} sem caminho a pé do templo — elas não entram no "
            f"travel-graph e não aparecem no jogo:"
        )
        for hunt in unreachable:
            print(f"       {hunt['id']}  {hunt['name']}")


if __name__ == "__main__":
    main()
