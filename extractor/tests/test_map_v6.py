import json

import map_v6
from sheet_packer import SheetPacker


def _analysis(appearance_id, *, flags=None, width=32, height=32, frame_count=1,
              source_path=None, animated=False, random=False, shift=None,
              elevation=0, automap_color=0, type_="static"):
    return {
        "appearanceId": appearance_id,
        "type": "animated" if animated else ("random" if random else type_),
        "hasSprite": source_path is not None,
        "animated": animated,
        "random": random,
        "animation": (
            {"appearanceId": appearance_id, "frameDurationMs": 500,
             "frameRate": 2, "loop": True, "startFrame": 0}
            if animated else None
        ),
        "flags": dict(flags or {}),
        "shift": shift,
        "elevation": elevation,
        "automapColor": automap_color,
        "spriteInfo": {"patternWidth": 1, "patternHeight": 1, "patternDepth": 1,
                       "boundingSquare": 32},
        "sprites": [
            {
                "spriteId": f"{appearance_id}_{i}",
                "sourcePath": source_path,
                "available": source_path is not None,
                "width": width,
                "height": height,
            }
            for i in range(frame_count)
        ],
        "issues": [],
    }


GROUND_FLAGS = {"bank": True, "unmove": True}
BORDER_FLAGS = {"clip": True, "unmove": True}


def _build(analyses, dump, assets_root="assets/test-sprites-v6",
           floorchange_by_id=None, ladder_ids=None):
    packer = SheetPacker()
    return map_v6.build_map_v6(
        dump,
        analyze=lambda appearance_id: analyses[appearance_id],
        packer=packer,
        assets_root=assets_root,
        floorchange_by_id=floorchange_by_id,
        ladder_ids=ladder_ids,
    )


def _dump(tiles, z=7, base=(0, 0)):
    """tiles: list of (x, y, tileid or None, [item ids or (id, uid) pairs])."""
    def _item(entry):
        if isinstance(entry, tuple):
            return {"id": entry[0], "uid": entry[1]}
        return {"id": entry}

    return {
        "data": {
            "nodes": [{
                "features": [{
                    "x": base[0], "y": base[1], "z": z,
                    "tiles": [
                        {"x": x, "y": y, "tileid": tileid,
                         "items": [_item(entry) for entry in items]}
                        for x, y, tileid, items in tiles
                    ],
                }]
            }]
        }
    }


def test_document_declares_version_six():
    analyses = {100: _analysis(100, flags=GROUND_FLAGS)}
    doc, _ = _build(analyses, _dump([(0, 0, 100, [])]))

    assert doc["version"] == 6


def test_no_render_role_or_depth_constant_survives_anywhere_in_the_document():
    analyses = {
        100: _analysis(100, flags=GROUND_FLAGS),
        4411: _analysis(4411, flags=BORDER_FLAGS),
        900: _analysis(900),
    }
    doc, _ = _build(analyses, _dump([(0, 0, 100, [4411, 900])]))

    serialized = json.dumps(doc)
    for banned in ("layerClass", "depthOffset", "roof", "Roof", "objectgroup", "tilelayer"):
        assert banned not in serialized


def test_each_tile_carries_its_ground_and_its_ordered_stack():
    analyses = {
        100: _analysis(100, flags=GROUND_FLAGS),
        4411: _analysis(4411, flags=BORDER_FLAGS),
        900: _analysis(900),
    }
    # The plain object is listed first in the OTBM; the border must still come
    # first in the stack, because a border is a background item.
    doc, _ = _build(analyses, _dump([(0, 0, 100, [900, 4411])]))

    assert doc["floors"]["7"]["tiles"] == [[0, 0, 100, 4411, 900]]


def test_a_tile_without_ground_uses_zero_in_the_ground_position():
    analyses = {900: _analysis(900)}
    doc, _ = _build(analyses, _dump([(0, 0, None, [900])]))

    assert doc["floors"]["7"]["tiles"] == [[0, 0, 0, 900]]


def test_tiles_are_emitted_row_by_row_so_paint_order_is_a_plain_walk():
    analyses = {100: _analysis(100, flags=GROUND_FLAGS)}
    doc, _ = _build(analyses, _dump([
        (2, 1, 100, []), (0, 1, 100, []), (1, 0, 100, []),
    ]))

    assert doc["floors"]["7"]["tiles"] == [
        [1, 0, 100], [0, 1, 100], [2, 1, 100],
    ]


def test_tile_coordinates_are_relative_to_the_map_bounds():
    analyses = {100: _analysis(100, flags=GROUND_FLAGS)}
    doc, _ = _build(analyses, _dump([(5, 9, 100, []), (7, 11, 100, [])], base=(1000, 2000)))

    assert doc["bounds"] == {"minX": 1005, "minY": 2009, "maxX": 1007, "maxY": 2011}
    assert doc["width"] == 3
    assert doc["height"] == 3
    assert doc["floors"]["7"]["tiles"] == [[0, 0, 100], [2, 2, 100]]


def test_floors_stay_independent_even_on_the_same_column():
    analyses = {100: _analysis(100, flags=GROUND_FLAGS), 900: _analysis(900)}
    dump = {
        "data": {
            "nodes": [{
                "features": [
                    {"x": 0, "y": 0, "z": 7,
                     "tiles": [{"x": 0, "y": 0, "tileid": 100, "items": []}]},
                    {"x": 0, "y": 0, "z": 8,
                     "tiles": [{"x": 0, "y": 0, "tileid": None,
                                "items": [{"id": 900}]}]},
                ]
            }]
        }
    }
    doc, _ = _build(analyses, dump)

    assert doc["floors"]["7"]["tiles"] == [[0, 0, 100]]
    assert doc["floors"]["8"]["tiles"] == [[0, 0, 0, 900]]
    assert doc["defaultZ"] == 7


def test_default_z_falls_back_to_the_lowest_floor_when_seven_is_absent():
    analyses = {100: _analysis(100, flags=GROUND_FLAGS)}
    doc, _ = _build(analyses, _dump([(0, 0, 100, [])], z=9))

    assert doc["defaultZ"] == 9


def test_marker_signs_never_reach_the_stack():
    analyses = {100: _analysis(100, flags=GROUND_FLAGS), 2016: _analysis(2016)}
    doc, _ = _build(analyses, _dump([(0, 0, 100, [(2016, 10001)])]))

    assert doc["floors"]["7"]["tiles"] == [[0, 0, 100]]
    assert "2016" not in doc["appearances"]


def test_ground_and_items_share_one_sheet_per_footprint():
    analyses = {
        100: _analysis(100, flags=GROUND_FLAGS, source_path="/tmp/100.png"),
        900: _analysis(900, source_path="/tmp/900.png"),
        800: _analysis(800, source_path="/tmp/800.png", width=64, height=64),
    }
    doc, frame_sources = _build(analyses, _dump([(0, 0, 100, [900, 800])]))

    assert doc["appearances"]["100"]["sheet"] == "sheet-32"
    assert doc["appearances"]["900"]["sheet"] == "sheet-32"
    assert doc["appearances"]["800"]["sheet"] == "sheet-64"
    assert set(doc["sheets"]) == {"sheet-32", "sheet-64"}
    assert doc["sheets"]["sheet-32"]["cellWidth"] == 32
    assert doc["sheets"]["sheet-32"]["image"] == "assets/test-sprites-v6/sheets/sheet-32.png"
    assert frame_sources["sheet-32"] == {
        doc["appearances"]["100"]["gids"][0]: "/tmp/100.png",
        doc["appearances"]["900"]["gids"][0]: "/tmp/900.png",
    }


def test_an_appearance_used_by_no_tile_gets_no_entry():
    analyses = {100: _analysis(100, flags=GROUND_FLAGS), 999: _analysis(999)}
    doc, _ = _build(analyses, _dump([(0, 0, 100, [])]))

    assert set(doc["appearances"]) == {"100"}


def test_multi_frame_appearance_gets_one_gid_per_frame():
    analyses = {
        7: _analysis(7, frame_count=3, animated=True, source_path="/tmp/7.png"),
    }
    doc, _ = _build(analyses, _dump([(0, 0, None, [7])]))

    entry = doc["appearances"]["7"]
    assert entry["gids"] == [0, 1, 2]
    assert entry["animated"] is True
    assert entry["animation"]["frameDurationMs"] == 500


def test_sprite_dimensions_are_emitted_only_when_they_differ_from_a_tile():
    analyses = {
        100: _analysis(100, flags=GROUND_FLAGS, source_path="/tmp/100.png"),
        800: _analysis(800, width=64, height=96, source_path="/tmp/800.png"),
    }
    doc, _ = _build(analyses, _dump([(0, 0, 100, [800])]))

    assert "spriteWidth" not in doc["appearances"]["100"]
    assert "spriteHeight" not in doc["appearances"]["100"]
    assert doc["appearances"]["800"]["spriteWidth"] == 64
    assert doc["appearances"]["800"]["spriteHeight"] == 96


# ── ticket 06: shift + elevation ──────────────────────────────────────────


def test_shift_and_elevation_are_emitted_when_non_zero():
    analyses = {
        10035: _analysis(10035, shift={"x": 8, "y": 8}),
        10033: _analysis(10033, elevation=8),
    }
    doc, _ = _build(analyses, _dump([(0, 0, None, [10035, 10033])]))

    assert doc["appearances"]["10035"]["shift"] == {"x": 8, "y": 8}
    assert "elevation" not in doc["appearances"]["10035"]
    assert doc["appearances"]["10033"]["elevation"] == 8
    assert "shift" not in doc["appearances"]["10033"]


def test_a_zero_shift_or_elevation_is_left_out():
    analyses = {
        1: _analysis(1, shift={"x": 0, "y": 0}, elevation=0),
    }
    doc, _ = _build(analyses, _dump([(0, 0, None, [1])]))

    assert "shift" not in doc["appearances"]["1"]
    assert "elevation" not in doc["appearances"]["1"]


def test_a_shift_on_one_axis_only_is_still_emitted_whole():
    analyses = {1: _analysis(1, shift={"x": 0, "y": 8})}
    doc, _ = _build(analyses, _dump([(0, 0, None, [1])]))

    assert doc["appearances"]["1"]["shift"] == {"x": 0, "y": 8}


# ── a cor do automap ──────────────────────────────────────────────────────


def test_automap_color_is_emitted_beside_shift_and_elevation():
    """Fora do bloco `flags`, que só serializa chave truthy e perderia a cor
    junto com o resto do valor."""
    analyses = {1: _analysis(1, automap_color=129, flags={"automap": True})}
    doc, _ = _build(analyses, _dump([(0, 0, None, [1])]))

    entry = doc["appearances"]["1"]
    assert entry["automapColor"] == 129
    assert "automapColor" not in entry["flags"]


def test_automap_color_zero_is_left_out():
    """Cor 0 é "não pinta o minimapa" — a maioria das aparências."""
    analyses = {1: _analysis(1, automap_color=0)}
    doc, _ = _build(analyses, _dump([(0, 0, None, [1])]))

    assert "automapColor" not in doc["appearances"]["1"]


def test_an_empty_dump_still_produces_a_readable_document():
    doc, frame_sources = _build({}, {"data": {"nodes": []}})

    assert doc["version"] == 6
    assert doc["floors"] == {"7": {"z": 7, "tiles": []}}
    assert doc["appearances"] == {}
    assert doc["sheets"] == {}
    assert frame_sources == {}


# ── flags: the appearances' own, not the old model's ──────────────────────


def test_the_derived_render_role_flags_of_v5_do_not_reach_v6():
    # `isRoof` came from the five-flag roof heuristic and `hookDirection` from
    # the wall-orientation one — both are render roles wearing a flag's
    # clothes, and v6 answers that question with the stack. analyze_item still
    # computes them for the v5 emitter, so they arrive here and must be dropped.
    analyses = {
        1128: _analysis(1128, flags={
            "bank": True, "unpass": True, "unmove": True, "unsight": True,
            "automap": True, "isRoof": True,
        }),
        1026: _analysis(1026, flags={
            "bottom": True, "unpass": True, "unmove": True,
            "hookDirection": "HOOK_TYPE_EAST",
        }),
    }
    doc, _ = _build(analyses, _dump([(0, 0, 1128, [1026])]))

    assert "isRoof" not in doc["appearances"]["1128"]["flags"]
    assert "hookDirection" not in doc["appearances"]["1026"]["flags"]
    assert doc["appearances"]["1128"]["flags"]["bank"] is True
    assert doc["appearances"]["1026"]["flags"]["bottom"] is True


def test_the_floor_transition_flag_survives_because_it_is_game_logic():
    # Derived too, but it answers "does stepping here change floor?" (ADR
    # 0002), not "where does this draw?".
    analyses = {386: _analysis(386, flags={"isFloorTransition": True, "usable": True})}
    doc, _ = _build(analyses, _dump([(0, 0, None, [386])]))

    assert doc["appearances"]["386"]["flags"]["isFloorTransition"] is True


# ── empty tiles ───────────────────────────────────────────────────────────


def test_a_tile_with_nothing_to_draw_is_left_out():
    analyses = {100: _analysis(100, flags=GROUND_FLAGS)}
    dump = _dump([(0, 0, 100, []), (1, 0, None, []), (2, 0, 100, [])])

    doc, _ = _build(analyses, dump)

    assert doc["floors"]["7"]["tiles"] == [[0, 0, 100], [2, 0, 100]]


def test_a_tile_holding_only_a_marker_sign_is_left_out_but_still_sets_bounds():
    analyses = {100: _analysis(100, flags=GROUND_FLAGS), 2016: _analysis(2016)}
    dump = _dump([(0, 0, 100, []), (4, 0, None, [(2016, 10001)])])

    doc, _ = _build(analyses, dump)

    assert doc["floors"]["7"]["tiles"] == [[0, 0, 100]]
    assert doc["width"] == 5


# ── transições de andar ───────────────────────────────────────────────────


TRANSITION_FLAGS = {"isFloorTransition": True, "usable": True}
WALL_FLAGS = {"unpass": True, "unmove": True}


def _floors_dump(tiles_by_z):
    """{z: [(x, y, tileid, [item ids])]} — lembrando que z menor é andar mais
    alto."""
    return {"data": {"nodes": [{"features": [
        {
            "x": 0, "y": 0, "z": z,
            "tiles": [{"x": x, "y": y, "tileid": tileid,
                       "items": [{"id": item} for item in items]}
                      for x, y, tileid, items in tiles],
        }
        for z, tiles in tiles_by_z.items()
    ]}]}}


def test_a_ladder_lands_one_tile_south_and_one_floor_up():
    analyses = {100: _analysis(100, flags=GROUND_FLAGS),
                1948: _analysis(1948, flags=TRANSITION_FLAGS)}
    dump = _floors_dump({
        8: [(0, 0, 100, [1948])],
        7: [(0, 0, 100, []), (0, 1, 100, [])],
    })

    doc, _ = _build(analyses, dump, ladder_ids={1948})

    assert doc["transitions"] == [0, 0, 8, 0, 1, 7]


def test_a_hole_drops_straight_down():
    analyses = {100: _analysis(100, flags=GROUND_FLAGS),
                386: _analysis(386, flags=TRANSITION_FLAGS)}
    dump = _floors_dump({
        7: [(0, 0, 100, [386])],
        8: [(0, 0, 100, [])],
    })

    doc, _ = _build(analyses, dump)

    assert doc["transitions"] == [0, 0, 7, 0, 0, 8]


def test_a_ramp_lands_where_its_floorchange_names():
    analyses = {100: _analysis(100, flags=GROUND_FLAGS), 1951: _analysis(1951)}
    dump = _floors_dump({
        8: [(1, 0, 100, [1951])],
        7: [(0, 0, 100, [])],
    })

    doc, _ = _build(analyses, dump, floorchange_by_id={1951: "west"})

    assert doc["transitions"] == [1, 0, 8, 0, 0, 7]


def test_transition_coordinates_are_relative_to_the_map_bounds():
    analyses = {100: _analysis(100, flags=GROUND_FLAGS),
                1948: _analysis(1948, flags=TRANSITION_FLAGS)}
    dump = _floors_dump({
        8: [(30, 40, 100, [1948])],
        7: [(30, 41, 100, [])],
    })

    doc, _ = _build(analyses, dump, ladder_ids={1948})

    assert doc["bounds"]["minX"] == 30
    assert doc["transitions"] == [0, 0, 8, 0, 1, 7]


def test_a_ladder_with_a_blocked_landing_produces_no_transition():
    analyses = {
        100: _analysis(100, flags=GROUND_FLAGS),
        1948: _analysis(1948, flags=TRANSITION_FLAGS),
        1000: _analysis(1000, flags=WALL_FLAGS),
    }
    dump = _floors_dump({
        8: [(0, 0, 100, [1948])],
        7: [(0, 1, 100, [1000])],
    })

    doc, _ = _build(analyses, dump, ladder_ids={1948})

    assert doc["transitions"] == []


def test_a_ladder_landing_outside_the_bundle_produces_no_transition():
    analyses = {100: _analysis(100, flags=GROUND_FLAGS),
                1948: _analysis(1948, flags=TRANSITION_FLAGS)}
    dump = _floors_dump({
        8: [(0, 0, 100, [1948])],
        7: [(9, 9, 100, [])],
    })

    doc, _ = _build(analyses, dump, ladder_ids={1948})

    assert doc["transitions"] == []


def test_a_transition_into_a_tile_with_nothing_to_draw_is_left_out():
    # A ponta tem que existir no `floors` que o consumidor lê; uma tile vazia
    # não vira linha nenhuma, então uma aresta até ela é aresta para lugar
    # nenhum.
    analyses = {100: _analysis(100, flags=GROUND_FLAGS),
                1948: _analysis(1948, flags=TRANSITION_FLAGS)}
    dump = _floors_dump({
        8: [(0, 0, 100, [1948])],
        7: [(0, 1, None, [])],
    })

    doc, _ = _build(analyses, dump, ladder_ids={1948})

    assert doc["transitions"] == []


def test_a_single_floor_map_declares_no_transitions():
    analyses = {100: _analysis(100, flags=GROUND_FLAGS)}

    doc, _ = _build(analyses, _dump([(0, 0, 100, [])]))

    assert doc["transitions"] == []


def test_without_the_canary_rules_a_ladder_falls_back_to_the_hole_geometry():
    # Sem `items.xml` a flag sozinha não diz a direção: desce na coluna, que é
    # a leitura conservadora — perde ligação, nunca inventa uma errada.
    analyses = {100: _analysis(100, flags=GROUND_FLAGS),
                1948: _analysis(1948, flags=TRANSITION_FLAGS)}
    dump = _floors_dump({
        8: [(0, 0, 100, [1948])],
        7: [(0, 1, 100, [])],
        9: [(0, 0, 100, [])],
    })

    doc, _ = _build(analyses, dump)

    assert doc["transitions"] == [0, 0, 8, 0, 0, 9]


def test_a_route_marker_item_never_reaches_the_stack_even_without_a_uid():
    # A bola de energia (27869) é o caminho da rota pintado no editor: entrada
    # de ferramenta, igual a uma placa. Ela não carrega uid — quem a pintou
    # pintou 219 tiles, e exigir uid em cada um seria exigir 219 cliques —, por
    # isso o corte tem de ser pelo id do item, não pela faixa de uid.
    analyses = {100: _analysis(100, flags=GROUND_FLAGS), 27869: _analysis(27869)}
    doc, _ = _build(analyses, _dump([(0, 0, 100, [27869])]))

    assert doc["floors"]["7"]["tiles"] == [[0, 0, 100]]
    assert "27869" not in doc["appearances"]
