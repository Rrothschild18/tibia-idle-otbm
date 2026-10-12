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


def is_training(hunt: Dict) -> bool:
    return hunt.get("type") == "TRAINING"


def hunt_from_signs(signs: Sequence[Dict], max_floor: int) -> Dict:
    """Uma ou mais placas com o **mesmo** id (`CIDADE-HUNT-NNNN` ou
    `CIDADE-TRAINING-NNNN`) como uma entrada de curadoria sintética — sem
    candidata, sem nome digitado à mão. A placa já decidiu o id; aqui só nasce o
    resto no formato que `assign`/`build_curated_hunts` esperam de uma hunt da
    tela.

    **Os andares são os andares onde você pôs placa.** Com uma placa só, valem
    o andar dela mais o de cima e o de baixo — é o que o treino sempre fez, e
    serve para quem marca um ponto e deixa o script decidir. Com mais de uma,
    valem exatamente os andares marcados: aí a intenção é explícita e inventar
    vizinhos atrapalharia. `crop_floors_for` ainda estende pra baixo pela regra
    de visibilidade do cliente, como em qualquer hunt.

    `extent` é a caixa que contém as placas — um ponto, quando é uma só. A folga
    padrão (`crop_bounds`) é quem vira isso num box, igual a toda hunt.

    A entrada é a placa de menor andar: é por onde o jogador chega.
    """
    if not signs:
        raise ValueError("hunt_from_signs: nenhuma placa")

    ids = {sign["id"] for sign in signs}
    if len(ids) > 1:
        raise ValueError(f"hunt_from_signs: placas de ids diferentes ({sorted(ids)})")

    hunt_id = signs[0]["id"]
    hunt_type = signs[0]["type"]
    xs = [sign["x"] for sign in signs]
    ys = [sign["y"] for sign in signs]
    zs = sorted(sign["z"] for sign in signs)

    if len(signs) == 1:
        z = zs[0]
        floors = sorted({f for f in (z - 1, z, z + 1) if 0 <= f <= max_floor})
    else:
        floors = sorted({z for z in zs if 0 <= z <= max_floor})

    entrance = min(signs, key=lambda sign: (sign["z"], sign["x"], sign["y"]))
    name = " ".join(word.capitalize() for word in hunt_id.split("-"))

    return {
        "id": hunt_id,
        "type": hunt_type,
        "name": name,
        "floors": floors,
        "candidateIds": [],
        "species": None,
        "creatures": 0,
        "extent": {
            "minX": min(xs),
            "minY": min(ys),
            "maxX": max(xs),
            "maxY": max(ys),
            "centerX": entrance["x"],
            "centerY": entrance["y"],
        },
        "subareaId": None,
        "walkTilesFromTemple": None,
        "entranceZ": entrance["z"],
    }


def training_hunt_from_sign(sign: Dict, max_floor: int) -> Dict:
    """Atalho histórico de uma placa só. Ver `hunt_from_signs`."""
    return hunt_from_signs([sign], max_floor)


# A placa pode cair numa tile não-caminhável (presa numa parede, como toda
# placa do Tibia tende a ficar) — por isso a entrada busca o próprio ponto e
# os quatro vizinhos cardeais. Sem diagonal de propósito: é a mesma regra que
# o pathfinding do jogo usa (ver ADR/memória "pathfinding evita diagonal"),
# não uma lista inventada aqui.
TRAINING_ENTRANCE_OFFSETS: Tuple[Tuple[int, int], ...] = ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1))


def training_entrance_of(hunt: Dict, walkable: Set[Node]) -> Optional[Node]:
    """O tile de entrada de um spot de treino: o próprio ponto da placa (centro
    do extent, que `training_hunt_from_sign` grava como a posição exata da
    placa), ou o vizinho cardeal mais próximo que seja caminhável.

    Sem candidata e sem rota do templo — o jogador chega a pé pela cidade, daí
    não comparar com `entrance_of` (que busca o tile mais barato a partir do
    templo entre os spawns escolhidos): aqui não há spawn escolhido nenhum.
    """
    cx = hunt["extent"]["centerX"]
    cy = hunt["extent"]["centerY"]
    cz = hunt["entranceZ"]
    return next(
        (
            (cx + dx, cy + dy, cz)
            for dx, dy in TRAINING_ENTRANCE_OFFSETS
            if (cx + dx, cy + dy, cz) in walkable
        ),
        None,
    )


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
    """A curadoria com id, slug e pasta — sem tocar em mapa nem em tile.

    **Todo hunt chega com `id`**: o de placa traz o que está escrito nela, o da
    curadoria da tela traz o que está no `curation.json`. Até 2026-10-12 a
    curadoria não trazia, e um contador posicional atribuía — então tirar ou
    reordenar uma entrada renumerava todas as seguintes. O mesmo mapa virava
    outro id, o mesmo id virava outro mapa, e o `name`/`label` escrito à mão
    passava a descrever a hunt errada. Foi o que fez um re-export mexer em 56
    bundles de uma vez.

    Entrada sem `id` é recusada em vez de ganhar um número de fila: inventar
    numeração é exatamente o que não pode voltar. Ver o ticket 11 de
    `.scratch/pipeline-de-hunts/` no repo do jogo.
    """
    assigned = []
    used_slugs: Set[str] = set()
    for hunt in hunts:
        if "id" not in hunt:
            raise ValueError(
                f"curadoria de {city} tem entrada sem `id`: {hunt.get('name', hunt)!r}. "
                "Escolha o próximo id livre da cidade e escreva no `curation.json` — "
                "id atribuído por posição renumera as hunts seguintes."
            )

        identifier = hunt["id"]
        fallback_slug = identifier.lower()
        slug = slugify(hunt["name"]) or fallback_slug
        while slug in used_slugs:
            slug = f"{slug}-{identifier.split('-')[-1]}"
        used_slugs.add(slug)
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
    """A hunt curada como uma `locations` de tipo HUNT ou TRAINING, no formato do catálogo.

    É o que a placa no OTBM produzia em Rookgaard, com duas diferenças: o
    `displayName` já vem curado (você o digitou na tela) e o `huntId` não tem o
    que confirmar — id da location e mapId da hunt são a mesma string, porque
    os dois nascem aqui. Por isso esta entrada não carrega `_todo`.
    """
    x, y, z = entrance
    city = city_ids.derive_city(hunt["id"])
    status = city_ids.derive_status(city)
    loc_type = "TRAINING" if is_training(hunt) else "HUNT"
    entry = {
        "id": hunt["id"],
        "type": loc_type,
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
