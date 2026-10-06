"""CLI: gera a malha de viagem entre cidades — templo↔templo, tile andado.

Viajar entre cidades é sempre POI interno → templo da própria cidade → templo
do destino → POI de lá, somando as pernas. Os POIs de uma cidade nunca conhecem
a árvore de outra; o templo é o único ponto de junção. Então a malha é o grafo
completo entre os templos, e nada mais — é o que `intercity_mesh_edges` monta.

Por que isto é um passo separado, e não sai do publish de uma cidade: uma aresta
Carlin↔Kazordoon tem um pé em cada uma, e o fragmento de uma cidade só conhece o
recorte dela — nenhum dos dois pode produzi-la. Antes deste script a malha era
uma rodada manual colada no catálogo, e o publish de qualquer cidade a apagava
(ver `merge_travel_graph_into_catalog`). Seis arestas morreram assim no
re-export das cinco cidades.

A medida sai de **um** recorte que contenha todos os templos: hoje o de THAIS,
cujo box de 1682×1682 cobre Carlin, Kazordoon, Thais e Venore com os corredores
entre eles. O script confere isso e recusa em vez de medir pela metade.

    uv run python extractor/scripts/build_intercity_mesh.py
    uv run python extractor/scripts/build_intercity_mesh.py --publish

Sem `--publish` ele só imprime a malha que mediu — é o ensaio.
"""

import argparse
import json
import os
import sys

import appearance_flags
import city_ids
import content_export
import paths
import update_canary_data
from travel_graph import (
    build_walkable_graph,
    extract_teleport_edges,
    extract_tile_flags,
    intercity_mesh_edges,
    merge_intercity_mesh_into_catalog,
)

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
EXTRACTOR_DIR = os.path.dirname(SCRIPTS_DIR)
RAW_MAPS_DIR = os.path.join(EXTRACTOR_DIR, "raw-maps")
FULL_MAPS_DIR = os.path.join(EXTRACTOR_DIR, "full-maps")

# Rookgaard fica fora por regra de produto, não por geografia: a ilha foi feita
# à mão e ninguém de lá alcança a mainland nem o contrário. A reachability do
# grafo provavelmente diria o mesmo (a ilha é cercada de água), mas depender
# disso deixaria a regra invisível — e um quirk de mapa publicaria uma viagem
# que o jogo não permite.
DEFAULT_EXCLUDED = ("ROOK",)


def temples_of_catalog(catalog, excluded):
    """Os templos publicados, um por cidade, fora os excluídos."""
    temples = [
        location
        for location in catalog.get("locations", [])
        if location.get("type") == "TEMPLE"
        and city_ids.derive_city(location["id"]) not in excluded
    ]
    temples.sort(key=lambda location: location["id"])

    by_city = {}
    for temple in temples:
        by_city.setdefault(city_ids.derive_city(temple["id"]), []).append(temple["id"])

    duplicated = {city: ids for city, ids in by_city.items() if len(ids) > 1}
    if duplicated:
        sys.exit(
            "error: cidade com mais de um templo no catálogo, a malha não sabe qual é o "
            f"ponto de junção: {duplicated}"
        )

    return temples


class MissingBoundsError(Exception):
    """Recorte sem `bounds` legíveis — ver `covered_by`."""


def covered_by(bounds, temples):
    """`(dentro, fora)` — os templos que caem na área do recorte, e os que não.

    `bounds` exige as quatro chaves. A primeira versão disto usava
    `bounds.get("minX", 0)`, e contra um dump sem `bounds` o default de zero
    disse que o recorte de THAIS não cobre o templo de Thais: comparação
    `0 <= 32369 <= 0`, falsa para tudo. O erro saiu correto por acidente — mas
    por engano, e um default que mente é exatamente o que esta leva de
    consertos existe para tirar do caminho."""
    missing = [key for key in ("minX", "minY", "maxX", "maxY") if key not in (bounds or {})]
    if missing:
        raise MissingBoundsError(f"bounds sem {', '.join(missing)}")

    inside, outside = [], []
    for temple in temples:
        within = (
            bounds["minX"] <= temple["x"] <= bounds["maxX"]
            and bounds["minY"] <= temple["y"] <= bounds["maxY"]
        )
        (inside if within else outside).append(temple)
    return inside, outside


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--from-city",
        default="THAIS",
        help="recorte de onde a medida sai; precisa conter todos os templos (padrão: THAIS)",
    )
    parser.add_argument(
        "--exclude",
        default=",".join(DEFAULT_EXCLUDED),
        help=f"cidades fora da malha, por vírgula (padrão: {','.join(DEFAULT_EXCLUDED)})",
    )
    parser.add_argument("--canary-dir", default=None)
    parser.add_argument("--tibia-idle-dir", default=None)
    parser.add_argument(
        "--publish",
        action="store_true",
        help="escreve a malha no catalog-source.json do tibia-idle",
    )
    args = parser.parse_args()

    excluded = {part.strip().upper() for part in args.exclude.split(",") if part.strip()}
    city = args.from_city.upper()

    tibia_idle_dir = paths.TIBIA_IDLE.require(args.tibia_idle_dir)
    catalog_path = content_export.catalog_source_path(tibia_idle_dir)
    with open(catalog_path, "r", encoding="utf-8") as handler:
        catalog = json.load(handler)

    temples = temples_of_catalog(catalog, excluded)
    if len(temples) < 2:
        sys.exit(
            f"error: {len(temples)} templo(s) fora de {sorted(excluded)} — malha precisa de dois"
        )
    print(f"[OK] {len(temples)} templos na malha: {', '.join(t['id'] for t in temples)}")
    if excluded:
        print(f"     fora por regra: {', '.join(sorted(excluded))}")

    dump_path = os.path.join(RAW_MAPS_DIR, f"{city}.raw.json")
    if not os.path.isfile(dump_path):
        sys.exit(f"error: recorte bruto não encontrado: {dump_path}")

    # Os bounds vêm do `source.json` do recorte, não do dump bruto: o bruto é o
    # OTBM serializado e não carrega a área que `cut_city.py` escolheu.
    source_path = os.path.join(FULL_MAPS_DIR, city, "source.json")
    if not os.path.isfile(source_path):
        sys.exit(f"error: recorte sem source.json, não sei a área dele: {source_path}")
    with open(source_path, "r", encoding="utf-8") as handler:
        source = json.load(handler)

    try:
        inside, outside = covered_by(source.get("bounds"), temples)
    except MissingBoundsError as exc:
        sys.exit(f"error: {source_path}: {exc}")

    if outside:
        sys.exit(
            f"error: o recorte de {city} não cobre "
            f"{', '.join(t['id'] for t in outside)} — medir só parte da malha daria "
            "aresta faltando sem aviso. Use --from-city com um recorte que cubra todos."
        )
    print(f"[OK] os {len(inside)} templos caem dentro do recorte de {city}")

    print(f"[..] lendo {os.path.basename(dump_path)} ({os.path.getsize(dump_path) / 1e6:.0f} MB)")
    with open(dump_path, "r", encoding="utf-8") as handler:
        dump = json.load(handler)

    try:
        object_defs_flags = appearance_flags.load_flags(city)
    except appearance_flags.MissingFlagsTableError as exc:
        sys.exit(f"error: {exc}")

    canary_dir = paths.CANARY.require(args.canary_dir)
    floorchange_by_id, ladder_ids = update_canary_data.read_floor_change_rules(canary_dir)
    tiles = extract_tile_flags(dump, object_defs_flags, floorchange_by_id, ladder_ids)
    teleport_edges = extract_teleport_edges(dump)
    graph = build_walkable_graph(tiles, teleport_edges)
    print(f"[OK] grafo com {len(graph):,} tiles andáveis, {len(teleport_edges)} teleport(s)")

    edges, warnings = intercity_mesh_edges(graph, temples)
    for warning in warnings:
        print(f"[WARN] {warning}")

    esperadas = len(temples) * (len(temples) - 1) // 2
    print(f"[OK] {len(edges)} de {esperadas} pares com rota andável:")
    for edge in edges:
        print(f"       {edge['from']} <-> {edge['to']}  {edge['tileCount']:,} tiles")

    if not args.publish:
        print("     (ensaio — use --publish para escrever no catálogo)")
        return

    report = merge_intercity_mesh_into_catalog(catalog["travelGraph"], edges)
    with open(catalog_path, "w", encoding="utf-8") as handler:
        json.dump(catalog, handler, indent=2, ensure_ascii=False)

    counts = {}
    for verdict in report.values():
        counts[verdict] = counts.get(verdict, 0) + 1
    print(
        f"[OK] catálogo: {counts.get('added', 0)} added / {counts.get('updated', 0)} updated / "
        f"{counts.get('removed', 0)} removed -> {catalog_path}"
    )


if __name__ == "__main__":
    main()
