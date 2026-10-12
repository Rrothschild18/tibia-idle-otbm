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
import render_map_v6
import update_canary_data
from travel_graph import (
    build_walkable_graph,
    extract_tile_flags,
    parse_marker_signs,
    signs_by_id,
    tile_distances_and_prev,
)

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

# O andar mais fundo que existe no OTBM.
MAX_FLOOR = 15

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


def crop_floors_for(floors) -> set:
    """Os andares que entram no recorte, dados os andares **com spawn**.

    Três coisas de uma vez, e todas sobre geometria — o spawn continua sendo só
    o dos andares curados (`spawn_floors`):

    1. Os andares do meio. A torre das amazonas tem bicho em z7, z4, z3 e z2, e
       as escadas em z5 e z6 — sem os dois andares vazios o mapa sai em pedaços
       que não se alcançam.
    2. Os andares **abaixo** do mais fundo, até onde o cliente enxerga. Sem
       eles, hunt de superfície num andar só (Wyvern Hill, z5) saía sem z6/z7:
       o front não tinha o que desenhar por baixo e `transitions` nascia vazio.
    3. O limite é o mesmo do front — `last_visible_floor`, de
       `render_map_v6.py`, que por sua vez espelha o `floor-visibility.ts`. Não
       há constante nova aqui de propósito: uma segunda régua divergiria da do
       cliente na primeira mudança.
    """
    deepest = min(render_map_v6.last_visible_floor(max(floors)), MAX_FLOOR)
    return set(range(min(floors), deepest + 1))


def crop_spawns(source: str, destination: str, bounds, floors, chosen=None) -> int:
    """O spawn da hunt: o que está dentro do recorte e nos andares escolhidos.

    `chosen` restringe ainda mais, ao conjunto exato de `(x, y, z, nome)` das
    candidatas que a curadoria juntou. Sem ele a caixa arrasta vizinho: a
    "Ghouls — Carlin Surroundings" saía com Poison Spider como monstro mais
    frequente, porque o bolsão de aranhas ao lado cabia na folga de 12 tiles.
    """
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
            and (
                chosen is None
                or (
                    center_x + int(entry.get("x")),
                    center_y + int(entry.get("y")),
                    int(entry.get("z", group.get("centerz"))),
                    entry.get("name"),
                )
                in chosen
            )
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
    city: str,
    hunt: dict,
    data: bytes,
    header: dict,
    bounds,
    crop_floors,
    entrance=None,
    spawn_floors=None,
    chosen_spawns=None,
    tile_in=None,
    tile_in_floor=None,
) -> dict:
    folder = os.path.join(MAPS_DIR, city, hunt["folder"])
    os.makedirs(folder, exist_ok=True)
    slug = hunt["slug"]

    min_x, min_y, max_x, max_y = bounds
    # Recorte, do mais específico pro geral:
    #  - `tile_in_floor(x,y,z)`: máscara POR ANDAR desenhada no editor (exata).
    #  - `tile_in(x,y)`: máscara 2D (mesma forma em todos os andares).
    #  - caixa: o recorte retangular de sempre.
    box_pred = lambda x, y: min_x <= x <= max_x and min_y <= y <= max_y
    predicate = tile_in if tile_in is not None else box_pred
    areas = [
        (origin, nodes)
        for origin, nodes in otbm_stream.crop_tiles(
            data, predicate, bounds=bounds, keep_column_z=tile_in_floor
        )
        if origin[2] in crop_floors
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
        crop_floors if spawn_floors is None else spawn_floors,
        chosen_spawns,
    )
    for kind, content in EMPTY_XML.items():
        with open(os.path.join(folder, f"{slug}-{kind}.xml"), "w", encoding="utf-8") as handler:
            handler.write(content)

    return {"tiles": tiles, "spawns": spawns, "folder": folder, "marked": marked}


def merge_manifest(previous, written):
    """O manifesto de uma rodada parcial: o que foi recortado agora substitui a
    entrada antiga **no lugar dela**, o resto fica como estava, e id novo entra
    no fim.

    A ordem é preservada, não reordenada. Ordenar faria o arquivo oscilar entre
    duas ordens — parcial ordenada, completa na ordem da curadoria — e todo diff
    viria cheio de movimentação sem mudança. Sem a mescla, uma rodada parcial
    reescrevia o arquivo com só o que acabou de sair e apagava a curadoria das
    outras, cujas pastas continuam em disco e cujo conteúdo o `publish.py` e o
    fragmento de hunt leem daqui.
    """
    recut = {hunt["id"]: hunt for hunt in written}
    known = {hunt["id"] for hunt in previous}

    return [recut.get(hunt["id"], hunt) for hunt in previous] + [
        hunt for hunt in written if hunt["id"] not in known
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("city")
    parser.add_argument("--margin", type=int, default=curated_hunts.DEFAULT_MARGIN_TILES)
    parser.add_argument("--canary-dir")
    parser.add_argument(
        "--only",
        action="append",
        metavar="ID",
        help="recorta só este id (repetível). As outras hunts da cidade não são tocadas — "
        "nem a pasta, nem o curated-hunts.json. Sem isto, recorta a cidade toda.",
    )
    args = parser.parse_args()

    city = args.city
    city_dir = os.path.join(FULL_MAPS_DIR, city)
    curation = _load_json(os.path.join(city_dir, CURATION_FILE_NAME), "curadoria")
    candidates_doc = _load_json(os.path.join(city_dir, "candidates.json"), "candidatas")
    candidates_by_id = {c["id"]: c for c in candidates_doc["candidates"]}

    dump = _load_json(os.path.join(RAW_MAPS_DIR, f"{city}.raw.json"), "dump OTBM")

    # Treino não passa pela tela: a placa CIDADE-TRAINING-NNNN já é a curadoria
    # inteira (id, posição, andar). Placa mal formada cai em `sign_issues` e
    # não gera hunt — mesmo relatório que build_travel_fragment.py já imprime
    # pra toda placa da cidade.
    # O relatório de placa é da cidade inteira, mesmo com `--only`: placa mal
    # formada é defeito do mapa, e esconder o aviso porque o recorte foi parcial
    # faria o defeito aparecer só na próxima rodada completa.
    _, sign_issues = parse_marker_signs(dump)
    for issue in sign_issues:
        print(
            f"[WARN] placa mal formada ({issue['reason']}): uid={issue['uid']} "
            f"text={issue['text']!r} em ({issue['x']}, {issue['y']}, {issue['z']})"
        )

    # Placa é curadoria completa: o id é dela, os andares são os que ela marca e
    # a caixa é o box das placas do mesmo id. Vale para TRAINING e para HUNT —
    # pôr placa é criar hunt, sem passar pela tela de curadoria.
    curated_ids = {hunt["id"] for hunt in curation["hunts"] if "id" in hunt}
    sign_groups = signs_by_id(dump)
    sign_hunts = []
    for sign_id, group in sorted(sign_groups.items()):
        if group[0]["type"] not in ("HUNT", "TRAINING"):
            continue
        if not sign_id.startswith(f"{city}-"):
            print(f"[WARN] placa {sign_id} não é de {city} — ignorada")
            continue
        if sign_id in curated_ids:
            print(
                f"[ERRO] {sign_id} está na placa e no curation.json ao mesmo tempo. "
                "Escolha um dos dois: a placa recorta pela caixa das placas, a "
                "curadoria recorta pela candidata. Nada foi escrito."
            )
            return 1
        sign_hunts.append(curated_hunts.hunt_from_signs(group, MAX_FLOOR))

    hunts = curated_hunts.assign(city, curation["hunts"] + sign_hunts)

    if args.only:
        wanted = set(args.only)
        unknown = sorted(wanted - {hunt["id"] for hunt in hunts})
        if unknown:
            print(
                f"[ERRO] {', '.join(unknown)} não existe em {city} — nem na curadoria, "
                "nem em placa. Nada foi recortado."
            )
            return 1
        hunts = [hunt for hunt in hunts if hunt["id"] in wanted]
        print(f"[--only] recortando {len(hunts)} de {len(wanted)} id(s) pedido(s)")
    shared = curated_hunts.duplicated_candidates(curation["hunts"])
    for candidate_id, names in sorted(shared.items()):
        print(f"[WARN] {candidate_id} está em {len(names)} hunts: {', '.join(names)}")

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
        is_training_hunt = curated_hunts.is_training(hunt)
        # Quem decide o recorte é a origem, não o tipo: hunt de placa (treino ou
        # não) não tem candidata, e a caixa dela são as placas. Hunt da tela tem
        # candidata, e a caixa sai do extent da candidata.
        from_sign = not hunt["candidateIds"]

        if not from_sign:
            members = curated_hunts.members_of(hunt, candidates_by_id)
            if not members:
                print(f"[WARN] {hunt['id']} {hunt['name']}: nenhuma candidata encontrada, pulando")
                continue
        else:
            members = []

        floors = set(hunt["floors"])
        crop_floors = crop_floors_for(floors)
        bounds = curated_hunts.crop_bounds(hunt["extent"], args.margin)

        anchor_of = lambda spawn: hunt_candidates.anchor_tile(spawn, walkable)

        if from_sign:
            # Hunt de placa tem entrada na própria placa — sem candidatas, sem
            # rota do templo. O jogador chega a pé pela cidade.
            entrance = curated_hunts.training_entrance_of(hunt, walkable)
            cost = None
        else:
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

        chosen_spawns = (
            None
            if from_sign
            else {
                (spawn["x"], spawn["y"], spawn["z"], spawn["name"])
                for spawn in curated_hunts.spawns_of(members)
            }
        )
        result = write_hunt_map(
            city,
            hunt,
            data,
            header,
            bounds,
            crop_floors,
            entrance,
            spawn_floors=floors,
            chosen_spawns=chosen_spawns,
        )
        if entrance is not None and not result["marked"]:
            print(f"[WARN] {hunt['id']}: tile de entrada {entrance} ficou fora do recorte")
        written.append(
            {
                "id": hunt["id"],
                "type": "TRAINING" if is_training_hunt else "HUNT",
                "name": hunt["name"].strip(),
                "slug": hunt["slug"],
                "folder": hunt["folder"],
                "floors": sorted(floors),
                "cropFloors": sorted(crop_floors),
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
                **({"isTrainingHunt": True} if is_training_hunt else {}),
            }
        )
        if from_sign:
            # `cost` é sempre None por desenho (sem rota do templo, ver
            # comentário acima) — não é falha de rota, então não é "SEM
            # CAMINHO". Falta de `entrance`, aqui, é que seria falha real: a
            # placa caiu sem vizinho caminhável.
            reach = "A PÉ" if entrance is not None else "SEM ENTRADA"
        else:
            reach = f"templo+{cost}" if cost is not None else "SEM CAMINHO"
        training_label = " [TRAINING]" if is_training_hunt else ""
        print(
            f"[OK] {hunt['id']:<22} {result['tiles']:>6} tiles, {result['spawns']:>3} bichos, "
            f"z{sorted(floors)} {reach:>12}{training_label}  {hunt['name'].strip()}"
        )

    destination = os.path.join(city_dir, CURATED_HUNTS_FILE_NAME)
    entries = written

    if args.only and os.path.isfile(destination):
        # Rodada parcial **mescla** o manifesto: as hunts que não foram
        # recortadas continuam valendo, e suas pastas estão intactas em disco.
        # Reescrever o arquivo inteiro com só o que acabou de sair apagaria a
        # curadoria das outras — o `publish.py` e o fragmento de hunt leem daqui.
        with open(destination, "r", encoding="utf-8") as handler:
            previous = json.load(handler).get("hunts", [])
        entries = merge_manifest(previous, written)
        print(
            f"[--only] manifesto mesclado: {len(written)} recortada(s), "
            f"{len(entries) - len(written)} preservada(s)"
        )

    with open(destination, "w", encoding="utf-8") as handler:
        json.dump(
            {"city": city, "area": curation.get("area"), "hunts": entries},
            handler,
            indent=2,
            ensure_ascii=False,
        )
        handler.write("\n")

    unreachable = [hunt for hunt in written if hunt["entrance"] is None]
    print(f"\n[OK] {len(entries)} hunts -> {destination}")
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
