"""
CLI: generate the {locations, travelGraph} fragment tibia-idle's db.json
needs for a city's travel graph — sign-marked POIs (HUNT/TEMPLE/DEPOT/QUEST)
plus every NPC's location and shop — and optionally merge it straight in
with --write-db. See travel_graph.py for the pure logic and
.scratch/travel-graph-and-locations/spec.md for the full design.

Requires the city's full-city map already processed once (`node build_map.js
<CIDADE>`, e.g. `node build_map.js ROOK` — see build_phaser_map.py): reads
extractor/raw-maps/<CIDADE>.raw.json (the raw OTBM dump) and
extractor/full-maps/<CIDADE>/map.json (for objectDefs).

Without --write-db (the default) nothing outside extractor/ is touched — the
fragment is written to extractor/full-maps/<CIDADE>/db-fragment.json for you
to review and copy in by hand. Mechanical fields (position, shop, tileCount)
always upsert by id/pair with --write-db; a location's curated `displayName`
is never overwritten once a human edit removed its `_todo` flag.

Run: python build_travel_fragment.py ROOK [--write-db]
"""

import argparse
import glob
import json
import os
import sys

from travel_graph import (
    build_npc_locations,
    build_sign_location,
    build_travel_fragment,
    build_travel_graph,
    build_walkable_graph,
    extract_tile_flags,
    match_npc_lua_filename,
    merge_travel_fragment_into_db,
    parse_marker_signs,
    parse_npc_shop_lua,
    parse_npc_xml,
)

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
EXTRACTOR_DIR = os.path.dirname(SCRIPTS_DIR)
RAW_MAPS_DIR = os.path.join(EXTRACTOR_DIR, "raw-maps")
FULL_MAPS_DIR = os.path.join(EXTRACTOR_DIR, "full-maps")
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


def _build_shops_by_name(npc_names, canary_npc_dir):
    """{npc name: parsed shop or None} — a name is a key only if a .lua file
    matched it (value None then means "matched, but no shop table"); a name
    genuinely absent (no file at all) is the CLI's cue to warn."""
    lua_filenames = [
        os.path.basename(p) for p in glob.glob(os.path.join(canary_npc_dir, "*.lua"))
    ]
    shops_by_name = {}
    for name in npc_names:
        filename = match_npc_lua_filename(name, lua_filenames)
        if filename is None:
            continue
        with open(os.path.join(canary_npc_dir, filename), "r", encoding="utf-8", errors="replace") as f:
            shops_by_name[name] = parse_npc_shop_lua(f.read())
    return shops_by_name


def build_region_fragment(city: str, canary_dir: str):
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

    tiles = extract_tile_flags(dump, object_defs)
    graph = build_walkable_graph(tiles)
    travel_graph_edges = build_travel_graph(graph, sign_locations)

    npc_xml_path = os.path.join(FULL_MAPS_DIR, city, f"{city}-npc.xml")
    npcs = []
    if os.path.exists(npc_xml_path):
        with open(npc_xml_path, "r", encoding="utf-8") as f:
            npcs = parse_npc_xml(f.read())
    else:
        print(f"[WARN] {npc_xml_path} não encontrado — nenhuma Location de NPC gerada")

    canary_npc_dir = os.path.join(canary_dir, "data-otservbr-global", "npc")
    shops_by_name = _build_shops_by_name({npc["name"] for npc in npcs}, canary_npc_dir)
    npc_locations, unmatched_npcs = build_npc_locations(npcs, city, shops_by_name)
    for name in unmatched_npcs:
        print(f"[WARN] NPC '{name}' sem .lua correspondente em {canary_npc_dir} — Location sem shop")

    return build_travel_fragment(sign_locations, npc_locations, travel_graph_edges)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("city", help="Código da cidade — pasta em extractor/full-maps/<CIDADE>/ (ex: ROOK)")
    parser.add_argument("--canary-dir", default=DEFAULT_CANARY_DIR,
                         help=f"Path do checkout local do Canary (default: {DEFAULT_CANARY_DIR})")
    parser.add_argument(
        "--write-db",
        action="store_true",
        help="Além do fragmento, mescla direto no db.json do tibia-idle: locations/travelGraph "
        "campos mecânicos sempre atualizados por id/par, displayName já curado nunca é sobrescrito",
    )
    parser.add_argument(
        "--tibia-idle-dir",
        default=DEFAULT_TIBIA_IDLE_DIR,
        help=f"Path do checkout do tibia-idle, usado só com --write-db (default: {DEFAULT_TIBIA_IDLE_DIR})",
    )
    args = parser.parse_args()

    if not os.path.isdir(args.canary_dir):
        parser.error(f"Canary install não encontrado em {args.canary_dir} (use --canary-dir)")

    fragment = build_region_fragment(args.city, args.canary_dir)

    out_path = os.path.join(FULL_MAPS_DIR, args.city, "db-fragment.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(fragment, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"[OK] {len(fragment['locations'])} locations, {len(fragment['travelGraph'])} travelGraph edges -> {out_path}")

    if args.write_db:
        db_path = os.path.join(args.tibia_idle_dir, "apps", "tibia-idle-mock-api", "db.json")
        if not os.path.exists(db_path):
            parser.error(f"db.json não encontrado em {db_path} (use --tibia-idle-dir)")
        with open(db_path, "r", encoding="utf-8") as f:
            db = json.load(f)
        db.setdefault("locations", [])
        db.setdefault("travelGraph", [])

        report = merge_travel_fragment_into_db(db, fragment)

        with open(db_path, "w", encoding="utf-8") as f:
            json.dump(db, f, indent=2, ensure_ascii=False)
            f.write("\n")

        added = sum(1 for v in report["locations"].values() if v == "added")
        updated = sum(1 for v in report["locations"].values() if v == "updated")
        edges_added = sum(1 for v in report["travelGraph"].values() if v == "added")
        edges_updated = sum(1 for v in report["travelGraph"].values() if v == "updated")
        print(f"     db.json: locations {added} added / {updated} updated, "
              f"travelGraph {edges_added} added / {edges_updated} updated -> {db_path}")
    else:
        print("     Nada foi escrito em db.json — copie o fragmento manualmente (ou rode com --write-db).")


if __name__ == "__main__":
    main()
