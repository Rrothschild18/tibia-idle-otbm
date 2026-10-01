"""A tabela regra × hunts prontas, contra o gabarito da spec.

    .scratch/hunts-por-subarea/spec.md, decisões 18-20

Gabarito: as 699 hunts de `extractor/hunt-catalog/catalog.json` (wiki
BR+EN), localizadas por coordenada de mundo em qual das nossas cidades cada
uma cai — nunca pelo nome (`extractor/full-maps/<CIDADE>/source.json.bounds`
decide). Rookgaard, Carlin e Kazordoon têm curadoria à mão além da wiki, mas
a pergunta que esta régua responde é sempre a mesma: **a candidata que a
regra gerou tem, na mesma subárea e andar, a espécie que a hunt precisa?**
(`hunt_readiness.is_ready_preferring_subarea`) — a fronteira oficial da
Cyclopedia, não distância de coordenada; extensão + folga só entra como
reserva onde a coluna não cai em máscara nenhuma.

Run: uv run python extractor/scripts/measure_hunt_readiness.py
     uv run python extractor/scripts/measure_hunt_readiness.py --city CARLIN
"""

import argparse
import json
import os
from typing import Dict, List, Optional, Tuple

from PIL import Image

import hunt_readiness
import map_dirs

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
EXTRACTOR_DIR = os.path.dirname(SCRIPTS_DIR)
FULL_MAPS_DIR = os.path.join(EXTRACTOR_DIR, "full-maps")
HUNT_CATALOG_FILE = os.path.join(EXTRACTOR_DIR, "hunt-catalog", "catalog.json")
MAP_REGIONS_DIR = os.path.join(EXTRACTOR_DIR, "map-regions")


def _load_json(path: str):
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as handler:
        return json.load(handler)


def load_bounds_by_city(cities: List[str]) -> Dict[str, Optional[Dict]]:
    bounds = {}
    for city in cities:
        source = _load_json(os.path.join(FULL_MAPS_DIR, city, "source.json"))
        bounds[city] = source.get("bounds") if source else None
    return bounds


def load_candidates_by_city(cities: List[str]) -> Dict[str, List[Dict]]:
    candidates = {}
    for city in cities:
        document = _load_json(os.path.join(FULL_MAPS_DIR, city, "candidates.json"))
        candidates[city] = document["candidates"] if document else []
    return candidates


def load_subarea_owner(map_regions_dir: str) -> Dict[Tuple[int, int], int]:
    """`(x, y) -> id da subárea`, das 204 máscaras já decodificadas em
    `map-regions/masks/` — lê o PNG publicado direto, sem precisar do
    cliente extraído (`build_hunt_candidates.subarea_lookup` faz a mesma
    conta, mas a partir dos assets do cliente; aqui o catálogo já chega
    pronto)."""
    catalog = _load_json(os.path.join(map_regions_dir, "regions.json"))
    if catalog is None:
        return {}
    owner: Dict[Tuple[int, int], int] = {}
    for subarea in catalog["subareas"]:
        mask = subarea.get("mask")
        if not mask:
            continue
        path = os.path.join(map_regions_dir, mask["file"])
        if not os.path.isfile(path):
            continue
        origin_x, origin_y = mask["origin"]["x"], mask["origin"]["y"]
        picture = Image.open(path).convert("RGBA")
        pixels = picture.load()
        for py in range(picture.height):
            for px in range(picture.width):
                red, green, blue, alpha = pixels[px, py]
                if alpha and (red or green or blue):
                    owner[(origin_x + px, origin_y + py)] = subarea["id"]
    return owner


def measure(cities: List[str]) -> Dict[str, Dict[str, int]]:
    """`{cidade: {ready, notReady, unmeasured}}`, mais a chave `"total"`."""
    catalog = _load_json(HUNT_CATALOG_FILE)
    if catalog is None:
        raise SystemExit(f"error: catálogo da wiki não encontrado em {HUNT_CATALOG_FILE}")

    bounds_by_city = load_bounds_by_city(cities)
    candidates_by_city = load_candidates_by_city(cities)
    owner = load_subarea_owner(MAP_REGIONS_DIR)

    results_by_city: Dict[str, List[Optional[bool]]] = {city: [] for city in cities}
    for hunt in catalog["hunts"]:
        city = hunt_readiness.city_of(hunt, bounds_by_city)
        if city is None:
            continue
        results_by_city[city].append(
            hunt_readiness.is_ready_preferring_subarea(hunt, candidates_by_city[city], owner)
        )

    summary = {city: hunt_readiness.summarize(results) for city, results in results_by_city.items()}
    summary["total"] = hunt_readiness.summarize(
        result for results in results_by_city.values() for result in results
    )
    return summary


def print_table(summary: Dict[str, Dict[str, int]]) -> None:
    print(f"{'cidade':<12} {'prontas':>8} {'não prontas':>12} {'sem gabarito':>13} {'medidas':>8}")
    for city, counts in summary.items():
        measured = counts["ready"] + counts["notReady"]
        total = measured + counts["unmeasured"]
        label = "TOTAL" if city == "total" else city
        print(
            f"{label:<12} {counts['ready']:>8} {counts['notReady']:>12} "
            f"{counts['unmeasured']:>13} {measured:>5}/{total:<5}"
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--city", help="só esta cidade, em vez de todas com candidates.json")
    parser.add_argument("--json", help="também grava o resumo aqui, em JSON")
    args = parser.parse_args()

    cities = [args.city] if args.city else map_dirs.discover_cities(FULL_MAPS_DIR)
    cities = [city for city in cities if os.path.isfile(os.path.join(FULL_MAPS_DIR, city, "candidates.json"))]

    summary = measure(cities)
    print_table(summary)

    if args.json:
        with open(args.json, "w", encoding="utf-8") as handler:
            json.dump(summary, handler, indent=2, ensure_ascii=False)
            handler.write("\n")
        print(f"\n[OK] resumo -> {args.json}")


if __name__ == "__main__":
    main()
