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
    return {str(k): {"flags": v} for k, v in flags_by_id.items()}


def test_extract_tile_flags_excludes_marker_sign_items_from_flags():
    dump = _dump([(0, 0, 7, [_sign_item(10001, "ROOK-HUNT-001")])])
    # If the marker sign contributed flags, this tile would report unpass —
    # it must not, since marker signs never reach the real map.json.
    object_defs = _object_defs({tg.SIGN_ITEM_ID: {"unpass": True}})

    tiles = tg.extract_tile_flags(dump, object_defs)

    assert tiles == [{"x": 0, "y": 0, "z": 7, "unpass": False, "isFloorTransition": False}]


def test_extract_tile_flags_combines_ground_and_item_flags():
    dump = {
        "data": {"nodes": [{"features": [{
            "x": 0, "y": 0, "z": 7,
            "tiles": [{"x": 0, "y": 0, "tileid": 100, "items": [{"id": 200, "uid": 500}]}],
        }]}]}
    }
    object_defs = _object_defs({100: {"unpass": False}, 200: {"unpass": True}})

    tiles = tg.extract_tile_flags(dump, object_defs)

    assert tiles == [{"x": 0, "y": 0, "z": 7, "unpass": True, "isFloorTransition": False}]


def _tile(x, y, z, unpass=False, transition=False):
    return {"x": x, "y": y, "z": z, "unpass": unpass, "isFloorTransition": transition}


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


def test_build_walkable_graph_bridges_floor_transition_tile_to_both_directions():
    tiles = [
        _tile(0, 0, 7, transition=True),
        _tile(0, 0, 6),
        _tile(0, 0, 8),
    ]

    graph = tg.build_walkable_graph(tiles)

    assert graph[(0, 0, 7)] == {(0, 0, 6), (0, 0, 8)}
    assert (0, 0, 7) in graph[(0, 0, 6)]
    assert (0, 0, 7) in graph[(0, 0, 8)]


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

    distances = tg.tile_distances(graph, {(0, 0, 7): 0}, {(3, 0, 7), (5, 0, 7)})

    assert distances == {(3, 0, 7): 3, (5, 0, 7): 5}


def test_tile_distances_unreachable_target_is_simply_absent():
    graph = {(0, 0, 7): set(), (5, 5, 7): set()}

    distances = tg.tile_distances(graph, {(0, 0, 7): 0}, {(5, 5, 7)})

    assert distances == {}


def test_tile_distances_counts_the_cost_of_entering_at_each_source():
    # Seeded costs are the only non-uniform part of the search: entering at
    # tile 4 already costs 2, so tile 6 is 2 + 2 hops, not 2.
    graph = _line_graph(10)

    distances = tg.tile_distances(graph, {(0, 0, 7): 0, (4, 0, 7): 2}, {(6, 0, 7)})

    assert distances == {(6, 0, 7): 4}


def test_tile_distances_takes_the_cheapest_source_not_the_first_one():
    graph = _line_graph(10)

    distances = tg.tile_distances(graph, {(0, 0, 7): 0, (5, 0, 7): 3}, {(6, 0, 7)})

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
    # a tileCount of 0 is the map's truth, not an error to filter out.
    graph = _line_graph(4)
    locations = [_location("NORMA", 1, 0), _location("AMBER", 1, 0)]

    edges = tg.build_travel_graph(graph, locations)

    assert edges == [{"from": "AMBER", "to": "NORMA", "tileCount": 0}]


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

    assert edges == [{"from": "A", "to": "B", "tileCount": 1}]


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
    assert edges == [{"from": "ROOK-NPC-norma", "to": "ROOK-TEMPLE-0001", "tileCount": 5}]


def test_build_travel_graph_npc_reach_does_not_shorten_an_open_air_npc():
    # An NPC standing in the street enters the graph on its own tile for 0,
    # so the reach costs its distances nothing. Seeding every tile within
    # reach at 0 instead would quietly shave 5 tiles off every NPC in town.
    graph = _line_graph(10)
    locations = [_location("ROOK-NPC-cipfried", 2, 0, loc_type="NPC"),
                 _location("ROOK-TEMPLE-0001", 8, 0, loc_type="TEMPLE")]

    edges = tg.build_travel_graph(graph, locations, npc_reach=5)

    assert edges == [{"from": "ROOK-NPC-cipfried", "to": "ROOK-TEMPLE-0001", "tileCount": 6}]


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
    shops_by_name = {"Obi": [{"itemName": "axe", "itemId": 3274, "sell": 7}]}

    locations, unmatched = tg.build_npc_locations(npcs, "ROOK", shops_by_name)

    assert [loc["id"] for loc in locations] == ["ROOK-NPC-obi", "ROOK-NPC-nobody"]
    assert "shop" in locations[0]
    assert "shop" not in locations[1]
    assert unmatched == ["Nobody"]


def test_build_npc_locations_does_not_warn_for_a_matched_file_with_no_shop_table():
    # "Trainer" matched a .lua file, but that file has no npcConfig.shop
    # table at all — expected (not every NPC sells things), not a warning.
    npcs = [{"name": "Trainer", "x": 1, "y": 1, "z": 7}]
    shops_by_name = {"Trainer": None}

    locations, unmatched = tg.build_npc_locations(npcs, "ROOK", shops_by_name)

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


def test_merge_locations_into_db_appends_a_new_location_as_a_draft():
    db_locations = []
    fragment = [tg.build_sign_location({"id": "ROOK-HUNT-001", "type": "HUNT", "x": 1, "y": 2, "z": 7})]

    report = tg.merge_locations_into_db(db_locations, fragment, "ROOK")

    assert report == {"ROOK-HUNT-001": "added"}
    assert db_locations == fragment


def test_merge_locations_into_db_never_duplicates_when_fragment_has_a_repeated_id():
    # Defensive: even if a fragment somehow carries the same id twice, the
    # second occurrence must upsert into the same db entry, not append a
    # second row (parse_marker_signs already prevents this upstream, but
    # this function shouldn't trust that).
    db_locations = []
    fragment = [
        {"id": "ROOK-HUNT-0006", "type": "HUNT", "x": 1, "y": 1, "z": 7},
        {"id": "ROOK-HUNT-0006", "type": "HUNT", "x": 2, "y": 2, "z": 7},
    ]

    tg.merge_locations_into_db(db_locations, fragment, "ROOK")

    assert len(db_locations) == 1
    assert db_locations[0]["x"] == 2


def test_merge_locations_into_db_preserves_curated_display_name_but_updates_position():
    curated = {"id": "ROOK-HUNT-001", "type": "HUNT", "x": 1, "y": 2, "z": 7, "displayName": "Rat Sewers Entrance"}
    db_locations = [curated]
    fragment = [{"id": "ROOK-HUNT-001", "type": "HUNT", "x": 999, "y": 888, "z": 7,
                 "displayName": "Rook Hunt 001", "_todo": ["confirmar displayName"]}]

    report = tg.merge_locations_into_db(db_locations, fragment, "ROOK")

    assert report == {"ROOK-HUNT-001": "updated"}
    assert db_locations[0]["displayName"] == "Rat Sewers Entrance"
    assert db_locations[0]["x"] == 999
    assert "_todo" not in db_locations[0]


def test_merge_locations_into_db_preserves_curated_hunt_id_but_updates_position():
    curated = {"id": "ROOK-HUNT-001", "type": "HUNT", "x": 1, "y": 2, "z": 7,
               "displayName": "Rat Sewers Entrance", "huntId": "ROOK-0002"}
    db_locations = [curated]
    fragment = [{"id": "ROOK-HUNT-001", "type": "HUNT", "x": 999, "y": 888, "z": 7,
                 "displayName": "Rook Hunt 001", "huntId": None, "_todo": ["associar huntId"]}]

    tg.merge_locations_into_db(db_locations, fragment, "ROOK")

    assert db_locations[0]["huntId"] == "ROOK-0002"
    assert db_locations[0]["displayName"] == "Rat Sewers Entrance"
    assert db_locations[0]["x"] == 999


def test_merge_locations_into_db_keeps_todo_flag_while_still_uncurated():
    draft = {"id": "ROOK-HUNT-001", "type": "HUNT", "x": 1, "y": 2, "z": 7,
              "displayName": "Rook Hunt 001", "_todo": ["confirmar displayName"]}
    db_locations = [dict(draft)]
    fragment = [{"id": "ROOK-HUNT-001", "type": "HUNT", "x": 5, "y": 6, "z": 7,
                 "displayName": "Rook Hunt 001", "_todo": ["confirmar displayName"]}]

    tg.merge_locations_into_db(db_locations, fragment, "ROOK")

    assert db_locations[0]["_todo"] == ["confirmar displayName"]
    assert db_locations[0]["x"] == 5


def test_merge_locations_into_db_upserts_npc_shop_mechanically_with_no_curation():
    db_locations = [{"id": "rook-npc-obi", "type": "NPC", "x": 1, "y": 1, "z": 7,
                      "displayName": "Obi", "shop": []}]
    fragment = [{"id": "rook-npc-obi", "type": "NPC", "x": 1, "y": 1, "z": 7,
                 "displayName": "Obi", "shop": [{"itemName": "axe", "itemId": 3274, "sell": 7}]}]

    tg.merge_locations_into_db(db_locations, fragment, "ROOK")

    assert db_locations[0]["shop"] == [{"itemName": "axe", "itemId": 3274, "sell": 7}]


# ======================================================
# db.json merge — travelGraph
# ======================================================


def test_merge_travel_graph_into_db_appends_new_edge():
    db_edges = []
    fragment_edges = [{"from": "ROOK-A", "to": "ROOK-B", "tileCount": 10}]

    report = tg.merge_travel_graph_into_db(db_edges, fragment_edges, "ROOK")

    assert report == {"ROOK-A<->ROOK-B": "added"}
    assert db_edges == fragment_edges


def test_merge_travel_graph_into_db_upserts_by_unordered_pair():
    db_edges = [{"from": "ROOK-A", "to": "ROOK-B", "tileCount": 10}]
    fragment_edges = [{"from": "ROOK-B", "to": "ROOK-A", "tileCount": 12}]

    report = tg.merge_travel_graph_into_db(db_edges, fragment_edges, "ROOK")

    assert report == {"ROOK-B<->ROOK-A": "updated"}
    assert db_edges == [{"from": "ROOK-B", "to": "ROOK-A", "tileCount": 12}]


def test_merge_travel_graph_into_db_drops_a_city_edge_the_fragment_no_longer_has():
    # The regression this whole ticket exists for: upsert-only let 23 edges
    # nobody's BFS ever produced survive in catalog-source.json, one of them
    # citing ROOK-HUNT-00015 — an id with a digit too many that is not a POI.
    db_edges = [
        {"from": "ROOK-HUNT-0001", "to": "ROOK-HUNT-00015", "tileCount": 40},
        {"from": "ROOK-HUNT-0001", "to": "ROOK-TEMPLE-0001", "tileCount": 12},
    ]
    fragment_edges = [{"from": "ROOK-HUNT-0001", "to": "ROOK-TEMPLE-0001", "tileCount": 12}]

    report = tg.merge_travel_graph_into_db(db_edges, fragment_edges, "ROOK")

    assert db_edges == fragment_edges
    assert report["ROOK-HUNT-0001<->ROOK-HUNT-00015"] == "removed"


def test_merge_travel_graph_into_db_leaves_another_citys_edges_untouched():
    other_city = {"from": "CARL-TEMPLE-0001", "to": "CARL-DEPOT-0001", "tileCount": 30}
    db_edges = [other_city, {"from": "ROOK-A", "to": "ROOK-STALE", "tileCount": 9}]
    fragment_edges = [{"from": "ROOK-A", "to": "ROOK-B", "tileCount": 5}]

    report = tg.merge_travel_graph_into_db(db_edges, fragment_edges, "ROOK")

    assert other_city in db_edges
    assert {"from": "ROOK-A", "to": "ROOK-STALE", "tileCount": 9} not in db_edges
    assert "CARL-TEMPLE-0001<->CARL-DEPOT-0001" not in report


def test_merge_travel_graph_into_db_drops_a_cross_city_edge_touching_the_city():
    # An edge with one foot in ROOK is ROOK's to regenerate; leaving it
    # because its other end is elsewhere is how an orphan survives.
    db_edges = [{"from": "ROOK-A", "to": "CARL-B", "tileCount": 99}]

    report = tg.merge_travel_graph_into_db(db_edges, [], "ROOK")

    assert db_edges == []
    assert report == {"ROOK-A<->CARL-B": "removed"}


def test_merge_locations_into_db_reports_a_city_location_the_fragment_dropped():
    # Report only, never deleted: a location rejected this run may be a sign
    # the user is mid-way through fixing, and its curated displayName must
    # survive that. The CLI surfaces these so nothing rots unnoticed.
    db_locations = [{"id": "ROOK-HUNT-0012", "type": "HUNT", "x": 1, "y": 2, "z": 7},
                    {"id": "CARL-HUNT-0001", "type": "HUNT", "x": 3, "y": 4, "z": 7}]
    fragment = [{"id": "ROOK-HUNT-0001", "type": "HUNT", "x": 5, "y": 6, "z": 7}]

    report = tg.merge_locations_into_db(db_locations, fragment, "ROOK")

    assert report["ROOK-HUNT-0012"] == "stale"
    assert "CARL-HUNT-0001" not in report
    assert len(db_locations) == 3


def test_merge_travel_fragment_into_db_merges_both_collections():
    db = {"locations": [], "travelGraph": []}
    fragment = {
        "locations": [tg.build_npc_location({"name": "Obi", "x": 1, "y": 1, "z": 7}, "ROOK", None)],
        "travelGraph": [{"from": "ROOK-HUNT-001", "to": "ROOK-TEMPLE-001", "tileCount": 5}],
    }

    report = tg.merge_travel_fragment_into_db(db, fragment, "ROOK")

    assert report["locations"] == {"ROOK-NPC-obi": "added"}
    assert report["travelGraph"] == {"ROOK-HUNT-001<->ROOK-TEMPLE-001": "added"}
    assert db["locations"] == fragment["locations"]
    assert db["travelGraph"] == fragment["travelGraph"]
