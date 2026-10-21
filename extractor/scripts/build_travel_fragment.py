"""
CLI: generate the {locations, travelGraph} fragment tibia-idle's back-end
needs for a city's travel graph — sign-marked POIs (HUNT/TEMPLE/DEPOT/QUEST/TRAINING)
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
import curated_hunts
import map_dirs
import appearance_flags
import paths
import update_canary_data
from hunt_fragment import map_id_from_folder
from travel_graph import (
    DEFAULT_NPC_REACH,
    build_mechanical_city_pois,
    connect_orphan_hunts,
    parse_depot_items,
    REJECTION_REASONS,
    apply_graph_rejections,
    NPC_ALLOWLIST_NAME,
    NPC_SKIP_REPORT_NAME,
    REJECTION_REPORT_NAME,
    ROOK_CITY,
    build_npc_locations,
    build_quest_slug_location,
    build_sign_location,
    build_travel_fragment,
    build_travel_graph,
    build_walkable_graph,
    close_bridged_pairs,
    extract_teleport_edges,
    extract_tile_flags,
    format_rejection_report,
    hunt_id_for_slug,
    match_npc_lua_filename,
    merge_travel_fragment_into_catalog,
    parse_marker_signs,
    parse_quest_slug_markers,
    parse_npc_outfit_lua,
    parse_npc_services_lua,
    parse_npc_shop_lua,
    filter_npc_locations,
    filter_rook_duplicates,
    format_npc_skip_report,
    parse_npc_xml,
    unresolved_allowlist_ids,
)

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
EXTRACTOR_DIR = os.path.dirname(SCRIPTS_DIR)
RAW_MAPS_DIR = os.path.join(EXTRACTOR_DIR, "raw-maps")
FULL_MAPS_DIR = os.path.join(EXTRACTOR_DIR, "full-maps")
MAPS_DIR = os.path.join(EXTRACTOR_DIR, "maps")
MASK_DIR = os.path.join(EXTRACTOR_DIR, "hunt-masks")


def _load_json(path, what):
    if not os.path.exists(path):
        print(f"[ERROR] {what} não encontrado em {path}")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


class StaleNpcFactsError(RuntimeError):
    """O extrato vendorizado é de antes de `services` existir."""


def _load_npc_lua_facts_source(canary_dir=None):
    """{nome do .lua: {"shop": ..., "outfit": ..., "services": [...]}} — do
    vendor ou de um checkout do Canary.

    O vendor é o padrão: os 1035 `.lua` (9 MB) já foram lidos uma vez e o que
    este pipeline extrai deles está versionado em
    `vendor/canary/npc-lua-facts.json`. Passar `--canary-dir` relê do checkout,
    que é como se confere se o vendor envelheceu.

    Um vendor de antes do campo `services` **levanta**, em vez de virar
    `services: []` por omissão: o filtro de NPC lê esse campo para decidir quem
    entra, e um extrato velho faria ele cortar todo barqueiro, banco, bênção e
    promoção do mapa sem uma linha de erro. Falhar alto aqui é a diferença entre
    "rode o update" e um catálogo silenciosamente errado."""
    if canary_dir:
        npc_dir = os.path.join(canary_dir, "data-otservbr-global", "npc")
        source = {}
        for path in sorted(glob.glob(os.path.join(npc_dir, "*.lua"))):
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
            source[os.path.basename(path)] = {
                "shop": parse_npc_shop_lua(text),
                "outfit": parse_npc_outfit_lua(text),
                "services": parse_npc_services_lua(text),
            }
        return source, npc_dir

    vendored = update_canary_data.vendored_npc_facts()
    if not os.path.exists(vendored):
        print(f"[WARN] {vendored} não encontrado — nenhum NPC terá shop. "
              f"Rode 'uv run python extractor/scripts/update_canary_data.py'")
        return {}, vendored

    with open(vendored, "r", encoding="utf-8") as f:
        source = json.load(f)

    if any("services" not in entry for entry in source.values()):
        raise StaleNpcFactsError(
            f"{vendored} tem entrada sem o campo `services` — é de antes do filtro de NPC, "
            f"ou foi regenerado pela metade. "
            f"Rode 'uv run python extractor/scripts/update_canary_data.py --canary-dir <clone>'"
        )

    return source, vendored


class UnresolvedAllowlistError(RuntimeError):
    """Id na `npc-allowlist.json` que este run consegue provar errado."""


class MissingAllowlistError(RuntimeError):
    """A `npc-allowlist.json` versionada não está no checkout."""


def _load_npc_allowlist():
    """`{id de location: motivo}` — o `npc-allowlist.json` sem as chaves `_`.

    As chaves que começam com `_` são documentação dentro do próprio arquivo
    (`_doc`), e não ids. Guardar a explicação no arquivo em vez de num README ao
    lado é de propósito: quem abre a allowlist para mexer nela é exatamente quem
    precisa ler por que ela existe."""
    path = os.path.join(EXTRACTOR_DIR, NPC_ALLOWLIST_NAME)
    if not os.path.exists(path):
        raise MissingAllowlistError(
            f"{path} não encontrado. O arquivo é versionado, então a ausência dele é "
            f"checkout quebrado — e seguir sem ele derrubaria calado os NPCs que só "
            f"entram por curadoria (barqueiro artesanal, loja por diálogo, Black Bert)"
        )

    with open(path, "r", encoding="utf-8") as handler:
        return {
            key: value
            for key, value in json.load(handler).items()
            if not key.startswith("_")
        }


def _load_city_npcs(city: str, warn: bool = False):
    """`<CIDADE>-npc.xml` -> `[{"name", "x", "y", "z"}, ...]`, vazio se o arquivo
    não existe.

    Lido para duas cidades em todo run que não é de Rookgaard: a que está sendo
    gerada, e ROOK — o lado de referência de `find_rook_duplicates`, que precisa
    vir do xml e não do fragmento para que rodar só Thais corte as mesmas
    duplicatas."""
    path = os.path.join(FULL_MAPS_DIR, city, f"{city}-npc.xml")
    if not os.path.exists(path):
        if warn:
            print(f"[WARN] {path} não encontrado — nenhuma Location de NPC gerada")
        return []

    with open(path, "r", encoding="utf-8") as handler:
        return parse_npc_xml(handler.read())


def _build_npc_lua_facts(npc_names, canary_dir=None):
    """{npc name: {"shop", "outfit", "services"}} — a name is a key only if a
    .lua file matched it (a None dentro do fato então quer dizer "casou, mas não
    tem essa tabela"); a name genuinely absent (no file at all) is the CLI's cue
    to warn.

    Os três vêm da mesma entrada, e é esse o ponto: eles vivem lado a lado no
    mesmo arquivo do Canary, e separá-los seriam três buscas pelo mesmo nome sem
    ganho nenhum."""
    source, origin = _load_npc_lua_facts_source(canary_dir)
    lua_filenames = list(source.keys())
    facts_by_name = {}
    for name in npc_names:
        filename = match_npc_lua_filename(name, lua_filenames)
        if filename is None:
            continue
        entry = source[filename]
        facts_by_name[name] = {
            "shop": entry["shop"],
            "outfit": entry["outfit"],
            "services": entry.get("services") or [],
        }
    return facts_by_name, origin


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


def _load_curated_hunt_locations(city: str):
    """As hunts curadas de `full-maps/<CIDADE>/curated-hunts.json` como POIs.

    Ausente é o caso normal: Rookgaard marca as entradas com placa no OTBM, e
    esse caminho continua valendo. Uma hunt sem entrada nenhuma no arquivo é
    pulada aqui e aparece no relatório de rejeição como hunt sem POI.
    """
    path = os.path.join(FULL_MAPS_DIR, city, "curated-hunts.json")
    if not os.path.exists(path):
        return [], path

    with open(path, "r", encoding="utf-8") as handler:
        document = json.load(handler)

    locations = []
    for hunt in document.get("hunts", []):
        entrance = hunt.get("entrance")
        if not entrance:
            continue
        locations.append(
            curated_hunts.build_location(
                hunt, (entrance["x"], entrance["y"], entrance["z"])
            )
        )
    return locations, path


def _resolve_mask_entrance(hunt_id, _seen=None):
    """A entrada de verdade de uma hunt nascida de split de andar no editor
    (`tibia-idle-map-editor`'s /api/split) — a própria `hunt-masks/<ID>.json`
    (campo `entrance`) ou, quando o split não escolheu uma, a da hunt de onde
    ela foi cortada (`splitFrom`), recursivamente. A entrada da origem serve
    porque fisicamente é o mesmo lugar no mapa da cidade, só um recorte de
    andar diferente — não é geograficamente exata, mas dá rota alcançável de
    verdade em vez de nenhuma (mesma lógica de `connect_orphan_hunts` pra ilha
    sem caminho: estimativa > esconder a hunt do jogador).

    `_seen` corta ciclo — `splitFrom` é texto digitado/copiado na mão (pelo
    split em si, mas também editável), não uma árvore garantida."""
    seen = _seen or set()
    if hunt_id in seen:
        return None
    seen.add(hunt_id)
    path = os.path.join(MASK_DIR, f"{hunt_id}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as handler:
        mask = json.load(handler)
    entrance = mask.get("entrance")
    if entrance:
        return tuple(entrance)
    split_from = mask.get("splitFrom")
    if split_from:
        return _resolve_mask_entrance(split_from, seen)
    return None


def _load_split_hunt_locations(city: str, exclude_ids):
    """POIs sintéticos pras hunts de split que não têm placa no OTBM nem
    entrada em `curated-hunts.json` — sem isto elas caem em `hunt-without-poi`
    mesmo quando a própria máscara (ou a de quem ela foi cortada) já sabe a
    entrada. `exclude_ids` são os ids que já têm POI de placa/curadoria: esses
    nunca são sobrescritos — uma entrada de máscara desatualizada não briga
    com a fonte mais confiável."""
    locations = []
    for folder in map_dirs.discover_city_map_names(MAPS_DIR, city):
        if "_" not in folder:
            continue
        hunt_id = map_id_from_folder(folder)
        if city_ids.derive_city(hunt_id) != city or hunt_id in exclude_ids:
            continue
        entrance = _resolve_mask_entrance(hunt_id)
        if entrance is None:
            continue
        name = folder.split("_", 1)[1]
        mask_path = os.path.join(MASK_DIR, f"{hunt_id}.json")
        if os.path.exists(mask_path):
            with open(mask_path, "r", encoding="utf-8") as handler:
                name = json.load(handler).get("name") or name
        fake_hunt = {
            "id": hunt_id,
            "name": name,
            "type": "TRAINING" if "-TRAINING-" in hunt_id else "HUNT",
        }
        locations.append(curated_hunts.build_location(fake_hunt, entrance))
    return locations


def build_city_fragment(
    city: str,
    canary_dir=None,
    npc_reach: int = DEFAULT_NPC_REACH,
    connect_orphans: bool = True,
):
    """-> (fragment, rejections). Signs and NPCs are both fed to the same
    search over walkable tiles, so an NPC is a travel destination measured in
    real tiles walked — never a euclidean guess, never an occupant hanging off
    some other POI. What comes out with no way in is rejected rather than
    emitted (see apply_graph_rejections)."""
    dump = _load_json(os.path.join(RAW_MAPS_DIR, f"{city}.raw.json"), "dump OTBM bruto")

    # A tabela de flags substitui o map.json v5 de 20,3 MB: o grafo nunca leu
    # um mapa, só `objectDefs[<id>].flags`. Ver appearance_flags.py.
    try:
        object_defs_flags = appearance_flags.load_flags(city)
    except appearance_flags.MissingFlagsTableError as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)

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

    # POIs marcados por slug: item com uid na faixa de quest e o slug no texto,
    # que é como uma área desenhada à mão se marca sem seguir o formato
    # `CIDADE-TIPO-NNNN` da placa. O id vem da pasta do mapa cujo slug casa —
    # a pasta se chama `<ID>_<slug>`, então nada precisa de tabela curada.
    slug_markers = parse_quest_slug_markers(dump)
    if slug_markers:
        folders = discover_hunt_maps(city)
        matched = []
        for marker in slug_markers:
            hunt_id = hunt_id_for_slug(marker["slug"], folders)
            if hunt_id is None:
                print(f"[WARN] marcador '{marker['slug']}' (uid {marker['uid']}) em "
                      f"({marker['x']},{marker['y']},{marker['z']}): nenhuma pasta de mapa com "
                      f"esse slug em maps/{city}/ — POI não gerado")
                continue
            matched.append(build_quest_slug_location(marker, hunt_id))
        if matched:
            by_id = {location["id"]: location for location in sign_locations}
            by_id.update({location["id"]: location for location in matched})
            sign_locations = list(by_id.values())
            print(f"[OK] {len(matched)} POIs de slug: "
                  f"{', '.join(location['id'] for location in matched)}")

    # POIs de hunt curados na tela `new-hunts` (ver curated_hunts.py). Onde uma
    # cidade tem os dois, o arquivo curado vence a placa: ele carrega
    # `displayName` escolhido e um `huntId` que não precisa de confirmação.
    curated_locations, curated_path = _load_curated_hunt_locations(city)
    if curated_locations:
        by_id = {location["id"]: location for location in sign_locations}
        by_id.update({location["id"]: location for location in curated_locations})
        sign_locations = list(by_id.values())
        print(f"[OK] {len(curated_locations)} POIs de hunt curados lidos de {curated_path}")

    # POIs sintéticos pras hunts de split de andar (ver _load_split_hunt_locations)
    # — só preenche o que placa e curadoria não cobriram, nunca sobrescreve.
    split_locations = _load_split_hunt_locations(
        city, {location["id"] for location in sign_locations}
    )
    if split_locations:
        sign_locations = [*sign_locations, *split_locations]
        print(f"[OK] {len(split_locations)} POIs sintéticos de hunt de split "
              f"(entrada da própria máscara ou de quem ela foi cortada)")

    npcs = _load_city_npcs(city, warn=True)

    lua_facts, npc_facts_origin = _build_npc_lua_facts(
        {npc["name"] for npc in npcs}, canary_dir
    )
    npc_locations, unmatched_npcs = build_npc_locations(npcs, city, lua_facts)
    for name in unmatched_npcs:
        print(f"[WARN] NPC '{name}' sem .lua correspondente em {npc_facts_origin} — Location sem shop")

    # A ilha de Rookgaard está dentro do corte de Thais, então os 24 NPCs de Rook
    # existem duas vezes. O `tibia-idle` já descarta a cópia não-ROOK no import;
    # parar de emiti-la poupa as 2.364 arestas que ela arrastava. Ver
    # find_rook_duplicates.
    skipped_npcs: list = []
    if city != ROOK_CITY:
        npc_locations, skipped_npcs = filter_rook_duplicates(
            npc_locations, _load_city_npcs(ROOK_CITY, warn=True)
        )
        if skipped_npcs:
            print(f"[OK] {len(skipped_npcs)} NPC(s) de Rookgaard duplicado(s) em {city} descartado(s)")

    # NPC que não vende, não presta serviço de motor e não está na allowlist não
    # vira destino: ele inflava o grafo (97% das arestas tocavam um NPC) sem
    # oferecer nada que o idle possa fazer. Ver npc_skip_reason.
    allowlist = _load_npc_allowlist()
    unresolved = unresolved_allowlist_ids(allowlist, npc_locations, city)
    if unresolved:
        raise UnresolvedAllowlistError(
            f"extractor/{NPC_ALLOWLIST_NAME} cita id que não casa com NPC nenhum: "
            f"{', '.join(unresolved)}"
        )

    npc_locations, filtered_out = filter_npc_locations(npc_locations, lua_facts, allowlist)
    skipped_npcs.extend(filtered_out)
    print(f"[OK] {len(npc_locations)} NPC(s) de {city} entram, {len(skipped_npcs)} descartado(s)")

    floorchange_by_id, ladder_ids = update_canary_data.read_floor_change_rules(canary_dir)
    tiles = extract_tile_flags(dump, object_defs_flags, floorchange_by_id, ladder_ids)
    teleport_edges = extract_teleport_edges(dump)
    graph = build_walkable_graph(tiles, teleport_edges)
    print(f"[OK] {len(teleport_edges)} teleport(s) ligando o grafo de viagem de {city}")

    # Templo e depot não vêm de placa: o primeiro está no nó `towns` do OTBM, o
    # segundo é o item `type="depot"`. Placa e curadoria continuam vencendo,
    # porque Rookgaard marca os dois à mão (e o depot dele é ficção — a cidade
    # não tem um no Tibia).
    mechanical, mechanical_warnings = build_mechanical_city_pois(
        dump, city, set(graph), parse_depot_items(update_canary_data.read_items_xml(canary_dir))
    )
    for warning in mechanical_warnings:
        print(f"[WARN] {warning}")
    if mechanical:
        taken = {location["id"] for location in sign_locations}
        added = [loc for loc in mechanical if loc["id"] not in taken]
        sign_locations = [*sign_locations, *added]
        print(f"[OK] {len(added)} POIs mecânicos (templo/depot) de {city}")
    travel_graph_edges = build_travel_graph(graph, [*sign_locations, *npc_locations], npc_reach)

    # Hunt que o grafo não alcança é ligada por estimativa, não descartada: o
    # caminho real depende de corda, alçapão de script ou teleport, e o jogador
    # escolhe a hunt numa lista sem nunca ver o trecho. Ver connect_orphan_hunts.
    invented = []
    if connect_orphans:
        travel_graph_edges, invented = connect_orphan_hunts(
            [*sign_locations, *npc_locations], travel_graph_edges
        )
        for link in invented:
            print(f"[~~] ilha de {link.get('hunts', 1)} hunt(s) ligada ao continente por "
                  f"estimativa: {link['hunt']} <-> {link['anchor']} ({link['tileCount']} tiles)")

        # Sem isto a ponte deixa a hunt do outro lado a 3-5 saltos da lista de
        # viagem; o resto do grafo é completo por componente. Ver close_bridged_pairs.
        if invented:
            travel_graph_edges, closed = close_bridged_pairs(travel_graph_edges)
            print(f"[OK] {closed} aresta(s) de fechamento transitivo pelas pontes")

    kept_locations, kept_edges, rejections = apply_graph_rejections(
        [*sign_locations, *npc_locations], travel_graph_edges, discover_hunt_maps(city)
    )
    return build_travel_fragment(kept_locations, kept_edges), rejections, invented, skipped_npcs


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("city", help="Código da cidade — pasta em extractor/full-maps/<CIDADE>/ (ex: ROOK)")
    parser.add_argument(
        "--no-connect-orphans",
        action="store_true",
        help="não liga por estimativa a hunt que o grafo não alcança (ela some do catálogo)",
    )
    parser.add_argument("--canary-dir", default=None,
                         help="Relê items.xml e os .lua de NPC deste checkout do Canary em vez do "
                              "vendor (extractor/vendor/canary/). Sem a flag, o vendor é usado e "
                              "nenhum clone do Canary é necessário.")
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
        default=None,
        help=f"Path do checkout do tibia-idle, usado só com --export (default: ${paths.TIBIA_IDLE.env_var} ou {paths.TIBIA_IDLE.sibling_default()})",
    )
    args = parser.parse_args()

    # Sem --canary-dir o vendor responde por tudo; com a flag, o checkout tem
    # que existir de verdade (passar um caminho errado e cair no vendor em
    # silêncio seria o pior dos dois mundos).
    canary_dir = None
    if args.canary_dir:
        try:
            canary_dir = paths.CANARY.require(args.canary_dir)
        except paths.MissingRepoError as exc:
            parser.error(str(exc))

    fragment, rejections, invented, skipped_npcs = build_city_fragment(
        args.city, canary_dir, args.npc_reach, connect_orphans=not args.no_connect_orphans
    )

    out_path = os.path.join(FULL_MAPS_DIR, args.city, "db-fragment.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(fragment, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"[OK] {len(fragment['locations'])} locations, {len(fragment['travelGraph'])} travelGraph edges -> {out_path}")
    if invented:
        print(f"[~~] {len(invented)} hunt(s) ligada(s) por estimativa — o mapa não tem "
              f"caminho andável até elas (corda, alçapão de script ou teleport)")

    skip_path = os.path.join(FULL_MAPS_DIR, args.city, NPC_SKIP_REPORT_NAME)
    with open(skip_path, "w", encoding="utf-8") as f:
        f.write(format_npc_skip_report(skipped_npcs, args.city))
    if skipped_npcs:
        by_reason = Counter(entry["reason"] for entry in skipped_npcs)
        print(f"[OK] {len(skipped_npcs)} NPC(s) descartado(s) -> {skip_path}")
        for reason, count in sorted(by_reason.items()):
            print(f"     {count} {reason}")

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
        try:
            tibia_idle_dir = paths.TIBIA_IDLE.require(args.tibia_idle_dir)
        except paths.MissingRepoError as exc:
            parser.error(str(exc))
        catalog_path = content_export.catalog_source_path(tibia_idle_dir)
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
        print(f"     catalog: locations {locations['added']} added / {locations['updated']} updated / "
              f"{locations['removed']} removed, "
              f"travelGraph {edges['added']} added / {edges['updated']} updated / "
              f"{edges['removed']} removed -> {catalog_path}")
        if locations["removed"]:
            print(f"[OK] {locations['removed']} locations de NPC de {args.city} removidas do catálogo "
                  f"(NPC é mecânico — não há curadoria para preservar; ver ADR-0009)")
        stale = sorted(loc_id for loc_id, state in report["locations"].items() if state == "stale")
        if stale:
            print(f"[WARN] {len(stale)} POIs de {args.city} continuam no catálogo sem vir deste run "
                  f"(não foram apagados — podem carregar displayName ou huntId curado): {', '.join(stale)}")
        print("     Rode `nx run db:reset` no tibia-idle pra o catálogo virar linha no Postgres.")
    else:
        print("     Nada foi escrito no back-end — copie o fragmento manualmente (ou rode com --export).")


if __name__ == "__main__":
    main()
