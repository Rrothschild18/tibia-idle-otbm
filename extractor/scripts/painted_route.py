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

**Um tile pintado inalcançável é erro, não aviso.** Uma bola atrás de parede é
rota truncada, e numa caçada que só acaba quando a área está limpa isso é uma
quest que nunca fecha. Melhor parar aqui, nomeando o tile, do que entregar ao
jogo um corredor sem fim.
"""

from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

import travel_graph

Node = Tuple[int, int, int]


class UnreachablePaintedTile(Exception):
    """Tiles pintados que o grafo andável não alcança, com quais são.

    Exceção própria e não `ValueError` porque quem chama precisa distinguir
    "mapa mal desenhado, com endereço" de "argumento errado"."""

    def __init__(self, tiles: Sequence[Node]):
        self.tiles = list(tiles)
        addresses = ", ".join(f"({x},{y},{z})" for x, y, z in self.tiles[:10])
        more = "" if len(self.tiles) <= 10 else f" e outros {len(self.tiles) - 10}"
        super().__init__(
            f"{len(self.tiles)} tile(s) de caminho pintado que ninguém alcança: "
            f"{addresses}{more}"
        )


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
) -> Dict:
    """`{waypoints, painted, bridged, floors}` seguindo o caminho pintado.

    Cada waypoint é `{x, y, z, kind}`, com `kind` em `path` (tile pintado) ou
    `bridge` (tile que o gerador inseriu para fechar um vão). A entrada não
    entra na lista: ela é de onde se parte, não um lugar a visitar.

    O próximo destino é sempre o tile pintado não visitado **mais próximo pelo
    grafo**, e não o adjacente. Num corredor contínuo as duas regras dão a mesma
    coisa; num caminho quebrado só a primeira continua funcionando, e é o que
    dispensa tratar fragmento como caso especial."""
    remaining = set(painted_tiles(dump))
    waypoints: List[Dict] = []

    if not remaining:
        return {"waypoints": [], "painted": 0, "bridged": 0, "floors": []}

    unreachable = [tile for tile in remaining if tile not in graph]
    if unreachable:
        raise UnreachablePaintedTile(sorted(unreachable))

    current = start
    painted_count = 0
    bridged_count = 0

    while remaining:
        distances, prev = travel_graph.tile_distances_and_prev(
            graph, {current: 0}, set(remaining)
        )
        reached = {tile: cost for tile, cost in distances.items() if tile in remaining}
        if not reached:
            raise UnreachablePaintedTile(sorted(remaining))

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
    }
