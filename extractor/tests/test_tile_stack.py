import pytest

from tile_stack import GROUND, ITEM, build_tile_stack, draw_slot, top_order


def test_bank_flag_is_the_only_thing_that_makes_an_appearance_ground():
    assert draw_slot({"bank": {"waypoints": 0}}) == GROUND
    assert draw_slot({"clip": True, "unmove": True}) == ITEM
    assert draw_slot({}) == ITEM


def test_passability_does_not_decide_the_draw_slot():
    # An impassable ground (a mountain wall's base, void tile 101) is still
    # ground; a walkable object is still an item. `unpass` answers a different
    # question entirely — see CONTEXT.md, "Draw slot".
    impassable_ground = {"bank": {"waypoints": 0}, "unpass": True, "unmove": True, "unsight": True}
    walkable_item = {"clip": True}

    assert draw_slot(impassable_ground) == GROUND
    assert draw_slot(walkable_item) == ITEM


def test_top_order_comes_straight_from_the_background_flags():
    assert top_order({"clip": True}) == 1
    assert top_order({"bottom": True}) == 2
    assert top_order({"top": True}) == 3


def test_an_appearance_with_no_background_flag_has_no_top_order():
    assert top_order({}) is None
    assert top_order({"unmove": True, "take": True}) is None


def test_lowest_flag_wins_when_an_appearance_carries_more_than_one():
    assert top_order({"clip": True, "top": True}) == 1
    assert top_order({"bottom": True, "top": True}) == 2


def _placement(appearance_id, **flags):
    return (appearance_id, flags)


def test_tile_with_only_a_ground_has_an_empty_stack():
    result = build_tile_stack([_placement(4526, bank={"waypoints": 0})])

    assert result == {"ground": 4526, "stack": []}


def test_tile_with_no_ground_at_all_keeps_the_slot_empty():
    # 10.880 tiles across the current map set carry items but no ground.
    result = build_tile_stack([_placement(1234, clip=True)])

    assert result == {"ground": None, "stack": [1234]}


def test_background_items_are_ordered_by_top_order_ascending():
    result = build_tile_stack([
        _placement(300, top=True),
        _placement(100, clip=True),
        _placement(200, bottom=True),
    ])

    assert result["stack"] == [100, 200, 300]


def test_background_items_come_before_plain_items_regardless_of_insertion_order():
    # This is the inversion the old model had backwards: a border (clip) is a
    # background item and belongs near the floor, under whatever covers it.
    result = build_tile_stack([
        _placement(900),            # plain object, inserted first
        _placement(4411, clip=True),  # border, inserted second
    ])

    assert result["stack"] == [4411, 900]


def test_plain_items_keep_their_insertion_order():
    result = build_tile_stack([
        _placement(30), _placement(10), _placement(20),
    ])

    assert result["stack"] == [30, 10, 20]


def test_items_sharing_a_top_order_keep_their_insertion_order():
    result = build_tile_stack([
        _placement(52, bottom=True),
        _placement(51, bottom=True),
    ])

    assert result["stack"] == [52, 51]


def test_ground_leaves_the_stack_no_matter_where_it_was_inserted():
    result = build_tile_stack([
        _placement(4411, clip=True),
        _placement(4526, bank={"waypoints": 0}),
        _placement(900),
    ])

    assert result == {"ground": 4526, "stack": [4411, 900]}


def test_an_impassable_ground_still_takes_the_ground_slot():
    void_tile = _placement(101, bank={"waypoints": 0}, unpass=True, unmove=True, unsight=True)

    result = build_tile_stack([void_tile, _placement(900)])

    assert result == {"ground": 101, "stack": [900]}


@pytest.mark.parametrize("roof_appearance_id", [1128, 4427, 1316])
def test_the_appearances_that_used_to_form_the_roof_layer_land_in_the_ground_slot(
    roof_appearance_id,
):
    # 1128/4427/1316 were the hand-written ROOF_IDS of item_classifier.py. All
    # three carry `bank`: they are ground, and there is no roof.
    result = build_tile_stack([
        (roof_appearance_id, {"bank": {"waypoints": 0}, "unpass": True,
                              "unmove": True, "unsight": True}),
    ])

    assert result["ground"] == roof_appearance_id
    assert result["stack"] == []


def test_a_second_ground_on_the_same_tile_falls_back_into_the_stack():
    # The single ground slot can hold one appearance. No tile in the current
    # 42 dumps has two, but the model has to stay total: the extra one is still
    # drawn, above the background items, in insertion order.
    result = build_tile_stack([
        _placement(4526, bank={"waypoints": 0}),
        _placement(4411, clip=True),
        _placement(101, bank={"waypoints": 0}),
    ])

    assert result == {"ground": 4526, "stack": [4411, 101]}


def test_empty_tile_yields_an_empty_stack_and_no_ground():
    assert build_tile_stack([]) == {"ground": None, "stack": []}


# ── the two shapes a flags dict arrives in ────────────────────────────────

# Raw `appearances.dat` metadata omits a flag it doesn't have and holds a
# payload dict when it does. The analysis dict `build_phaser_map.analyze_item`
# produces is normalized: every key is always present, holding False when the
# appearance lacks the flag. `draw_slot`/`top_order` see both.
RAW_WALL_FLAGS = {
    "bottom": True, "unpass": True, "unmove": True, "unsight": True,
    "automap": {"color": 114},
}
NORMALIZED_WALL_FLAGS = {
    "fullbank": False, "unmove": True, "unpass": True, "unsight": True,
    "automap": True, "bank": False, "clip": False, "bottom": True,
    "top": False, "hang": False, "usable": False, "forceuse": False,
    "isRoof": False, "isFloorTransition": False, "hookDirection": None,
}
NORMALIZED_GROUND_FLAGS = {**NORMALIZED_WALL_FLAGS, "bank": True, "bottom": False}


def test_an_explicit_false_bank_is_not_ground():
    assert draw_slot(NORMALIZED_WALL_FLAGS) == ITEM
    assert draw_slot({"bank": False}) == ITEM


def test_the_two_flag_shapes_agree_on_the_same_appearance():
    assert draw_slot(RAW_WALL_FLAGS) == draw_slot(NORMALIZED_WALL_FLAGS) == ITEM
    assert top_order(RAW_WALL_FLAGS) == top_order(NORMALIZED_WALL_FLAGS) == 2


def test_a_wall_is_a_background_item_not_a_ground():
    # Appearance 5632 (a sewer wall) has bottom+unpass+unmove+unsight and no
    # `bank`. The old model called this a wall and gave it its own layer; the
    # new one just puts it in the stack at top order 2.
    result = build_tile_stack([(5632, NORMALIZED_WALL_FLAGS)])

    assert result == {"ground": None, "stack": [5632]}


def test_a_normalized_ground_still_takes_the_ground_slot():
    result = build_tile_stack([
        (100, NORMALIZED_GROUND_FLAGS), (5632, NORMALIZED_WALL_FLAGS),
    ])

    assert result == {"ground": 100, "stack": [5632]}
