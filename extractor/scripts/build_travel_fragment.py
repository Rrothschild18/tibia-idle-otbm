"""
CLI: generate the {locations, travelGraph} fragment tibia-idle's back-end
needs for a city's travel graph — sign-marked POIs (HUNT/TEMPLE/DEPOT/QUEST)
plus every NPC's location and shop, all of them nodes measured against each
other over the same graph of walkable tiles — and optionally write it into
the catalog with --export. See travel_graph.py for the pure logic,
content_export.py for where the catalog lives, and
.scratch/travel-graph-and-locations/spec.md for the full design.

Requires the city's full-city map already processed once (`node build_map.js
<CIDADE>`, e.g. `node build_map.js ROOK` — see build_phaser_map.py): reads
extractor/raw-maps/<CIDADE>.raw.json (the raw OTBM dump) and
extractor/full-maps/<CIDADE>/map.json (for objectDefs).

Two files come out, both under extractor/full-maps/<CIDADE>/: db-fragment.json
(what may be imported) and travel-graph-rejections.txt (every node with no way
into the graph, with the coordinate to open in the map editor and what to do
about it). A rejected node is never in the fragment — an unreachable
destination that reached the game would be a hunt the player simply cannot
play, with no trace of why.

Without --export (the default) nothing outside extractor/ is touched.
With it, both collections go into content/catalog-source.json, which
`nx run db:reset` turns into rows. `travelGraph` is *replaced* for this city
(the fragment is the complete edge set — an edge missing from it stops
existing), while `locations` upsert by id: mechanical fields (position, shop)
always take the fresh value, a curated `displayName` is never overwritten once
a human edit removed its `_todo` flag, and a city location the fragment no
longer carries is reported but never deleted.

Run: python build_travel_fragment.py ROOK [--export]
"""

import argparse
import glob
import json
import os
import sys
from collections import Counter

import city_ids
import content_export
import map_dirs
from hunt_fragment import map_id_from_folder
from travel_graph import (
    DEFAULT_NPC_REACH,
    REJECTION_REASONS,
    apply_graph_rejections,
    build_npc_locations,
    build_sign_location,
    build_travel_fragment,
    build_travel_graph,
    build_walkable_graph,
    extract_tile_flags,
    format_rejection_report,
    match_npc_lua_filename,
    merge_travel_fragment_into_catalog,
    parse_marker_signs,
    parse_npc_outfit_lua,
    parse_npc_shop_lua,
    parse_npc_xml,
)

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
EXTRACTOR_DIR = os.path.dirname(SCRIPTS_DIR)
RAW_MAPS_DIR = os.path.join(EXTRACTOR_DIR, "raw-maps")
FULL_MAPS_DIR = os.path.join(EXTRACTOR_DIR, "full-maps")
MAPS_DIR = os.path.join(EXTRACTOR_DIR, "maps")
REJECTION_REPORT_NAME = "travel-graph-rejections.txt"
# Sibling repo checkout: <workspace>/tibia-idle-otbm and <workspace>/tibia-idle/tibia-idle.
DEFAULT_TIBIA_IDLE_DIR = os.path.abspath(
    os.path.join(EXTRACTOR_DIR, "..", "..", "tibia-idle", "tibia-idle")
)
DEFAULT_CANARY_DIR = r"C:\canary-3.2.1"


def _load_json(path, what):
    if not os.path.exists(path):
        print(f"[ERROR] {what} não encontrado em {path}")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _build_npc_lua_facts(npc_names, canary_npc_dir):
    """{npc name: (parsed shop or None, parsed outfit or None)} — a name is a
    key only if a .lua file matched it (a None inside the tuple then means
    "matched, but no such table"); a name genuinely absent (no file at all) is
    the CLI's cue to warn.

    Shop **and** outfit in one pass, from one read: the two live side by side
    in the same Canary file, and reading it twice to fetch them separately
    would be two passes over the same text for no gain."""
    lua_filenames = [
        os.path.basename(p) for p in glob.glob(os.path.join(canary_npc_dir, "*.lua"))
    ]
    facts_by_name = {}
    for name in npc_names:
        filename = match_npc_lua_filename(name, lua_filenames)
        if filename is None:
            continue
        with open(os.path.join(canary_npc_dir, filename), "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        facts_by_name[name] = (parse_npc_shop_lua(text), parse_npc_outfit_lua(text))
    return facts_by_name


def discover_hunt_maps(city: str):
    """extractor/maps/<CIDADE>/<ID>_<nome-descritivo>/ -> [{"id", "name"}],
    sorted by id. This is the list of hunts that exist on disk, which the
    rejection pass checks the graph against: a hunt map with no POI marking
    its entrance is a hunt nobody can travel to. A folder with no `_` (or
    whose id belongs to another city) isn't an id-carrying hunt map — e.g.
    `training-spots` — and is skipped."""
    hunts = []
    for folder in map_dirs.discover_city_map_names(MAPS_DIR, city):
        if "_" not in folder:
            continue
        map_id = map_id_from_folder(folder)
        if city_ids.derive_city(map_id) != city:
            continue
        hunts.append({"id": map_id, "name": folder.split("_", 1)[1]})
    return sorted(hunts, key=lambda h: h["id"])


def build_city_fragment(city: str, canary_dir: str, npc_reach: int = DEFAULT_NPC_REACH):
    """-> (fragment, rejections). Signs and NPCs are both fed to the same
    search over walkable tiles, so an NPC is a travel destination measured in
    real tiles walked — never a euclidean guess, never an occupant hanging off
    some other POI. What comes out with no way in is rejected rather than
    emitted (see apply_graph_rejections)."""
    dump = _load_json(os.path.join(RAW_MAPS_DIR, f"{city}.raw.json"), "dump OTBM bruto")
    map_json = _load_json(os.path.join(FULL_MAPS_DIR, city, "map.json"), "map.json da cidade inteira")
    object_defs = map_json.get("objectDefs", {})

    signs, sign_issues = parse_marker_signs(dump)
    for issue in sign_issues:
        location = f"uid={issue['uid']} text={issue['text']!r} em ({issue['x']}, {issue['y']}, {issue['z']})"
        if issue["reason"] == "duplicate-sign-id":
            print(f"[WARN] placa com id duplicado (outra placa já usa esse texto/uid, "
                  f"provável copiar-colar sem trocar o texto ao duplicar a placa): {location}")
        elif issue["reason"] == "invalid-sign-format":
            print(f"[WARN] placa fora do formato CIDADE-TIPO-NNNN, com NNNN sendo exatamente "
                  f"4 dígitos (ex: ROOK-HUNT-0013 — não 5 dígitos, não 3): {location}")
        else:
            print(f"[WARN] placa com problema não reconhecido ({issue['reason']}): {location}")

    sign_locations = [build_sign_location(s) for s in signs]

    npc_xml_path = os.path.join(FULL_MAPS_DIR, city, f"{city}-npc.xml")
    npcs = []
    if os.path.exists(npc_xml_path):
        with open(npc_xml_path, "r", encoding="utf-8") as f:
            npcs = parse_npc_xml(f.read())
    else:
        print(f"[WARN] {npc_xml_path} não encontrado — nenhuma Location de NPC gerada")

    canary_npc_dir = os.path.join(canary_dir, "data-otservbr-global", "npc")
    lua_facts = _build_npc_lua_facts({npc["name"] for npc in npcs}, canary_npc_dir)
    shops_by_name = {name: shop for name, (shop, _) in lua_facts.items()}
    outfits_by_name = {name: outfit for name, (_, outfit) in lua_facts.items()}
    npc_locations, unmatched_npcs = build_npc_locations(
        npcs, city, shops_by_name, outfits_by_name
    )
    for name in unmatched_npcs:
        print(f"[WARN] NPC '{name}' sem .lua correspondente em {canary_npc_dir} — Location sem shop")

    tiles = extract_tile_flags(dump, object_defs)
    graph = build_walkable_graph(tiles)
    travel_graph_edges = build_travel_graph(graph, [*sign_locations, *npc_locations], npc_reach)

    kept_locations, kept_edges, rejections = apply_graph_rejections(
        [*sign_locations, *npc_locations], travel_graph_edges, discover_hunt_maps(city)
    )
    return build_travel_fragment(kept_locations, kept_edges), rejections


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("city", help="Código da cidade — pasta em extractor/full-maps/<CIDADE>/ (ex: ROOK)")
    parser.add_argument("--canary-dir", default=DEFAULT_CANARY_DIR,
                         help=f"Path do checkout local do Canary (default: {DEFAULT_CANARY_DIR})")
    parser.add_argument(
        "--export",
        action="store_true",
        help="Além do fragmento, escreve locations/travelGraph no catalog-source.json do "
        "tibia-idle: travelGraph é substituído pra esta cidade, locations tem os campos mecânicos "
        "atualizados por id e o displayName já curado nunca é sobrescrito",
    )
    parser.add_argument(
        "--npc-reach",
        type=int,
        default=DEFAULT_NPC_REACH,
        help=f"Até quantos tiles de distância o jogador conta como tendo chegado num NPC "
        f"(default: {DEFAULT_NPC_REACH}). Existe porque balconista fica atrás de um balcão "
        f"intransponível: sem alcance, o tile dele é um bolsão ilhado e ele vira destino "
        f"inalcançável. Só vale pra NPC — placa ilhada continua indo pro relatório",
    )
    parser.add_argument(
        "--tibia-idle-dir",
        default=DEFAULT_TIBIA_IDLE_DIR,
        help=f"Path do checkout do tibia-idle, usado só com --export (default: {DEFAULT_TIBIA_IDLE_DIR})",
    )
    args = parser.parse_args()

    if not os.path.isdir(args.canary_dir):
        parser.error(f"Canary install não encontrado em {args.canary_dir} (use --canary-dir)")

    fragment, rejections = build_city_fragment(args.city, args.canary_dir, args.npc_reach)

    out_path = os.path.join(FULL_MAPS_DIR, args.city, "db-fragment.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(fragment, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"[OK] {len(fragment['locations'])} locations, {len(fragment['travelGraph'])} travelGraph edges -> {out_path}")

    report_path = os.path.join(FULL_MAPS_DIR, args.city, REJECTION_REPORT_NAME)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(format_rejection_report(rejections, args.city))
    if rejections:
        by_reason = Counter(r["reason"] for r in rejections)
        summary = ", ".join(f"{by_reason[reason]} {reason}" for reason in REJECTION_REASONS if by_reason[reason])
        print(f"[WARN] {len(rejections)} nós sem entrada no grafo, fora do fragmento ({summary})")
        print(f"       coordenada e o que fazer com cada um -> {report_path}")
    else:
        print(f"[OK] nenhum nó sem entrada no grafo -> {report_path}")

    if args.export:
        catalog_path = content_export.catalog_source_path(args.tibia_idle_dir)
        if not os.path.exists(catalog_path):
            parser.error(f"catalog-source.json não encontrado em {catalog_path} (use --tibia-idle-dir)")
        with open(catalog_path, "r", encoding="utf-8") as f:
            catalog = json.load(f)
        for collection in content_export.CATALOG_COLLECTIONS:
            catalog.setdefault(collection, [])

        report = merge_travel_fragment_into_catalog(catalog, fragment, args.city)

        with open(catalog_path, "w", encoding="utf-8") as f:
            json.dump(catalog, f, indent=2, ensure_ascii=False)
            f.write("\n")

        locations = Counter(report["locations"].values())
        edges = Counter(report["travelGraph"].values())
        print(f"     catalog: locations {locations['added']} added / {locations['updated']} updated, "
              f"travelGraph {edges['added']} added / {edges['updated']} updated / "
              f"{edges['removed']} removed -> {catalog_path}")
        stale = sorted(loc_id for loc_id, state in report["locations"].items() if state == "stale")
        if stale:
            print(f"[WARN] {len(stale)} locations de {args.city} continuam no catálogo sem vir deste run "
                  f"(não foram apagadas — podem carregar displayName curado): {', '.join(stale)}")
        print("     Rode `nx run db:reset` no tibia-idle pra o catálogo virar linha no Postgres.")
    else:
        print("     Nada foi escrito no back-end — copie o fragmento manualmente (ou rode com --export).")


if __name__ == "__main__":
    main()
