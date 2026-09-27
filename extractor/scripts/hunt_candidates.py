"""Candidatas de hunt de uma cidade recortada — lógica pura.

Uma candidata é **um bolsão de spawn num andar**: pontos de spawn agrupados por
proximidade, sem nunca atravessar parede (dois pontos só entram no mesmo bolsão
se estiverem no mesmo componente caminhável daquele andar). Daí nascerem
separadas as duas metades de uma mina que não se alcançam a pé, em vez de virar
"a caverna inteira" — e daí uma hunt ser de um andar só por padrão, que é como
elas foram feitas à mão em Rookgaard.

O que a máquina **não** decide: se dois bolsões são a mesma hunt (fundir), se um
bolsão devia ser duas por espécie (dividir) e como a hunt se chama. Por isso
cada candidata carrega o desmembramento por espécie já calculado — a tela de
curadoria precisa dos números para oferecer as duas ações sem recalcular nada.
"""

from collections import Counter, defaultdict
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple
import xml.etree.ElementTree as ElementTree

Node = Tuple[int, int, int]

DEFAULT_CLUSTER_RADIUS = 10
DEFAULT_MIN_CREATURES = 3

_NEIGHBOR_OFFSETS = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]


def parse_spawn_xml(xml_text: str) -> List[Dict]:
    """`<monster centerx centery centerz>` com filhos por deslocamento -> pontos.

    O `z` do filho é absoluto no export do editor (repete o `centerz`), não um
    deslocamento — somá-lo ao centro dobraria o andar.
    """
    root = ElementTree.fromstring(xml_text)
    points: List[Dict] = []
    for group in root:
        center_x = int(group.get("centerx"))
        center_y = int(group.get("centery"))
        center_z = int(group.get("centerz"))
        radius = int(group.get("radius", 0))
        for entry in group:
            z = entry.get("z")
            points.append(
                {
                    "name": entry.get("name"),
                    "x": center_x + int(entry.get("x")),
                    "y": center_y + int(entry.get("y")),
                    "z": int(z) if z is not None else center_z,
                    "spawntime": int(entry.get("spawntime", 0)),
                    "radius": radius,
                }
            )
    return points


def same_floor_components(walkable: Set[Node]) -> Dict[Node, int]:
    """Componente conexo por andar, 8-vizinhos. Escada não liga nada aqui: a
    pergunta é "dá pra andar daqui até lá sem trocar de andar?"."""
    component_of: Dict[Node, int] = {}
    next_id = 0
    for start in walkable:
        if start in component_of:
            continue
        stack = [start]
        component_of[start] = next_id
        while stack:
            x, y, z = stack.pop()
            for dx, dy in _NEIGHBOR_OFFSETS:
                neighbor = (x + dx, y + dy, z)
                if neighbor in walkable and neighbor not in component_of:
                    component_of[neighbor] = next_id
                    stack.append(neighbor)
        next_id += 1
    return component_of


def anchor_tile(point: Dict, walkable: Set[Node], reach: int = 2) -> Optional[Node]:
    """O tile caminhável que representa um spawn — ele mesmo, ou o vizinho mais
    próximo. Um spawn costuma cair em cima de um tile bloqueado (o ponto é o
    centro do grupo, não um lugar onde se pisa)."""
    node = (point["x"], point["y"], point["z"])
    if node in walkable:
        return node
    for distance in range(1, reach + 1):
        for dx in range(-distance, distance + 1):
            for dy in range(-distance, distance + 1):
                if max(abs(dx), abs(dy)) != distance:
                    continue
                neighbor = (node[0] + dx, node[1] + dy, node[2])
                if neighbor in walkable:
                    return neighbor
    return None


def _cluster(indexed: Sequence[Tuple[int, Dict]], radius: int, key_of) -> List[List[Dict]]:
    """Agrupamento por ligação simples: dois pontos ficam juntos se distam
    `radius` em Chebyshev **e** `key_of` (o componente caminhável) é o mesmo."""
    parent = list(range(len(indexed)))

    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    buckets: Dict[Tuple[int, int, object], List[int]] = defaultdict(list)
    for position, (_, point) in enumerate(indexed):
        buckets[(point["x"] // radius, point["y"] // radius, key_of(point))].append(position)

    for (cell_x, cell_y, key), positions in buckets.items():
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for other in buckets.get((cell_x + dx, cell_y + dy, key), ()):
                    for position in positions:
                        if position >= other:
                            continue
                        first, second = indexed[position][1], indexed[other][1]
                        if (
                            max(abs(first["x"] - second["x"]), abs(first["y"] - second["y"]))
                            <= radius
                        ):
                            root_a, root_b = find(position), find(other)
                            if root_a != root_b:
                                parent[root_a] = root_b

    grouped: Dict[int, List[Dict]] = defaultdict(list)
    for position, (_, point) in enumerate(indexed):
        grouped[find(position)].append(point)
    return list(grouped.values())


def _extent(points: Sequence[Dict]) -> Dict:
    xs = [p["x"] for p in points]
    ys = [p["y"] for p in points]
    return {
        "minX": min(xs),
        "minY": min(ys),
        "maxX": max(xs),
        "maxY": max(ys),
        "centerX": (min(xs) + max(xs)) // 2,
        "centerY": (min(ys) + max(ys)) // 2,
    }


def _species(points: Sequence[Dict]) -> List[Dict]:
    counts = Counter(p["name"] for p in points)
    return [{"name": name, "count": count} for name, count in counts.most_common()]


def build_candidates(
    city: str,
    points: Sequence[Dict],
    walkable: Set[Node],
    component_of: Dict[Node, int],
    subarea_of_column=None,
    radius: int = DEFAULT_CLUSTER_RADIUS,
    min_creatures: int = DEFAULT_MIN_CREATURES,
) -> Tuple[List[Dict], List[Dict]]:
    """-> `(candidatas, spawns sem tile caminhável por perto)`.

    O segundo valor não é ruído a esconder: spawn que não encosta em tile
    andável costuma ser bicho atrás de parede (ou erro de mapa), e some da
    contagem da candidata sem esse relatório.
    """
    anchored: List[Tuple[int, Dict]] = []
    orphans: List[Dict] = []
    for point in points:
        anchor = anchor_tile(point, walkable)
        if anchor is None:
            orphans.append(point)
            continue
        anchored.append((component_of.get(anchor, -1), {**point, "anchor": anchor}))

    candidates: List[Dict] = []
    by_floor: Dict[int, int] = defaultdict(int)
    component_size = Counter(component_of.values())

    groups = _cluster(anchored, radius, key_of=lambda p: component_of.get(p["anchor"], -1))
    for group in sorted(
        groups, key=lambda g: (g[0]["z"], -len(g), _extent(g)["minX"], _extent(g)["minY"])
    ):
        if len(group) < min_creatures:
            continue
        floor = group[0]["z"]
        by_floor[floor] += 1
        component = component_of.get(group[0]["anchor"], -1)
        extent = _extent(group)

        by_species: List[Dict] = []
        for name in (entry["name"] for entry in _species(group)):
            same_name = [p for p in group if p["name"] == name]
            for piece in _cluster(
                [(0, p) for p in same_name], radius, key_of=lambda p: component
            ):
                by_species.append(
                    {"name": name, "count": len(piece), "extent": _extent(piece)}
                )

        columns = Counter(
            subarea_of_column(p["x"], p["y"]) if subarea_of_column else None for p in group
        )
        subarea_id, _ = columns.most_common(1)[0]

        candidates.append(
            {
                "id": f"{city}-C{floor:02d}-{by_floor[floor]:03d}",
                "city": city,
                "floor": floor,
                "component": component,
                "componentTiles": component_size.get(component, 0),
                "creatures": len(group),
                "species": _species(group),
                "extent": extent,
                "subareaId": subarea_id,
                "splitBySpecies": sorted(
                    by_species, key=lambda piece: (-piece["count"], piece["name"])
                ),
                "spawns": sorted(
                    (
                        {"name": p["name"], "x": p["x"], "y": p["y"], "z": p["z"]}
                        for p in group
                    ),
                    key=lambda p: (p["y"], p["x"], p["name"]),
                ),
            }
        )

    return candidates, orphans


def attach_walk_distance(
    candidates: List[Dict], distances: Dict[Node, int], anchor_of
) -> None:
    """Grava em cada candidata quantos tiles se anda do templo até ela."""
    for candidate in candidates:
        reachable = [
            distances[node]
            for node in (anchor_of(spawn) for spawn in candidate["spawns"])
            if node in distances
        ]
        candidate["walkTilesFromTemple"] = min(reachable) if reachable else None
