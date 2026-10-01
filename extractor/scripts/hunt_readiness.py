""""Hunt pronta": a regra do pipeline produziu material pra montar a hunt da
wiki — lógica pura. Mede o critério da spec
(`.scratch/hunts-por-subarea/spec.md`, decisão 18-20): "mesmo conjunto
dominante + andares sobrepostos", nunca distância de centróide (reprova
acerto pelo lugar onde caiu o centro, não pelo que tem dentro).

`is_ready` responde três coisas, nunca confundidas: `None` é "não dá pra
medir" (a hunt da wiki não tem `creatures`, 301 das 699 não têm); `False` é
"medido e não bate"; `True` é "medido e bate". Juntar `None` com `False` já
escondeu hunt sem gabarito dentro da contagem de reprovação uma vez.
"""

from typing import Dict, Iterable, List, Optional, Sequence

# Quantas espécies do gabarito da wiki precisam aparecer no material
# produzido para contar como pronta. Metade, com piso de 1 — uma hunt de
# espécie só (a maioria) exige bater nela; uma de três só pede duas.
MIN_OVERLAP_FRACTION = 0.5

# Folga em tiles ao redor da extensão da candidata, pra casar com a
# coordenada da wiki sem exigir o pixel exato — mesma ideia de
# `curated_hunts.DEFAULT_MARGIN_TILES`, independente dele de propósito (um
# muda, o outro não precisa seguir).
COORD_MARGIN_TILES = 20


def _extent_contains(extent: Dict, x: int, y: int, margin: int = COORD_MARGIN_TILES) -> bool:
    return (
        extent["minX"] - margin <= x <= extent["maxX"] + margin
        and extent["minY"] - margin <= y <= extent["maxY"] + margin
    )


def _nearby_candidates(hunt: Dict, candidates: Sequence[Dict]) -> List[Dict]:
    floors = set(hunt.get("floors") or [coord["z"] for coord in hunt["coords"]])
    return [
        candidate
        for candidate in candidates
        if candidate["floor"] in floors
        and any(_extent_contains(candidate["extent"], coord["x"], coord["y"]) for coord in hunt["coords"])
    ]


def _overlap_meets_threshold(wiki_species: set, produced: set) -> bool:
    overlap = wiki_species & produced
    threshold = max(1, round(len(wiki_species) * MIN_OVERLAP_FRACTION))
    return len(overlap) >= threshold


def is_ready(hunt: Dict, candidates: Sequence[Dict]) -> Optional[bool]:
    """A hunt da wiki tem, entre as candidatas do mesmo andar e perto da
    coluna (extensão + folga), espécie o bastante pra ela nascer? `None`
    quando a wiki não dá gabarito de espécie pra essa pergunta ter resposta.

    Reserva: usa só quando não há máscara de subárea pra decidir por
    `is_ready_by_subarea` (subsolo sem gêmeo de superfície, ou cidade sem
    `candidates.json` rodado com `subarea_of_column`). A folga de tiles é uma
    aproximação geométrica — `is_ready_by_subarea` é o critério fiel à
    decisão 18, "mesmo conjunto dominante + andares sobrepostos", sem
    inventar distância nenhuma.
    """
    wiki_species = {name.lower() for name in hunt.get("creatures") or []}
    if not wiki_species:
        return None

    nearby = _nearby_candidates(hunt, candidates)
    if not nearby:
        return False

    produced = {
        entry["name"].lower() for candidate in nearby for entry in candidate["species"]
    }
    return _overlap_meets_threshold(wiki_species, produced)


def subarea_of(hunt: Dict, owner: Dict) -> Optional[int]:
    """A subárea da hunt da wiki, pela mesma coluna 2D que rotula nossas
    candidatas (`build_hunt_candidates.subarea_lookup`) — nunca por nome."""
    for coord in hunt["coords"]:
        subarea = owner.get((coord["x"], coord["y"]))
        if subarea is not None:
            return subarea
    return None


def is_ready_by_subarea(hunt: Dict, candidates: Sequence[Dict], owner: Dict) -> Optional[bool]:
    """A mesma pergunta de `is_ready`, mas pela fronteira oficial da
    subárea em vez de extensão + folga — fiel à decisão 18 ("mesmo conjunto
    dominante + andares sobrepostos"), e ao mesmo recorte que a decisão 1
    impõe às nossas próprias candidatas ("hunt nunca cruza fronteira de
    subárea"). `None` sem gabarito de espécie; `False` sem coluna que caia em
    alguma subárea mascarada (ela ainda cai em `is_ready`, a reserva por
    extensão)."""
    wiki_species = {name.lower() for name in hunt.get("creatures") or []}
    if not wiki_species:
        return None

    subarea = subarea_of(hunt, owner)
    if subarea is None:
        return False

    floors = set(hunt.get("floors") or [coord["z"] for coord in hunt["coords"]])
    nearby = [
        candidate
        for candidate in candidates
        if candidate["floor"] in floors and candidate.get("subareaId") == subarea
    ]
    if not nearby:
        return False

    produced = {entry["name"].lower() for candidate in nearby for entry in candidate["species"]}
    return _overlap_meets_threshold(wiki_species, produced)


def is_ready_preferring_subarea(
    hunt: Dict, candidates: Sequence[Dict], owner: Dict
) -> Optional[bool]:
    """`is_ready_by_subarea` quando a coluna cai em alguma subárea mascarada
    **e** existe candidata lá; `is_ready` (extensão + folga) como reserva —
    cobre subsolo sem gêmeo de superfície e as 14 órfãs que o ticket 03 da
    `janela-mapa-cyclopedia` mediu."""
    wiki_species = {name.lower() for name in hunt.get("creatures") or []}
    if not wiki_species:
        return None

    subarea = subarea_of(hunt, owner)
    if subarea is not None:
        floors = set(hunt.get("floors") or [coord["z"] for coord in hunt["coords"]])
        nearby = [
            candidate
            for candidate in candidates
            if candidate["floor"] in floors and candidate.get("subareaId") == subarea
        ]
        if nearby:
            produced = {
                entry["name"].lower() for candidate in nearby for entry in candidate["species"]
            }
            return _overlap_meets_threshold(wiki_species, produced)

    return is_ready(hunt, candidates)


def city_of(hunt: Dict, bounds_by_city: Dict[str, Optional[Dict]]) -> Optional[str]:
    """Em qual das nossas cidades a hunt cai, pela coluna de mundo — nunca
    pelo nome: a wiki escreve "Gray Beach", o código é `GRAYBEACH`, e
    "Ab'Dendriel" tem até duas grafias diferentes no mesmo catálogo."""
    for coord in hunt["coords"]:
        for city, bounds in bounds_by_city.items():
            if bounds is None:
                continue
            if (
                bounds["minX"] <= coord["x"] <= bounds["maxX"]
                and bounds["minY"] <= coord["y"] <= bounds["maxY"]
            ):
                return city
    return None


def summarize(results: Iterable[Optional[bool]]) -> Dict[str, int]:
    """`{ready, notReady, unmeasured}` — a mesma tripla de `is_ready`, somada."""
    summary = {"ready": 0, "notReady": 0, "unmeasured": 0}
    for result in results:
        if result is None:
            summary["unmeasured"] += 1
        elif result:
            summary["ready"] += 1
        else:
            summary["notReady"] += 1
    return summary
