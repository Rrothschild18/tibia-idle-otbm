import pytest

import travel_graph as tg


# ======================================================
# Sign parsing
# ======================================================


def _dump(tiles):
    """tiles: list of (x, y, z, items) -> one feature per z, base (0, 0)."""
    by_z: dict = {}
    for x, y, z, items in tiles:
        by_z.setdefault(z, []).append({"x": x, "y": y, "items": items})
    return {
        "data": {
            "nodes": [{
                "features": [
                    {"x": 0, "y": 0, "z": z, "tiles": tile_list}
                    for z, tile_list in by_z.items()
                ]
            }]
        }
    }


def _sign_item(uid, text):
    return {"id": tg.SIGN_ITEM_ID, "uid": uid, "text": text}


def test_parse_marker_signs_accepts_a_well_formed_id_in_reserved_uid_range():
    dump = _dump([(1000, 2000, 7, [_sign_item(10001, "ROOK-HUNT-0001")])])

    locations, issues = tg.parse_marker_signs(dump)

    assert locations == [{"id": "ROOK-HUNT-0001", "type": "HUNT", "x": 1000, "y": 2000, "z": 7}]
    assert issues == []


def test_parse_marker_signs_ignores_uid_outside_reserved_range():
    dump = _dump([(1000, 2000, 7, [_sign_item(500, "ROOK-HUNT-0001")])])

    locations, issues = tg.parse_marker_signs(dump)

    assert locations == []
    assert issues == []


def test_parse_marker_signs_reports_legacy_format_without_tipo_segment():
    dump = _dump([(1000, 2000, 7, [_sign_item(10002, "ROOK-0002")])])

    locations, issues = tg.parse_marker_signs(dump)

    assert locations == []
    assert issues == [{"reason": "invalid-sign-format", "uid": 10002, "text": "ROOK-0002", "x": 1000, "y": 2000, "z": 7}]


def test_parse_marker_signs_rejects_five_digit_sequence_as_a_typo():
    # Real-world bug found live in ROOK.otbm: a sign typed with 5 digits
    # (instead of 4) used to slip through as "valid" and silently produced an
    # id nothing could ever resolve to.
    dump = _dump([(1000, 2000, 7, [_sign_item(10015, "ROOK-HUNT-00015")])])

    locations, issues = tg.parse_marker_signs(dump)

    assert locations == []
    assert issues == [{"reason": "invalid-sign-format", "uid": 10015, "text": "ROOK-HUNT-00015", "x": 1000, "y": 2000, "z": 7}]


def test_parse_marker_signs_rejects_sequence_with_fewer_than_four_digits():
    dump = _dump([(1000, 2000, 7, [_sign_item(10001, "ROOK-HUNT-1")])])

    locations, issues = tg.parse_marker_signs(dump)

    assert locations == []
    assert issues == [{"reason": "invalid-sign-format", "uid": 10001, "text": "ROOK-HUNT-1", "x": 1000, "y": 2000, "z": 7}]


def test_parse_marker_signs_accepts_every_currently_valid_four_digit_sequence():
    # Regression: the 12 sign ids already placed in ROOK.otbm today, all
    # 4 digits, must keep validating under the stricter regex.
    texts = [f"ROOK-HUNT-{n:04d}" for n in range(1, 13)]
    dump = _dump([(1000 + i, 2000, 7, [_sign_item(10001 + i, text)]) for i, text in enumerate(texts)])

    locations, issues = tg.parse_marker_signs(dump)

    assert issues == []
    assert [loc["id"] for loc in locations] == texts


def test_parse_marker_signs_ignores_non_sign_items_even_with_high_uid():
    dump = _dump([(1000, 2000, 7, [{"id": 2473, "uid": 64129}])])

    locations, issues = tg.parse_marker_signs(dump)

    assert locations == []
    assert issues == []


def test_parse_marker_signs_reports_a_second_sign_that_reuses_the_same_id():
    # Real-world case found in ROOK.otbm: two signs share a uid (a copy-paste
    # mistake in the map editor) and ended up with identical text too — only
    # the first becomes a location, the second is reported, never silently
    # duplicated downstream.
    dump = _dump([
        (1000, 2000, 7, [_sign_item(10006, "ROOK-HUNT-0006")]),
        (1213, 1119, 7, [_sign_item(10006, "ROOK-HUNT-0006")]),
    ])

    locations, issues = tg.parse_marker_signs(dump)

    assert len(locations) == 1
    assert locations[0]["x"] == 1000
    assert issues == [{"reason": "duplicate-sign-id", "uid": 10006, "text": "ROOK-HUNT-0006", "x": 1213, "y": 1119, "z": 7}]


def test_build_sign_location_derives_placeholder_display_name_and_flags_todo():
    entry = tg.build_sign_location({"id": "ROOK-DEPOT-001", "type": "DEPOT", "x": 1, "y": 2, "z": 7})

    assert entry["displayName"] == "Rook Depot 001"
    assert entry["_todo"]
    assert "huntId" not in entry


def test_build_sign_location_hunt_type_also_gets_a_hunt_id_placeholder():
    entry = tg.build_sign_location({"id": "ROOK-HUNT-001", "type": "HUNT", "x": 1, "y": 2, "z": 7})

    assert entry["huntId"] is None
    assert any("huntId" in note for note in entry["_todo"])


def test_build_sign_location_derives_city_with_no_status_for_a_real_city():
    entry = tg.build_sign_location({"id": "ROOK-DEPOT-001", "type": "DEPOT", "x": 1, "y": 2, "z": 7})

    assert entry["city"] == "ROOK"
    assert "status" not in entry


def test_build_sign_location_derives_test_status_for_the_test_city():
    entry = tg.build_sign_location({"id": "TEST-HUNT-0001", "type": "HUNT", "x": 1, "y": 2, "z": 7})

    assert entry["city"] == "TEST"
    assert entry["status"] == "test"


# ======================================================
# Walkability graph
# ======================================================


def _object_defs(flags_by_id):
    """A tabela de flags é `{id: {flag: valor}}` — sem o envelope `{"flags":...}`
    que o objectDefs do map.json carregava."""
    return {str(k): v for k, v in flags_by_id.items()}


def test_extract_tile_flags_excludes_marker_sign_items_from_flags():
    dump = _dump([(0, 0, 7, [_sign_item(10001, "ROOK-HUNT-001")])])
    # If the marker sign contributed flags, this tile would report unpass —
    # it must not, since marker signs never reach the real map.json.
    object_defs = _object_defs({tg.SIGN_ITEM_ID: {"unpass": True}})

    tiles = tg.extract_tile_flags(dump, object_defs)

    assert tiles == [{"x": 0, "y": 0, "z": 7, "unpass": False,
                      "isFloorTransition": False, "isLadder": False,
                      "floorchange": None}]


def test_extract_tile_flags_combines_ground_and_item_flags():
    dump = {
        "data": {"nodes": [{"features": [{
            "x": 0, "y": 0, "z": 7,
            "tiles": [{"x": 0, "y": 0, "tileid": 100, "items": [{"id": 200, "uid": 500}]}],
        }]}]}
    }
    object_defs = _object_defs({100: {"unpass": False}, 200: {"unpass": True}})

    tiles = tg.extract_tile_flags(dump, object_defs)

    assert tiles == [{"x": 0, "y": 0, "z": 7, "unpass": True,
                      "isFloorTransition": False, "isLadder": False,
                      "floorchange": None}]


def test_extract_tile_flags_takes_floorchange_from_an_item_on_the_tile():
    dump = {
        "data": {"nodes": [{"features": [{
            "x": 0, "y": 0, "z": 8,
            "tiles": [{"x": 5, "y": 5, "tileid": 100, "items": [{"id": 1951}]}],
        }]}]}
    }

    tiles = tg.extract_tile_flags(dump, _object_defs({}), {1951: "west"})

    assert tiles[0]["floorchange"] == "west"


def test_extract_tile_flags_reports_no_floorchange_when_items_xml_is_absent():
    # O fallback declarado de `_read_floorchange_items`: sem items.xml o grafo
    # perde ligações, mas nunca inventa uma.
    dump = {
        "data": {"nodes": [{"features": [{
            "x": 0, "y": 0, "z": 8,
            "tiles": [{"x": 5, "y": 5, "tileid": 100, "items": [{"id": 1951}]}],
        }]}]}
    }

    tiles = tg.extract_tile_flags(dump, _object_defs({}))

    assert tiles[0]["floorchange"] is None


def _tile(x, y, z, unpass=False, transition=False, ladder=False, floorchange=None):
    return {
        "x": x,
        "y": y,
        "z": z,
        "unpass": unpass,
        "isFloorTransition": transition,
        "isLadder": ladder,
        "floorchange": floorchange,
    }


# ======================================================
# floorchange — o que se ANDA (rampa/escada/buraco)
# ======================================================


def test_parse_floorchange_items_reads_single_ids_and_ranges():
    xml = """
    <items>
      <item id="1951" article="a" name="ramp">
        <attribute key="floorchange" value="west"/>
      </item>
      <item fromid="369" toid="371" article="a" name="trapdoor">
        <attribute key="floorchange" value="down"/>
      </item>
      <item id="2160" article="a" name="crystal coin"/>
    </items>
    """

    directions = tg.parse_floorchange_items(xml)

    assert directions[1951] == "west"
    assert directions[369] == directions[370] == directions[371] == "down"
    assert 2160 not in directions


def test_parse_floorchange_items_ignores_the_ladder_which_is_used_not_walked():
    # 1948 é "ladder" no items.xml e **não** tem floorchange: escada de mão se
    # usa, não se pisa. Quem a liga é `isFloorTransition` — é por isso que as
    # duas regras coexistem em vez de uma substituir a outra.
    xml = '<items><item id="1948" article="a" name="ladder"/></items>'

    assert tg.parse_floorchange_items(xml) == {}


def test_parse_floorchange_items_does_not_let_a_self_closing_item_steal_the_next_body():
    # O `items.xml` do Canary mistura `<item .../>` e `<item ...>...</item>`, e
    # 7541 ("earth", intransponível) precede 7542 ("ramp", east). Ler até o
    # próximo `</item>` dava o floorchange do 7542 ao 7541 — 804 dos 997 ids
    # lidos eram do item errado, e os 241 certos ficavam de fora. No mapa dos
    # orcs isso punha `east` em 15 pedras e em nenhuma rampa.
    xml = """
    <items>
      <item id="7541" name="earth"/>
      <item id="7542" article="a" name="ramp">
        <attribute key="floorchange" value="east"/>
      </item>
    </items>
    """

    assert tg.parse_floorchange_items(xml) == {7542: "east"}


def test_parse_ladder_items_does_not_let_a_self_closing_item_steal_the_next_body():
    xml = """
    <items>
      <item id="1967" article="a" name="wall"/>
      <item id="1968" article="a" name="ladder">
        <attribute key="type" value="ladder"/>
      </item>
    </items>
    """

    assert tg.parse_ladder_items(xml) == {1968}


def test_parse_ladder_items_reads_single_ids_and_ranges():
    xml = """
    <items>
      <item id="1948" article="a" name="ladder">
        <attribute key="type" value="ladder"/>
      </item>
      <item fromid="5542" toid="5543" article="a" name="rope ladder">
        <attribute key="type" value="ladder"/>
      </item>
      <item id="1949" article="a" name="depot">
        <attribute key="type" value="depot"/>
      </item>
    </items>
    """

    assert tg.parse_ladder_items(xml) == {1948, 5542, 5543}


def test_extract_tile_flags_marks_a_ladder_on_the_tile():
    dump = {
        "data": {"nodes": [{"features": [{
            "x": 0, "y": 0, "z": 8,
            "tiles": [{"x": 5, "y": 5, "tileid": 100, "items": [{"id": 1948}]}],
        }]}]}
    }

    tiles = tg.extract_tile_flags(dump, _object_defs({}), ladder_ids={1948})

    assert tiles[0]["isLadder"] is True


def test_extract_tile_flags_reports_no_ladder_when_items_xml_is_absent():
    dump = {
        "data": {"nodes": [{"features": [{
            "x": 0, "y": 0, "z": 8,
            "tiles": [{"x": 5, "y": 5, "tileid": 100, "items": [{"id": 1948}]}],
        }]}]}
    }

    tiles = tg.extract_tile_flags(dump, _object_defs({}))

    assert tiles[0]["isLadder"] is False


def test_build_walkable_graph_ramp_connects_one_tile_over_and_one_floor_up():
    # A rampa encontrada ao lado da placa de ROOK-HUNT-0016: exatamente o caso
    # que a ponte do mesmo (x, y) não consegue expressar.
    tiles = [_tile(5, 5, 8, floorchange="west"), _tile(4, 5, 7)]

    graph = tg.build_walkable_graph(tiles)

    assert graph[(5, 5, 8)] == {(4, 5, 7)}
    assert (5, 5, 8) in graph[(4, 5, 7)]


def test_build_walkable_graph_hole_connects_straight_down():
    tiles = [_tile(5, 5, 7, floorchange="down"), _tile(5, 5, 8)]

    graph = tg.build_walkable_graph(tiles)

    assert graph[(5, 5, 7)] == {(5, 5, 8)}


def test_build_walkable_graph_alt_variants_step_two_tiles_not_one():
    # São escadas de largura dupla (`*_EX` no TFS), não variantes de sprite das
    # mesmas duas direções: o degrau de cima fica dois tiles adiante.
    tiles = [
        _tile(0, 0, 8, floorchange="southalt"), _tile(0, 1, 7), _tile(0, 2, 7),
        _tile(9, 9, 8, floorchange="eastalt"), _tile(10, 9, 7), _tile(11, 9, 7),
    ]

    graph = tg.build_walkable_graph(tiles)

    assert graph[(0, 0, 8)] == {(0, 2, 7)}
    assert graph[(9, 9, 8)] == {(11, 9, 7)}


def test_build_walkable_graph_floorchange_into_a_blocked_tile_connects_nothing():
    tiles = [_tile(5, 5, 8, floorchange="west"), _tile(4, 5, 7, unpass=True)]

    graph = tg.build_walkable_graph(tiles)

    assert graph[(5, 5, 8)] == set()


def test_build_walkable_graph_tiles_without_the_floorchange_key_still_work():
    # Um chamador que não passou `items.xml` continua valendo: sem a chave, o
    # comportamento é o de antes desta regra existir.
    tiles = [
        {"x": 0, "y": 0, "z": 7, "unpass": False, "isFloorTransition": False},
        {"x": 1, "y": 0, "z": 7, "unpass": False, "isFloorTransition": False},
    ]

    graph = tg.build_walkable_graph(tiles)

    assert graph[(0, 0, 7)] == {(1, 0, 7)}


def test_build_walkable_graph_excludes_unpass_tiles():
    tiles = [_tile(0, 0, 7), _tile(1, 0, 7, unpass=True)]

    graph = tg.build_walkable_graph(tiles)

    assert (1, 0, 7) not in graph
    assert graph[(0, 0, 7)] == set()


def test_build_walkable_graph_connects_diagonal_neighbors_at_same_cost():
    tiles = [_tile(0, 0, 7), _tile(1, 1, 7)]

    graph = tg.build_walkable_graph(tiles)

    assert (1, 1, 7) in graph[(0, 0, 7)]
    assert (0, 0, 7) in graph[(1, 1, 7)]


def test_build_walkable_graph_floor_transition_without_a_ladder_drops_straight_down():
    # Buraco/alçapão: quem cai desce na mesma coluna. Nunca para z-1 — subir
    # sem escada é o que a regra antiga inventava.
    tiles = [
        _tile(0, 0, 7, transition=True),
        _tile(0, 0, 6),
        _tile(0, 0, 8),
    ]

    graph = tg.build_walkable_graph(tiles)

    assert graph[(0, 0, 7)] == {(0, 0, 8)}
    assert (0, 0, 7) in graph[(0, 0, 8)]


def test_build_walkable_graph_ladder_climbs_one_tile_south_and_one_floor_up():
    # `moveUpstairs()` do Canary: z -= 1 e depois o offset de DIRECTION_SOUTH.
    # O topo da escada não é a mesma coluna — é o tile ao sul dela.
    tiles = [
        _tile(0, 0, 8, transition=True, ladder=True),
        _tile(0, 0, 7),
        _tile(0, 1, 7),
    ]

    graph = tg.build_walkable_graph(tiles)

    assert graph[(0, 0, 8)] == {(0, 1, 7)}
    assert (0, 0, 8) in graph[(0, 1, 7)]


def test_build_walkable_graph_ladder_with_a_blocked_landing_connects_nothing():
    tiles = [
        _tile(0, 0, 8, transition=True, ladder=True),
        _tile(0, 1, 7, unpass=True),
    ]

    graph = tg.build_walkable_graph(tiles)

    assert graph[(0, 0, 8)] == set()


def test_build_walkable_graph_transition_tile_only_bridges_walkable_neighbor_floor():
    tiles = [
        _tile(0, 0, 7, transition=True),
        _tile(0, 0, 8, unpass=True),
    ]

    graph = tg.build_walkable_graph(tiles)

    assert graph[(0, 0, 7)] == set()


# ======================================================
# Tile distances / travelGraph
# ======================================================


def _line_graph(length):
    """A straight line of tiles (0,0,7) .. (length-1, 0, 7), each connected
    to its immediate neighbor only."""
    graph = {}
    for i in range(length):
        neighbors = set()
        if i > 0:
            neighbors.add((i - 1, 0, 7))
        if i < length - 1:
            neighbors.add((i + 1, 0, 7))
        graph[(i, 0, 7)] = neighbors
    return graph


def test_tile_distances_finds_every_target_and_stops_early():
    graph = _line_graph(10)

    distances, _ = tg.tile_distances_and_prev(graph, {(0, 0, 7): 0}, {(3, 0, 7), (5, 0, 7)})

    assert distances == {(3, 0, 7): 3, (5, 0, 7): 5}


def test_tile_distances_unreachable_target_is_simply_absent():
    graph = {(0, 0, 7): set(), (5, 5, 7): set()}

    distances, _ = tg.tile_distances_and_prev(graph, {(0, 0, 7): 0}, {(5, 5, 7)})

    assert distances == {}


def test_tile_distances_counts_the_cost_of_entering_at_each_source():
    # Seeded costs are the only non-uniform part of the search: entering at
    # tile 4 already costs 2, so tile 6 is 2 + 2 hops, not 2.
    graph = _line_graph(10)

    distances, _ = tg.tile_distances_and_prev(graph, {(0, 0, 7): 0, (4, 0, 7): 2}, {(6, 0, 7)})

    assert distances == {(6, 0, 7): 4}


def test_tile_distances_takes_the_cheapest_source_not_the_first_one():
    graph = _line_graph(10)

    distances, _ = tg.tile_distances_and_prev(graph, {(0, 0, 7): 0, (5, 0, 7): 3}, {(6, 0, 7)})

    assert distances == {(6, 0, 7): 4}


def test_approach_costs_is_just_the_own_tile_when_there_is_no_reach():
    graph = _line_graph(4)

    assert tg.approach_costs((2, 0, 7), graph, 0) == {(2, 0, 7): 0}


def test_approach_costs_is_empty_when_the_tile_itself_is_not_walkable():
    graph = _line_graph(4)

    assert tg.approach_costs((9, 9, 7), graph, 0) == {}


def test_approach_costs_charges_each_reachable_tile_its_own_distance():
    graph = _line_graph(6)

    costs = tg.approach_costs((2, 0, 7), graph, 2)

    assert costs == {(0, 0, 7): 2, (1, 0, 7): 1, (2, 0, 7): 0, (3, 0, 7): 1, (4, 0, 7): 2}


def _location(loc_id, x, y, z=7, loc_type="HUNT"):
    return {"id": loc_id, "x": x, "y": y, "z": z, "type": loc_type}


def test_build_travel_graph_produces_one_edge_per_reachable_pair_symmetrically():
    graph = _line_graph(10)
    locations = [_location("A", 0, 0), _location("B", 3, 0), _location("C", 5, 0)]

    edges = tg.build_travel_graph(graph, locations)

    by_pair = {frozenset((e["from"], e["to"])): e["tileCount"] for e in edges}
    assert len(edges) == 3
    assert by_pair[frozenset(("A", "B"))] == 3
    assert by_pair[frozenset(("B", "C"))] == 2
    assert by_pair[frozenset(("A", "C"))] == 5


def test_build_travel_graph_disconnected_pair_produces_no_edge():
    graph = {(0, 0, 7): set(), (9, 9, 7): set()}
    locations = [_location("A", 0, 0), _location("B", 9, 9)]

    edges = tg.build_travel_graph(graph, locations)

    assert edges == []


def test_build_travel_graph_distance_is_the_real_shortest_path_not_a_hub_sum():
    # A-B and A-C are both 1 hop through the shared hub A, but B and C are
    # NOT directly connected — their only path is the real graph edge
    # A-B + A-C (distance 2), not some other value a hub-sum shortcut might
    # produce. Proves each pair gets its own independent search.
    graph = {
        (0, 0, 7): {(1, 0, 7), (2, 0, 7)},
        (1, 0, 7): {(0, 0, 7)},
        (2, 0, 7): {(0, 0, 7)},
    }
    locations = [_location("A", 0, 0), _location("B", 1, 0), _location("C", 2, 0)]

    edges = tg.build_travel_graph(graph, locations)
    by_pair = {frozenset((e["from"], e["to"])): e["tileCount"] for e in edges}

    assert by_pair[frozenset(("A", "B"))] == 1
    assert by_pair[frozenset(("A", "C"))] == 1
    assert by_pair[frozenset(("B", "C"))] == 2


def test_build_travel_graph_orients_every_edge_from_lower_id_to_higher():
    graph = _line_graph(10)
    locations = [_location("C", 5, 0), _location("A", 0, 0), _location("B", 3, 0)]

    edges = tg.build_travel_graph(graph, locations)

    assert all(e["from"] < e["to"] for e in edges)


def test_build_travel_graph_emits_no_self_edge_and_no_duplicate_pair():
    graph = _line_graph(10)
    locations = [_location("A", 0, 0), _location("B", 3, 0), _location("C", 5, 0)]

    edges = tg.build_travel_graph(graph, locations)

    assert all(e["from"] != e["to"] for e in edges)
    pairs = [frozenset((e["from"], e["to"])) for e in edges]
    assert len(pairs) == len(set(pairs))


def test_build_travel_graph_two_locations_on_the_same_tile_are_zero_tiles_apart():
    # Two NPCs behind the same tavern counter are two destinations, not one:
    # a tileCount of 0 is the map's truth, not an error to filter out. A
    # polilinha repete o tile porque ela vai de pino a pino, e os dois pinos
    # entram mesmo sendo o mesmo tile (ver _without_repeats).
    graph = _line_graph(4)
    locations = [_location("NORMA", 1, 0), _location("AMBER", 1, 0)]

    edges = tg.build_travel_graph(graph, locations)

    assert edges == [{"from": "AMBER", "to": "NORMA", "tileCount": 0,
                      "path": [1, 0, 7, 1, 0, 7]}]


def test_build_travel_graph_co_located_pair_still_reaches_the_rest_of_the_city():
    graph = _line_graph(6)
    locations = [_location("NORMA", 1, 0), _location("AMBER", 1, 0), _location("TEMPLE", 4, 0)]

    edges = tg.build_travel_graph(graph, locations)
    by_pair = {frozenset((e["from"], e["to"])): e["tileCount"] for e in edges}

    assert by_pair[frozenset(("AMBER", "NORMA"))] == 0
    assert by_pair[frozenset(("NORMA", "TEMPLE"))] == 3
    assert by_pair[frozenset(("AMBER", "TEMPLE"))] == 3


def test_build_travel_graph_adjacent_locations_are_one_tile_apart():
    graph = _line_graph(4)
    locations = [_location("A", 1, 0), _location("B", 2, 0)]

    edges = tg.build_travel_graph(graph, locations)

    assert edges == [{"from": "A", "to": "B", "tileCount": 1,
                      "path": [1, 0, 7, 2, 0, 7]}]


def test_build_travel_graph_edges_are_sorted_for_a_stable_diff():
    graph = _line_graph(10)
    locations = [_location("C", 5, 0), _location("A", 0, 0), _location("B", 3, 0)]

    edges = tg.build_travel_graph(graph, locations)

    assert [(e["from"], e["to"]) for e in edges] == sorted((e["from"], e["to"]) for e in edges)


def test_build_travel_graph_location_on_an_unwalkable_tile_gets_no_edge():
    # Not an error here — apply_graph_rejections is what turns a node with
    # no edge into a reported rejection.
    graph = _line_graph(4)
    locations = [_location("A", 1, 0), _location("WALLED", 99, 99)]

    edges = tg.build_travel_graph(graph, locations)

    assert edges == []


def _counter_graph():
    """Rookgaard's shop shape: the shopkeeper's tile (0) and one more behind
    the counter (1) are walkable but walled off; the counter itself (2) is
    `unpass` and absent from the graph; the street picks back up at 3."""
    graph = {(0, 0, 7): {(1, 0, 7)}, (1, 0, 7): {(0, 0, 7)}}
    for i in range(3, 8):
        graph[(i, 0, 7)] = {(j, 0, 7) for j in (i - 1, i + 1) if 3 <= j <= 7}
    return graph


def test_build_travel_graph_reaches_an_npc_across_a_counter():
    # The story this ticket exists for: Norma stands behind the bakery
    # counter, so her own tile is a two-tile pocket. Without a reach she is
    # not a destination at all and "viajar até a Norma" cannot be expressed.
    graph = _counter_graph()
    locations = [_location("ROOK-NPC-norma", 0, 0, loc_type="NPC"),
                 _location("ROOK-TEMPLE-0001", 5, 0, loc_type="TEMPLE")]

    edges = tg.build_travel_graph(graph, locations, npc_reach=5)

    # 3 tiles from Norma across the counter to the near side of the street,
    # then 2 more up it — the counter tile itself is never walked through.
    # A polilinha sai do tile da Norma e chega no do templo. O balcão é
    # atravessado como o segmento reto que o custo de aproximação descreve.
    assert edges == [{"from": "ROOK-NPC-norma", "to": "ROOK-TEMPLE-0001", "tileCount": 5,
                      "path": [0, 0, 7, 5, 0, 7]}]


def test_build_travel_graph_npc_reach_does_not_shorten_an_open_air_npc():
    # An NPC standing in the street enters the graph on its own tile for 0,
    # so the reach costs its distances nothing. Seeding every tile within
    # reach at 0 instead would quietly shave 5 tiles off every NPC in town.
    graph = _line_graph(10)
    locations = [_location("ROOK-NPC-cipfried", 2, 0, loc_type="NPC"),
                 _location("ROOK-TEMPLE-0001", 8, 0, loc_type="TEMPLE")]

    edges = tg.build_travel_graph(graph, locations, npc_reach=5)

    assert edges == [{"from": "ROOK-NPC-cipfried", "to": "ROOK-TEMPLE-0001", "tileCount": 6,
                      "path": [2, 0, 7, 8, 0, 7]}]


def test_build_travel_graph_reach_applies_to_npcs_only_not_to_signs():
    # A sign is placed by hand on a walkable tile. One that ended up walled
    # in is a map bug for the rejection report to surface, not something to
    # paper over with a reach.
    graph = _counter_graph()
    locations = [_location("ROOK-HUNT-0012", 0, 0, loc_type="HUNT"),
                 _location("ROOK-TEMPLE-0001", 5, 0, loc_type="TEMPLE")]

    edges = tg.build_travel_graph(graph, locations, npc_reach=5)

    assert edges == []


def test_build_travel_graph_npc_beyond_the_reach_still_gets_no_edge():
    graph = _counter_graph()
    locations = [_location("ROOK-NPC-loui", 0, 0, loc_type="NPC"),
                 _location("ROOK-TEMPLE-0001", 5, 0, loc_type="TEMPLE")]

    edges = tg.build_travel_graph(graph, locations, npc_reach=1)

    assert edges == []


# ======================================================
# NPC XML parsing
# ======================================================


_NPC_XML = """<?xml version="1.0"?>
<npcs>
\t<npc centerx="1151" centery="1130" centerz="7" radius="1">
\t\t<npc name="Obi" x="0" y="0" z="7" spawntime="60" />
\t</npc>
\t<npc centerx="1146" centery="1106" centerz="8" radius="1">
\t\t<npc name="Amber" x="0" y="0" z="8" spawntime="60" />
\t</npc>
</npcs>"""


def test_parse_npc_xml_combines_center_and_inner_offset():
    npcs = tg.parse_npc_xml(_NPC_XML)

    assert npcs == [
        {"name": "Obi", "x": 1151, "y": 1130, "z": 7},
        {"name": "Amber", "x": 1146, "y": 1106, "z": 8},
    ]


def test_slugify_handles_apostrophes_and_spaces():
    assert tg.slugify("Lee'Delle") == "lee-delle"
    assert tg.slugify("An Orc Guard") == "an-orc-guard"


def test_match_npc_lua_filename_matches_case_insensitively():
    assert tg.match_npc_lua_filename("Obi", ["obi.lua", "robin.lua"]) == "obi.lua"


def test_match_npc_lua_filename_returns_none_when_unmatched():
    assert tg.match_npc_lua_filename("Nobody", ["obi.lua"]) is None


def test_match_npc_lua_filename_matches_underscore_separated_canary_filenames():
    # Canary's own filenames use "_" between words (an_orc_guard.lua), while
    # slugify()/location ids use "-" — matching must bridge the two.
    assert tg.match_npc_lua_filename("An Orc Guard", ["an_orc_guard.lua"]) == "an_orc_guard.lua"


# ======================================================
# Lua shop parsing
# ======================================================


_OBI_LUA = """
local internalNpcName = "Obi"
npcConfig.shop = {
\t{ itemName = "axe", clientId = 3274, buy = 20, sell = 7 },
\t{ itemName = "bone club", clientId = 3337, sell = 5 },
\t{ itemName = "dagger", clientId = 3267, buy = 5 },
}
npcType.onBuyItem = function() end
"""


def test_parse_npc_shop_lua_extracts_items_with_optional_buy_sell():
    entries = tg.parse_npc_shop_lua(_OBI_LUA)

    assert entries == [
        {"itemName": "axe", "itemId": 3274, "buy": 20, "sell": 7},
        {"itemName": "bone club", "itemId": 3337, "sell": 5},
        {"itemName": "dagger", "itemId": 3267, "buy": 5},
    ]


_XODET_LUA = """
local internalNpcName = "Xodet"
local itemsTable = {
\t["potions"] = {
\t\t{ itemName = "empty potion flask", clientId = 283, sell = 5 },
\t\t{ itemName = "health potion", clientId = 266, buy = 50 },
\t},
\t["runes"] = {
\t\t{ itemName = "sudden death rune", clientId = 3155, buy = 108 },
\t},
}

npcConfig.shop = {}
for _, categoryTable in pairs(itemsTable) do
\tfor _, itemTable in ipairs(categoryTable) do
\t\ttable.insert(npcConfig.shop, itemTable)
\tend
end
"""


def test_parse_npc_shop_lua_reads_the_items_table_filled_by_a_loop():
    entries = tg.parse_npc_shop_lua(_XODET_LUA)

    assert entries == [
        {"itemName": "empty potion flask", "itemId": 283, "sell": 5},
        {"itemName": "health potion", "itemId": 266, "buy": 50},
        {"itemName": "sudden death rune", "itemId": 3155, "buy": 108},
    ]


def test_parse_npc_shop_lua_returns_none_when_no_shop_table():
    assert tg.parse_npc_shop_lua('local x = "no shop here"') is None


# ======================================================
# NPC location assembly
# ======================================================


def test_build_npc_location_includes_shop_when_present():
    npc = {"name": "Obi", "x": 1151, "y": 1130, "z": 7}
    shop = [{"itemName": "axe", "itemId": 3274, "buy": 20, "sell": 7}]

    entry = tg.build_npc_location(npc, "ROOK", shop)

    assert entry == {
        "id": "ROOK-NPC-obi",
        "type": "NPC",
        "x": 1151, "y": 1130, "z": 7,
        "displayName": "Obi",
        "city": "ROOK",
        "shop": shop,
    }


def test_build_npc_location_omits_shop_field_when_none():
    entry = tg.build_npc_location({"name": "Nobody", "x": 0, "y": 0, "z": 7}, "ROOK", None)

    assert "shop" not in entry


def test_build_npc_location_uppercases_city_and_type_but_keeps_slug_lowercase():
    # "An Orc Guard" -> slug "an-orc-guard", city/type upper: ROOK-NPC-an-orc-guard
    entry = tg.build_npc_location({"name": "An Orc Guard", "x": 0, "y": 0, "z": 7}, "rook", None)

    assert entry["id"] == "ROOK-NPC-an-orc-guard"


def test_build_npc_location_derives_test_status_for_the_test_city():
    entry = tg.build_npc_location({"name": "Nobody", "x": 0, "y": 0, "z": 7}, "TEST", None)

    assert entry["city"] == "TEST"
    assert entry["status"] == "test"


def test_build_npc_location_omits_status_for_a_real_city():
    entry = tg.build_npc_location({"name": "Obi", "x": 0, "y": 0, "z": 7}, "ROOK", None)

    assert "status" not in entry


def test_build_npc_locations_flags_unmatched_npc_names_without_dropping_the_location():
    npcs = [{"name": "Obi", "x": 1, "y": 1, "z": 7}, {"name": "Nobody", "x": 2, "y": 2, "z": 7}]
    facts = {"Obi": {"shop": [{"itemName": "axe", "itemId": 3274, "sell": 7}], "services": []}}

    locations, unmatched = tg.build_npc_locations(npcs, "ROOK", facts)

    assert [loc["id"] for loc in locations] == ["ROOK-NPC-obi", "ROOK-NPC-nobody"]
    assert "shop" in locations[0]
    assert "shop" not in locations[1]
    assert unmatched == ["Nobody"]


def test_build_npc_locations_does_not_warn_for_a_matched_file_with_no_shop_table():
    # "Trainer" matched a .lua file, but that file has no npcConfig.shop
    # table at all — expected (not every NPC sells things), not a warning.
    npcs = [{"name": "Trainer", "x": 1, "y": 1, "z": 7}]
    facts = {"Trainer": {"shop": None, "services": []}}

    locations, unmatched = tg.build_npc_locations(npcs, "ROOK", facts)

    assert "shop" not in locations[0]
    assert unmatched == []


# ======================================================
# Fragment assembly
# ======================================================


def test_build_travel_fragment_carries_locations_and_edges_under_their_db_keys():
    locations = [{"id": "ROOK-HUNT-001"}, {"id": "ROOK-NPC-obi"}]
    edges = [{"from": "ROOK-HUNT-001", "to": "ROOK-TEMPLE-001", "tileCount": 10}]

    fragment = tg.build_travel_fragment(locations, edges)

    assert fragment == {"locations": locations, "travelGraph": edges}


# ======================================================
# Rejecting nodes with no way in
# ======================================================


def _poi(loc_id, x=1, y=2, z=7, loc_type="HUNT"):
    return {"id": loc_id, "type": loc_type, "x": x, "y": y, "z": z}


def _edge(a, b, tile_count=10):
    return {"from": a, "to": b, "tileCount": tile_count}


def test_apply_graph_rejections_keeps_a_fully_connected_city_intact():
    locations = [_poi("ROOK-HUNT-0001"), _poi("ROOK-TEMPLE-0001")]
    edges = [_edge("ROOK-HUNT-0001", "ROOK-TEMPLE-0001")]

    kept_locations, kept_edges, rejections = tg.apply_graph_rejections(locations, edges)

    assert kept_locations == locations
    assert kept_edges == edges
    assert rejections == []


def test_apply_graph_rejections_rejects_a_poi_with_no_edge_and_carries_its_coordinate():
    walled_in = _poi("ROOK-HUNT-0012", x=1178, y=990, z=12)
    locations = [_poi("ROOK-HUNT-0001"), _poi("ROOK-TEMPLE-0001"), walled_in]
    edges = [_edge("ROOK-HUNT-0001", "ROOK-TEMPLE-0001")]

    kept_locations, _, rejections = tg.apply_graph_rejections(locations, edges)

    assert walled_in not in kept_locations
    assert rejections == [{"reason": "poi-without-edge", "id": "ROOK-HUNT-0012", "type": "HUNT",
                           "x": 1178, "y": 990, "z": 12}]


def test_apply_graph_rejections_drops_an_edge_citing_an_id_that_is_not_a_poi():
    # ROOK-HUNT-00015: a sign id typed with one digit too many. It has no
    # coordinate anywhere — the only trace of it is the edges naming it.
    locations = [_poi("ROOK-HUNT-0001"), _poi("ROOK-TEMPLE-0001")]
    phantom = _edge("ROOK-HUNT-0001", "ROOK-HUNT-00015", 40)
    edges = [_edge("ROOK-HUNT-0001", "ROOK-TEMPLE-0001"), phantom]

    kept_locations, kept_edges, rejections = tg.apply_graph_rejections(locations, edges)

    assert phantom not in kept_edges
    assert kept_locations == locations
    assert rejections == [{"reason": "edge-without-poi", "id": "ROOK-HUNT-00015", "edges": [phantom]}]


def test_apply_graph_rejections_cascades_when_a_phantom_edge_was_a_pois_only_link():
    # Degree is counted after the phantom edges are gone, so a POI whose
    # only edge pointed at a non-existent id is rejected too, not kept on
    # the strength of an edge that is about to disappear.
    lonely = _poi("ROOK-HUNT-0004", x=50, y=60, z=7)
    locations = [_poi("ROOK-HUNT-0001"), _poi("ROOK-TEMPLE-0001"), lonely]
    edges = [_edge("ROOK-HUNT-0001", "ROOK-TEMPLE-0001"),
             _edge("ROOK-HUNT-0004", "ROOK-HUNT-00015")]

    kept_locations, kept_edges, rejections = tg.apply_graph_rejections(locations, edges)

    assert lonely not in kept_locations
    assert len(kept_edges) == 1
    assert [r["id"] for r in rejections] == ["ROOK-HUNT-0004", "ROOK-HUNT-00015"]


def test_apply_graph_rejections_reports_a_hunt_map_with_no_poi_by_id_and_name():
    locations = [_poi("ROOK-HUNT-0001"), _poi("ROOK-TEMPLE-0001")]
    edges = [_edge("ROOK-HUNT-0001", "ROOK-TEMPLE-0001")]
    hunts = [{"id": "ROOK-HUNT-0001", "name": "rats-sewers"},
             {"id": "ROOK-HUNT-0018", "name": "bugs-rookguard"}]

    _, _, rejections = tg.apply_graph_rejections(locations, edges, hunts)

    assert rejections == [{"reason": "hunt-without-poi", "id": "ROOK-HUNT-0018",
                           "name": "bugs-rookguard"}]


def test_apply_graph_rejections_does_not_report_a_hunt_twice_when_its_poi_was_rejected():
    # ROOK-HUNT-0012 has a sign — it's just walled in. "POI with no edge,
    # here is its coordinate" is the actionable line; adding "hunt with no
    # POI" on top would send the user looking for a sign that exists.
    locations = [_poi("ROOK-HUNT-0001"), _poi("ROOK-TEMPLE-0001"), _poi("ROOK-HUNT-0012")]
    edges = [_edge("ROOK-HUNT-0001", "ROOK-TEMPLE-0001")]
    hunts = [{"id": "ROOK-HUNT-0012", "name": "orcs-cave-rookguard"}]

    _, _, rejections = tg.apply_graph_rejections(locations, edges, hunts)

    assert [r["reason"] for r in rejections] == ["poi-without-edge"]


def test_apply_graph_rejections_orders_by_case_then_id_for_a_clean_diff():
    locations = [_poi("ROOK-HUNT-0001"), _poi("ROOK-TEMPLE-0001"),
                 _poi("ROOK-HUNT-0012"), _poi("ROOK-HUNT-0004")]
    edges = [_edge("ROOK-HUNT-0001", "ROOK-TEMPLE-0001"),
             _edge("ROOK-HUNT-0001", "ROOK-HUNT-00015")]
    hunts = [{"id": "ROOK-HUNT-0018", "name": "bugs"}, {"id": "ROOK-HUNT-0010", "name": "bears"}]

    _, _, rejections = tg.apply_graph_rejections(locations, edges, hunts)

    assert [(r["reason"], r["id"]) for r in rejections] == [
        ("poi-without-edge", "ROOK-HUNT-0004"),
        ("poi-without-edge", "ROOK-HUNT-0012"),
        ("edge-without-poi", "ROOK-HUNT-00015"),
        ("hunt-without-poi", "ROOK-HUNT-0010"),
        ("hunt-without-poi", "ROOK-HUNT-0018"),
    ]


def test_apply_graph_rejections_leaves_every_surviving_node_with_a_location_and_an_edge():
    # The two invariants the emitted fragment must hold, asserted together:
    # no edge cites an id that isn't a location, and no location is isolated.
    locations = [_poi("ROOK-HUNT-0001"), _poi("ROOK-TEMPLE-0001"),
                 _poi("ROOK-HUNT-0012"), _poi("ROOK-NPC-obi", loc_type="NPC")]
    edges = [_edge("ROOK-HUNT-0001", "ROOK-TEMPLE-0001"),
             _edge("ROOK-HUNT-0001", "ROOK-HUNT-00015")]

    kept_locations, kept_edges, _ = tg.apply_graph_rejections(locations, edges)

    kept_ids = {loc["id"] for loc in kept_locations}
    cited = {e["from"] for e in kept_edges} | {e["to"] for e in kept_edges}
    assert cited <= kept_ids
    assert kept_ids <= cited


def test_apply_graph_rejections_keeps_a_zero_tile_count_edge_as_a_real_link():
    # Two NPCs on the same tile: degree 1 each, and that is a real way in.
    locations = [_poi("ROOK-NPC-amber", loc_type="NPC"), _poi("ROOK-NPC-norma", loc_type="NPC")]
    edges = [_edge("ROOK-NPC-amber", "ROOK-NPC-norma", 0)]

    kept_locations, kept_edges, rejections = tg.apply_graph_rejections(locations, edges)

    assert kept_locations == locations
    assert kept_edges == edges
    assert rejections == []


def test_format_rejection_report_names_the_case_and_what_to_do_for_each():
    rejections = [
        {"reason": "poi-without-edge", "id": "ROOK-HUNT-0012", "type": "HUNT",
         "x": 1178, "y": 990, "z": 12},
        {"reason": "edge-without-poi", "id": "ROOK-HUNT-00015",
         "edges": [{"from": "ROOK-HUNT-0001", "to": "ROOK-HUNT-00015", "tileCount": 40}]},
        {"reason": "hunt-without-poi", "id": "ROOK-HUNT-0018", "name": "bugs-rookguard"},
    ]

    report = tg.format_rejection_report(rejections, "ROOK")

    assert "ROOK-HUNT-0012" in report
    assert "1178" in report and "990" in report
    assert "ROOK-HUNT-0001<->ROOK-HUNT-00015" in report
    assert "bugs-rookguard" in report
    # Each case carries its own instruction, so a line is actionable alone.
    assert "placa" in report
    assert report == tg.format_rejection_report(rejections, "ROOK")


def test_format_rejection_report_says_so_when_nothing_was_rejected():
    report = tg.format_rejection_report([], "ROOK")

    assert "ROOK" in report
    assert report.strip().endswith("Nenhum nó rejeitado.")


# ======================================================
# db.json merge — locations
# ======================================================


def test_merge_locations_into_catalog_appends_a_new_location_as_a_draft():
    catalog_locations = []
    fragment = [tg.build_sign_location({"id": "ROOK-HUNT-001", "type": "HUNT", "x": 1, "y": 2, "z": 7})]

    report = tg.merge_locations_into_catalog(catalog_locations, fragment, "ROOK")

    assert report == {"ROOK-HUNT-001": "added"}
    assert catalog_locations == fragment


def test_merge_locations_into_catalog_never_duplicates_when_fragment_has_a_repeated_id():
    # Defensive: even if a fragment somehow carries the same id twice, the
    # second occurrence must upsert into the same db entry, not append a
    # second row (parse_marker_signs already prevents this upstream, but
    # this function shouldn't trust that).
    catalog_locations = []
    fragment = [
        {"id": "ROOK-HUNT-0006", "type": "HUNT", "x": 1, "y": 1, "z": 7},
        {"id": "ROOK-HUNT-0006", "type": "HUNT", "x": 2, "y": 2, "z": 7},
    ]

    tg.merge_locations_into_catalog(catalog_locations, fragment, "ROOK")

    assert len(catalog_locations) == 1
    assert catalog_locations[0]["x"] == 2


def test_merge_locations_into_catalog_preserves_curated_display_name_but_updates_position():
    curated = {"id": "ROOK-HUNT-001", "type": "HUNT", "x": 1, "y": 2, "z": 7, "displayName": "Rat Sewers Entrance"}
    catalog_locations = [curated]
    fragment = [{"id": "ROOK-HUNT-001", "type": "HUNT", "x": 999, "y": 888, "z": 7,
                 "displayName": "Rook Hunt 001", "_todo": ["confirmar displayName"]}]

    report = tg.merge_locations_into_catalog(catalog_locations, fragment, "ROOK")

    assert report == {"ROOK-HUNT-001": "updated"}
    assert catalog_locations[0]["displayName"] == "Rat Sewers Entrance"
    assert catalog_locations[0]["x"] == 999
    assert "_todo" not in catalog_locations[0]


def test_merge_locations_into_catalog_preserves_curated_hunt_id_but_updates_position():
    curated = {"id": "ROOK-HUNT-001", "type": "HUNT", "x": 1, "y": 2, "z": 7,
               "displayName": "Rat Sewers Entrance", "huntId": "ROOK-0002"}
    catalog_locations = [curated]
    fragment = [{"id": "ROOK-HUNT-001", "type": "HUNT", "x": 999, "y": 888, "z": 7,
                 "displayName": "Rook Hunt 001", "huntId": None, "_todo": ["associar huntId"]}]

    tg.merge_locations_into_catalog(catalog_locations, fragment, "ROOK")

    assert catalog_locations[0]["huntId"] == "ROOK-0002"
    assert catalog_locations[0]["displayName"] == "Rat Sewers Entrance"
    assert catalog_locations[0]["x"] == 999


def test_merge_locations_into_catalog_keeps_todo_flag_while_still_uncurated():
    draft = {"id": "ROOK-HUNT-001", "type": "HUNT", "x": 1, "y": 2, "z": 7,
              "displayName": "Rook Hunt 001", "_todo": ["confirmar displayName"]}
    catalog_locations = [dict(draft)]
    fragment = [{"id": "ROOK-HUNT-001", "type": "HUNT", "x": 5, "y": 6, "z": 7,
                 "displayName": "Rook Hunt 001", "_todo": ["confirmar displayName"]}]

    tg.merge_locations_into_catalog(catalog_locations, fragment, "ROOK")

    assert catalog_locations[0]["_todo"] == ["confirmar displayName"]
    assert catalog_locations[0]["x"] == 5


def test_merge_locations_into_catalog_upserts_npc_shop_mechanically_with_no_curation():
    catalog_locations = [{"id": "rook-npc-obi", "type": "NPC", "x": 1, "y": 1, "z": 7,
                      "displayName": "Obi", "shop": []}]
    fragment = [{"id": "rook-npc-obi", "type": "NPC", "x": 1, "y": 1, "z": 7,
                 "displayName": "Obi", "shop": [{"itemName": "axe", "itemId": 3274, "sell": 7}]}]

    tg.merge_locations_into_catalog(catalog_locations, fragment, "ROOK")

    assert catalog_locations[0]["shop"] == [{"itemName": "axe", "itemId": 3274, "sell": 7}]


# ======================================================
# db.json merge — travelGraph
# ======================================================


def test_merge_travel_graph_into_catalog_appends_new_edge():
    db_edges = []
    fragment_edges = [{"from": "ROOK-A", "to": "ROOK-B", "tileCount": 10}]

    report = tg.merge_travel_graph_into_catalog(db_edges, fragment_edges, "ROOK")

    assert report == {"ROOK-A<->ROOK-B": "added"}
    assert db_edges == fragment_edges


def test_merge_travel_graph_into_catalog_upserts_by_unordered_pair():
    db_edges = [{"from": "ROOK-A", "to": "ROOK-B", "tileCount": 10}]
    fragment_edges = [{"from": "ROOK-B", "to": "ROOK-A", "tileCount": 12}]

    report = tg.merge_travel_graph_into_catalog(db_edges, fragment_edges, "ROOK")

    assert report == {"ROOK-B<->ROOK-A": "updated"}
    assert db_edges == [{"from": "ROOK-B", "to": "ROOK-A", "tileCount": 12}]


def test_merge_travel_graph_into_catalog_drops_a_city_edge_the_fragment_no_longer_has():
    # The regression this whole ticket exists for: upsert-only let 23 edges
    # nobody's BFS ever produced survive in catalog-source.json, one of them
    # citing ROOK-HUNT-00015 — an id with a digit too many that is not a POI.
    db_edges = [
        {"from": "ROOK-HUNT-0001", "to": "ROOK-HUNT-00015", "tileCount": 40},
        {"from": "ROOK-HUNT-0001", "to": "ROOK-TEMPLE-0001", "tileCount": 12},
    ]
    fragment_edges = [{"from": "ROOK-HUNT-0001", "to": "ROOK-TEMPLE-0001", "tileCount": 12}]

    report = tg.merge_travel_graph_into_catalog(db_edges, fragment_edges, "ROOK")

    assert db_edges == fragment_edges
    assert report["ROOK-HUNT-0001<->ROOK-HUNT-00015"] == "removed"


def test_merge_travel_graph_into_catalog_leaves_another_citys_edges_untouched():
    other_city = {"from": "CARL-TEMPLE-0001", "to": "CARL-DEPOT-0001", "tileCount": 30}
    db_edges = [other_city, {"from": "ROOK-A", "to": "ROOK-STALE", "tileCount": 9}]
    fragment_edges = [{"from": "ROOK-A", "to": "ROOK-B", "tileCount": 5}]

    report = tg.merge_travel_graph_into_catalog(db_edges, fragment_edges, "ROOK")

    assert other_city in db_edges
    assert {"from": "ROOK-A", "to": "ROOK-STALE", "tileCount": 9} not in db_edges
    assert "CARL-TEMPLE-0001<->CARL-DEPOT-0001" not in report


def test_merge_travel_graph_into_catalog_drops_a_cross_city_edge_touching_the_city():
    # An edge with one foot in ROOK is ROOK's to regenerate; leaving it
    # because its other end is elsewhere is how an orphan survives.
    db_edges = [{"from": "ROOK-A", "to": "CARL-B", "tileCount": 99}]

    report = tg.merge_travel_graph_into_catalog(db_edges, [], "ROOK")

    assert db_edges == []
    assert report == {"ROOK-A<->CARL-B": "removed"}


def test_merge_locations_into_catalog_reports_a_city_location_the_fragment_dropped():
    # Report only, never deleted: a location rejected this run may be a sign
    # the user is mid-way through fixing, and its curated displayName must
    # survive that. The CLI surfaces these so nothing rots unnoticed.
    catalog_locations = [{"id": "ROOK-HUNT-0012", "type": "HUNT", "x": 1, "y": 2, "z": 7},
                    {"id": "CARL-HUNT-0001", "type": "HUNT", "x": 3, "y": 4, "z": 7}]
    fragment = [{"id": "ROOK-HUNT-0001", "type": "HUNT", "x": 5, "y": 6, "z": 7}]

    report = tg.merge_locations_into_catalog(catalog_locations, fragment, "ROOK")

    assert report["ROOK-HUNT-0012"] == "stale"
    assert "CARL-HUNT-0001" not in report
    assert len(catalog_locations) == 3


def test_merge_travel_fragment_into_catalog_merges_both_collections():
    db = {"locations": [], "travelGraph": []}
    fragment = {
        "locations": [tg.build_npc_location({"name": "Obi", "x": 1, "y": 1, "z": 7}, "ROOK", None)],
        "travelGraph": [{"from": "ROOK-HUNT-001", "to": "ROOK-TEMPLE-001", "tileCount": 5}],
    }

    report = tg.merge_travel_fragment_into_catalog(db, fragment, "ROOK")

    assert report["locations"] == {"ROOK-NPC-obi": "added"}
    assert report["travelGraph"] == {"ROOK-HUNT-001<->ROOK-TEMPLE-001": "added"}
    assert db["locations"] == fragment["locations"]
    assert db["travelGraph"] == fragment["travelGraph"]


# ======================================================
# A polilinha de cada aresta
# ======================================================


def _undirected(pairs):
    """[(a, b), ...] -> mapa de adjacência não-direcionado."""
    graph: dict = {}
    for a, b in pairs:
        graph.setdefault(a, set()).add(b)
        graph.setdefault(b, set()).add(a)
    return graph


def test_reconstruct_path_walks_prev_back_to_the_seed():
    prev = {(1, 0, 7): (0, 0, 7), (2, 0, 7): (1, 0, 7), (0, 0, 7): None}

    assert tg.reconstruct_path(prev, (2, 0, 7)) == [(0, 0, 7), (1, 0, 7), (2, 0, 7)]


def test_reconstruct_path_of_the_seed_itself_is_a_single_point():
    assert tg.reconstruct_path({}, (4, 4, 7)) == [(4, 4, 7)]


def test_prev_comes_from_the_settle_not_from_the_last_relax():
    """A armadilha. T é vizinho do atalho (A) **e** do fim do desvio (B3), e a
    busca continua depois de achar T porque U ainda falta. Quem grava o pai no
    relax deixa o relax tardio de B3 — que chega por um caminho duas vezes mais
    longo — sobrescrever o pai certo, e a polilinha sai contradizendo o
    tileCount que a mesma busca reporta."""
    seed, shortcut, target = (0, 0, 7), (1, 0, 7), (2, 0, 7)
    detour = [(1, 1, 7), (2, 2, 7), (3, 3, 7)]
    graph = _undirected([
        (seed, shortcut), (shortcut, target),
        (seed, detour[0]), (detour[0], detour[1]), (detour[1], detour[2]),
        (detour[2], target),
        (detour[2], (4, 4, 7)), ((4, 4, 7), (5, 5, 7)),
    ])

    distances, prev = tg.tile_distances_and_prev(
        graph, {seed: 0}, {target, (5, 5, 7)}
    )

    assert distances[target] == 2
    assert tg.reconstruct_path(prev, target) == [seed, shortcut, target]


def test_simplify_polyline_turns_a_straight_run_into_its_two_ends():
    line = [(0, 0, 7), (1, 0, 7), (2, 0, 7), (3, 0, 7)]

    assert tg.simplify_polyline(line) == [(0, 0, 7), (3, 0, 7)]


def test_simplify_polyline_keeps_the_corner_of_an_elbow():
    elbow = [(0, 0, 7), (1, 0, 7), (2, 0, 7), (2, 1, 7), (2, 2, 7)]

    assert tg.simplify_polyline(elbow) == [(0, 0, 7), (2, 0, 7), (2, 2, 7)]


def test_simplify_polyline_treats_a_diagonal_as_its_own_direction():
    """Grid 8-conectado: a diagonal é um passo, e sair dela é dobrar."""
    path = [(0, 0, 7), (1, 1, 7), (2, 2, 7), (3, 2, 7)]

    assert tg.simplify_polyline(path) == [(0, 0, 7), (2, 2, 7), (3, 2, 7)]


def test_simplify_polyline_keeps_the_tile_where_the_floor_changes():
    path = [(0, 0, 7), (1, 0, 7), (1, 0, 8), (2, 0, 8)]

    assert tg.simplify_polyline(path) == [(0, 0, 7), (1, 0, 7), (1, 0, 8), (2, 0, 8)]


def test_simplify_polyline_keeps_the_floor_in_between_two_changes_in_a_row():
    """Duas descidas seguidas são o mesmo passo, e fundi-las apagaria o z=8 da
    rota — quem desenha decide pelo z de cada vértice, sem interpolar."""
    path = [(0, 0, 9), (0, 0, 8), (0, 0, 7), (1, 0, 7)]

    assert tg.simplify_polyline(path) == [(0, 0, 9), (0, 0, 8), (0, 0, 7), (1, 0, 7)]


def test_simplify_polyline_keeps_the_vertex_before_a_jump_off_the_line():
    """O salto de aproximação a um NPC anda mais de um tile de uma vez, e
    `(5, -4)` só tem o mesmo *sinal* da corrida diagonal `(1, -1)` — não é a
    mesma reta. Pelo sinal o tile de aproximação sumiria e o segmento
    atravessaria tiles que ninguém pisou."""
    path = [(0, 0, 7), (1, -1, 7), (2, -2, 7), (7, -6, 7)]

    assert tg.simplify_polyline(path) == [(0, 0, 7), (2, -2, 7), (7, -6, 7)]


def test_simplify_polyline_absorbs_a_jump_that_continues_the_same_line():
    """Colinear e no mesmo sentido: a reta de ponta a ponta cobre exatamente
    os mesmos tiles dos dois segmentos, então o vértice do meio não diz nada."""
    path = [(0, 0, 7), (1, 0, 7), (2, 0, 7), (7, 0, 7)]

    assert tg.simplify_polyline(path) == [(0, 0, 7), (7, 0, 7)]


def test_simplify_polyline_of_one_or_two_points_is_itself():
    assert tg.simplify_polyline([(0, 0, 7)]) == [(0, 0, 7)]
    assert tg.simplify_polyline([(0, 0, 7), (1, 0, 7)]) == [(0, 0, 7), (1, 0, 7)]


def test_flatten_polyline_is_a_flat_array_of_triples():
    assert tg.flatten_polyline([(10, 20, 7), (11, 20, 8)]) == [10, 20, 7, 11, 20, 8]


def test_build_travel_graph_gives_every_edge_a_path():
    graph = _line_graph(10)
    locations = [_location("A", 0, 0), _location("B", 3, 0)]

    edges = tg.build_travel_graph(graph, locations)

    assert edges[0]["path"] == [0, 0, 7, 3, 0, 7]


def test_build_travel_graph_orients_the_path_from_the_edges_own_from_to_its_to():
    """A aresta é canônica (from < to) e a polilinha serve os dois sentidos;
    orientá-la junto com a aresta poupa o consumidor de adivinhar qual ponta
    é qual."""
    graph = _line_graph(10)
    locations = [_location("Z", 0, 0), _location("A", 3, 0)]

    edge = tg.build_travel_graph(graph, locations)[0]

    assert (edge["from"], edge["to"]) == ("A", "Z")
    assert edge["path"] == [3, 0, 7, 0, 0, 7]


def test_build_travel_graph_path_bends_where_the_walk_bends():
    graph = _undirected([
        ((0, 0, 7), (1, 0, 7)), ((1, 0, 7), (2, 0, 7)),
        ((2, 0, 7), (2, 1, 7)), ((2, 1, 7), (2, 2, 7)),
    ])
    locations = [_location("A", 0, 0), _location("B", 2, 2)]

    edge = tg.build_travel_graph(graph, locations)[0]

    assert edge["tileCount"] == 4
    assert edge["path"] == [0, 0, 7, 2, 0, 7, 2, 2, 7]


def test_build_travel_graph_path_of_a_co_located_pair_repeats_the_tile():
    """Pino a pino vale também quando os dois pinos são o mesmo tile: o schema
    do catálogo recusa polilinha de um ponto, e o extractor emitindo uma era o
    importador falhando com um par de hunts curadas que dividem a entrada."""
    graph = _line_graph(3)
    locations = [_location("A", 1, 0), _location("B", 1, 0)]

    edge = tg.build_travel_graph(graph, locations)[0]

    assert edge["tileCount"] == 0
    assert edge["path"] == [1, 0, 7, 1, 0, 7]


def test_build_travel_graph_npc_approach_is_one_straight_hop_at_the_end():
    """A ponta é ancorada no tile do NPC — senão a rota terminaria a dois
    tiles do pino — mas o trecho de aproximação é Chebyshev em linha reta,
    não caminho andado: nenhum vértice é inventado dentro dele."""
    graph = _line_graph(10)
    graph[(6, 1, 7)] = set()
    locations = [_location("A", 0, 0), _location("N", 6, 1, loc_type="NPC")]

    edge = tg.build_travel_graph(graph, locations, npc_reach=2)[0]

    assert edge["tileCount"] == 6
    assert edge["path"] == [0, 0, 7, 4, 0, 7, 6, 1, 7]


def test_build_travel_graph_default_reach_crosses_a_four_tile_shop_gap():
    graph = _line_graph(10)
    graph[(0, 4, 7)] = set()
    locations = [_location("A", 0, 0), _location("THAIS-NPC-xodet", 0, 4, loc_type="NPC")]

    edge = tg.build_travel_graph(graph, locations)[0]

    assert edge["tileCount"] == 4


def test_build_travel_graph_keeps_the_last_walked_tile_before_the_npc_hop():
    """O salto de aproximação alinhado com a corrida diagonal que vem antes:
    o tile onde o jogador de fato para (4,-4) é vértice, e a rota não vira uma
    reta de (0,0) até o balcão por cima de tiles que ninguém andou."""
    run = [(0, 0, 7), (1, -1, 7), (2, -2, 7), (3, -3, 7), (4, -4, 7)]
    graph = _undirected(list(zip(run, run[1:])))
    locations = [_location("A", 0, 0), _location("N", 7, -6, loc_type="NPC")]

    edge = tg.build_travel_graph(graph, locations, npc_reach=3)[0]

    assert edge["tileCount"] == 7
    assert edge["path"] == [0, 0, 7, 4, -4, 7, 7, -6, 7]


def test_a_route_marker_item_contributes_no_flags_to_the_graph():
    """A bola de energia da rota é marcador, não conteúdo: se ela contribuísse
    `unpass`, o próprio caminho que ela desenha ficaria inandável e a rota que
    depende dele nunca fecharia."""
    dump = {"data": {"nodes": [{"features": [{"x": 0, "y": 0, "z": 7, "tiles": [
        {"x": 1, "y": 1, "tileid": 100, "items": [{"id": 27869}]},
    ]}]}]}}
    flags = {"100": {}, "27869": {"unpass": True}}

    tiles = tg.extract_tile_flags(dump, flags)

    assert [t["unpass"] for t in tiles] == [False]


# ======================================================
# Marcador de quest por slug (uid em faixa + texto)
# ======================================================

def _slug_marker_dump(items):
    return {"data": {"nodes": [{"features": [{"x": 0, "y": 0, "z": 7, "tiles": [
        {"x": i, "y": 0, "tileid": 1, "items": [it]} for i, it in enumerate(items)
    ]}]}]}}


def test_a_slug_marker_is_read_from_the_uid_band_and_its_text():
    """O autor marcou a entrada com um item qualquer carregando uid na faixa de
    quest e o slug no texto — não com a placa `CIDADE-TIPO-NNNN`."""
    dump = _slug_marker_dump([{"id": 2014, "uid": 20001, "text": "copper_shield_quest"}])

    markers = tg.parse_quest_slug_markers(dump)

    assert markers == [{"slug": "copper_shield_quest", "uid": 20001, "x": 0, "y": 0, "z": 7}]


def test_the_slug_band_leaves_the_poi_signs_and_the_world_maps_own_uids_alone():
    dump = _slug_marker_dump([
        {"id": 2016, "uid": 10005, "text": "ROOK-HUNT-0005"},   # placa de POI
        {"id": 2473, "uid": 64129},                             # uid do proprio mapa-mundo
        {"id": 2012, "uid": 20002, "text": "katana_quest"},
    ])

    assert [m["slug"] for m in tg.parse_quest_slug_markers(dump)] == ["katana_quest"]


def test_a_slug_marker_mints_a_hunt_poi_matching_the_map_folder():
    # O slug do marcador casa com o slug da pasta do mapa, e a pasta carrega o
    # id. Nada de tabela curada nova: se a pasta existe, o id existe.
    marker = {"slug": "copper_shield_quest", "uid": 20001, "x": 1188, "y": 1134, "z": 7}

    location = tg.build_quest_slug_location(marker, "ROOK-HUNT-0013")

    assert location["id"] == "ROOK-HUNT-0013"
    assert location["type"] == "HUNT"
    assert (location["x"], location["y"], location["z"]) == (1188, 1134, 7)


def test_matching_a_slug_to_a_folder_ignores_underscore_versus_hyphen():
    folders = [{"id": "ROOK-HUNT-0013", "name": "copper-shield-quest"},
               {"id": "ROOK-HUNT-0014", "name": "katana-quest"}]

    assert tg.hunt_id_for_slug("copper_shield_quest", folders) == "ROOK-HUNT-0013"
    assert tg.hunt_id_for_slug("katana_quest", folders) == "ROOK-HUNT-0014"
    assert tg.hunt_id_for_slug("sem_pasta", folders) is None


# ======================================================
# Teleport como aresta do grafo de viagem
# ======================================================


def _teleport_item(dest):
    return {"id": 1959, "destination": {"x": dest[0], "y": dest[1], "z": dest[2]}}


def test_extract_teleport_edges_reads_destination_in_world_coords():
    dump = _dump([(5, 6, 7, [_teleport_item((40, 41, 9))])])

    assert tg.extract_teleport_edges(dump) == [((5, 6, 7), (40, 41, 9))]


def test_extract_teleport_edges_skips_the_decorative_zero_destination():
    dump = _dump([(5, 6, 7, [_teleport_item((0, 0, 0))])])

    assert tg.extract_teleport_edges(dump) == []


def test_build_walkable_graph_connects_a_teleport_to_its_destination():
    tiles = [_tile(0, 0, 7), _tile(9, 9, 9)]

    graph = tg.build_walkable_graph(tiles, [((0, 0, 7), (9, 9, 9))])

    assert (9, 9, 9) in graph[(0, 0, 7)]
    assert (0, 0, 7) in graph[(9, 9, 9)]


def test_build_walkable_graph_ignores_a_teleport_whose_end_is_off_the_cut():
    tiles = [_tile(0, 0, 7)]

    graph = tg.build_walkable_graph(tiles, [((0, 0, 7), (900, 900, 9))])

    assert graph[(0, 0, 7)] == set()


def test_build_walkable_graph_without_extra_edges_behaves_as_before():
    tiles = [_tile(0, 0, 7), _tile(1, 0, 7)]

    assert tg.build_walkable_graph(tiles) == tg.build_walkable_graph(tiles, [])


# ======================================================
# Ponte por componente (ilha) e fechamento transitivo
# ======================================================


def _island_poi(poi_id, poi_type, x, y, z=7):
    return {"id": poi_id, "type": poi_type, "x": x, "y": y, "z": z}


def _island_edge(a, b, tile_count=10):
    low, high = sorted((a, b))
    return {"from": low, "to": high, "tileCount": tile_count, "path": []}


def test_connect_orphan_hunts_bridges_an_island_whose_hunts_link_to_each_other():
    # A ilha tem aresta interna, então a regra antiga ("hunt sem aresta") a
    # deixava passar e o templo não chegava em nenhuma das duas.
    locations = [
        _island_poi("C-TEMPLE-0001", "TEMPLE", 0, 0),
        _island_poi("C-HUNT-0001", "HUNT", 5, 0),
        _island_poi("C-HUNT-0002", "HUNT", 100, 0),
        _island_poi("C-HUNT-0003", "HUNT", 105, 0),
    ]
    edges = [_island_edge("C-TEMPLE-0001", "C-HUNT-0001"), _island_edge("C-HUNT-0002", "C-HUNT-0003")]

    bridged, invented = tg.connect_orphan_hunts(locations, list(edges))

    assert len(invented) == 1
    reachable = _reachable(bridged, "C-TEMPLE-0001")
    assert {"C-HUNT-0001", "C-HUNT-0002", "C-HUNT-0003"} <= reachable


def test_connect_orphan_hunts_bridges_an_island_that_only_holds_the_depot():
    # Yalahar perdia o depot por isso: componente sem hunt nenhuma.
    locations = [
        _island_poi("C-TEMPLE-0001", "TEMPLE", 0, 0),
        _island_poi("C-HUNT-0001", "HUNT", 5, 0),
        _island_poi("C-DEPOT-0001", "DEPOT", 200, 0),
    ]
    edges = [_island_edge("C-TEMPLE-0001", "C-HUNT-0001")]

    bridged, invented = tg.connect_orphan_hunts(locations, list(edges))

    assert [link["hunt"] for link in invented] == ["C-DEPOT-0001"]
    assert "C-DEPOT-0001" in _reachable(bridged, "C-TEMPLE-0001")


def test_connect_orphan_hunts_leaves_an_npc_only_island_to_the_rejection_report():
    locations = [
        _island_poi("C-TEMPLE-0001", "TEMPLE", 0, 0),
        _island_poi("C-HUNT-0001", "HUNT", 5, 0),
        _island_poi("C-NPC-sozinho", "NPC", 300, 0),
    ]
    edges = [_island_edge("C-TEMPLE-0001", "C-HUNT-0001")]

    bridged, invented = tg.connect_orphan_hunts(locations, list(edges))

    assert invented == []
    assert "C-NPC-sozinho" not in _reachable(bridged, "C-TEMPLE-0001")


def test_connect_orphan_hunts_does_nothing_when_everything_already_connects():
    locations = [_island_poi("C-TEMPLE-0001", "TEMPLE", 0, 0), _island_poi("C-HUNT-0001", "HUNT", 5, 0)]
    edges = [_island_edge("C-TEMPLE-0001", "C-HUNT-0001")]

    bridged, invented = tg.connect_orphan_hunts(locations, list(edges))

    assert invented == []
    assert len(bridged) == 1


def test_close_bridged_pairs_puts_every_pair_one_hop_apart():
    # Depois da ponte o grafo deixa de ser completo: a hunt do outro lado fica
    # a 2+ saltos e sai da lista de viagem, que só mostra vizinho direto.
    edges = [
        _island_edge("C-TEMPLE-0001", "C-HUNT-0001", 10),
        _island_edge("C-HUNT-0001", "C-HUNT-0002", 30),
    ]

    closed, added = tg.close_bridged_pairs(list(edges))

    assert added == 1
    assert frozenset(("C-TEMPLE-0001", "C-HUNT-0002")) in {
        frozenset((e["from"], e["to"])) for e in closed
    }
    direct = next(
        e for e in closed
        if {e["from"], e["to"]} == {"C-TEMPLE-0001", "C-HUNT-0002"}
    )
    assert direct["tileCount"] == 40


def test_close_bridged_pairs_is_a_noop_on_a_graph_that_is_already_complete():
    edges = [_island_edge("A", "B"), _island_edge("B", "C"), _island_edge("A", "C")]

    closed, added = tg.close_bridged_pairs(list(edges))

    assert added == 0
    assert len(closed) == 3


def _reachable(edges, start):
    import collections

    adjacency = collections.defaultdict(set)
    for edge in edges:
        adjacency[edge["from"]].add(edge["to"])
        adjacency[edge["to"]].add(edge["from"])
    seen = {start}
    queue = [start]
    while queue:
        node = queue.pop()
        for neighbor in adjacency[node]:
            if neighbor not in seen:
                seen.add(neighbor)
                queue.append(neighbor)
    return seen


# ======================================================
# Duplicata de Rookgaard dentro do corte de outra cidade
# ======================================================


ROOK_OBI = {"name": "Obi", "x": 32097, "y": 32205, "z": 7}


def _npc_location(city, name, x, y, z):
    return tg.build_npc_location({"name": name, "x": x, "y": y, "z": z}, city, None)


def test_rook_npc_copied_into_another_city_is_a_duplicate():
    """O corte do mapa de Thais pegou a ilha de Rookgaard com coordenada de mundo
    preservada, então `THAIS-NPC-obi` é o mesmo NPC que `ROOK-NPC-obi`."""
    thais_copy = _npc_location("THAIS", "Obi", 32097, 32205, 7)

    duplicates = tg.find_rook_duplicates([thais_copy], [ROOK_OBI])

    assert duplicates == {"THAIS-NPC-obi": "ROOK-NPC-obi"}


def test_the_rook_side_is_never_its_own_duplicate():
    """Quem ganha é ROOK — a mesma regra que o `findRookDuplicateNpcs` do
    `tibia-idle` já aplica no import."""
    assert tg.find_rook_duplicates([_npc_location("ROOK", "Obi", 32097, 32205, 7)], [ROOK_OBI]) == {}


def test_a_namesake_somewhere_else_is_a_different_npc():
    """`Junkar` existe em três lugares com `.lua` diferentes e `Ferryman Kamil`
    em dois. Casar só pelo nome tiraria nós que o grafo precisa — por isso a
    chave é slug **e** posição."""
    elsewhere = _npc_location("THAIS", "Obi", 32400, 32100, 7)

    assert tg.find_rook_duplicates([elsewhere], [ROOK_OBI]) == {}


def test_same_name_one_floor_up_is_not_a_duplicate():
    assert tg.find_rook_duplicates([_npc_location("THAIS", "Obi", 32097, 32205, 8)], [ROOK_OBI]) == {}


def test_no_rook_xml_means_no_duplicate_is_claimed():
    """Sem o `ROOK-npc.xml` do lado a função não inventa corte nenhum."""
    assert tg.find_rook_duplicates([_npc_location("THAIS", "Obi", 32097, 32205, 7)], []) == {}


def test_npc_slug_of_is_the_inverse_of_the_id_build():
    """A conta tem que seguir igual à do `npcSlugOf` no `tibia-idle`: as duas
    pontas comparam NPC pelo mesmo par slug+posição."""
    location = _npc_location("THAIS", "Lee'Delle", 1, 1, 7)

    assert location["id"] == "THAIS-NPC-lee-delle"
    assert tg.npc_slug_of(location["id"]) == "lee-delle"


# ======================================================
# Relatório de descarte de NPC
# ======================================================


def test_npc_skip_report_groups_by_reason_and_points_at_the_allowlist():
    skipped = [
        {"id": "THAIS-NPC-obi", "name": "Obi", "reason": "duplicata de ROOK-NPC-obi"},
        {"id": "THAIS-NPC-bozo", "name": "Bozo", "reason": "sem shop e sem serviço"},
        {"id": "THAIS-NPC-pig", "name": "Pig", "reason": "sem shop e sem serviço"},
    ]

    report = tg.format_npc_skip_report(skipped, "THAIS")

    assert "3 NPC(s) fora do fragmento" in report
    assert "## sem shop e sem serviço (2)" in report
    assert "## duplicata de ROOK-NPC-obi (1)" in report
    assert tg.NPC_ALLOWLIST_NAME in report
    # Quem lê o arquivo tem que saber que nó ilhado é o *outro* relatório.
    assert tg.REJECTION_REPORT_NAME in report


def test_npc_skip_report_says_so_when_nothing_was_cut():
    """Arquivo vazio e arquivo ausente são indistinguíveis num diff; a frase não."""
    assert "nenhum NPC descartado" in tg.format_npc_skip_report([], "ROOK")


# ======================================================
# Filtro: quem vira location de NPC
# ======================================================


def _shop_npc(city, name):
    location = _npc_location(city, name, 1, 1, 7)
    location["shop"] = [{"itemName": "bread", "itemId": 3600, "buy": 3}]
    return location


def test_a_rook_npc_enters_with_no_shop_and_no_service():
    """Rookgaard é a área inicial e precisa de volume — a isenção é pelo `city`
    do id, e não pela geografia."""
    assert tg.npc_skip_reason(_npc_location("ROOK", "Bozo", 1, 1, 7), [], {}) is None


def test_the_same_npc_outside_rook_is_cut():
    assert tg.npc_skip_reason(_npc_location("THAIS", "Bozo", 1, 1, 7), [], {}) == "sem shop e sem serviço"


def test_a_shop_of_one_item_still_counts_as_a_merchant():
    """Tamanho do inventário não entra na conta: filtrar por tamanho seria
    enfiar julgamento de relevância dentro da regra mecânica."""
    location = _npc_location("THAIS", "Albinius", 1, 1, 7)
    location["shop"] = [{"itemName": "scroll", "itemId": 1949, "buy": 100}]

    assert tg.npc_skip_reason(location, [], {}) is None


def test_an_empty_shop_table_is_not_a_shop():
    """`shop: []` é tabela que o parser leu e achou sem nada (issue 06), não um
    comerciante. Quem tem item de verdade por trás disso está na allowlist."""
    location = _npc_location("THAIS", "Black Bert", 1, 1, 7)
    location["shop"] = []

    assert tg.npc_skip_reason(location, [], {}) == "sem shop e sem serviço"


@pytest.mark.parametrize("service", sorted(tg.NPC_KEPT_SERVICES))
def test_each_kept_service_is_enough_on_its_own(service):
    assert tg.npc_skip_reason(_npc_location("THAIS", "Someone", 1, 1, 7), [service], {}) is None


def test_spell_alone_is_cut_and_the_reason_says_which_service():
    """Magia está fora por decisão de escopo, não por o NPC não fazer nada — e o
    motivo tem que distinguir os dois, porque se consertam de formas diferentes."""
    reason = tg.npc_skip_reason(_npc_location("CARLIN", "Lea", 1, 1, 7), ["spell"], {})

    assert reason == "serviço só de spell"


def test_spell_plus_a_kept_service_enters():
    """Cargo acumulado: Padreia ensina magia **e** vende; quem acumula entra pelo
    que conta."""
    assert tg.npc_skip_reason(_npc_location("CARLIN", "Padreia", 1, 1, 7), ["spell", "bless"], {}) is None


def test_the_allowlist_lets_an_npc_in_with_nothing_else():
    allowlist = {"VENORE-NPC-zebron": "cassino: aposta 1-99g com payout"}

    assert tg.npc_skip_reason(_npc_location("VENORE", "Zebron", 1, 1, 7), [], allowlist) is None


def test_filter_splits_kept_from_skipped_and_keeps_the_reason():
    locations = [_shop_npc("THAIS", "Hardek"), _npc_location("THAIS", "Pig", 1, 1, 7)]

    kept, skipped = tg.filter_npc_locations(locations, {}, {})

    assert [loc["id"] for loc in kept] == ["THAIS-NPC-hardek"]
    assert skipped == [
        {"id": "THAIS-NPC-pig", "name": "Pig", "reason": "sem shop e sem serviço"}
    ]


def test_services_are_looked_up_by_display_name():
    """A allowlist casa por id e os serviços por nome, e as duas chaves são de
    propósito: o `.lua` do Canary casa por nome de arquivo, e o nome não
    desambigua `Junkar` nem `Ferryman Kamil`."""
    locations = [_npc_location("THAIS", "Captain Bluebear", 1, 1, 7)]

    kept, skipped = tg.filter_npc_locations(locations, {"Captain Bluebear": ["travel"]}, {})

    assert len(kept) == 1 and skipped == []


def test_an_allowlist_id_that_matches_no_npc_of_this_city_is_reported():
    """A falha silenciosa que a allowlist convida: a linha fica no arquivo, o NPC
    continua cortado, e nada avisa."""
    allowlist = {"THAIS-NPC-nao-existe": "typo", "THAIS-NPC-pig": "ok", "VENORE-NPC-zebron": "outra cidade"}

    unresolved = tg.unresolved_allowlist_ids(
        allowlist, [_npc_location("THAIS", "Pig", 1, 1, 7)], "THAIS"
    )

    assert unresolved == ["THAIS-NPC-nao-existe"]


def test_the_shipped_allowlist_resolves_in_full():
    """Cada id da allowlist versionada casa com um NPC de verdade do
    `<CIDADE>-npc.xml` da sua cidade. Um typo aqui é um NPC que fica cortado
    para sempre sem ninguém notar."""
    import build_travel_fragment as btf

    allowlist = btf._load_npc_allowlist()
    assert allowlist, "a allowlist versionada não deveria estar vazia"

    for city in ["ROOK", "THAIS", "CARLIN", "KAZORDOON", "VENORE"]:
        npcs = btf._load_city_npcs(city)
        locations, _ = tg.build_npc_locations(npcs, city, {})
        assert tg.unresolved_allowlist_ids(allowlist, locations, city) == []

