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
    dump = _dump([(1000, 2000, 7, [_sign_item(10001, "ROOK-HUNT-001")])])

    locations, issues = tg.parse_marker_signs(dump)

    assert locations == [{"id": "ROOK-HUNT-001", "type": "HUNT", "x": 1000, "y": 2000, "z": 7}]
    assert issues == []


def test_parse_marker_signs_ignores_uid_outside_reserved_range():
    dump = _dump([(1000, 2000, 7, [_sign_item(500, "ROOK-HUNT-001")])])

    locations, issues = tg.parse_marker_signs(dump)

    assert locations == []
    assert issues == []


def test_parse_marker_signs_reports_legacy_format_without_tipo_segment():
    dump = _dump([(1000, 2000, 7, [_sign_item(10002, "ROOK-0002")])])

    locations, issues = tg.parse_marker_signs(dump)

    assert locations == []
    assert issues == [{"reason": "invalid-sign-format", "uid": 10002, "text": "ROOK-0002", "x": 1000, "y": 2000, "z": 7}]


def test_parse_marker_signs_ignores_non_sign_items_even_with_high_uid():
    dump = _dump([(1000, 2000, 7, [{"id": 2473, "uid": 64129}])])

    locations, issues = tg.parse_marker_signs(dump)

    assert locations == []
    assert issues == []


def test_build_sign_location_derives_placeholder_display_name_and_flags_todo():
    entry = tg.build_sign_location({"id": "ROOK-DEPOT-001", "type": "DEPOT", "x": 1, "y": 2, "z": 7})

    assert entry["displayName"] == "Rook Depot 001"
    assert entry["_todo"]


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
# BFS / travelGraph
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


def test_bfs_distances_finds_every_target_and_stops_early():
    graph = _line_graph(10)

    distances = tg.bfs_distances(graph, (0, 0, 7), {(3, 0, 7), (5, 0, 7)})

    assert distances == {(3, 0, 7): 3, (5, 0, 7): 5}


def test_bfs_distances_unreachable_target_is_simply_absent():
    graph = {(0, 0, 7): set(), (5, 5, 7): set()}

    distances = tg.bfs_distances(graph, (0, 0, 7), {(5, 5, 7)})

    assert distances == {}


def _location(loc_id, x, y, z=7):
    return {"id": loc_id, "x": x, "y": y, "z": z}


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
    # produce. Proves each pair gets its own independent BFS.
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
        "id": "rook-npc-obi",
        "type": "NPC",
        "x": 1151, "y": 1130, "z": 7,
        "displayName": "Obi",
        "shop": shop,
    }


def test_build_npc_location_omits_shop_field_when_none():
    entry = tg.build_npc_location({"name": "Nobody", "x": 0, "y": 0, "z": 7}, "ROOK", None)

    assert "shop" not in entry


def test_build_npc_locations_flags_unmatched_npc_names_without_dropping_the_location():
    npcs = [{"name": "Obi", "x": 1, "y": 1, "z": 7}, {"name": "Nobody", "x": 2, "y": 2, "z": 7}]
    shops_by_name = {"Obi": [{"itemName": "axe", "itemId": 3274, "sell": 7}]}

    locations, unmatched = tg.build_npc_locations(npcs, "ROOK", shops_by_name)

    assert [loc["id"] for loc in locations] == ["rook-npc-obi", "rook-npc-nobody"]
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


def test_build_travel_fragment_combines_both_location_sources():
    sign_locs = [{"id": "ROOK-HUNT-001"}]
    npc_locs = [{"id": "rook-npc-obi"}]
    edges = [{"from": "ROOK-HUNT-001", "to": "ROOK-TEMPLE-001", "tileCount": 10}]

    fragment = tg.build_travel_fragment(sign_locs, npc_locs, edges)

    assert fragment["locations"] == [*sign_locs, *npc_locs]
    assert fragment["travelGraph"] == edges


# ======================================================
# db.json merge — locations
# ======================================================


def test_merge_locations_into_db_appends_a_new_location_as_a_draft():
    db_locations = []
    fragment = [tg.build_sign_location({"id": "ROOK-HUNT-001", "type": "HUNT", "x": 1, "y": 2, "z": 7})]

    report = tg.merge_locations_into_db(db_locations, fragment)

    assert report == {"ROOK-HUNT-001": "added"}
    assert db_locations == fragment


def test_merge_locations_into_db_preserves_curated_display_name_but_updates_position():
    curated = {"id": "ROOK-HUNT-001", "type": "HUNT", "x": 1, "y": 2, "z": 7, "displayName": "Rat Sewers Entrance"}
    db_locations = [curated]
    fragment = [{"id": "ROOK-HUNT-001", "type": "HUNT", "x": 999, "y": 888, "z": 7,
                 "displayName": "Rook Hunt 001", "_todo": ["confirmar displayName"]}]

    report = tg.merge_locations_into_db(db_locations, fragment)

    assert report == {"ROOK-HUNT-001": "updated"}
    assert db_locations[0]["displayName"] == "Rat Sewers Entrance"
    assert db_locations[0]["x"] == 999
    assert "_todo" not in db_locations[0]


def test_merge_locations_into_db_keeps_todo_flag_while_still_uncurated():
    draft = {"id": "ROOK-HUNT-001", "type": "HUNT", "x": 1, "y": 2, "z": 7,
              "displayName": "Rook Hunt 001", "_todo": ["confirmar displayName"]}
    db_locations = [dict(draft)]
    fragment = [{"id": "ROOK-HUNT-001", "type": "HUNT", "x": 5, "y": 6, "z": 7,
                 "displayName": "Rook Hunt 001", "_todo": ["confirmar displayName"]}]

    tg.merge_locations_into_db(db_locations, fragment)

    assert db_locations[0]["_todo"] == ["confirmar displayName"]
    assert db_locations[0]["x"] == 5


def test_merge_locations_into_db_upserts_npc_shop_mechanically_with_no_curation():
    db_locations = [{"id": "rook-npc-obi", "type": "NPC", "x": 1, "y": 1, "z": 7,
                      "displayName": "Obi", "shop": []}]
    fragment = [{"id": "rook-npc-obi", "type": "NPC", "x": 1, "y": 1, "z": 7,
                 "displayName": "Obi", "shop": [{"itemName": "axe", "itemId": 3274, "sell": 7}]}]

    tg.merge_locations_into_db(db_locations, fragment)

    assert db_locations[0]["shop"] == [{"itemName": "axe", "itemId": 3274, "sell": 7}]


# ======================================================
# db.json merge — travelGraph
# ======================================================


def test_merge_travel_graph_into_db_appends_new_edge():
    db_edges = []
    fragment_edges = [{"from": "A", "to": "B", "tileCount": 10}]

    report = tg.merge_travel_graph_into_db(db_edges, fragment_edges)

    assert report == {"A<->B": "added"}
    assert db_edges == fragment_edges


def test_merge_travel_graph_into_db_upserts_by_unordered_pair():
    db_edges = [{"from": "A", "to": "B", "tileCount": 10}]
    fragment_edges = [{"from": "B", "to": "A", "tileCount": 12}]

    report = tg.merge_travel_graph_into_db(db_edges, fragment_edges)

    assert report == {"B<->A": "updated"}
    assert db_edges == [{"from": "B", "to": "A", "tileCount": 12}]


def test_merge_travel_fragment_into_db_merges_both_collections():
    db = {"locations": [], "travelGraph": []}
    fragment = {
        "locations": [tg.build_npc_location({"name": "Obi", "x": 1, "y": 1, "z": 7}, "ROOK", None)],
        "travelGraph": [{"from": "ROOK-HUNT-001", "to": "ROOK-TEMPLE-001", "tileCount": 5}],
    }

    report = tg.merge_travel_fragment_into_db(db, fragment)

    assert report["locations"] == {"rook-npc-obi": "added"}
    assert report["travelGraph"] == {"ROOK-HUNT-001<->ROOK-TEMPLE-001": "added"}
    assert db["locations"] == fragment["locations"]
    assert db["travelGraph"] == fragment["travelGraph"]
