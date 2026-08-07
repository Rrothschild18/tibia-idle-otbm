import map_v6_migration_report as report


def _v5(floors, tilesets=(), sheets=()):
    return {
        "version": 5,
        "tilesets": list(tilesets),
        "sheets": {key: {} for key in sheets},
        "floors": floors,
    }


def _v5_floor(z, ground_data, width, objectgroups=()):
    layers = [{
        "name": "Ground", "type": "tilelayer", "width": width,
        "height": len(ground_data) // width, "data": ground_data,
    }]
    for name, objects in objectgroups:
        layers.append({"name": name, "type": "objectgroup", "objects": objects})
    return {"z": z, "layers": layers}


def _v6(floors, sheets=()):
    return {"version": 6, "sheets": {key: {} for key in sheets}, "floors": floors}


# ── what each format says a tile holds ────────────────────────────────────


def test_v5_names_its_objectgroup_entries_and_counts_its_tilelayer_ground():
    doc = _v5({"7": _v5_floor(7, [1, 0, 0, 0], width=2, objectgroups=[
        ("Borders", [[0, 0, [4411, 0], [4412, 1]]]),
        ("Objects", [[1, 1, [900, 0]]]),
    ])})

    assert report.tile_contents_v5(doc) == {
        (7, 0, 0): {"named": [4411, 4412], "unnamedGrounds": 1},
        (7, 1, 1): {"named": [900], "unnamedGrounds": 0},
    }


def test_v5_names_a_ground_it_redirected_into_an_objectgroup():
    # v5 pushed a large blocking ground out of the tilelayer into the Roof
    # objectgroup with stackIndex -1 — the one case where the file records
    # which appearance a ground is.
    doc = _v5({"7": _v5_floor(7, [0], width=1, objectgroups=[
        ("Roof", [[0, 0, [1128, -1], [900, 0]]]),
    ])})

    assert report.tile_contents_v5(doc) == {
        (7, 0, 0): {"named": [900, 1128], "unnamedGrounds": 0},
    }


def test_v6_names_everything_including_its_ground():
    doc = _v6({"7": {"z": 7, "tiles": [[0, 0, 100, 4411, 900], [1, 1, 0, 900]]}})

    assert report.tile_contents_v6(doc) == {
        (7, 0, 0): {"named": [100, 900, 4411], "unnamedGrounds": 0},
        (7, 1, 1): {"named": [900], "unnamedGrounds": 0},
    }


# ── the comparison ────────────────────────────────────────────────────────


def test_identical_maps_compare_clean():
    v5 = _v5({"7": _v5_floor(7, [1, 0], width=2, objectgroups=[
        ("Objects", [[0, 0, [900, 0]]]),
    ])})
    v6 = _v6({"7": {"z": 7, "tiles": [[0, 0, 100, 900]]}})

    result = report.compare(v5, v6)

    assert result["placementsV5"] == result["placementsV6"] == 2
    assert result["divergentTiles"] == []
    assert result["matches"] is True


def test_stack_order_does_not_count_as_divergence():
    # v6 reorders the stack on purpose — that is the whole change. Only the
    # multiset of appearances has to survive.
    v5 = _v5({"7": _v5_floor(7, [1], width=1, objectgroups=[
        ("Objects", [[0, 0, [900, 0]]]),
        ("Borders", [[0, 0, [4411, 1]]]),
    ])})
    v6 = _v6({"7": {"z": 7, "tiles": [[0, 0, 100, 4411, 900]]}})

    assert report.compare(v5, v6)["matches"] is True


def test_an_appearance_moving_from_the_stack_into_the_ground_slot_is_not_divergence():
    # A `bank` appearance that v5 shoved into an objectgroup is the tile's
    # ground in v6. Nothing was lost — that relocation is the fix.
    v5 = _v5({"7": _v5_floor(7, [0], width=1, objectgroups=[
        ("Roof", [[0, 0, [1128, 0]]]),
    ])})
    v6 = _v6({"7": {"z": 7, "tiles": [[0, 0, 1128]]}})

    assert report.compare(v5, v6)["matches"] is True


def test_a_tile_that_lost_a_stack_entry_is_reported():
    v5 = _v5({"7": _v5_floor(7, [1], width=1, objectgroups=[
        ("Objects", [[0, 0, [900, 0], [901, 1]]]),
    ])})
    v6 = _v6({"7": {"z": 7, "tiles": [[0, 0, 100, 900]]}})

    result = report.compare(v5, v6)

    assert result["divergentTiles"] == [
        {"z": 7, "x": 0, "y": 0, "reason": "sumiu no v6: [901]",
         "v5": [900, 901], "v6": [100, 900]}
    ]
    assert result["matches"] is False


def test_a_stack_entry_swapped_for_another_appearance_is_reported():
    # The whole point of comparing content rather than counts: this tile has
    # the same number of appearances in both formats.
    v5 = _v5({"7": _v5_floor(7, [1], width=1, objectgroups=[
        ("Objects", [[0, 0, [900, 0]]]),
    ])})
    v6 = _v6({"7": {"z": 7, "tiles": [[0, 0, 100, 901]]}})

    result = report.compare(v5, v6)

    assert result["divergentTiles"][0]["reason"] == "sumiu no v6: [900]"
    assert result["matches"] is False


def test_an_appearance_v5_never_had_is_reported():
    v5 = _v5({"7": _v5_floor(7, [0], width=1, objectgroups=[
        ("Objects", [[0, 0, [900, 0]]]),
    ])})
    v6 = _v6({"7": {"z": 7, "tiles": [[0, 0, 0, 900, 901]]}})

    result = report.compare(v5, v6)

    assert result["divergentTiles"] == [
        {"z": 7, "x": 0, "y": 0, "reason": "apareceu no v6: [901]",
         "v5": [900], "v6": [900, 901]}
    ]


def test_a_tile_that_dropped_its_tilelayer_ground_is_reported():
    # v5 had a ground the file doesn't name; v6 names nothing extra, so the
    # ground vanished.
    v5 = _v5({"7": _v5_floor(7, [1], width=1, objectgroups=[
        ("Objects", [[0, 0, [900, 0]]]),
    ])})
    v6 = _v6({"7": {"z": 7, "tiles": [[0, 0, 0, 900]]}})

    result = report.compare(v5, v6)

    assert result["divergentTiles"][0]["reason"] == "apareceu no v6: []"
    assert result["matches"] is False


def test_a_tile_present_in_only_one_format_is_reported():
    v5 = _v5({"7": _v5_floor(7, [1, 0], width=2)})
    v6 = _v6({"7": {"z": 7, "tiles": [[1, 0, 100]]}})

    result = report.compare(v5, v6)

    reasons = {tile["reason"] for tile in result["divergentTiles"]}
    assert reasons == {"tile só no v5", "tile só no v6"}
    assert result["matches"] is False


def test_sheet_counts_are_the_rendered_pngs_not_the_tileset_entries():
    # v5's `tilesets` point at PNGs the `sheets` manifest already lists —
    # adding the two would count ground-32 twice.
    v5 = _v5({}, sheets=["ground-32", "object-32", "border-32", "bottom-64"],
             tilesets=[{"name": "ground-32"}])
    v6 = _v6({}, sheets=["sheet-32", "sheet-64"])

    result = report.compare(v5, v6)

    assert result["sheetsV5"] == 4
    assert result["sheetsV6"] == 2
