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

# Bicho de cenário não faz hunt. Snake, Skunk, Rat, Bug e Cat aparecem aos
# montes em volta de qualquer cidade e formavam candidatas inteiras, que a
# curadoria tinha de recusar uma a uma. O corte é pelo XP do Canary, calibrado
# na casa decimal: Minotaur vale exatamente 50, e o corte é `>= 50` para não
# derrubá-lo (`.scratch/hunts-por-subarea/spec.md`, decisões 6-7).
MIN_MONSTER_EXPERIENCE = 50

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


def is_notable(name: str, christens_name: Optional[Set[str]] = None) -> bool:
    """A espécie dá nome a alguma hunt da wiki — sinal gerado
    (`wiki_hunt_names.christened_species`), nunca lista à mão."""
    return bool(christens_name) and name.lower() in christens_name


def _experience_of(experience_by_name: Optional[Dict[str, int]], name: str) -> Optional[int]:
    """O XP do monstro, sem caixa. `None` é "não sei" — nunca zero, para que
    bicho desconhecido não seja confundido com bicho sem valor."""
    if not experience_by_name:
        return None
    return experience_by_name.get(name.lower())


def is_admitted_on_its_own(
    name: str,
    experience_by_name: Optional[Dict[str, int]],
    min_experience: int,
    christens_name: Optional[Set[str]],
) -> bool:
    """A espécie se sustenta sem precisar de família por perto: bate o teto
    de XP, batiza hunt da wiki, ou o XP é desconhecido (bicho novo nunca é
    descartado por falta de dado — decisões 6-9 da spec)."""
    if is_notable(name, christens_name):
        return True
    experience = _experience_of(experience_by_name, name)
    if experience is None:
        return True
    return experience >= min_experience


def _within_radius(point: Dict, group: Sequence[Dict], radius: int) -> bool:
    return any(
        max(abs(point["x"] - other["x"]), abs(point["y"] - other["y"])) <= radius
        for other in group
    )


def _species(
    points: Sequence[Dict],
    experience_by_name=None,
    christens_name: Optional[Set[str]] = None,
) -> List[Dict]:
    counts = Counter(p["name"] for p in points)
    return [
        {"name": name, "count": count}
        for name, count in sorted(
            counts.items(),
            key=lambda item: (
                not is_notable(item[0], christens_name),
                -item[1],
                -(_experience_of(experience_by_name, item[0]) or 0),
                item[0],
            ),
        )
    ]


def build_candidates(
    city: str,
    points: Sequence[Dict],
    walkable: Set[Node],
    component_of: Dict[Node, int],
    subarea_of_column=None,
    radius: int = DEFAULT_CLUSTER_RADIUS,
    min_creatures: int = DEFAULT_MIN_CREATURES,
    experience_by_name: Optional[Dict[str, int]] = None,
    min_experience: int = MIN_MONSTER_EXPERIENCE,
    christens_name: Optional[Set[str]] = None,
    family_by_name: Optional[Dict[str, str]] = None,
) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    """-> `(candidatas, spawns sem tile caminhável por perto, descartados)`.

    O segundo valor não é ruído a esconder: spawn que não encosta em tile
    andável costuma ser bicho atrás de parede (ou erro de mapa), e some da
    contagem da candidata sem esse relatório. O terceiro é o monstro fraco
    descartado — nunca em silêncio (ordem de execução, item 5): `[{"name",
    "count"}]`, por cidade, não por candidata.

    `experience_by_name` é o XP do Canary por nome (sem caixa). A candidata
    nasce só de quem **se sustenta por si** (`is_admitted_on_its_own`): bate o
    teto `min_experience`, batiza hunt da wiki (`christens_name`), ou tem XP
    desconhecido (bicho novo nunca é descartado por falta de dado). Isso
    acontece **antes** do agrupamento — senão um bolsão de Snake continuaria
    puxando o recorte e a extensão da candidata.

    Quem não se sustenta por si ainda pode entrar: se partilha
    `family_by_name` (a classe do Bestiary) com alguém já admitido **no mesmo
    bolsão e andar**, ele entra como companheiro (decisões 10-11) — Skeleton
    (35, não batiza nada) acompanha Ghoul (85, Undead) onde os dois convivem,
    e fica de fora onde só há Rat. Família nunca atravessa andar: o bolsão é
    por `component_of`, que já é por andar.
    """
    anchored: List[Tuple[int, Dict]] = []
    orphans: List[Dict] = []
    for point in points:
        anchor = anchor_tile(point, walkable)
        if anchor is None:
            orphans.append(point)
            continue
        anchored.append((component_of.get(anchor, -1), {**point, "anchor": anchor}))

    strong = [
        (component, point)
        for component, point in anchored
        if is_admitted_on_its_own(point["name"], experience_by_name, min_experience, christens_name)
    ]
    weak = [
        (component, point)
        for component, point in anchored
        if not is_admitted_on_its_own(point["name"], experience_by_name, min_experience, christens_name)
    ]

    component_size = Counter(component_of.values())
    raw_groups = _cluster(strong, radius, key_of=lambda p: component_of.get(p["anchor"], -1))

    group_component = [component_of.get(g[0]["anchor"], -1) for g in raw_groups]
    group_floor = [g[0]["z"] for g in raw_groups]
    group_admitted_families = [
        {
            family_by_name.get(p["name"].lower())
            for p in g
            if family_by_name and family_by_name.get(p["name"].lower())
        }
        for g in raw_groups
    ]

    discarded_counter: "Counter[str]" = Counter()
    extra_by_group: Dict[int, List[Dict]] = defaultdict(list)
    for w_component, w_point in weak:
        family = family_by_name.get(w_point["name"].lower()) if family_by_name else None
        matches = [
            index
            for index, _ in enumerate(raw_groups)
            if family is not None
            and family in group_admitted_families[index]
            and group_component[index] == w_component
            and group_floor[index] == w_point["z"]
            and _within_radius(w_point, raw_groups[index], radius)
        ]
        if not matches:
            discarded_counter[w_point["name"]] += 1
            continue
        best = min(
            matches,
            key=lambda index: min(
                max(abs(w_point["x"] - g["x"]), abs(w_point["y"] - g["y"]))
                for g in raw_groups[index]
            ),
        )
        extra_by_group[best].append(w_point)

    candidates: List[Dict] = []
    by_floor: Dict[int, int] = defaultdict(int)

    def _rank(group: Sequence[Dict]):
        notable = sum(1 for p in group if is_notable(p["name"], christens_name))
        experience = sum(_experience_of(experience_by_name, p["name"]) or 0 for p in group)
        extent = _extent(group)
        return (group[0]["z"], -notable, -len(group), -experience, extent["minX"], extent["minY"])

    members_by_group = [
        raw_groups[index] + extra_by_group.get(index, []) for index in range(len(raw_groups))
    ]

    for group in sorted(members_by_group, key=_rank):
        if len(group) < min_creatures:
            for p in group:
                discarded_counter[p["name"]] += 1
            continue
        floor = group[0]["z"]
        by_floor[floor] += 1
        component = component_of.get(group[0]["anchor"], -1)
        extent = _extent(group)

        by_species: List[Dict] = []
        for name in (entry["name"] for entry in _species(group, experience_by_name, christens_name)):
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
                "species": _species(group, experience_by_name, christens_name),
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

    discarded = [
        {"name": name, "count": count}
        for name, count in sorted(discarded_counter.items(), key=lambda item: (-item[1], item[0]))
    ]

    return candidates, orphans, discarded


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
