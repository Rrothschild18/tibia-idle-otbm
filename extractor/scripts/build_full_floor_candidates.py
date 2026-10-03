"""Candidatas de "andar inteiro" pra casamento com placa numérica.

Diferente de `build_hunt_candidates.py` (clusteriza por raio, descarta bicho
fraco e bolsão pequeno), aqui a candidata é o **componente caminhável por
andar inteiro** (`hunt_candidates.same_floor_components` — só parede corta,
sem raio nenhum) com **todo** bicho ancorado nele, sem filtro de XP nem de
contagem mínima. É o que a placa pede: "aquele andar é uma hunt, todos os
monstros são da hunt" (decisão do Rault, 2026-10-02) — nenhum corte por
tamanho de bolsão nem por espécie fraca.

Saída: `full-maps/<CIDADE>/candidates-full.json`, mesmo formato de
`candidates.json` (CandidatesDocument), pra `sign_groups.py` e
`build-curation-signs-only.ts` lerem sem mudança de tipo.

Run: uv run python extractor/scripts/build_full_floor_candidates.py CARLIN THAIS VENORE KAZORDOON
"""

import argparse
import json
import os
import sys
from collections import Counter, defaultdict

import appearance_flags
import fetch_assets
import hunt_candidates
import map_regions
import paths
import update_canary_data
from travel_graph import build_walkable_graph, extract_tile_flags

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


def build_full_floor_candidates(city, points, walkable, component_of, subarea_of_column=None):
    """Agrupa só por componente (andar inteiro) — sem raio, sem corte de XP,
    sem contagem mínima. Reusa `_species`/`_extent` de `hunt_candidates` pra
    não reimplementar o que já é testado lá."""
    anchored = []
    orphans = []
    for point in points:
        anchor = hunt_candidates.anchor_tile(point, walkable)
        if anchor is None:
            orphans.append(point)
            continue
        anchored.append({**point, "anchor": anchor, "component": component_of.get(anchor, -1)})

    by_component = defaultdict(list)
    for point in anchored:
        by_component[point["component"]].append(point)

    candidates = []
    for component, group in sorted(by_component.items()):
        floor = group[0]["z"]
        extent = hunt_candidates._extent(group)
        columns = Counter(
            subarea_of_column(p["x"], p["y"]) if subarea_of_column else None for p in group
        )
        subarea_id, _ = columns.most_common(1)[0]
        candidates.append(
            {
                "id": f"{city}-FULL-z{floor:02d}-{component}",
                "city": city,
                "floor": floor,
                "component": component,
                "creatures": len(group),
                "species": hunt_candidates._species(group),
                "extent": extent,
                "subareaId": subarea_id,
                "spawns": sorted(
                    (
                        {"name": p["name"], "x": p["x"], "y": p["y"], "z": p["z"]}
                        for p in group
                    ),
                    key=lambda p: (p["y"], p["x"], p["name"]),
                ),
            }
        )
    return candidates, orphans


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("cities", nargs="+")
    parser.add_argument("--canary-dir")
    parser.add_argument("--client-dir")
    args = parser.parse_args()

    floorchange_by_id, ladder_ids = update_canary_data.read_floor_change_rules(args.canary_dir)

    for city in args.cities:
        city_dir = os.path.join(FULL_MAPS_DIR, city)
        source = _load_json(os.path.join(city_dir, "source.json"), "manifesto do recorte")
        dump = _load_json(os.path.join(RAW_MAPS_DIR, f"{city}.raw.json"), "dump OTBM")
        bounds = _load_json(os.path.join(city_dir, "minimap", "bounds.json"), "bounds do minimapa")
        flags_by_id = appearance_flags.load_flags(city)

        tiles = extract_tile_flags(dump, flags_by_id, floorchange_by_id, ladder_ids)
        graph = build_walkable_graph(tiles)
        walkable = set(graph)
        component_of = hunt_candidates.same_floor_components(walkable)

        with open(os.path.join(city_dir, f"{city}-monster.xml"), encoding="utf-8") as handler:
            points = hunt_candidates.parse_spawn_xml(handler.read())

        client_dir = paths.TIBIA_CLIENT.require(args.client_dir)
        assets_dir = fetch_assets.assets_dir(client_dir, fetch_assets.load_manifest())
        owner, names = subarea_lookup(assets_dir, [s["id"] for s in source["subareas"]])
        placement = mask_placement(assets_dir, [s["id"] for s in source["subareas"]])

        candidates, orphans = build_full_floor_candidates(
            city, points, walkable, component_of, subarea_of_column=lambda x, y: owner.get((x, y))
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
            "candidates": candidates,
            "orphanSpawns": [
                {"name": p["name"], "x": p["x"], "y": p["y"], "z": p["z"]} for p in orphans
            ],
        }

        destination = os.path.join(city_dir, "candidates-full.json")
        with open(destination, "w", encoding="utf-8") as handler:
            json.dump(document, handler, indent=2, ensure_ascii=False)
            handler.write("\n")

        creatures = sum(c["creatures"] for c in candidates)
        print(f"[OK] {city}: {len(candidates)} componentes ({creatures} criaturas), {len(orphans)} órfãos -> {destination}")


if __name__ == "__main__":
    main()
