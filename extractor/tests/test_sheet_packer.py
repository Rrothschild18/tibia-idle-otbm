from sheet_packer import SheetPacker, bucket_for


def test_bucket_for_exact_sizes():
    assert bucket_for(32, 32) == 32
    assert bucket_for(64, 64) == 64
    assert bucket_for(128, 128) == 128


def test_bucket_for_odd_size_rounds_up_to_next_bucket():
    # 96x96 must round UP to 128, not down to 64.
    assert bucket_for(96, 96) == 128
    assert bucket_for(96, 32) == 128


def test_bucket_for_clamps_anything_larger_than_max_bucket():
    assert bucket_for(200, 200) == 128


def test_multi_frame_appearance_gets_consecutive_gids_in_same_sheet():
    packer = SheetPacker()

    sheet_key, gids = packer.add_appearance(18609, "object", 32, 32, frame_count=6)

    assert sheet_key == "object-32"
    assert gids == [0, 1, 2, 3, 4, 5]


def test_sheet_wraps_to_next_row_past_column_limit():
    packer = SheetPacker()
    columns = packer.columns_for_bucket(32)

    # Fill exactly one row, then add one more — it must land at the start of row 1.
    for i in range(columns):
        packer.add_appearance(1000 + i, "object", 32, 32)
    sheet_key, gids = packer.add_appearance(2000, "object", 32, 32)

    dims = packer.sheet_dims(sheet_key)
    assert dims["rows"] == 2
    rect = packer.gid_to_rect(sheet_key, gids[0])
    assert rect["row"] == 1
    assert rect["col"] == 0


def test_gid_to_rect_pixel_math_matches_row_col():
    packer = SheetPacker()
    columns = packer.columns_for_bucket(32)
    for i in range(columns + 3):
        packer.add_appearance(3000 + i, "object", 32, 32)

    rect = packer.gid_to_rect("object-32", columns + 2)

    assert rect["row"] == 1
    assert rect["col"] == 2
    assert rect["x"] == 2 * 32
    assert rect["y"] == 1 * 32
    assert rect["w"] == 32
    assert rect["h"] == 32


def test_different_layer_classes_same_size_get_separate_sheets():
    packer = SheetPacker()

    object_key, _ = packer.add_appearance(1, "object", 32, 32)
    bottom_key, _ = packer.add_appearance(2, "bottom", 32, 32)

    assert object_key == "object-32"
    assert bottom_key == "bottom-32"
    assert object_key != bottom_key


def test_packing_is_deterministic_across_independent_runs():
    appearances = [(100, "object", 32, 32, 1), (101, "roof", 64, 64, 1), (102, "object", 96, 96, 1)]

    def run():
        packer = SheetPacker()
        return {aid: packer.add_appearance(aid, lc, w, h, fc) for aid, lc, w, h, fc in appearances}

    assert run() == run()
