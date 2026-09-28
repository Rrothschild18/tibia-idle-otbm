"""
CLI: copia os marcadores que um humano pintou num OTBM para outro, aplicando
um offset de coordenada medido.

Existe porque marcador não é conteúdo derivável: a rota de uma hunt e a entrada
de uma quest saem de itens colocados à mão no editor, e quando o mapa de onde
eles saíram não é o mapa que o jogo usa, alguém tem de levá-los de um para o
outro. Fazer isso à mão em centenas de tiles é 219 chances de errar o eixo — e
errar o eixo é exatamente o defeito que este pipeline já viu acontecer.

Dois tipos de marcador, e a diferença é como cada um se identifica:

- **rota**: item de `travel_graph.MARKER_ITEM_IDS` (hoje 27869, "red energy
  ball"). Centenas deles, sem uid — exigir uid em cada um seria exigir
  centenas de cliques para marcar o que o id do item já diz.
- **quest**: item de qualquer id carregando um uid na faixa de quest e um texto
  (o slug, `copper_shield_quest`). Poucos, e o texto é o que dá nome.

A faixa de quest é **limitada nas duas pontas** de propósito. O mapa-mundo do
otservbr usa uid alto para as coisas dele — 50080, 64128 e outros aparecem de
verdade dentro de Rookgaard —, e uma faixa aberta em ">= 20001" copiaria esses
objetos como se fossem marcadores do autor.

Falha alto quando um marcador cai num tile que não existe no destino: rota
truncada e quest sem entrada são defeitos que o jogo não sabe explicar, e é
mais barato parar aqui.

Run: python transplant_markers.py --from raw-maps/FONTE.raw.json --into full-maps/ROOK/ROOK.otbm \\
        --offset -30958,-31074,0
"""

import argparse
import json
import os
import sys
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

import otbm_stream
import travel_graph

Node = Tuple[int, int, int]

# Faixa de uid reservada para marcador de quest — a mesma que
# `travel_graph.parse_quest_slug_markers` lê, e por isso importada de lá em vez
# de recopiada: duas faixas que discordam é um marcador que o transplante leva
# e o grafo não vê.
QUEST_MARKER_UID_MIN = travel_graph.QUEST_MARKER_UID_MIN
QUEST_MARKER_UID_MAX = travel_graph.QUEST_MARKER_UID_MAX


def _is_quest_marker(raw_item: Dict) -> bool:
    uid = raw_item.get("uid")
    if uid is None or not (QUEST_MARKER_UID_MIN <= uid <= QUEST_MARKER_UID_MAX):
        return False
    # Sem texto não há slug, e sem slug não há o que cunhar: é marcador
    # inacabado, não marcador de quest.
    return bool(raw_item.get("text"))


def read_markers(dump: Dict) -> List[Dict]:
    """Todo marcador do dump, na ordem da varredura, como
    `{kind, world, itemId, uid, text}`.

    `kind` é `"route"` ou `"quest"`. Uma instância por item, não por tile: seis
    tiles do mapa real carregam duas bolas, e a contagem é o que confere se o
    transplante levou tudo."""
    markers: List[Dict] = []

    for x, y, z, tile in travel_graph._iter_dump_tiles(dump):
        for raw_item in tile.get("items") or []:
            item_id = raw_item.get("id")
            if item_id in travel_graph.MARKER_ITEM_IDS:
                kind = "route"
            elif _is_quest_marker(raw_item):
                kind = "quest"
            else:
                continue

            markers.append({
                "kind": kind,
                "world": (x, y, z),
                "itemId": item_id,
                "uid": raw_item.get("uid"),
                "text": raw_item.get("text"),
            })

    return markers


def to_local(node: Node, offset: Sequence[int]) -> Node:
    return (node[0] + offset[0], node[1] + offset[1], node[2] + offset[2])


def plan_transplant(
    markers: Iterable[Dict],
    present_tiles: Set[Node],
    offset: Sequence[int],
    already_there: Optional[Set[Tuple[Node, int]]] = None,
) -> Tuple[List[Dict], List[Dict]]:
    """`(injeções, faltantes)`.

    Uma injeção é um marcador cujo tile de destino existe e que ainda não está
    lá. `already_there` é o conjunto `((x,y,z), itemId)` que o destino já tem,
    e é o que faz rodar duas vezes não empilhar 219 bolas sobre 219 bolas.

    Faltante é marcador cujo tile de destino não existe. Ele sai na lista em
    vez de ser descartado porque é a única pista de que a rota ficou truncada."""
    already_there = already_there or set()
    injections: List[Dict] = []
    missing: List[Dict] = []

    for marker in markers:
        local = to_local(marker["world"], offset)
        entry = {**marker, "local": local}

        if local not in present_tiles:
            missing.append(entry)
            continue
        if (local, marker["itemId"]) in already_there:
            continue

        injections.append(entry)

    return injections, missing


# ======================================================
# CLI
# ======================================================

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
EXTRACTOR_DIR = os.path.dirname(SCRIPTS_DIR)


def _parse_offset(raw: str) -> Tuple[int, int, int]:
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) != 3:
        sys.exit("error: --offset quer três inteiros, ex: -30958,-31074,0")
    try:
        return (int(parts[0]), int(parts[1]), int(parts[2]))
    except ValueError:
        sys.exit(f"error: --offset não é numérico: {raw!r}")


def _destination_tiles(data: bytes) -> Tuple[List, Dict[Node, int]]:
    """`(áreas, índice de tile)` do destino.

    As áreas vêm de `crop_tiles` aceitando tudo, então cada nó de tile é
    verbatim da fonte — reescrever o mapa não reinterpreta nada do que já
    estava lá. O índice diz, para cada `(x,y,z)`, em que área e em que posição
    aquele nó está, que é o que permite trocar só os tiles tocados."""
    areas = otbm_stream.crop_tiles(data, lambda x, y: True)
    index: Dict[Node, int] = {}

    for area_i, ((base_x, base_y, z), tile_nodes) in enumerate(areas):
        for tile_i, node in enumerate(tile_nodes):
            dx, dy = otbm_stream.tile_offsets(node, 0)
            index[(base_x + dx, base_y + dy, z)] = (area_i, tile_i)

    return areas, index


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--from", dest="source", required=True,
                        help="dump cru (raw-maps/<X>.raw.json) de onde os marcadores saem")
    parser.add_argument("--into", dest="destination", required=True,
                        help="OTBM de destino, reescrito no lugar")
    parser.add_argument("--offset", required=True,
                        help="dx,dy,dz aplicado à coordenada de origem, ex: -30958,-31074,0")
    parser.add_argument("--dry-run", action="store_true",
                        help="só relata; não escreve no destino")
    args = parser.parse_args()

    offset = _parse_offset(args.offset)

    if not os.path.exists(args.source):
        sys.exit(f"error: dump de origem não encontrado em {args.source}")
    if not os.path.exists(args.destination):
        sys.exit(f"error: OTBM de destino não encontrado em {args.destination}")

    with open(args.source, encoding="utf-8") as handle:
        markers = read_markers(json.load(handle))

    by_kind: Dict[str, int] = {}
    for marker in markers:
        by_kind[marker["kind"]] = by_kind.get(marker["kind"], 0) + 1
    print(f"origem: {len(markers)} marcadores {by_kind}")

    with open(args.destination, "rb") as handle:
        data = handle.read()

    areas, index = _destination_tiles(data)
    print(f"destino: {len(index)} tiles em {len(areas)} áreas")

    # O que o destino já tem, para o transplante ser idempotente.
    already = _existing_markers(areas)

    injections, missing = plan_transplant(markers, set(index), offset, already)

    print(f"injetar: {len(injections)} | já lá: {len(markers) - len(injections) - len(missing)}"
          f" | sem tile de destino: {len(missing)}")

    if missing:
        for entry in missing[:20]:
            print(f"  [!!] {entry['kind']} {entry['world']} -> {entry['local']} "
                  f"item={entry['itemId']} texto={entry['text']!r}: tile não existe no destino")
        sys.exit(
            f"error: {len(missing)} marcador(es) sem tile de destino — rota truncada ou quest "
            f"sem entrada. Confira o offset antes de seguir."
        )

    if args.dry_run:
        print("  (dry-run: nada escrito)")
        return

    for entry in injections:
        area_i, tile_i = index[entry["local"]]
        item = otbm_stream.item_node(
            entry["itemId"], unique_id=entry["uid"], text=entry["text"]
        )
        _, tile_nodes = areas[area_i]
        tile_nodes[tile_i] = otbm_stream.with_extra_item(tile_nodes[tile_i], item)

    header = otbm_stream.map_header(data)
    city = os.path.splitext(os.path.basename(args.destination))[0]
    written = otbm_stream.write_map(
        args.destination,
        header,
        f"{city} com marcadores transplantados por transplant_markers.py",
        f"{city}-monster.xml",
        f"{city}-house.xml",
        areas,
        otbm_stream.towns(data),
    )
    print(f"  -> {args.destination}: {written} tiles, {len(injections)} marcadores injetados")


def _existing_markers(areas) -> Set[Tuple[Node, int]]:
    """Marcadores que o destino já carrega, lidos dos próprios nós de tile."""
    found: Set[Tuple[Node, int]] = set()
    for (base_x, base_y, z), tile_nodes in areas:
        for node in tile_nodes:
            dx, dy = otbm_stream.tile_offsets(node, 0)
            here = (base_x + dx, base_y + dy, z)
            for item_id, uid, _text in _tile_items(node):
                if item_id in travel_graph.MARKER_ITEM_IDS or (
                    uid is not None and QUEST_MARKER_UID_MIN <= uid <= QUEST_MARKER_UID_MAX
                ):
                    found.add((here, item_id))
    return found


def _tile_items(tile_node: bytes):
    """`(item id, uid, text)` de cada item do nó de tile, lido dos bytes."""
    for child_start, _ in otbm_stream.children(tile_node, 0):
        if otbm_stream.node_type(tile_node, child_start) != otbm_stream.OTBM_ITEM:
            continue
        raw = otbm_stream.unescape(
            tile_node[child_start + 1 : otbm_stream.node_end(tile_node, child_start)]
        )
        if len(raw) < 3:
            continue
        item_id = int.from_bytes(raw[1:3], "little")
        uid: Optional[int] = None
        text: Optional[str] = None
        i = 3
        while i < len(raw):
            attr = raw[i]
            i += 1
            if attr == otbm_stream.OTBM_ATTR_UNIQUE_ID and i + 2 <= len(raw):
                uid = int.from_bytes(raw[i : i + 2], "little")
                i += 2
            elif attr == otbm_stream.OTBM_ATTR_ACTION_ID and i + 2 <= len(raw):
                i += 2
            elif attr == otbm_stream.OTBM_ATTR_TEXT and i + 2 <= len(raw):
                length = int.from_bytes(raw[i : i + 2], "little")
                text = raw[i + 2 : i + 2 + length].decode("latin-1", errors="replace")
                i += 2 + length
            else:
                # Atributo que este leitor não conhece: não dá para saber o
                # comprimento, então para aqui em vez de adivinhar e ler lixo.
                break
        yield item_id, uid, text


if __name__ == "__main__":
    main()
