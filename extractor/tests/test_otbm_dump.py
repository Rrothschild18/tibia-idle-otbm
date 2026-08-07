from otbm_dump import DEFAULT_Z, floor_zs, iter_tiles


def _dump(*features):
    """One node holding every given feature — the nesting level scripts never
    care about, so tests don't either."""
    return {"data": {"nodes": [{"features": list(features)}]}}


def _feature(tiles, *, x=0, y=0, z=None):
    feature = {"x": x, "y": y, "tiles": tiles}
    if z is not None:
        feature["z"] = z
    return feature


# ======================================================
# iter_tiles
# ======================================================

def test_tile_coordinates_are_relative_to_their_feature():
    tile = {"x": 3, "y": 4}
    dump = _dump(_feature([tile], x=1000, y=2000, z=5))

    assert list(iter_tiles(dump)) == [(1003, 2004, 5, tile)]


def test_feature_without_z_lands_on_the_surface_floor():
    dump = _dump(_feature([{"x": 0, "y": 0}]))

    assert [z for _, _, z, _ in iter_tiles(dump)] == [DEFAULT_Z]


def test_feature_without_origin_starts_at_zero():
    dump = _dump({"tiles": [{"x": 3, "y": 4}], "z": 7})

    assert [(x, y) for x, y, _, _ in iter_tiles(dump)] == [(3, 4)]


def test_tile_missing_a_coordinate_is_skipped():
    # Guessing 0 would silently stack it onto the feature's corner.
    kept = {"x": 1, "y": 1}
    dump = _dump(_feature([{"y": 1}, {"x": 1}, {}, kept], x=10, y=10, z=7))

    assert list(iter_tiles(dump)) == [(11, 11, 7, kept)]


def test_tiles_come_out_in_dump_order_across_nodes_and_features():
    dump = {"data": {"nodes": [
        {"features": [_feature([{"x": 0, "y": 0}, {"x": 1, "y": 0}], x=0, y=0, z=7)]},
        {"features": [_feature([{"x": 0, "y": 0}], x=100, y=100, z=6)]},
    ]}}

    assert [(x, y, z) for x, y, z, _ in iter_tiles(dump)] == [
        (0, 0, 7), (1, 0, 7), (100, 100, 6),
    ]


def test_empty_and_malformed_dumps_yield_nothing():
    assert list(iter_tiles({})) == []
    assert list(iter_tiles({"data": {}})) == []
    assert list(iter_tiles(_dump({"z": 7}))) == []


# ======================================================
# floor_zs
# ======================================================

def test_floor_zs_collects_every_declared_floor():
    dump = _dump(
        _feature([{"x": 0, "y": 0}], z=7),
        _feature([{"x": 0, "y": 0}], z=6),
        _feature([{"x": 1, "y": 0}], z=6),
    )

    assert floor_zs(dump) == {6, 7}


def test_floor_zs_keeps_a_floor_whose_only_feature_has_no_tiles():
    # Real ROOK/TEST dumps do this: three maps declare floor 7 solely through
    # an empty feature. Deriving floors from tiles would drop the floor.
    dump = _dump(
        _feature([], z=7),
        _feature([{"x": 0, "y": 0}], z=8),
    )

    assert floor_zs(dump) == {7, 8}
    assert [z for _, _, z, _ in iter_tiles(dump)] == [8]


def test_floor_zs_defaults_a_feature_without_z_to_the_surface():
    assert floor_zs(_dump(_feature([]))) == {DEFAULT_Z}


def test_floor_zs_of_an_empty_dump_is_empty():
    assert floor_zs({}) == set()
