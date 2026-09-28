"""
CLI: copia os marcadores que um humano pintou num OTBM para outro, aplicando
um offset de coordenada medido.

Existe porque marcador não é conteúdo derivável: a rota de uma hunt, a entrada
de uma quest e a placa que nomeia um POI saem de itens colocados à mão no
editor, e quando o mapa de onde eles saíram não é o mapa que o jogo usa, alguém
tem de levá-los de um para o outro. Fazer isso à mão em centenas de tiles é 219
chances de errar o eixo — e errar o eixo é exatamente o defeito que este
pipeline já viu acontecer.

Três tipos de marcador, e a diferença é como cada um se identifica:

- **rota**: item de `travel_graph.MARKER_ITEM_IDS` (hoje 27869, "red energy
  ball"). Centenas deles, sem uid — exigir uid em cada um seria exigir
  centenas de cliques para marcar o que o id do item já diz.
- **quest**: item de qualquer id carregando um uid na faixa de quest e um texto
  (o slug, `copper_shield_quest`). Poucos, e o texto é o que dá nome.
- **placa**: item 2016 com uid na faixa reservada de POI (>= 10001) e texto
  `CIDADE-TIPO-NNNN`. É o que faz nascer a location de entrada de uma hunt, e
  por isso é o marcador mais caro de perder: sem placa,
  `apply_graph_rejections` derruba a hunt três comandos depois, longe da causa.

A faixa de quest é **limitada nas duas pontas** de propósito. O mapa-mundo do
otservbr usa uid alto para as coisas dele — 50080, 64128 e outros aparecem de
verdade dentro de Rookgaard —, e uma faixa aberta em ">= 20001" copiaria esses
objetos como se fossem marcadores do autor.

Duas fontes, e `--from` aceita as duas porque os dois casos reais têm
procedência diferente:

- **dump cru** (`raw-maps/<X>.raw.json`): de onde saem rota e quest, que são
  pintadas no mapa-mundo e por isso sobrevivem a um recorte novo por conta
  própria.
- **snapshot de placas** (`sign-snapshots/<CIDADE>-<sha>.json`, do
  `dump_marker_signs.py`): de onde saem as placas. Elas **não existem no
  mapa-mundo** — recortar a cidade de novo produz um mapa sem nenhuma —, então
  a fonte delas é o snapshot tirado antes de o arquivo ser sobrescrito, não um
  dump.

O offset é argumento, sem default, e o sentido dele é do chamador: o mesmo par
de mapas se transplanta nos dois sentidos. Para Rookgaard, **local -> mundo** é
`+30958,+31074,0` e **mundo -> local** é o negativo disso. Como foi medido:
casando grupo de spawn por assinatura `(z, radius, roster ordenado)` entre
`full-maps/ROOK/ROOK-monster.xml` e o `otservbr-monster.xml` do mapa-mundo e
votando o delta de cada par — 590 de 626 grupos casam exatos, o segundo
colocado fica em 53 votos (ruído de assinatura genérica casando com vizinho).
Como conferir sem refazer a medição: `ROOK-TEMPLE-0001` local `(1139,1145,7)`
tem de cair no templo de Rookgaard, mundo `(32097,32219,7)`. Um offset sem
procedência é número mágico, e um número mágico com o sinal trocado põe as
placas 30 mil tiles fora da ilha.

Falha alto, e nomeia quem, quando um marcador não pode ser injetado: tile de
destino que não existe, tile que existe e não é andável, ou uid de placa já
ocupado por outra placa. Rota truncada, quest sem entrada e POI que desaparece
são defeitos que o jogo não sabe explicar, e é mais barato parar aqui.

Run: python transplant_markers.py --from raw-maps/FONTE.raw.json --into full-maps/ROOK/ROOK.otbm \\
        --offset -30958,-31074,0
     python transplant_markers.py --from sign-snapshots/ROOK-<sha>.json \\
        --into full-maps/ROOK/ROOK.otbm --offset 30958,31074,0
"""

import argparse
import json
import os
import sys
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

import appearance_flags
import otbm_stream
import travel_graph

Node = Tuple[int, int, int]

# Faixa de uid reservada para marcador de quest — a mesma que
# `travel_graph.parse_quest_slug_markers` lê, e por isso importada de lá em vez
# de recopiada: duas faixas que discordam é um marcador que o transplante leva
# e o grafo não vê.
QUEST_MARKER_UID_MIN = travel_graph.QUEST_MARKER_UID_MIN
QUEST_MARKER_UID_MAX = travel_graph.QUEST_MARKER_UID_MAX

# E o mesmo para a placa: item e piso de uid saem de `travel_graph`, que é quem
# decide o que o grafo enxerga como placa.
SIGN_ITEM_ID = travel_graph.SIGN_ITEM_ID
SIGN_UID_MIN = travel_graph.MARKER_UID_MIN

REASON_NO_TILE = "tile-de-destino-nao-existe"
REASON_UNPASSABLE = "tile-de-destino-nao-andavel"
REASON_UID_TAKEN = "uid-ja-ocupado-por-outra-placa"


def _is_quest_marker(raw_item: Dict) -> bool:
    uid = raw_item.get("uid")
    if uid is None or not (QUEST_MARKER_UID_MIN <= uid <= QUEST_MARKER_UID_MAX):
        return False
    # Sem texto não há slug, e sem slug não há o que cunhar: é marcador
    # inacabado, não marcador de quest.
    return bool(raw_item.get("text"))


def read_markers(dump: Dict) -> List[Dict]:
    """Todo marcador do dump, na ordem da varredura, como
    `{kind, source, itemId, uid, text}`.

    `kind` é `"route"` ou `"quest"`. Uma instância por item, não por tile: seis
    tiles do mapa real carregam duas bolas, e a contagem é o que confere se o
    transplante levou tudo.

    Placa não sai daqui de propósito. O dump que serve de fonte é o do
    mapa-mundo, e no mapa-mundo placa de POI não existe — quem a lê é
    `read_signs`, do snapshot."""
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
                "source": (x, y, z),
                "itemId": item_id,
                "uid": raw_item.get("uid"),
                "text": raw_item.get("text"),
            })

    return markers


def read_signs(snapshot: Dict) -> List[Dict]:
    """As placas de um snapshot do `dump_marker_signs.py`, como
    `{kind: "sign", source, itemId, uid, text, id}`.

    O snapshot já é a saída de `parse_marker_signs`, então não há filtro a
    reaplicar aqui — repetir o parser sobre a saída dele seria uma segunda
    cópia da regra. O que se confere é o uid: abaixo da faixa reservada a placa
    **aparece desenhada no jogo** (`map_v6.py` e `minimap.py` apagam do bundle
    pela faixa, não pelo id do item), e uma placa visível é um defeito que só
    se descobre olhando a tela."""
    signs: List[Dict] = []

    for row in snapshot.get("signs") or []:
        uid = row.get("uid")
        if uid is None or uid < SIGN_UID_MIN:
            sys.exit(
                f"error: placa {row.get('id')!r} com uid={uid} fora da faixa reservada "
                f"(>= {SIGN_UID_MIN}) — injetada assim, ela apareceria desenhada no jogo."
            )
        signs.append({
            "kind": "sign",
            "source": (row["x"], row["y"], row["z"]),
            "itemId": SIGN_ITEM_ID,
            "uid": uid,
            # O texto é o id do POI, e vai verbatim: é dele que
            # `parse_marker_signs` cunha o id do outro lado.
            "text": row["text"],
            "id": row.get("id"),
        })

    return signs


def read_source(document: Dict) -> List[Dict]:
    """Os marcadores de um `--from`, seja ele dump cru ou snapshot de placas.

    A forma do arquivo é o que decide, não a extensão nem um flag: um snapshot
    tem `signs`, um dump tem `data.nodes`. Um flag `--kind` deixaria o operador
    pedir a leitura errada do arquivo certo, e a leitura errada de um dump de 72
    MB é zero marcador — silêncio, não erro."""
    if "signs" in document:
        return read_signs(document)
    if "data" in document:
        return read_markers(document)
    sys.exit(
        "error: --from não parece nem dump cru (sem 'data') nem snapshot de placas "
        "(sem 'signs')."
    )


def to_target(node: Node, offset: Sequence[int]) -> Node:
    return (node[0] + offset[0], node[1] + offset[1], node[2] + offset[2])


def plan_transplant(
    markers: Iterable[Dict],
    present_tiles: Set[Node],
    offset: Sequence[int],
    already_there: Optional[Set[Tuple[Node, int]]] = None,
    unpassable: Optional[Set[Node]] = None,
    sign_uid_owner: Optional[Dict[int, Node]] = None,
) -> Tuple[List[Dict], List[Dict]]:
    """`(injeções, recusas)`.

    Uma injeção é um marcador cujo tile de destino existe e que ainda não está
    lá. `already_there` é o conjunto `((x,y,z), itemId)` que o destino já tem,
    e é o que faz rodar duas vezes não empilhar 219 bolas sobre 219 bolas.

    Recusa é marcador que não pode ser injetado, com o `reason` dizendo qual dos
    três casos. Ela sai na lista em vez de ser descartada porque é a única
    pista de que a rota ficou truncada ou o POI desapareceu.

    `unpassable` e `sign_uid_owner` valem **só para placa**. Placa é o tile de
    onde se chega num destino, então um tile `unpass` a torna um POI que
    `apply_graph_rejections` derruba, e um uid repetido faz duas placas
    cunharem o mesmo POI. Bola de rota é outra coisa: ela marca caminho, quem
    reclama de caminho que não fecha é o `build_painted_route.py`, e recusá-la
    aqui pararia o transplante por um defeito que não é deste comando."""
    already_there = already_there or set()
    unpassable = unpassable or set()
    sign_uid_owner = sign_uid_owner or {}
    injections: List[Dict] = []
    refusals: List[Dict] = []

    for marker in markers:
        target = to_target(marker["source"], offset)
        entry = {**marker, "target": target}

        if target not in present_tiles:
            refusals.append({**entry, "reason": REASON_NO_TILE})
            continue
        if (target, marker["itemId"]) in already_there:
            continue

        if marker["kind"] == "sign":
            if target in unpassable:
                refusals.append({**entry, "reason": REASON_UNPASSABLE})
                continue
            owner = sign_uid_owner.get(marker["uid"])
            if owner is not None and owner != target:
                refusals.append({**entry, "reason": REASON_UID_TAKEN, "owner": owner})
                continue

        injections.append(entry)

    return injections, refusals


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


def as_dump(areas) -> Dict:
    """As áreas do destino na forma de dump cru, para reusar quem já sabe ler
    dump.

    Andabilidade é `travel_graph.extract_tile_flags`, e ela come dump, não nó
    de OTBM. Reconstituir o dump é mais barato que reescrever a regra de
    `unpass` aqui: a regra já tinha três cópias no repo uma vez, e a quarta é
    a que ia discordar do grafo que rejeita o POI."""
    features = []

    for (base_x, base_y, z), tile_nodes in areas:
        tiles = []
        for node in tile_nodes:
            dx, dy = otbm_stream.tile_offsets(node, 0)
            tiles.append({
                "x": dx,
                "y": dy,
                "tileid": otbm_stream.tile_ground_id(node, 0),
                "items": [
                    {"id": item_id, "uid": uid, "text": text}
                    for item_id, uid, text in _tile_items(node)
                ],
            })
        features.append({"x": base_x, "y": base_y, "z": z, "tiles": tiles})

    return {"data": {"nodes": [{"features": features}]}}


def _unpassable_tiles(areas, city: str) -> Set[Node]:
    tiles = travel_graph.extract_tile_flags(
        as_dump(areas), appearance_flags.load_flags(city)
    )
    return {(t["x"], t["y"], t["z"]) for t in tiles if t["unpass"]}


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--from", dest="source", required=True,
                        help="dump cru (raw-maps/<X>.raw.json) ou snapshot de placas "
                             "(sign-snapshots/<CIDADE>-<sha>.json) de onde os marcadores saem")
    parser.add_argument("--into", dest="destination", required=True,
                        help="OTBM de destino, reescrito no lugar")
    parser.add_argument("--offset", required=True,
                        help="dx,dy,dz aplicado à coordenada de origem, ex: -30958,-31074,0")
    parser.add_argument("--dry-run", action="store_true",
                        help="só relata; não escreve no destino")
    args = parser.parse_args()

    offset = _parse_offset(args.offset)

    if not os.path.exists(args.source):
        sys.exit(f"error: arquivo de origem não encontrado em {args.source}")
    if not os.path.exists(args.destination):
        sys.exit(f"error: OTBM de destino não encontrado em {args.destination}")

    with open(args.source, encoding="utf-8") as handle:
        markers = read_source(json.load(handle))

    by_kind: Dict[str, int] = {}
    for marker in markers:
        by_kind[marker["kind"]] = by_kind.get(marker["kind"], 0) + 1
    print(f"origem: {len(markers)} marcadores {by_kind}")

    with open(args.destination, "rb") as handle:
        data = handle.read()

    areas, index = _destination_tiles(data)
    print(f"destino: {len(index)} tiles em {len(areas)} áreas")

    # O que o destino já tem, para o transplante ser idempotente.
    already, sign_uid_owner = _existing_markers(areas)

    # A tabela de flags do destino só é lida quando há placa para injetar: um
    # transplante de rota funciona em mapa que ainda não tem tabela gerada, e
    # exigi-la ali seria pedir um arquivo que não muda a resposta.
    city = os.path.splitext(os.path.basename(args.destination))[0]
    unpassable = _unpassable_tiles(areas, city) if by_kind.get("sign") else set()

    injections, refusals = plan_transplant(
        markers, set(index), offset, already, unpassable, sign_uid_owner
    )

    print(f"injetar: {len(injections)} | já lá: {len(markers) - len(injections) - len(refusals)}"
          f" | recusados: {len(refusals)}")

    for entry in injections:
        if entry["kind"] == "sign":
            print(f"  {entry['text']} uid={entry['uid']} "
                  f"origem{entry['source']} -> destino{entry['target']}")

    if refusals:
        for entry in refusals[:20]:
            print(f"  [!!] {entry['kind']} origem{entry['source']} -> destino{entry['target']} "
                  f"item={entry['itemId']} uid={entry['uid']} texto={entry['text']!r}: "
                  f"{entry['reason']}"
                  + (f" (em {entry['owner']})" if entry.get("owner") else ""))
        sys.exit(
            f"error: {len(refusals)} marcador(es) recusado(s) — rota truncada, quest sem "
            f"entrada ou POI que desaparece. Confira o offset antes de seguir."
        )

    if args.dry_run:
        print("  (dry-run: nada escrito)")
        return

    for entry in injections:
        area_i, tile_i = index[entry["target"]]
        item = otbm_stream.item_node(
            entry["itemId"], unique_id=entry["uid"], text=entry["text"]
        )
        _, tile_nodes = areas[area_i]
        tile_nodes[tile_i] = otbm_stream.with_extra_item(tile_nodes[tile_i], item)

    header = otbm_stream.map_header(data)
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


def _existing_markers(areas) -> Tuple[Set[Tuple[Node, int]], Dict[int, Node]]:
    """`(marcadores que o destino já carrega, tile de cada uid de placa)`, lidos
    dos próprios nós de tile.

    O mapa de uid é restrito a item de placa de propósito. O mapa-mundo usa uid
    alto para as coisas dele (50080, 64128 vistos de verdade em Rookgaard), e
    um mapa de uid aberto recusaria uma placa por colidir com um objeto do
    otservbr que não é placa nenhuma."""
    found: Set[Tuple[Node, int]] = set()
    sign_uid_owner: Dict[int, Node] = {}

    for (base_x, base_y, z), tile_nodes in areas:
        for node in tile_nodes:
            dx, dy = otbm_stream.tile_offsets(node, 0)
            here = (base_x + dx, base_y + dy, z)
            for item_id, uid, _text in _tile_items(node):
                is_sign = item_id == SIGN_ITEM_ID and uid is not None and uid >= SIGN_UID_MIN
                is_route = item_id in travel_graph.MARKER_ITEM_IDS
                is_quest = uid is not None and QUEST_MARKER_UID_MIN <= uid <= QUEST_MARKER_UID_MAX

                if is_sign:
                    sign_uid_owner.setdefault(uid, here)
                if is_sign or is_route or is_quest:
                    found.add((here, item_id))

    return found, sign_uid_owner


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
