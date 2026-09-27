"""Da curadoria da tela `new-hunts` para as pastas de mapa de hunt — lógica pura.

Entrada: o JSON que a tela baixa (`{city, area, subareas, hunts: [...]}`), onde
cada hunt é um nome, os andares escolhidos e os ids das candidatas que ela
juntou. Saída: um id por hunt, a pasta `<ID>_slug`, o recorte de tiles e a
entrada (o tile por onde se chega a pé).

O id **é** atribuído aqui, e é a única vez em que isso acontece no pipeline:
até Rookgaard ele era escolhido à mão e digitado numa placa do editor. A ordem
da lista é a ordem do arquivo, então rodar de novo sobre a mesma curadoria dá
os mesmos ids.
"""

import re
import unicodedata

import city_ids
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

Node = Tuple[int, int, int]

DEFAULT_MARGIN_TILES = 12
HUNT_ID_FORMAT = "{city}-HUNT-{index:04d}"


def slugify(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_only).strip("-").lower()
    return re.sub(r"-{2,}", "-", slug)


def hunt_id(city: str, index: int) -> str:
    return HUNT_ID_FORMAT.format(city=city, index=index)


def folder_name(hunt_id_value: str, slug: str) -> str:
    return f"{hunt_id_value}_{slug}"


def crop_bounds(extent: Dict, margin: int = DEFAULT_MARGIN_TILES) -> Tuple[int, int, int, int]:
    return (
        extent["minX"] - margin,
        extent["minY"] - margin,
        extent["maxX"] + margin,
        extent["maxY"] + margin,
    )


def duplicated_candidates(hunts: Sequence[Dict]) -> Dict[str, List[str]]:
    """Candidata usada por mais de uma hunt -> os nomes que a reivindicam.

    Não é erro: duas hunts podem legitimamente compartilhar um andar. É aviso
    porque o mesmo spawn vira dois mapas, e o jogador mata o mesmo bicho em
    dois lugares sem que nada no jogo diga isso.
    """
    claims: Dict[str, List[str]] = {}
    for hunt in hunts:
        for candidate_id in hunt["candidateIds"]:
            claims.setdefault(candidate_id, []).append(hunt["name"])
    return {cid: names for cid, names in claims.items() if len(names) > 1}


def assign(city: str, hunts: Sequence[Dict]) -> List[Dict]:
    """A curadoria com id, slug e pasta — sem tocar em mapa nem em tile."""
    assigned = []
    used_slugs: Set[str] = set()
    for index, hunt in enumerate(hunts, start=1):
        slug = slugify(hunt["name"]) or f"hunt-{index:04d}"
        while slug in used_slugs:
            slug = f"{slug}-{index:04d}"
        used_slugs.add(slug)
        identifier = hunt_id(city, index)
        assigned.append(
            {
                **hunt,
                "id": identifier,
                "slug": slug,
                "folder": folder_name(identifier, slug),
            }
        )
    return assigned


def members_of(hunt: Dict, candidates_by_id: Dict[str, Dict]) -> List[Dict]:
    return [
        candidates_by_id[candidate_id]
        for candidate_id in hunt["candidateIds"]
        if candidate_id in candidates_by_id
    ]


def spawns_of(members: Iterable[Dict]) -> List[Dict]:
    return [spawn for member in members for spawn in member["spawns"]]


def entrance_of(
    members: Sequence[Dict],
    distances: Dict[Node, int],
    anchor_of,
) -> Tuple[Optional[Node], Optional[int]]:
    """O tile da hunt mais barato de alcançar a pé, e o custo dele.

    Sem caminho nenhum a entrada é `None`: a hunt existe no mapa e não existe
    como destino, e é o relatório de rejeição do travel-graph que conta isso —
    inventar uma entrada aqui esconderia uma hunt que o jogador não alcança.
    """
    best: Optional[Node] = None
    best_cost: Optional[int] = None
    for spawn in spawns_of(members):
        anchor = anchor_of(spawn)
        if anchor is None or anchor not in distances:
            continue
        cost = distances[anchor]
        if best_cost is None or cost < best_cost:
            best, best_cost = anchor, cost
    return best, best_cost


def build_location(hunt: Dict, entrance: Node) -> Dict:
    """A hunt curada como uma `locations` de tipo HUNT, no formato do catálogo.

    É o que a placa no OTBM produzia em Rookgaard, com duas diferenças: o
    `displayName` já vem curado (você o digitou na tela) e o `huntId` não tem o
    que confirmar — id da location e mapId da hunt são a mesma string, porque
    os dois nascem aqui. Por isso esta entrada não carrega `_todo`.
    """
    x, y, z = entrance
    city = city_ids.derive_city(hunt["id"])
    status = city_ids.derive_status(city)
    entry = {
        "id": hunt["id"],
        "type": "HUNT",
        "x": x,
        "y": y,
        "z": z,
        "displayName": hunt["name"].strip(),
        "city": city,
        "huntId": hunt["id"],
    }
    if status is not None:
        entry["status"] = status
    return entry
