"""
Lógica pura: o caminho que alguém pintou no editor -> a rota ordenada que o
gerador de waypoints consome.

O caminho é pintado com um item-marcador (`travel_graph.MARKER_ITEM_IDS`), tile
a tile, e a ordem sai da **adjacência**: começa na entrada e vai para o tile
pintado mais próximo ainda não visitado, pelo grafo andável. Não há número em
marcador nenhum, e não precisa haver — pintar 219 tiles já é dizer por onde ir.

Duas consequências que o mapa real impõe:

**O caminho quebra.** Onde há escada, o autor pinta os dois lados e não o meio:
a transição te move de lado, não reto. No mapa de Rookgaard os dois caminhos
pintados viraram 8 pedaços. O vão é fechado pelo mesmo grafo andável que a
viagem usa — incluindo as arestas de troca de andar —, e o tile inserido sai
marcado como `bridge` para que ninguém o confunda com caminho pintado.

**A entrada é rótulo, não chão.** O autor põe o marcador sobre o que identifica
o lugar, e em ROOK-HUNT-0014 ele caiu sobre uma lápide de verdade (item 2012,
"Kendram Benson"), que bloqueia de propósito. O marcador em si sai das flags
(`travel_graph.is_marker_item`), a lápide não — e a entrada ficava fora do grafo,
o que fazia os 109 tiles pintados do mapa virarem 0 alcançáveis. Então a entrada
desce para o vizinho andável que alcança mais caminho pintado, e o artefato diz
que desceu e de onde. Apagar a lápide tiraria conteúdo de Rookgaard, e liberar o
id 2012 nas flags tornaria andável toda lápide da ilha.

**O que precisa fechar é a cobertura de spawn, não a de bola pintada.** A regra
antiga parava em qualquer tile pintado inalcançável. Mas "todos os monstros
precisam morrer" é promessa sobre monstro: no mapa da Katana os 9 tiles pintados
que ninguém alcança estão atrás de uma porta trancada (5106) e de uma porta
fechada (5107) e **não têm spawn nenhum** — parar por causa deles é parar por
decoração. Então este módulo mede e nomeia as duas coberturas, e quem decide o
que é reprovação é o CLI (spawn fora do alcance) e, no jogo, o
`requiredKillPercent` da quest. Porta e parede secreta são mecânica que o grafo
não modela de propósito — ver `travel_graph.connect_orphan_hunts`.
"""

from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

import travel_graph

Node = Tuple[int, int, int]


class EntranceUnreachable(Exception):
    """O tile marcado como entrada não é andável e nenhum vizinho dele serve.

    Exceção e não relatório porque sem entrada não há rota nenhuma a medir: é o
    único caso em que não há o que entregar."""

    def __init__(self, start: Node):
        self.start = start
        super().__init__(
            f"a entrada {start} não é andável e nenhum dos 8 vizinhos dela alcança "
            "caminho pintado — o marcador está dentro de parede, não sobre mobília"
        )


def _neighbours(node: Node) -> List[Node]:
    """Os 8 vizinhos do mesmo andar, em ordem fixa.

    Ordem fixa porque o desempate do snap é por coordenada: duas rodadas do
    pipeline sobre o mesmo mapa têm que escolher a mesma entrada."""
    x, y, z = node
    return [
        (x + dx, y + dy, z)
        for dx in (-1, 0, 1)
        for dy in (-1, 0, 1)
        if (dx, dy) != (0, 0)
    ]


def reachable_from(graph: Dict[Node, Set[Node]], origin: Node) -> Set[Node]:
    """Tudo que se alcança a pé de `origin`, incluindo trocas de andar."""
    if origin not in graph:
        return set()

    seen = {origin}
    stack = [origin]
    while stack:
        current = stack.pop()
        for neighbour in graph.get(current, ()):  # noqa: SIM118 - dict de conjuntos
            if neighbour not in seen:
                seen.add(neighbour)
                stack.append(neighbour)
    return seen


def resolve_entrance(
    start: Node,
    graph: Dict[Node, Set[Node]],
    painted: Set[Node],
) -> Tuple[Node, Optional[Node]]:
    """`(entrada, de_onde_desceu)` — o segundo é `None` quando não precisou descer.

    Escolhe o vizinho que alcança **mais** caminho pintado, e não o primeiro
    andável: num corredor com a lápide no meio os dois lados são andáveis e só um
    leva à quest."""
    if start in graph:
        return start, None

    best: Optional[Tuple[Tuple[int, Node], Node]] = None
    for candidate in _neighbours(start):
        if candidate not in graph:
            continue
        covered = len(painted & reachable_from(graph, candidate))
        key = (-covered, candidate)
        if best is None or key < best[0]:
            best = (key, candidate)

    if best is None or (painted and -best[0][0] == 0):
        raise EntranceUnreachable(start)

    return best[1], start


def painted_tiles(dump: Dict) -> Set[Node]:
    """Os tiles que carregam item-marcador de caminho.

    Um tile com duas bolas é um tile — a rota passa uma vez por lugar."""
    found: Set[Node] = set()

    for x, y, z, tile in travel_graph._iter_dump_tiles(dump):
        for raw_item in tile.get("items") or []:
            if raw_item.get("id") in travel_graph.MARKER_ITEM_IDS:
                found.add((x, y, z))
                break

    return found


def build_painted_route(
    dump: Dict,
    graph: Dict[Node, Set[Node]],
    start: Node,
    spawns: Iterable[Node] = (),
) -> Dict:
    """A rota do caminho pintado, mais as duas coberturas medidas.

    Cada waypoint é `{x, y, z, kind}`, com `kind` em `path` (tile pintado) ou
    `bridge` (tile que o gerador inseriu para fechar um vão). A entrada não entra
    na lista: ela é de onde se parte, não um lugar a visitar.

    O próximo destino é sempre o tile pintado não visitado **mais próximo pelo
    grafo**, e não o adjacente. Num corredor contínuo as duas regras dão a mesma
    coisa; num caminho quebrado só a primeira continua funcionando, e é o que
    dispensa tratar fragmento como caso especial.

    `spawns` é opcional porque a ordenação da rota não depende dela — ela entra
    para que o artefato diga quantos monstros a rota alcança, que é a promessa
    que a quest faz ao jogador."""
    painted = painted_tiles(dump)
    entrance, snapped_from = resolve_entrance(start, graph, painted)
    reach = reachable_from(graph, entrance)

    remaining = set(painted & reach)
    unreachable_painted = sorted(painted - reach)

    spawn_tiles = list(spawns)
    unreachable_spawns = sorted({tile for tile in spawn_tiles if tile not in reach})

    coverage = {
        "entrance": _point(entrance),
        "entranceSnappedFrom": None if snapped_from is None else _point(snapped_from),
        "paintedTotal": len(painted),
        "unreachablePainted": [_point(tile) for tile in unreachable_painted],
        "spawnsTotal": len(spawn_tiles),
        "unreachableSpawns": [_point(tile) for tile in unreachable_spawns],
    }

    waypoints: List[Dict] = []
    painted_count = 0
    bridged_count = 0
    current = entrance

    while remaining:
        distances, prev = travel_graph.tile_distances_and_prev(
            graph, {current: 0}, set(remaining)
        )
        reached = {tile: cost for tile, cost in distances.items() if tile in remaining}
        # `remaining` já é só o que a entrada alcança, então isto não acontece —
        # mas se acontecer é bug de grafo, e travar calado seria pior.
        if not reached:
            raise AssertionError(
                f"tiles pintados dentro do componente da entrada que a busca não "
                f"alcançou: {sorted(remaining)[:5]}"
            )

        target = min(reached, key=lambda tile: (reached[tile], tile))
        path = travel_graph.reconstruct_path(prev, target) if target != current else [target]

        # O primeiro nó do caminho é de onde já se está: ele não vira waypoint
        # de novo, senão a rota repete o tile a cada pedaço.
        for node in path[1:] if path and path[0] == current else path:
            kind = "path" if node in remaining else "bridge"
            waypoints.append({"x": node[0], "y": node[1], "z": node[2], "kind": kind})
            if kind == "path":
                painted_count += 1
                remaining.discard(node)
            else:
                bridged_count += 1

        current = target

    return {
        "waypoints": waypoints,
        "painted": painted_count,
        "bridged": bridged_count,
        "floors": sorted({w["z"] for w in waypoints}),
        **coverage,
    }


def _point(node: Node) -> Dict[str, int]:
    return {"x": node[0], "y": node[1], "z": node[2]}
