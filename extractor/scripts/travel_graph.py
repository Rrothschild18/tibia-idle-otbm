"""
Pure logic for the travel-graph & locations pipeline — turning a full-city
OTBM dump (+ its map.json objectDefs) and the map editor's NPC export into
the tibia-idle `locations`/`travelGraph` catalog fragment. See
build_travel_fragment.py for the CLI that reads/writes files and
.scratch/travel-graph-and-locations/spec.md for the full design.

Five independent concerns, kept as separate function groups so each is
testable with tiny in-memory fixtures (no real .otbm/map.json/.lua touched):

1. Marker-sign parsing — POIs (HUNT/TEMPLE/DEPOT/QUEST) marked in the OTBM
   with sign item 2016 at a reserved uid (10001+), text = "CIDADE-TIPO-INCREMENTAL".
2. Walkability graph + tile distances — the tileCount between two locations,
   walked over real tiles rather than measured across the coordinates.
3. NPC locations + Canary shop extraction — no sign needed, position/name
   come from <CIDADE>-npc.xml; shop table comes from a same-named .lua.
4. Rejecting nodes with no way in — a destination nobody can travel to never
   reaches the fragment; it leaves in a report with whatever identifies it.
5. Catalog merge — `travelGraph` is *replaced* per city (the fragment is the
   complete edge set), while `locations` upsert by id in hunt_fragment.py's
   mechanical-vs-curated split, per-field rather than per-entry: position and
   shop always take the fresh value, `displayName` is append-only once
   curated, and an entry the fragment dropped is reported, never deleted.
"""

import heapq
import itertools
import re
import xml.etree.ElementTree as ET
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

import city_ids

# ======================================================
# Marker signs -> POI locations (HUNT/TEMPLE/DEPOT/QUEST)
# ======================================================

SIGN_ITEM_ID = 2016
MARKER_UID_MIN = 10001
POI_TYPES = ("HUNT", "TEMPLE", "DEPOT", "QUEST")

# Itens que são entrada de ferramenta pelo próprio id, sem depender de uid.
#
# A placa de POI se identifica pelo uid reservado, porque são poucas e cada uma
# precisa de um uid único mesmo (é o que o editor garante). O caminho de uma
# rota é outra escala: são centenas de tiles pintados de uma vez, e exigir uid
# em cada um seria exigir centenas de cliques para marcar o que o id do item já
# diz. Então este conjunto responde "este item é marcador?" sem olhar uid.
#
# 27869 ("red energy ball", quest item no items.xml do Canary) é o caminho que
# o gerador de rota segue.
MARKER_ITEM_IDS = frozenset({27869})


def is_marker_item(raw_item: Dict) -> bool:
    """O item é entrada de ferramenta, e não conteúdo que a cidade mostra?

    Existe para que a regra viva num lugar só: ela é consumida pelo grafo
    (`extract_tile_flags`), pelo bundle (`map_v6`) e pelo minimapa (`minimap`),
    e antes disto estava escrita à mão nos três — três cópias que só por sorte
    concordavam."""
    if raw_item.get("id") in MARKER_ITEM_IDS:
        return True
    uid = raw_item.get("uid")
    return uid is not None and uid >= MARKER_UID_MIN

_SIGN_ID_RE = re.compile(
    r"^(?P<city>[A-Z]+)-(?P<type>" + "|".join(POI_TYPES) + r")-(?P<seq>\d{4})$"
)


def _iter_dump_tiles(dump: Dict):
    """Yields (x, y, z, tile) for every tile in a raw otbm2json dump — same
    node/feature/tile walk build_phaser_map.py uses."""
    for node in dump.get("data", {}).get("nodes", []):
        for feature in node.get("features", []):
            base_x = feature.get("x", 0)
            base_y = feature.get("y", 0)
            z = feature.get("z", 7)
            for tile in feature.get("tiles", []):
                tx, ty = tile.get("x"), tile.get("y")
                if tx is None or ty is None:
                    continue
                yield base_x + tx, base_y + ty, z, tile


def iter_marker_sign_items(dump: Dict):
    """Yields (x, y, z, uid, text) for every sign item in the reserved uid
    range — the raw marker items, before any judgement about whether their
    text is a valid id.

    Public because more than one consumer needs the *items* and not the
    locations parse_marker_signs distils them into: the sign snapshot taken
    before a city is re-cut needs each marker's `uid`, which a location has no
    room for. Without this, a second consumer either reaches for a private
    helper or copies the filter, and the copy is the part that rots."""
    for x, y, z, tile in _iter_dump_tiles(dump):
        for raw_item in tile.get("items", []):
            if raw_item.get("id") != SIGN_ITEM_ID:
                continue
            uid = raw_item.get("uid")
            if uid is None or uid < MARKER_UID_MIN:
                continue
            yield x, y, z, uid, raw_item.get("text", "")


def parse_marker_signs(dump: Dict) -> Tuple[List[Dict], List[Dict]]:
    """Every sign item (id 2016) with a uid in the reserved range -> a
    (locations, issues) pair. A sign whose uid falls outside the reserved
    range isn't a marker at all and is silently skipped (it's an ordinary
    in-game sign, not travel-graph input). A reserved-uid sign whose text
    doesn't match CIDADE-TIPO-NNNN (exactly 4 digits — a stray digit count,
    like the 5-digit `ROOK-HUNT-00015` typo found live, is rejected instead
    of silently minting an id nothing can ever resolve to) is reported as an
    issue, not silently dropped. Two signs that resolve to the same id (typically a
    copy-pasted sign that kept the old uid — a map-editing mistake) are also
    reported: only the first occurrence becomes a location, so a duplicate
    id can never reach the fragment/catalog and silently collide there."""
    locations: List[Dict] = []
    issues: List[Dict] = []
    seen_ids: Set[str] = set()

    for x, y, z, uid, text in iter_marker_sign_items(dump):
        match = _SIGN_ID_RE.match(text)
        if not match:
            issues.append({"reason": "invalid-sign-format", "uid": uid, "text": text, "x": x, "y": y, "z": z})
            continue

        if text in seen_ids:
            issues.append({"reason": "duplicate-sign-id", "uid": uid, "text": text, "x": x, "y": y, "z": z})
            continue
        seen_ids.add(text)

        locations.append({
            "id": text,
            "type": match.group("type"),
            "x": x,
            "y": y,
            "z": z,
        })

    return locations, issues


# =========================================================
# Marcador de quest por slug
# =========================================================
#
# A placa de POI se chama `CIDADE-TIPO-NNNN` e é lida por `parse_marker_signs`.
# Uma área marcada no editor por quem está desenhando conteúdo tende a não
# seguir esse formato: o autor põe um item qualquer, um uid numa faixa que ele
# reservou, e no texto o **slug** do que aquilo é (`copper_shield_quest`).
#
# Isto lê essa convenção. Ela conviva com a placa em vez de substituí-la: são
# dois jeitos de marcar a mesma coisa, e o mapa de Rookgaard tem os dois.
#
# A faixa é limitada nas duas pontas de propósito — o mapa-mundo do otservbr usa
# uid alto para as coisas dele (50080 e 64128 aparecem dentro de Rookgaard), e
# uma faixa aberta em ">= 20001" leria esses objetos como marcador do autor.
QUEST_MARKER_UID_MIN = 20001
QUEST_MARKER_UID_MAX = 20999


def parse_quest_slug_markers(dump: Dict) -> List[Dict]:
    """Todo item com uid na faixa de quest e texto -> `{slug, uid, x, y, z}`.

    Sem texto não há slug, e sem slug não há o que casar com pasta de mapa: é
    marcador inacabado, e não entra."""
    markers: List[Dict] = []

    for x, y, z, tile in _iter_dump_tiles(dump):
        for raw_item in tile.get("items") or []:
            uid = raw_item.get("uid")
            if uid is None or not (QUEST_MARKER_UID_MIN <= uid <= QUEST_MARKER_UID_MAX):
                continue
            slug = (raw_item.get("text") or "").strip()
            if not slug:
                continue
            markers.append({"slug": slug, "uid": uid, "x": x, "y": y, "z": z})

    return markers


def _normalize_slug(slug: str) -> str:
    return slug.strip().lower().replace("_", "-")


def hunt_id_for_slug(slug: str, hunt_folders: Sequence[Dict]) -> Optional[str]:
    """O id da hunt cuja pasta tem esse slug, ou `None`.

    `hunt_folders` é `[{"id", "name"}]`, o que `build_travel_fragment` já lê das
    pastas de `maps/<CIDADE>/` — a pasta se chama `<ID>_<slug>`, então o id já
    está lá e não precisa de tabela curada nenhuma para ligar um ao outro.
    Underscore e hífen são a mesma coisa nessa comparação: o editor aceita os
    dois e ninguém deveria perder uma quest por isso."""
    wanted = _normalize_slug(slug)
    for folder in hunt_folders:
        if _normalize_slug(folder.get("name", "")) == wanted:
            return folder.get("id")
    return None


def build_quest_slug_location(marker: Dict, hunt_id: str) -> Dict:
    """O POI de entrada de uma hunt marcada por slug.

    Tipo `HUNT`, não um tipo novo: no grafo de viagem a entrada de uma quest faz
    exatamente o que a entrada de uma hunt faz, e o `displayName` sai curado do
    catálogo como em qualquer hunt."""
    return {
        "id": hunt_id,
        "type": "HUNT",
        "x": marker["x"],
        "y": marker["y"],
        "z": marker["z"],
        "huntId": hunt_id,
        "_todo": ["revisar displayName"],
        "displayName": _title_from_location_id(hunt_id),
    }


def _title_from_location_id(location_id: str) -> str:
    return " ".join(word.capitalize() for word in location_id.split("-"))


# Fields on a `locations` entry that need a human decision and are never
# overwritten by a later run once the entry is curated (see merge_locations_into_catalog).
# `huntId` only applies to type "HUNT" — it's the mapId a HUNT location's
# sign-based id can't derive on its own, since the two ids come from
# unrelated sources: a sign's CIDADE-TIPO-INCREMENTAL text vs. a hunt map's
# hand-assigned mapId in the `hunts` collection (see hunt_fragment.py).
CURATED_LOCATION_FIELDS = ("displayName", "huntId")


def build_sign_location(sign: Dict) -> Dict:
    """A parsed marker sign -> a draft `locations` entry. `displayName` is a
    placeholder derived from the id; a HUNT location also gets a `huntId`
    placeholder (None) to be pointed at the matching `hunts` entry's mapId —
    both flagged for human curation via `_todo`. merge_locations_into_catalog
    never overwrites either once curated on a later run. `city`/`status` are
    derived from the id on every run — never curated, never stale."""
    city = city_ids.derive_city(sign["id"])
    status = city_ids.derive_status(city)
    entry = {
        "id": sign["id"],
        "type": sign["type"],
        "x": sign["x"],
        "y": sign["y"],
        "z": sign["z"],
        "displayName": _title_from_location_id(sign["id"]),
        "city": city,
    }
    if status is not None:
        entry["status"] = status
    todo = ["confirmar displayName (gerado automaticamente do id)"]
    if sign["type"] == "HUNT":
        entry["huntId"] = None
        todo.append("associar huntId com o mapId da hunt correspondente (coleção hunts)")
    entry["_todo"] = todo
    return entry


# ======================================================
# Walkability graph + tile distances
# ======================================================

_NEIGHBOR_OFFSETS = [(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if (dx, dy) != (0, 0)]

# How far from an NPC the player may stand and still count as having arrived
# at it. Not a movement rule — it's how a shop counter is crossed: most
# shopkeepers stand on a tile walled off by an `unpass` counter, and without a
# reach every one of them is an unreachable destination. See approach_costs for
# how the distance stays honest.
#
# 10 porque o OTBM de Thais tem lojas com um vão de 4 tiles entre o NPC e o
# primeiro tile caminhável (Xodet, a loja de poção e runa; Hanna, a de joias).
# Com 3 elas sumiam do catálogo e ninguém comprava suprimento na cidade. O
# custo é conhecido: um alcance largo pode ligar por uma aresta artificial um
# NPC mal posto no mapa, em vez de deixá-lo no relatório de rejeição.
# `approach_costs` cobra a distância Chebyshev, então o tileCount continua
# contando o vão como tiles.
DEFAULT_NPC_REACH = 10

Node = Tuple[int, int, int]

# Where each `floorchange` value takes you, as (dx, dy, dz) from the tile
# carrying it. `down` drops straight through; the four compass values are
# ramps/stairs you *walk up* by moving that way, so they land one tile over
# **and** one floor up — which is exactly the case the same-(x, y) bridge
# below cannot express, and why every cave entered by a ramp used to come out
# islanded.
#
# `southalt`/`eastalt` are the double-width stairs — `FLOORCHANGE_SOUTH_ALT` /
# `FLOORCHANGE_EAST_ALT` in Canary, the `*_EX` family in TFS 0.3.7, spelled
# `southex`/`eastex` in TFS 0.2. You come out **two** tiles over, not one:
# `Tile::queryDestination`, Canary `src/items/tile.cpp:1018-1026`.
#
# The graph is undirected, so one entry per value covers both directions:
# walking up the ramp and walking back down it are the same edge.
FLOORCHANGE_DELTAS: Dict[str, Tuple[int, int, int]] = {
    "down": (0, 0, 1),
    "north": (0, -1, -1),
    "south": (0, 1, -1),
    "east": (1, 0, -1),
    "west": (-1, 0, -1),
    "southalt": (0, 2, -1),
    "eastalt": (2, 0, -1),
}

# Onde um `isFloorTransition` leva — o que o `floorchange` não cobre, porque
# estes se *usam* em vez de se pisar.
#
# A escada de mão sobe, e não na mesma coluna:
# `data/scripts/actions/items/ladder_up.lua:5-18` chama `moveUpstairs()`, e
# `data/libs/functions/position.lua:22-50` faz `z -= 1` e soma o offset de
# `DIRECTION_SOUTH` (`{x=0, y=1}`). O resto — buraco, alçapão, grade — desce
# na coluna.
LADDER_DELTA: Tuple[int, int, int] = (0, 1, -1)
HOLE_DELTA: Tuple[int, int, int] = (0, 0, 1)

_ITEM_ELEMENT_RE = re.compile(r"<item\s([^>]*?)(?:/>|>(.*?)</item>)", re.S)
_FLOORCHANGE_ATTR_RE = re.compile(r'key="floorchange"\s+value="([a-z]+)"')
_DEPOT_ATTR_RE = re.compile(r'key="type"\s+value="depot"')
_LADDER_ATTR_RE = re.compile(r'key="type"\s+value="ladder"')
_ITEM_ID_RE = re.compile(r'\bid="(\d+)"')
_ITEM_RANGE_RE = re.compile(r'fromid="(\d+)"[^>]*toid="(\d+)"')


def _iter_declared_items(items_xml: str):
    """`(ids declarados, corpo)` por `<item>`, com `fromid`/`toid` expandido.

    Canary declara a maioria das famílias de escada e rampa por faixa, então
    ler só a forma de `id` único pegaria uma fração delas.

    O `items.xml` mistura `<item .../>` e `<item ...>...</item>`, e as duas
    formas precisam ser reconhecidas **separadamente**: ler sempre até o
    próximo `</item>` dava a um item vazio o corpo do item seguinte. Isso
    deslocava a atribuição de uma casa em toda a sequência — 7541 ("earth",
    intransponível) ficava com o `floorchange` de 7542 ("ramp"), e 804 dos 997
    ids lidos eram do item errado."""
    for element in _ITEM_ELEMENT_RE.finditer(items_xml):
        attributes, body = element.group(1), element.group(2) or ""
        single = _ITEM_ID_RE.search(attributes)
        span = _ITEM_RANGE_RE.search(attributes)
        if single:
            yield [int(single.group(1))], body
        elif span:
            yield list(range(int(span.group(1)), int(span.group(2)) + 1)), body


def parse_floorchange_items(items_xml: str) -> Dict[int, str]:
    """Canary's `items.xml` -> {item id: floorchange direction}.

    This is the authority on "does walking here change my floor", and it
    replaces guessing from render flags. The previous rule inferred stairs
    from a four-flag combo (`usable`+`forceuse`+`unmove`+`automap`) calibrated
    on four known appearance ids; a ramp carries none of them, so every ramp
    in the map was invisible to the graph — the whole reason hunts sitting in
    ramp-entered caves were reported as unreachable.

    Deliberately *not* a curated id list kept in this repo: the same file the
    map editor reads is the one the server reads, so a new stairs id arrives
    with a Canary bump instead of with somebody remembering to add it here.

    **Does not** cover ladders, holes and rope spots: those have no
    `floorchange` because they are *used*, not walked onto (item 1948, the
    ladder, carries none). They keep coming from `isFloorTransition` — see
    `build_walkable_graph` and `parse_ladder_items`."""
    directions: Dict[int, str] = {}

    for item_ids, body in _iter_declared_items(items_xml):
        direction = _FLOORCHANGE_ATTR_RE.search(body)
        if not direction:
            continue
        for item_id in item_ids:
            directions[item_id] = direction.group(1)

    return directions


def parse_depot_items(items_xml: str) -> Set[int]:
    """`items.xml` -> os ids que são depot (o `locker`, hoje 3497-3500).

    É a mesma leitura que dá floorchange e escada, e é o que permite marcar o
    depot de uma cidade sem placa nenhuma. Rookgaard é a exceção que confirma a
    regra: o `ROOK-DEPOT-0001` está numa tile sem objeto de depot, porque
    Rookgaard não tem depot no Tibia — aquilo é decisão de design, não fato do
    mapa, e por isso continua vindo de placa.
    """
    ids: Set[int] = set()
    for item_ids, body in _iter_declared_items(items_xml):
        if _DEPOT_ATTR_RE.search(body):
            ids.update(item_ids)
    return ids


def find_depot_tiles(dump: Dict, depot_ids: Set[int]) -> List[Node]:
    """Toda tile da cidade que carrega um item de depot **fora de casa**.

    Todo locker de casa é um item de depot, e são eles a maioria: em Carlin, 8
    dos 46. O que separa os dois é a própria tile — o OTBM marca a de casa com
    `houseId`, e o depot da cidade nunca está numa.
    """
    found: Set[Node] = set()

    def scan(items, node: Node) -> None:
        for raw_item in items or []:
            if raw_item.get("id") in depot_ids:
                found.add(node)
            scan(raw_item.get("content"), node)

    for x, y, z, tile in _iter_dump_tiles(dump):
        if tile.get("houseId"):
            continue
        scan(tile.get("items"), (x, y, z))

    return sorted(found)


def town_positions(dump: Dict) -> List[Dict]:
    """Os `towns` do OTBM — id, nome e a posição do templo."""
    towns = []
    for node in dump.get("data", {}).get("nodes", []):
        for feature in node.get("features", []):
            for town in feature.get("towns", []) or []:
                towns.append(
                    {
                        "id": town.get("townid"),
                        "name": town.get("name", ""),
                        "x": town.get("x"),
                        "y": town.get("y"),
                        "z": town.get("z"),
                    }
                )
    return towns


def nearest_walkable(node: Node, walkable: Set[Node], reach: int = 3) -> Optional[Node]:
    """O próprio tile, ou o andável mais próximo dele no mesmo andar.

    Um depot é um móvel intransponível: o POI tem que cair ao lado dele, senão
    o grafo rejeita a location por não alcançar ninguém — que é o que acontece
    hoje com a placa ilhada.
    """
    if node in walkable:
        return node
    x, y, z = node
    for distance in range(1, reach + 1):
        for dx in range(-distance, distance + 1):
            for dy in range(-distance, distance + 1):
                if max(abs(dx), abs(dy)) != distance:
                    continue
                candidate = (x + dx, y + dy, z)
                if candidate in walkable:
                    return candidate
    return None


def cluster_tiles(tiles: Sequence[Node], radius: int = 10) -> List[List[Node]]:
    """Agrupa tiles por proximidade em x/y, **ignorando o andar**: um prédio de
    depot ocupa a mesma planta em vários andares e é um destino só."""
    groups: List[List[Node]] = []
    for tile in sorted(tiles):
        for group in groups:
            if any(
                max(abs(tile[0] - other[0]), abs(tile[1] - other[1])) <= radius
                for other in group
            ):
                group.append(tile)
                break
        else:
            groups.append([tile])
    return groups


def build_mechanical_city_pois(
    dump: Dict, city: str, walkable: Set[Node], depot_ids: Set[int]
) -> Tuple[List[Dict], List[str]]:
    """`(locations, avisos)` — o templo e o depot de uma cidade, sem placa.

    O templo vem do nó `towns` do OTBM; o depot, do item. São os dois POIs que
    toda cidade tem e que ninguém deveria precisar marcar à mão — sem eles uma
    cidade importada não tem de onde partir nem onde guardar.
    """
    locations: List[Dict] = []
    warnings: List[str] = []

    for index, town in enumerate(town_positions(dump), start=1):
        node = nearest_walkable((town["x"], town["y"], town["z"]), walkable)
        if node is None:
            warnings.append(
                f"templo {town['name']!r} em {town['x']},{town['y']},{town['z']} "
                "não encosta em tile andável"
            )
            continue
        locations.append(
            build_city_poi(
                f"{city}-TEMPLE-{index:04d}", "TEMPLE", node, town["name"] or f"{city} Temple"
            )
        )

    town_name = next((t["name"] for t in town_positions(dump) if t.get("name")), None)
    depot_label = f"{town_name or city.capitalize()} Depot"

    # **Um** depot por cidade, como o templo. Era um por aglomerado de lockers,
    # e isso dava 16 em Thais e 6 em Kazordoon: o recorte por máscara de
    # subárea arrasta locker de cidade vizinha (o maior aglomerado de
    # Kazordoon está em coordenada de Ab'Dendriel, a 642 tiles do templo
    # dela), e o raio do `cluster_tiles` ainda parte um mesmo prédio em dois
    # (Venore, 32910 e 32911). Os dois somados é a inconsistência de depot.
    #
    # O critério é a distância ao templo, não o tamanho: o depot da cidade é o
    # que fica *na* cidade. Tamanho engana — guildhall tem locker à vontade, e
    # o maior aglomerado costuma ser de outra cidade que entrou no recorte.
    # Locker de casa já estava fora por `houseId` (ver `find_depot_tiles`).
    temples = [(loc["x"], loc["y"], loc["z"]) for loc in locations if loc["type"] == "TEMPLE"]
    candidates: List[Tuple[int, Node]] = []
    for group in cluster_tiles(find_depot_tiles(dump, depot_ids)):
        node = next(
            (found for found in (nearest_walkable(tile, walkable) for tile in group) if found),
            None,
        )
        if node is None:
            continue
        if not temples:
            candidates.append((0, node))
            continue
        candidates.append((
            min(
                max(abs(node[0] - t[0]), abs(node[1] - t[1]))
                + FLOOR_CHANGE_TILE_COST * abs(node[2] - t[2])
                for t in temples
            ),
            node,
        ))

    if candidates:
        _, node = min(candidates)
        locations.append(build_city_poi(f"{city}-DEPOT-0001", "DEPOT", node, depot_label))
    elif find_depot_tiles(dump, depot_ids):
        warnings.append("nenhum depot encosta em tile andável")

    return locations, warnings


def build_city_poi(location_id: str, poi_type: str, node: Node, display_name: str) -> Dict:
    """Um POI mecânico da cidade (templo, depot) como entrada de `locations`.

    Nem placa nem curadoria: o templo sai do nó `towns` do próprio OTBM e o
    depot do item. Os dois são fato do mapa, e ficar esperando alguém marcá-los
    à mão é o que deixou uma cidade recém-importada sem lugar nenhum de onde
    partir.
    """
    x, y, z = node
    city = city_ids.derive_city(location_id)
    status = city_ids.derive_status(city)
    entry = {
        "id": location_id,
        "type": poi_type,
        "x": x,
        "y": y,
        "z": z,
        "displayName": display_name,
        "city": city,
    }
    if status is not None:
        entry["status"] = status
    return entry


def parse_ladder_items(items_xml: str) -> Set[int]:
    """Canary's `items.xml` -> os ids marcados
    `<attribute key="type" value="ladder"/>`.

    É o que separa as duas geometrias de `isFloorTransition`: escada de mão
    sobe (e para o sul), buraco desce. A flag sozinha nunca diz qual — o
    `appearances.dat` do cliente carrega um booleano sem direção
    (`opentibiabr/otclient`, `thingtype.h:138`), e era por isso que a
    `ADR 0002` ligava os dois sentidos e errava os dois. Do `items.xml` a
    direção sai.

    Mesma decisão de `parse_floorchange_items`: lido do arquivo que o servidor
    lê, não de uma lista curada aqui."""
    ladders: Set[int] = set()

    for item_ids, body in _iter_declared_items(items_xml):
        if _LADDER_ATTR_RE.search(body):
            ladders.update(item_ids)

    return ladders


def extract_tile_flags(
    dump: Dict,
    flags_by_id: Dict[str, Dict],
    floorchange_by_id: Optional[Dict[int, str]] = None,
    ladder_ids: Optional[Set[int]] = None,
) -> List[Dict]:
    """Every tile in the dump -> {"x", "y", "z", "unpass", "isFloorTransition",
    "isLadder", "floorchange"}, combining the ground tileid's flags with every item stacked
    on it (each resolved through `flags_by_id`, keyed by appearanceId — the
    versioned table in `appearance-flags/<CIDADE>.json`, which replaced the
    `objectDefs` of a 20,3 MB map.json this never otherwise read). Marker signs
    (reserved uid range) never contribute — they're stripped from the city's
    real output, and the graph must reflect that same city, not the raw OTBM's
    extra markup. A tile with no entry for an id contributes no flags.

    `floorchange` is the direction from `parse_floorchange_items`, or `None`
    when nothing on the tile changes floors — and `None` for every tile when
    `floorchange_by_id` is omitted, which is what keeps a caller that has no
    `items.xml` behaving exactly as before this existed. The *first* direction
    found on the tile wins: ground first, then items bottom-up, so a ramp that
    someone decorated doesn't lose its movement to the decoration.

    `isLadder` sai de `parse_ladder_items` e responde para onde o
    `isFloorTransition` daquele tile leva (`build_walkable_graph`). Sem
    `ladder_ids` é sempre `False`, que é a leitura conservadora: buraco desce
    na coluna e nada sobe para o tile errado."""
    floorchange_by_id = floorchange_by_id or {}
    ladder_ids = ladder_ids or set()

    def _flags(appearance_id: Optional[int]) -> Dict:
        if appearance_id is None:
            return {}
        return flags_by_id.get(str(appearance_id), {})

    tiles: Dict[Node, Dict] = {}
    for x, y, z, tile in _iter_dump_tiles(dump):
        key = (x, y, z)
        unpass = False
        is_floor_transition = False
        is_ladder = False
        floorchange: Optional[str] = None

        ground_id = tile.get("tileid")
        ground_flags = _flags(ground_id)
        unpass = unpass or ground_flags.get("unpass", False)
        is_floor_transition = is_floor_transition or ground_flags.get("isFloorTransition", False)
        if ground_id is not None:
            is_ladder = is_ladder or ground_id in ladder_ids
            floorchange = floorchange_by_id.get(ground_id)

        for raw_item in tile.get("items", []):
            if is_marker_item(raw_item):
                continue
            item_flags = _flags(raw_item.get("id"))
            unpass = unpass or item_flags.get("unpass", False)
            is_floor_transition = is_floor_transition or item_flags.get("isFloorTransition", False)
            is_ladder = is_ladder or raw_item.get("id") in ladder_ids
            if floorchange is None:
                floorchange = floorchange_by_id.get(raw_item.get("id"))

        tiles[key] = {
            "x": x,
            "y": y,
            "z": z,
            "unpass": unpass,
            "isFloorTransition": is_floor_transition,
            "isLadder": is_ladder,
            "floorchange": floorchange,
        }

    return list(tiles.values())


def _floor_change_deltas(tile: Dict) -> List[Tuple[int, int, int]]:
    """Os `(dx, dy, dz)` que este tile oferece para trocar de andar.

    Duas regras, nenhuma redundante: `floorchange` cobre o que se **pisa**
    (rampa, escada de pedra, alçapão) e vem do `items.xml`; `isFloorTransition`
    cobre o que se **usa** (escada de mão, corda), que não tem `floorchange`
    nenhum. Um tile pode carregar as duas."""
    deltas: List[Tuple[int, int, int]] = []

    if tile.get("isFloorTransition"):
        deltas.append(LADDER_DELTA if tile.get("isLadder") else HOLE_DELTA)

    named = FLOORCHANGE_DELTAS.get(tile.get("floorchange") or "")
    if named:
        deltas.append(named)

    return deltas


def floor_transition_edges(tiles: List[Dict]) -> List[Tuple[Node, Node]]:
    """As arestas de mudança de andar entre tiles caminháveis, uma por par.

    Não-direcionada e sem duplicata: quem consome liga os dois sentidos. Só
    sai aresta cujas duas pontas existem no recorte e não são `unpass` — um
    destino fora do mapa ou bloqueado não vira ligação, e é isso que impede o
    delta errado de inventar caminho.

    Existe separada de `build_walkable_graph` porque o `map.json` v6 precisa
    exatamente destas arestas e de mais nada do grafo (`map_v6.build_map_v6`).
    Duas cópias da regra divergiriam."""
    walkable = {(t["x"], t["y"], t["z"]) for t in tiles if not t["unpass"]}
    edges: List[Tuple[Node, Node]] = []
    seen: Set[Tuple[Node, Node]] = set()

    for t in tiles:
        if t["unpass"]:
            continue
        node = (t["x"], t["y"], t["z"])
        for dx, dy, dz in _floor_change_deltas(t):
            neighbor = (node[0] + dx, node[1] + dy, node[2] + dz)
            if neighbor not in walkable:
                continue
            pair = (node, neighbor) if node <= neighbor else (neighbor, node)
            if pair in seen:
                continue
            seen.add(pair)
            edges.append((node, neighbor))

    return edges


def extract_teleport_edges(dump: Dict) -> List[Tuple[Node, Node]]:
    """Os pares `(tile do teleport, tile de destino)` do dump OTBM.

    Cada item de teleport carrega `destination {x,y,z}` já em coordenada de
    mundo — a mesma do recorte, que não é rebaseado. Destino `(0,0,0)` é
    teleport decorativo/sem ligar e não entra. Não-direcionado por decisão
    (ADR/di memória): no idle de fast-travel todo TP vale nos dois sentidos,
    então quem consome liga os dois lados. O `floorchange`/`isFloorTransition`
    (escada, rampa, corda, buraco) continua em `floor_transition_edges`; isto
    cobre só o que teleporta, que aqueles não pegam e que ilhava cidade com
    área separada por água/portal (Zao, Thais, Yalahar)."""
    edges: List[Tuple[Node, Node]] = []
    for x, y, z, tile in _iter_dump_tiles(dump):
        for item in tile.get("items", []):
            if is_marker_item(item):
                continue
            dest = item.get("destination")
            if not isinstance(dest, dict):
                continue
            dx, dy, dz = dest.get("x", 0), dest.get("y", 0), dest.get("z", 0)
            if dx == 0 and dy == 0 and dz == 0:
                continue
            edges.append(((x, y, z), (dx, dy, dz)))
    return edges


def build_walkable_graph(
    tiles: List[Dict],
    extra_edges: Iterable[Tuple[Node, Node]] = (),
) -> Dict[Node, Set[Node]]:
    """Walkable tiles -> an undirected adjacency map. Tiles flagged `unpass`
    are excluded entirely (never a node). Same-floor neighbors (orthogonal +
    diagonal) all cost 1 — no diagonal penalty.

    As ligações entre andares saem de `floor_transition_edges`, que é a mesma
    regra que o `map.json` v6 publica.

    `extra_edges` são pares extras a ligar — hoje os teleports de
    `extract_teleport_edges`. Só o grafo de viagem os passa; candidato de
    hunt e mapa v6 não, porque lá teleport fundiria bolsão de spawn que o
    jogador não atravessa a pé. Uma ponta fora do recorte ou `unpass` é
    ignorada: destino que não existe no mapa não vira ligação, igual à regra
    de `floor_transition_edges`."""
    walkable = {(t["x"], t["y"], t["z"]) for t in tiles if not t["unpass"]}
    graph: Dict[Node, Set[Node]] = {node: set() for node in walkable}

    def _connect(a: Node, b: Node) -> None:
        graph[a].add(b)
        graph[b].add(a)

    for t in tiles:
        if t["unpass"]:
            continue
        x, y, z = t["x"], t["y"], t["z"]
        for dx, dy in _NEIGHBOR_OFFSETS:
            neighbor = (x + dx, y + dy, z)
            if neighbor in walkable:
                _connect((x, y, z), neighbor)

    for a, b in floor_transition_edges(tiles):
        _connect(a, b)

    for a, b in extra_edges:
        if a in walkable and b in walkable:
            _connect(a, b)

    return graph


def _step_direction(a: Node, b: Node) -> Tuple[int, int, int]:
    return ((b[0] > a[0]) - (b[0] < a[0]),
            (b[1] > a[1]) - (b[1] < a[1]),
            (b[2] > a[2]) - (b[2] < a[2]))


def _step_delta(a: Node, b: Node) -> Tuple[int, int, int]:
    return (b[0] - a[0], b[1] - a[1], b[2] - a[2])


def _extends_the_segment(first: Tuple[int, int, int], second: Tuple[int, int, int]) -> bool:
    """Se dois passos seguidos desenham a mesma reta — e portanto o vértice
    entre eles não diz nada.

    É colinearidade de verdade (produto vetorial zero, mesmo sentido), não
    igualdade de sinal: um passo pode ter mais de um tile de comprimento, e aí
    o sinal mente. Um salto de aproximação `(5, -4)` depois de uma corrida
    diagonal `(1, -1)` tem o mesmo sinal e não é a mesma reta.

    Passo que muda de andar nunca estende nada, nem outro igual a ele: quem
    desenha decide o que mostrar pelo z de cada vértice, sem interpolar, então
    fundir duas descidas seguidas apagaria o andar do meio da rota.
    """
    if first[2] or second[2]:
        return False
    cross = first[0] * second[1] - first[1] * second[0]
    return cross == 0 and first[0] * second[0] + first[1] * second[1] > 0


def tile_distances_and_prev(
    graph: Dict[Node, Set[Node]], sources: Dict[Node, int], targets: Set[Node]
) -> Tuple[Dict[Node, int], Dict[Node, Optional[Node]]]:
    """`(distâncias, pai de cada nó aceito)` — a busca inteira, com o que
    `reconstruct_path` precisa para remontar o caminho andado.

    Distância é a contagem de tiles de `sources` até cada nó de `targets` que
    seja alcançável, parando assim que todos foram aceitos (ou o grafo se
    esgotou) em vez de inundar o grafo inteiro.

    `sources` mapeia um tile de partida para o custo de *entrar* no grafo ali
    (0 para uma location em cima do próprio tile caminhável; ver
    `approach_costs`). Toda aresta do grafo custa 1 — os custos de semente são
    a única parte não uniforme, e é por isso que isto tira do heap o nó mais
    barato em vez de confiar em ordem FIFO.

    **O pai é gravado no settle** (quando o nó sai do heap e vira definitivo),
    nunca no relax. No relax um nó pode ser tocado de novo, mais tarde e por um
    caminho pior — e como a busca só para quando o último alvo é aceito, esse
    relax tardio existe de verdade. Gravar ali daria uma polilinha que
    contradiz o `tileCount` que esta mesma busca reporta.

    Entre dois caminhos de mesmo custo — e num grid 8-conectado há muitos —
    ganha o de menos curvas. O custo continua sendo a chave primária, então
    nenhuma distância muda; o que muda é *qual* caminho mínimo sobrevive, e
    escolher o zigue-zague seria um vértice a cada dois tiles mesmo depois de
    simplificar. Só este desempate leva o ROOK de 37 mil vértices para 15.467.

    O último critério é um contador de inserção, que garante desempate total:
    sem ele duas entradas idênticas até o nó cairiam em comparar os pais, e
    `None` (a semente) não se compara com uma tupla.
    """
    remaining = set(targets) - {node for node in sources if node in graph}
    found: Dict[Node, int] = {node: cost for node, cost in sources.items()
                              if node in graph and node in targets}
    prev: Dict[Node, Optional[Node]] = {}
    if not remaining:
        return found, prev

    order = itertools.count()
    visited = set()
    frontier = [(cost, 0, next(order), node, None)
                for node, cost in sources.items() if node in graph]
    heapq.heapify(frontier)
    while frontier and remaining:
        dist, turns, _, node, parent = heapq.heappop(frontier)
        if node in visited:
            continue
        visited.add(node)
        prev[node] = parent
        if node in remaining:
            found[node] = dist
            remaining.discard(node)
        incoming = _step_direction(parent, node) if parent is not None else None
        for neighbor in graph.get(node, ()):
            if neighbor in visited:
                continue
            step = _step_direction(node, neighbor)
            turned = 0 if incoming is None or step == incoming else 1
            heapq.heappush(frontier, (dist + 1, turns + turned, next(order), neighbor, node))
    return found, prev


def reconstruct_path(prev: Dict[Node, Optional[Node]], node: Node) -> List[Node]:
    """O caminho andado até `node`, da semente até ele. Um nó sem pai (a
    própria semente, ou um alvo que já era semente) é um caminho de um ponto
    só — não um erro."""
    path = [node]
    while prev.get(path[-1]) is not None:
        path.append(prev[path[-1]])
    path.reverse()
    return path


def simplify_polyline(path: Sequence[Node]) -> List[Node]:
    """Guarda vértice só onde a direção muda, com as duas pontas sempre
    presentes.

    Num grid 8-conectado a maioria dos trechos é reta longa, e cada tile
    intermediário dela é um ponto que não diz nada: sem isto as 630 arestas do
    ROOK sairiam com 69.659 vértices, e saem com 15.467.

    O que descarta um vértice é os dois passos vizinhos desenharem a mesma
    reta (`_extends_the_segment`), e não terem o mesmo sinal: nem todo par
    consecutivo do caminho é um passo de um tile — `build_travel_graph`
    prepende/anexa o tile da location, e a aproximação a um NPC atrás do
    balcão é um salto Chebyshev de até `npc_reach`. Pelo sinal, um salto
    alinhado com a corrida diagonal anterior engolia o tile de aproximação e a
    reta resultante atravessava tiles que ninguém pisou.
    """
    if len(path) <= 2:
        return list(path)

    simplified = [path[0]]
    for before, here, after in zip(path, path[1:], path[2:]):
        if not _extends_the_segment(_step_delta(before, here), _step_delta(here, after)):
            simplified.append(here)
    simplified.append(path[-1])
    return simplified


def _without_repeats(path: Sequence[Node]) -> List[Node]:
    """Tira repetição consecutiva, mas nunca devolve um ponto só.

    Duas locations no **mesmo tile** existem de verdade — duas hunts curadas
    que compartilham a entrada, dois NPCs colados — e a aresta entre elas é
    legítima, com `tileCount` 0. Sem o segundo ponto ela sairia com uma
    polilinha de um vértice, que o schema do catálogo recusa (e com razão: a
    polilinha vai de pino a pino, então os dois pinos sempre entram, mesmo
    quando são o mesmo tile)."""
    trimmed = [
        node for index, node in enumerate(path) if index == 0 or node != path[index - 1]
    ]
    return trimmed * 2 if len(trimmed) == 1 else trimmed


def flatten_polyline(path: Sequence[Node]) -> List[int]:
    """`[(x, y, z), ...]` -> `[x0, y0, z0, x1, y1, z1, ...]`, o formato plano
    de triplas que o contrato fixou."""
    return [value for node in path for value in node]


def approach_costs(node: Node, graph: Dict[Node, Set[Node]], reach: int) -> Dict[Node, int]:
    """The tiles a location can be reached *from*, mapped to how many tiles
    away from it they are -> what `tile_distances_and_prev` takes as `sources`.

    With `reach` 0 that's just the location's own tile, when walkable. A
    larger reach exists for NPCs: most of Rookgaard's shopkeepers stand
    behind an `unpass` counter, so their own tile is a two-tile pocket the
    player can never walk into — the player stops on the far side of the
    counter and trades across it. Charging each approach tile its own
    distance (rather than seeding them all at 0) keeps that honest in both
    directions: an NPC standing in the open street still enters at its own
    tile for 0 and its distances are untouched, while a shopkeeper's start
    at the 2 tiles that actually separate the player from the counter."""
    costs: Dict[Node, int] = {}
    x, y, z = node
    for dx in range(-reach, reach + 1):
        for dy in range(-reach, reach + 1):
            candidate = (x + dx, y + dy, z)
            if candidate in graph:
                costs[candidate] = max(abs(dx), abs(dy))
    return costs


def build_travel_graph(
    graph: Dict[Node, Set[Node]], locations: List[Dict], npc_reach: int = DEFAULT_NPC_REACH
) -> List[Dict]:
    """One search per location, reaching every other location (early exit
    once all are found) -> one {from, to, tileCount, path} edge per reachable
    pair. `path` is the walked route as a flat array of x,y,z triples, with a
    vertex only where the direction changes — the same route `tileCount`
    counts, now drawable.
    Distance is computed independently per pair (real tiles walked, never
    inferred through a shared hub, never euclidean), and a pair on
    disconnected regions of the graph simply produces no edge.

    A location is reached at whichever of its approach tiles is cheapest
    (see `approach_costs`) — for everything but an NPC that is its own tile
    and nothing else. Two locations sharing a tile are zero tiles apart, and
    that edge is emitted like any other: since NPCs became travel
    destinations, two of them behind the same tavern counter are two
    destinations the player picks between, not graph noise to collapse.

    Edges are canonical — `from` < `to`, one per unordered pair, never a
    self-edge — and the list is sorted, so re-running against an unchanged
    map produces a byte-identical fragment."""
    approaches: List[Tuple[str, Dict[Node, int]]] = [
        (loc["id"], approach_costs(
            (loc["x"], loc["y"], loc["z"]),
            graph,
            npc_reach if loc.get("type") == "NPC" else 0,
        ))
        for loc in locations
    ]
    every_approach_tile = {node for _, costs in approaches for node in costs}
    # Onde o pino de cada location fica. A polilinha é ancorada nele nas duas
    # pontas: o caminho andado começa e termina num tile de *aproximação*, e
    # para um NPC atrás do balcão esse tile está a até `npc_reach` dele — uma
    # rota que começa cinco tiles longe do pino é rota errada na tela. O
    # trecho de aproximação entra como o segmento reto que ele é, sem nenhum
    # vértice inventado no meio (o custo dele é Chebyshev, não caminho andado)
    # — e `simplify_polyline` só o funde com o segmento vizinho quando os dois
    # desenham a mesma reta, senão o último tile andado sumiria.
    #
    # Esse segmento é o único da rota que o jogador não pisa, e ele não vem
    # marcado: para uma linha na tela dá no mesmo, para navegação passo a
    # passo não daria. O contrato é silencioso sobre onde a polilinha começa;
    # está documentado como "de pino a pino" no README.
    own_tile: Dict[str, Node] = {loc["id"]: (loc["x"], loc["y"], loc["z"]) for loc in locations}

    edges: List[Dict] = []
    seen_pairs: Set[frozenset] = set()

    def _emit(a_id: str, b_id: str, dist: int, walked: List[Node]) -> None:
        if a_id == b_id:
            return
        pair = frozenset((a_id, b_id))
        if pair in seen_pairs:
            return
        seen_pairs.add(pair)
        low, high = sorted((a_id, b_id))
        # A polilinha sai orientada junto com a aresta canônica: ela serve os
        # dois sentidos, e quem consome inverte em triplas quando precisa —
        # mas adivinhar qual ponta é `from` seria trabalho de graça.
        anchored = _without_repeats([own_tile[a_id], *walked, own_tile[b_id]])
        oriented = anchored if low == a_id else list(reversed(anchored))
        edges.append({
            "from": low,
            "to": high,
            "tileCount": dist,
            "path": flatten_polyline(simplify_polyline(oriented)),
        })

    for loc_id, costs in approaches:
        if not costs:
            continue
        distances, prev = tile_distances_and_prev(graph, costs, every_approach_tile)
        for other_id, other_costs in approaches:
            if other_id == loc_id:
                continue
            # (custo, tile) e não só o custo: o tile que venceu é por onde a
            # polilinha termina. O desempate pela coordenada mantém a escolha
            # estável entre dois runs do mesmo mapa.
            reachable = [(distances[node] + cost, node) for node, cost in other_costs.items()
                         if node in distances]
            if reachable:
                dist, arrival = min(reachable)
                _emit(loc_id, other_id, dist, reconstruct_path(prev, arrival))

    edges.sort(key=lambda e: (e["from"], e["to"]))
    return edges


# ======================================================
# NPC locations + Canary shop extraction
# ======================================================


def slugify(name: str) -> str:
    """"Lee'Delle" -> "lee-delle". Used both for the NPC location id and for
    matching a Canary npc/*.lua filename (which follows the same convention)."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug


def parse_npc_xml(xml_text: str) -> List[Dict]:
    """<region>-npc.xml -> [{"name", "x", "y", "z"}, ...]. Position is the
    outer <npc centerx/centery/centerz> plus the inner <npc name="..." x="0"
    y="0" z="..."> offset (0,0 in every placement seen so far, but the offset
    is honoured rather than assumed away)."""
    root = ET.fromstring(xml_text)
    npcs: List[Dict] = []
    for outer in root.findall("npc"):
        center_x = int(outer.get("centerx", 0))
        center_y = int(outer.get("centery", 0))
        center_z = int(outer.get("centerz", 7))
        for inner in outer.findall("npc"):
            name = inner.get("name")
            if not name:
                continue
            npcs.append({
                "name": name,
                "x": center_x + int(inner.get("x", 0)),
                "y": center_y + int(inner.get("y", 0)),
                "z": int(inner.get("z", center_z)),
            })
    return npcs


def match_npc_lua_filename(npc_name: str, lua_filenames: List[str]) -> Optional[str]:
    """The NPC's name, slugified, matched against a same-named .lua filename
    (case-insensitive stem match — Canary's own filenames are lowercase and
    use "_" as a word separator, e.g. "An Orc Guard" -> an_orc_guard.lua,
    while `slugify`/location ids use "-"; both sides are normalized to "-"
    for the comparison only). None if nothing matches."""
    slug = slugify(npc_name)
    for filename in lua_filenames:
        stem = filename[:-4] if filename.lower().endswith(".lua") else filename
        if stem.lower().replace("_", "-") == slug:
            return filename
    return None


_SHOP_BLOCK_START_RE = re.compile(r"npcConfig\.shop\s*=\s*\{")
_SHOP_ENTRY_RE = re.compile(r"\{([^{}]*)\}")
_SHOP_FIELD_RE = re.compile(r'(\w+)\s*=\s*("(?:[^"\\]|\\.)*"|-?\d+(?:\.\d+)?)')


def _extract_braced_block(text: str, start: int) -> str:
    depth = 1
    i = start
    while i < len(text) and depth > 0:
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
        i += 1
    return text[start:i - 1]


def _parse_lua_scalar(raw: str):
    raw = raw.strip()
    if raw.startswith('"'):
        return raw[1:-1]
    return int(raw) if re.fullmatch(r"-?\d+", raw) else float(raw)


_OUTFIT_BLOCK_START_RE = re.compile(r"npcConfig\.outfit\s*=\s*\{")

#: `lookType` is the only required key — an NPC with no colours is a valid
#: outfit (the base sprite), and `lookAddons` is absent on most of them.
_OUTFIT_KEYS = ("lookType", "lookHead", "lookBody", "lookLegs", "lookFeet", "lookAddons")


def parse_npc_outfit_lua(lua_text: str) -> Optional[Dict]:
    """A Canary npc .lua file's text -> its `npcConfig.outfit` table, or None
    when the file has none.

    Same file the shop already comes from, and that is the whole point: the
    two facts about an NPC that the game needs to *draw* and *trade with* him
    live side by side in Canary, and reading the file twice to fetch them
    separately would be two passes over the same text.

    `lookType` is what indexes the outfit atlases the client already ships
    (`/assets/outfits/<lookType>.png`); the four colour indices and the addon
    bitmask are what turn the base sprite into *this* NPC. An outfit table
    without `lookType` is not an outfit, and is reported as None rather than
    as a half-filled dict — the consumer would have nothing to draw.
    """
    block_match = _OUTFIT_BLOCK_START_RE.search(lua_text)
    if not block_match:
        return None

    block = _extract_braced_block(lua_text, block_match.end())
    fields = {
        m.group(1): _parse_lua_scalar(m.group(2))
        for m in _SHOP_FIELD_RE.finditer(block)
        if m.group(1) in _OUTFIT_KEYS
    }

    if "lookType" not in fields:
        return None

    return {key: int(fields[key]) for key in _OUTFIT_KEYS if key in fields}


_ITEMS_TABLE_START_RE = re.compile(r"local\s+itemsTable\s*=\s*\{")


def _parse_shop_entries(block: str) -> List[Dict]:
    entries: List[Dict] = []
    for line in block.splitlines():
        line = line.split("--", 1)[0].strip()
        if not line.startswith("{"):
            continue
        entry_match = _SHOP_ENTRY_RE.search(line)
        if not entry_match:
            continue
        fields = {m.group(1): _parse_lua_scalar(m.group(2)) for m in _SHOP_FIELD_RE.finditer(entry_match.group(1))}
        if "itemName" not in fields or "clientId" not in fields:
            continue
        entry = {"itemName": fields["itemName"], "itemId": int(fields["clientId"])}
        if "buy" in fields:
            entry["buy"] = int(fields["buy"])
        if "sell" in fields:
            entry["sell"] = int(fields["sell"])
        entries.append(entry)
    return entries


def parse_npc_shop_lua(lua_text: str) -> Optional[List[Dict]]:
    """A Canary npc .lua file's text -> its `npcConfig.shop` table, or None
    if the NPC has no shop at all (a trainer/quest NPC). `clientId` is used
    directly as `itemId` — verified against Canary's own npc_functions.cpp
    and items.xml, no id-translation table needed (see spec's Further Notes).

    Canary escreve a loja de dois jeitos. O antigo é a tabela por extenso em
    `npcConfig.shop = { {...}, ... }`. O novo agrupa por categoria em
    `local itemsTable = { ["potions"] = { {...} } }` e deixa
    `npcConfig.shop = {}` ser preenchido por um laço no fim do arquivo — ler só
    o `{}` vazio dava um NPC sem nada à venda (Xodet, Rachel, Sigurd...)."""
    block_match = _SHOP_BLOCK_START_RE.search(lua_text)
    if not block_match:
        return None

    entries = _parse_shop_entries(_extract_braced_block(lua_text, block_match.end()))
    if entries:
        return entries

    items_table = _ITEMS_TABLE_START_RE.search(lua_text)
    if not items_table:
        return entries

    return _parse_shop_entries(_extract_braced_block(lua_text, items_table.end()))


#: As cinco funções do motor do Canary que prestam serviço cobrado, com a
#: assinatura exata da chamada que cada uma recebe no `.lua` do NPC. Definidas em
#: `data/npclib/npc_system/modules.lua` (promotePlayer, learnSpell, bless,
#: travel) e `data/npclib/npc_system/bank_system.lua` (parseBank).
#:
#: O `(` de `:parseBank(` não é decoração: `parseBankMessages` é outra função,
#: chamada pelos mesmos NPCs, e um `parseBank` solto casaria com as duas.
NPC_SERVICE_SIGNATURES = (
    ("travel", "StdModule.travel"),
    ("bank", ":parseBank("),
    ("bless", "StdModule.bless"),
    ("promote", "StdModule.promotePlayer"),
    ("spell", "StdModule.learnSpell"),
)


def parse_npc_services_lua(lua_text: str) -> List[str]:
    """A Canary npc .lua file's text -> os serviços de motor que ele presta, na
    ordem de `NPC_SERVICE_SIGNATURES`. Lista vazia quando não presta nenhum —
    nunca None, pela mesma razão que o extrato guarda arquivo sem shop nem
    outfit: "não presta serviço" e "não foi olhado" têm que ser distinguíveis.

    **Assinatura, não nome nem diálogo**, e isso é o ponto da função.
    `captain_tiberius.lua` diz "I transport my passengers back to the
    continent." e não tem keyword nenhum nem `teleportTo`; `captain_kurt.lua`
    são 58 linhas de config sem um único keyword. Os dois parecem barqueiro e
    nenhum dos dois é — qualquer heurística por nome aceitaria os dois, e um
    `StdModule.travel` não aceita nenhum.

    Pelo mesmo motivo nada aqui procura `removeMoneyBank`, `addItem` ou
    `teleportTo`: esses padrões não separam loja repetível de quest de uma vez
    só (o Blind Orc vende dez itens; o Oswald cobra 1000g uma vez). Quem precisa
    desse corte vai à mão na `npc-allowlist.json`."""
    return [name for name, signature in NPC_SERVICE_SIGNATURES if signature in lua_text]


def build_npc_location(
    npc: Dict,
    city_prefix: str,
    shop: Optional[List[Dict]],
    outfit: Optional[Dict] = None,
) -> Dict:
    """An NPC (position + name) plus its already-resolved shop (or None) ->
    a `locations` entry. No sign involved, no `displayName` curation — the
    NPC's real in-game name is already a good display name. The id follows
    the same CIDADE-TIPO-slug shape every other POI type uses
    (`ROOK-NPC-obi`), city/type uppercase, slug lowercase — `city`/`status`
    are derived from that same id."""
    city = city_prefix.upper()
    status = city_ids.derive_status(city)
    entry: Dict = {
        "id": f"{city}-NPC-{slugify(npc['name'])}",
        "type": "NPC",
        "x": npc["x"],
        "y": npc["y"],
        "z": npc["z"],
        "displayName": npc["name"],
        "city": city,
    }
    if status is not None:
        entry["status"] = status
    if outfit is not None:
        entry["outfit"] = outfit
    if shop is not None:
        entry["shop"] = shop
    return entry


def build_npc_locations(
    npcs: List[Dict],
    city_prefix: str,
    facts_by_name: Dict[str, Dict],
) -> Tuple[List[Dict], List[str]]:
    """Every NPC -> its Location, plus the list of NPC names with no matching
    `.lua` file at all (still get a Location — position/name — just no
    `shop` field, and the run should warn about these). A name that IS a key
    in `facts_by_name` matched a file — seu `shop` ainda pode ser None (um NPC
    de treino/quest sem tabela `npcConfig.shop`), o que é esperado e não é
    motivo de warning, diferente de arquivo genuinamente ausente.

    `facts_by_name` é **um** dict de `{"shop", "outfit", "services"}` por nome, e
    não três dicts paralelos: os três são campos do mesmo fato sobre o NPC e
    vivem lado a lado no mesmo arquivo do Canary. `services` fica no fato e
    **não** entra na location — ele serve ao filtro, dentro do extractor, e
    `npcSourceSchema` no `tibia-idle` descreve o que uma location de NPC é."""
    locations: List[Dict] = []
    unmatched: List[str] = []
    for npc in npcs:
        name = npc["name"]
        if name not in facts_by_name:
            unmatched.append(name)
        facts = facts_by_name.get(name) or {}
        locations.append(
            build_npc_location(npc, city_prefix, facts.get("shop"), facts.get("outfit"))
        )
    return locations, unmatched


# ======================================================
# Fragment assembly + catalog merge
# ======================================================


FLOOR_CHANGE_TILE_COST = 10


def connect_orphan_hunts(
    locations: List[Dict], edges: List[Dict]
) -> Tuple[List[Dict], List[Dict]]:
    """Liga ao continente toda HUNT que não se alcança dele. -> `(arestas, ligações inventadas)`.

    Uma hunt fica fora de alcance quando o caminho até ela depende de algo que
    o grafo não modela: buraco que exige corda, alçapão aberto por script,
    porta de quest, **barco** (Fibula, Mount Sternum) ou **airship** (a mina de
    Farmine, em Zao, que fica a andares do resto da cidade).

    Não basta olhar "tem aresta?": uma ilha com várias hunts liga as suas entre
    si e passa por conectada, mas o templo não chega em nenhuma. Então o corte
    é por **componente**: acha o maior (o continente, onde o templo está) e
    liga a ele cada componente que tenha hunt, pelo par de POIs mais baratos.
    Foi medindo isso que Zao apareceu com 1 de 19 hunts alcançáveis.

    O jogador **não anda esse trecho e nem o vê**: ele escolhe a hunt numa
    lista e o jogo conta o tempo de viagem. Então a escolha aqui é entre a hunt
    não existir e a hunt existir com uma estimativa — e uma hunt que o mapa tem
    e o jogo esconde é pior. O custo estimado é a distância em linha reta mais
    `FLOOR_CHANGE_TILE_COST` por andar de diferença, e a polilinha é o segmento
    reto entre os dois pinos.

    Componente só de NPC continua indo pro relatório de rejeição: aquilo é bug
    de mapa (ou de posição do NPC) e some assim que alguém o conserta.
    """
    by_id = {location["id"]: location for location in locations}
    if not by_id:
        return edges, []

    adjacency: Dict[str, Set[str]] = {name: set() for name in by_id}
    for edge in edges:
        if edge["from"] in adjacency and edge["to"] in adjacency:
            adjacency[edge["from"]].add(edge["to"])
            adjacency[edge["to"]].add(edge["from"])

    components: List[Set[str]] = []
    seen: Set[str] = set()
    for name in sorted(by_id):
        if name in seen:
            continue
        component = {name}
        seen.add(name)
        queue = [name]
        while queue:
            current = queue.pop()
            for neighbor in adjacency[current]:
                if neighbor not in seen:
                    seen.add(neighbor)
                    component.add(neighbor)
                    queue.append(neighbor)
        components.append(component)

    if len(components) < 2:
        return edges, []

    # O continente é o maior componente — é onde o templo está em toda cidade
    # medida. Empate resolve por id, pra o fragmento sair idêntico a cada run.
    mainland = max(components, key=lambda c: (len(c), -ord(min(c)[0])))
    islands = [c for c in components if c is not mainland]

    def cost(a: Dict, b: Dict) -> int:
        return max(abs(a["x"] - b["x"]), abs(a["y"] - b["y"])) + (
            FLOOR_CHANGE_TILE_COST * abs(a["z"] - b["z"])
        )

    anchors = [by_id[name] for name in sorted(mainland)]
    invented: List[Dict] = []

    for island in islands:
        # Hunt é o motivo original da ponte; templo e depot entraram porque
        # toda cidade precisa dos dois, e Yalahar perdia o seu — o depot dela
        # cai num componente sem hunt nenhuma e era rejeitado. Componente só
        # de NPC continua indo pro relatório: aquilo é bug de mapa.
        hunts = sorted(
            name
            for name in island
            if by_id[name]["type"] in ("HUNT", "TEMPLE", "DEPOT")
        )
        if not hunts:
            continue

        pairs = (
            (cost(by_id[near], anchor), near, anchor["id"])
            for near in sorted(island)
            for anchor in anchors
        )
        _, island_id, anchor_id = min(pairs)
        tile_count = max(1, cost(by_id[island_id], by_id[anchor_id]))
        low, high = sorted((island_id, anchor_id))
        ends = {
            name: (by_id[name]["x"], by_id[name]["y"], by_id[name]["z"])
            for name in (island_id, anchor_id)
        }
        edges.append(
            {
                "from": low,
                "to": high,
                "tileCount": tile_count,
                "path": flatten_polyline([ends[low], ends[high]]),
            }
        )
        invented.append(
            {
                "hunt": island_id,
                "anchor": anchor_id,
                "tileCount": tile_count,
                "hunts": len(hunts),
            }
        )

    edges.sort(key=lambda edge: (edge["from"], edge["to"]))
    return edges, invented


def close_bridged_pairs(edges: List[Dict]) -> Tuple[List[Dict], int]:
    """Dá aresta direta a todo par que só se ligava passando por uma ponte. -> `(arestas, quantas)`.

    `build_travel_graph` emite **uma aresta por par mutuamente alcançável**, não
    por vizinhança: dentro de um componente o grafo já é completo, e é por isso
    que a tela de viagem lista a cidade inteira de uma vez. As pontes de
    `connect_orphan_hunts` quebram essa propriedade — elas ligam dois
    componentes por um fio só, e aí chegar numa hunt do outro lado passa a
    exigir 3, 4, 5 saltos (Zao: 1 hunt a um salto, 3 a cinco).

    Então o transitivo é fechado aqui: Dijkstra de cada POI sobre o grafo de
    POIs, e todo par que ficou sem aresta ganha uma, com `tileCount` somado e a
    polilinha concatenada no caminho. Só toca par que a ponte tornou possível —
    par do mesmo componente já tinha a sua, medida em tile andado de verdade.
    O custo somado é estimativa por cima de estimativa, e assumido: a ponte já
    era inventada."""
    adjacency: Dict[str, Dict[str, Dict]] = {}
    for edge in edges:
        adjacency.setdefault(edge["from"], {})[edge["to"]] = edge
        adjacency.setdefault(edge["to"], {})[edge["from"]] = edge

    existing = {frozenset((edge["from"], edge["to"])) for edge in edges}
    added: List[Dict] = []

    for source in sorted(adjacency):
        # Dijkstra guardando o antecessor, pra reconstruir a polilinha.
        best: Dict[str, int] = {source: 0}
        previous: Dict[str, str] = {}
        heap: List[Tuple[int, str]] = [(0, source)]
        while heap:
            distance, node = heapq.heappop(heap)
            if distance > best.get(node, distance):
                continue
            for neighbor, edge in adjacency[node].items():
                candidate = distance + edge["tileCount"]
                if candidate < best.get(neighbor, candidate + 1):
                    best[neighbor] = candidate
                    previous[neighbor] = node
                    heapq.heappush(heap, (candidate, neighbor))

        for target, distance in sorted(best.items()):
            if target <= source:
                continue
            pair = frozenset((source, target))
            if pair in existing:
                continue
            existing.add(pair)

            hops = [target]
            while hops[-1] != source:
                hops.append(previous[hops[-1]])
            hops.reverse()

            # A polilinha de cada perna é gravada de `from` para `to`; andada no
            # sentido contrário ela entra invertida, senão o traço volta no
            # próprio rastro. O vértice de junção não se repete.
            walked: List[Node] = []
            for first, second in zip(hops, hops[1:]):
                leg = adjacency[first][second]
                flat = leg["path"] or []
                nodes = [tuple(flat[i:i + 3]) for i in range(0, len(flat), 3)]
                if leg["from"] != first:
                    nodes.reverse()
                if walked and nodes and nodes[0] == walked[-1]:
                    nodes = nodes[1:]
                walked.extend(nodes)

            low, high = sorted((source, target))
            added.append(
                {
                    "from": low,
                    "to": high,
                    "tileCount": max(1, distance),
                    "path": flatten_polyline(
                        walked if low == source else list(reversed(walked))
                    ),
                }
            )

    if not added:
        return edges, 0

    edges = [*edges, *added]
    edges.sort(key=lambda edge: (edge["from"], edge["to"]))
    return edges, len(added)


def build_travel_fragment(locations: List[Dict], travel_graph: List[Dict]) -> Dict:
    """The one place the fragment's shape is spelled out. `locations` is
    already both sources combined — sign-marked POIs and NPCs stop being two
    lists the moment they enter the same graph, and re-splitting them here
    just to concatenate them again would be ceremony."""
    return {"locations": locations, "travelGraph": travel_graph}


# ======================================================
# Rejecting nodes with no way in
# ======================================================

def _poi_without_edge_line(rejection: Dict) -> str:
    return (f"  {rejection['id']}  ({rejection['type']})  "
            f"x={rejection['x']} y={rejection['y']} z={rejection['z']}")


def _edge_without_poi_line(rejection: Dict) -> str:
    cited = ", ".join(f"{edge['from']}<->{edge['to']} ({edge['tileCount']} tiles)"
                      for edge in rejection["edges"])
    return f"  {rejection['id']}  sem coordenada  citado por: {cited}"


def _hunt_without_poi_line(rejection: Dict) -> str:
    return f"  {rejection['id']}  {rejection['name']}  sem coordenada de mundo"


# The three ways a node can have no way into the travel graph: the reason,
# what to do about it, and how its line reads — one row per case, because
# the three travel together (the report groups by reason, in this order, and
# each case's line shows different fields, since each has different evidence
# to show). Ordered most actionable (a coordinate to open in the map editor)
# first, vaguest (a hunt whose entrance nobody has marked yet) last.
_REJECTION_CASES = (
    (
        "poi-without-edge",
        "POI com coordenada e sem aresta — a placa existe no OTBM, mas o tile dela não\n"
        "alcança nenhum outro POI da cidade (ilhado por parede/água, ou a placa está num\n"
        "tile intransponível). Abra a coordenada no editor de mapa e mova a placa pra um\n"
        "tile caminhável ligado ao resto da cidade.",
        _poi_without_edge_line,
    ),
    (
        "edge-without-poi",
        "Id citado numa aresta que não é POI — não existe placa com esse id em lugar nenhum,\n"
        "então ele não tem coordenada: é id escrito errado na fonte (ex: um dígito a mais).\n"
        "Corrija o texto da placa no OTBM pro formato CIDADE-TIPO-NNNN, com exatamente 4 dígitos.",
        _edge_without_poi_line,
    ),
    (
        "hunt-without-poi",
        "Hunt sem POI de entrada — o mapa da hunt existe em extractor/maps/, mas nenhuma placa\n"
        "marca por onde se entra nela. A hunt não tem coordenada de mundo (o startPosition dela é\n"
        "posição dentro do próprio mapa da hunt), então só o OTBM sabe onde fica: coloque a placa\n"
        "com esse id na entrada, no editor de mapa.",
        _hunt_without_poi_line,
    ),
)

REJECTION_REASONS = tuple(reason for reason, _, _ in _REJECTION_CASES)


def apply_graph_rejections(
    locations: List[Dict], edges: List[Dict], hunts: Sequence[Dict] = ()
) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    """Splits a freshly built graph into what may be emitted and what has no
    way in -> (kept_locations, kept_edges, rejections).

    A node nobody can travel to is rejected here rather than emitted for a
    downstream gate to drop in silence: while `tileCount` only decorated a
    label, an unreachable destination cost nothing; once travel is
    authoritative it is a hunt the player simply cannot play, with no trace
    of why. Each rejection carries whatever that case actually has to
    identify it (see `_REJECTION_CASES`) — a coordinate is not invented for a
    node that never had one.

    Phantom edges go first, so degree is counted over links that will still
    exist: a POI whose only edge cited a non-existent id is isolated too, and
    is rejected in the same pass. A hunt whose POI exists but was rejected is
    reported once, under that POI's own (more actionable) case.

    `hunts` is [{"id", "name"}] — the hunt maps on disk, whose entrance the
    graph is checked against. Order is by case, then id, so two runs against
    an unchanged map produce identical output."""
    location_ids = {loc["id"] for loc in locations}

    kept_edges: List[Dict] = []
    edges_by_phantom: Dict[str, List[Dict]] = {}
    for edge in edges:
        phantoms = [side for side in (edge["from"], edge["to"]) if side not in location_ids]
        if not phantoms:
            kept_edges.append(edge)
            continue
        for phantom in phantoms:
            edges_by_phantom.setdefault(phantom, []).append(edge)

    degree: Dict[str, int] = {}
    for edge in kept_edges:
        degree[edge["from"]] = degree.get(edge["from"], 0) + 1
        degree[edge["to"]] = degree.get(edge["to"], 0) + 1

    kept_locations = [loc for loc in locations if degree.get(loc["id"], 0) > 0]

    rejections: List[Dict] = []
    for loc in locations:
        if degree.get(loc["id"], 0) == 0:
            rejections.append({
                "reason": "poi-without-edge",
                "id": loc["id"],
                "type": loc.get("type"),
                "x": loc["x"],
                "y": loc["y"],
                "z": loc["z"],
            })
    for phantom_id, citing_edges in edges_by_phantom.items():
        rejections.append({"reason": "edge-without-poi", "id": phantom_id, "edges": citing_edges})
    for hunt in hunts:
        if hunt["id"] not in location_ids:
            rejections.append({"reason": "hunt-without-poi", "id": hunt["id"], "name": hunt["name"]})

    rejections.sort(key=lambda r: (REJECTION_REASONS.index(r["reason"]), r["id"]))
    return kept_locations, kept_edges, rejections


def format_rejection_report(rejections: List[Dict], city: str) -> str:
    """The rejection list -> the text file the user opens next to the map
    editor. Grouped by case, each group stating what to do about it, so a
    line is actionable without reading the spec. Deterministic: same
    rejections in, same bytes out, for a clean diff between runs."""
    lines = [
        f"# Nós sem entrada no grafo de viagem — {city}",
        "#",
        "# Gerado por build_travel_fragment.py. Nada aqui entrou no fragmento: são os nós que",
        "# ninguém consegue alcançar viajando, e o que fazer com cada um.",
        "",
    ]

    if not rejections:
        lines.append("Nenhum nó rejeitado.")
        return "\n".join(lines) + "\n"

    for reason, help_text, format_line in _REJECTION_CASES:
        group = [r for r in rejections if r["reason"] == reason]
        if not group:
            continue
        lines.append(f"## {reason} ({len(group)})")
        lines.append(help_text)
        lines.append("")
        lines.extend(format_line(rejection) for rejection in group)
        lines.append("")

    return "\n".join(lines).rstrip("\n") + "\n"


def merge_locations_into_catalog(
    catalog_locations: List[Dict], fragment_locations: List[Dict], city: str
) -> Dict[str, str]:
    """Upserts each fragment location into catalog_locations in place, by id.
    Mechanical fields (position, type, shop) always take the fragment's
    fresh value. Once a human edit removes `_todo` from an existing entry,
    it's considered fully curated: every field in CURATED_LOCATION_FIELDS
    (`displayName`, `huntId`) is preserved from then on, never overwritten
    by a later run's placeholder, and `_todo` stays gone. While `_todo` is
    still present (still a draft nobody's reviewed yet), the entry is fully
    regenerated from the fresh fragment instead — including `_todo` itself,
    so a code change that adds a new curation note (e.g. `huntId`) reaches
    every not-yet-curated draft on its next run, not just brand-new ones.
    `by_id` is kept up to date as entries are appended, so two fragment
    locations sharing an id (should never happen — see parse_marker_signs'
    duplicate-id check — but this function doesn't trust that) upsert into
    the same db entry instead of duplicating it.

    An entry of `city` already in the db that this run's fragment no longer
    carries (a rejected node, or a sign deleted from the OTBM) is reported as
    `"stale"` but never removed: unlike an edge, a location holds curated
    fields, and a node rejected on one run is often a sign the user is
    halfway through fixing. Edges are the collection that gets replaced
    outright (see merge_travel_graph_into_catalog)."""
    by_id = {entry["id"]: i for i, entry in enumerate(catalog_locations)}
    report: Dict[str, str] = {}

    fragment_ids = {loc["id"] for loc in fragment_locations}
    for entry in catalog_locations:
        if city_ids.derive_city(entry["id"]) == city and entry["id"] not in fragment_ids:
            report[entry["id"]] = "stale"

    for loc in fragment_locations:
        existing_index = by_id.get(loc["id"])
        if existing_index is None:
            catalog_locations.append(dict(loc))
            by_id[loc["id"]] = len(catalog_locations) - 1
            report[loc["id"]] = "added"
            continue

        existing = catalog_locations[existing_index]
        merged = dict(loc)
        if "_todo" not in existing:
            for field in CURATED_LOCATION_FIELDS:
                if field in existing:
                    merged[field] = existing[field]
            merged.pop("_todo", None)
        catalog_locations[existing_index] = merged
        report[loc["id"]] = "updated"

    return report


def merge_travel_graph_into_catalog(
    catalog_travel_graph: List[Dict], fragment_travel_graph: List[Dict], city: str
) -> Dict[str, str]:
    """Replaces `city`'s slice of catalog_travel_graph in place with the fragment's
    edges — the fragment is the complete edge set for that city, so an edge
    missing from it stops existing in the db too.

    This is a replacement and not an upsert on purpose. Upserting is how 23
    edges no BFS ever produced (one of them citing `ROOK-HUNT-00015`, an id
    a digit too long that is not a POI) outlived the map they came from and
    ended up in a versioned catalog nobody could explain. An edge with even
    one foot in `city` belongs to this run's regeneration; edges wholly
    between other cities are left exactly as they are.

    Reports per unordered pair: `"added"`, `"updated"` (in the fragment,
    was already in the db) or `"removed"` (was in the db for this city, the
    fragment doesn't carry it). Always mechanical — no human curation lives
    on an edge, so tileCount is simply overwritten with the fresh value."""

    def _label(edge: Dict) -> str:
        return f"{edge['from']}<->{edge['to']}"

    def _touches_city(edge: Dict) -> bool:
        return city in (city_ids.derive_city(edge["from"]), city_ids.derive_city(edge["to"]))

    existing_pairs = {frozenset((e["from"], e["to"])) for e in catalog_travel_graph}
    fragment_pairs = {frozenset((e["from"], e["to"])) for e in fragment_travel_graph}
    report: Dict[str, str] = {}

    kept: List[Dict] = []
    for edge in catalog_travel_graph:
        if frozenset((edge["from"], edge["to"])) in fragment_pairs:
            continue  # re-appended below, with the fresh tileCount
        if _touches_city(edge):
            report[_label(edge)] = "removed"
            continue
        kept.append(edge)

    for edge in fragment_travel_graph:
        pair = frozenset((edge["from"], edge["to"]))
        report[_label(edge)] = "updated" if pair in existing_pairs else "added"
        kept.append(dict(edge))

    catalog_travel_graph[:] = kept
    return report


def merge_travel_fragment_into_catalog(db: Dict, fragment: Dict, city: str) -> Dict[str, Dict[str, str]]:
    return {
        "locations": merge_locations_into_catalog(db["locations"], fragment["locations"], city),
        "travelGraph": merge_travel_graph_into_catalog(db["travelGraph"], fragment["travelGraph"], city),
    }
