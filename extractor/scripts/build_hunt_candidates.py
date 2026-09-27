"""Gera as candidatas de hunt de uma cidade recortada, para curadoria humana.

    extractor/full-maps/<CIDADE>/candidates.json

Lê o dump da cidade (`raw-maps/<CIDADE>.raw.json`), a tabela de flags
(`appearance-flags/<CIDADE>.json`), o spawn do recorte e o `source.json` que
`cut_city.py` deixou. Nada fora de `extractor/` é tocado — este arquivo é
entrada da tela `new-hunts` do tibia-idle, não do banco.

Ordem: `cut_city.py` -> `dump_otbm.js` -> `build_appearance_flags.py` ->
`build_city_minimap.py` -> este.

Run: uv run python extractor/scripts/build_hunt_candidates.py CARLIN
"""

import argparse
import json
import os
import sys

import appearance_flags
import fetch_assets
import hunt_candidates
import map_regions
import paths
import update_canary_data
from travel_graph import build_walkable_graph, extract_tile_flags, tile_distances_and_prev

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
EXTRACTOR_DIR = os.path.dirname(SCRIPTS_DIR)
RAW_MAPS_DIR = os.path.join(EXTRACTOR_DIR, "raw-maps")
FULL_MAPS_DIR = os.path.join(EXTRACTOR_DIR, "full-maps")


def _load_json(path: str, what: str):
    if not os.path.isfile(path):
        sys.exit(f"error: {what} não encontrado: {path}")
    with open(path, encoding="utf-8") as handler:
        return json.load(handler)


def mask_placement(assets_dir: str, subarea_ids):
    """Onde cada máscara começa no mundo — sem isso quem desenha põe todas na
    origem do mapa, e o contorno fica em cima da cidade errada."""
    document = map_regions.load(assets_dir)
    masks = map_regions.masks_by_subarea(document)
    placement = {}
    for subarea_id in subarea_ids:
        image = masks.get(subarea_id)
        if image is None:
            continue
        placement[subarea_id] = {
            "x": image.position.x,
            "y": image.position.y,
            "width": image.width,
            "height": image.height,
        }
    return placement


def subarea_lookup(assets_dir: str, subarea_ids):
    """`(x, y) -> id da subárea`, da máscara de cada uma. Coluna coberta por
    duas máscaras fica com a última — sobreposição entre subáreas existe e não
    muda nada aqui, porque isto só rotula a candidata."""
    document = map_regions.load(assets_dir)
    masks = map_regions.masks_by_subarea(document)
    names = {region.id: region.name for region in document.region}
    owner = {}
    for subarea_id in subarea_ids:
        image = masks.get(subarea_id)
        if image is None:
            continue
        for column in map_regions.mask_columns(assets_dir, image):
            owner[column] = subarea_id
    return owner, names


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("city")
    parser.add_argument("--radius", type=int, default=hunt_candidates.DEFAULT_CLUSTER_RADIUS)
    parser.add_argument(
        "--min-creatures", type=int, default=hunt_candidates.DEFAULT_MIN_CREATURES
    )
    parser.add_argument("--canary-dir")
    parser.add_argument("--client-dir")
    args = parser.parse_args()

    city = args.city
    city_dir = os.path.join(FULL_MAPS_DIR, city)
    source = _load_json(os.path.join(city_dir, "source.json"), "manifesto do recorte")
    dump = _load_json(os.path.join(RAW_MAPS_DIR, f"{city}.raw.json"), "dump OTBM")
    bounds = _load_json(os.path.join(city_dir, "minimap", "bounds.json"), "bounds do minimapa")

    try:
        flags_by_id = appearance_flags.load_flags(city)
    except appearance_flags.MissingFlagsTableError as exc:
        sys.exit(f"error: {exc}")

    floorchange_by_id, ladder_ids = update_canary_data.read_floor_change_rules(args.canary_dir)
    tiles = extract_tile_flags(dump, flags_by_id, floorchange_by_id, ladder_ids)
    graph = build_walkable_graph(tiles)
    walkable = set(graph)
    print(f"[OK] {len(tiles):,} tiles, {len(walkable):,} caminháveis")

    component_of = hunt_candidates.same_floor_components(walkable)
    print(f"[OK] {len(set(component_of.values())):,} componentes caminháveis (por andar)")

    with open(os.path.join(city_dir, f"{city}-monster.xml"), encoding="utf-8") as handler:
        points = hunt_candidates.parse_spawn_xml(handler.read())
    print(f"[OK] {len(points):,} criaturas no spawn do recorte")

    client_dir = paths.TIBIA_CLIENT.require(args.client_dir)
    assets_dir = fetch_assets.assets_dir(client_dir, fetch_assets.load_manifest())
    owner, names = subarea_lookup(assets_dir, [s["id"] for s in source["subareas"]])
    placement = mask_placement(assets_dir, [s["id"] for s in source["subareas"]])

    candidates, orphans = hunt_candidates.build_candidates(
        city,
        points,
        walkable,
        component_of,
        subarea_of_column=lambda x, y: owner.get((x, y)),
        radius=args.radius,
        min_creatures=args.min_creatures,
    )

    temples = [town for town in source.get("towns", [])]
    distances = {}
    if temples:
        temple = temples[0]
        anchor = hunt_candidates.anchor_tile(
            {"x": temple["x"], "y": temple["y"], "z": temple["z"]}, walkable, reach=3
        )
        if anchor is None:
            print(f"[WARN] templo {temple['name']} não encosta em tile caminhável")
        else:
            targets = {
                node
                for candidate in candidates
                for node in (
                    hunt_candidates.anchor_tile(spawn, walkable)
                    for spawn in candidate["spawns"]
                )
                if node is not None
            }
            distances, _ = tile_distances_and_prev(graph, {anchor: 0}, targets)
            hunt_candidates.attach_walk_distance(
                candidates,
                distances,
                anchor_of=lambda spawn: hunt_candidates.anchor_tile(spawn, walkable),
            )

    document = {
        "city": city,
        "area": source["area"],
        "subareas": [
            {
                "id": s["id"],
                "name": s["name"],
                "mask": f"masks/{s['id']:04d}.png",
                "maskPlacement": placement.get(s["id"]),
            }
            for s in source["subareas"]
        ],
        "minimap": bounds,
        "temple": temples[0] if temples else None,
        "clusterRadius": args.radius,
        "minCreatures": args.min_creatures,
        "candidates": candidates,
        "orphanSpawns": [
            {"name": p["name"], "x": p["x"], "y": p["y"], "z": p["z"]} for p in orphans
        ],
    }

    destination = os.path.join(city_dir, "candidates.json")
    with open(destination, "w", encoding="utf-8") as handler:
        json.dump(document, handler, indent=2, ensure_ascii=False)
        handler.write("\n")

    creatures = sum(c["creatures"] for c in candidates)
    print(
        f"[OK] {len(candidates)} candidatas ({creatures} criaturas), "
        f"{len(orphans)} spawns sem tile andável -> {destination}"
    )
    for candidate in sorted(candidates, key=lambda c: -c["creatures"])[:15]:
        top = ", ".join(f"{s['count']}x {s['name']}" for s in candidate["species"][:3])
        subarea = names.get(candidate["subareaId"], "?")
        distance = candidate.get("walkTilesFromTemple")
        print(
            f"   {candidate['id']}  z{candidate['floor']:<2} {candidate['creatures']:3d} bichos  "
            f"{'templo+' + str(distance) if distance is not None else 'sem caminho':>12}  "
            f"{subarea:<22} {top}"
        )


if __name__ == "__main__":
    main()
