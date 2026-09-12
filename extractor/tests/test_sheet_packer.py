from sheet_packer import SAFE_TEXTURE_SIZE, SheetPacker, bucket_for


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

    sheet_key, gids = packer.add_appearance(18609, 32, 32, frame_count=6)

    assert sheet_key == "sheet-32"
    assert gids == [0, 1, 2, 3, 4, 5]


def test_sheet_wraps_to_next_row_past_column_limit():
    packer = SheetPacker()
    columns = packer.columns_for_bucket(32)

    # Fill exactly one row, then add one more — it must land at the start of row 1.
    for i in range(columns):
        packer.add_appearance(1000 + i, 32, 32)
    sheet_key, gids = packer.add_appearance(2000, 32, 32)

    dims = packer.sheet_dims(sheet_key)
    assert dims["rows"] == 2
    rect = packer.gid_to_rect(sheet_key, gids[0])
    assert rect["row"] == 1
    assert rect["col"] == 0


def test_gid_to_rect_pixel_math_matches_row_col():
    packer = SheetPacker()
    columns = packer.columns_for_bucket(32)
    for i in range(columns + 3):
        packer.add_appearance(3000 + i, 32, 32)

    rect = packer.gid_to_rect("sheet-32", columns + 2)

    assert rect["row"] == 1
    assert rect["col"] == 2
    assert rect["x"] == 2 * 32
    assert rect["y"] == 1 * 32
    assert rect["w"] == 32
    assert rect["h"] == 32




def test_packing_is_deterministic_across_independent_runs():
    appearances = [(100, 32, 32, 1), (101, 64, 64, 1), (102, 96, 96, 1)]

    def run():
        packer = SheetPacker()
        return {aid: packer.add_appearance(aid, w, h, fc) for aid, w, h, fc in appearances}

    assert run() == run()


def test_sheet_key_is_the_footprint_alone():
    # map.json v6 has no render role to group by — footprint is the whole key.
    packer = SheetPacker()

    a_key, _ = packer.add_appearance(1, 32, 32)
    b_key, _ = packer.add_appearance(2, 64, 64)

    assert a_key == "sheet-32"
    assert b_key == "sheet-64"


def test_appearances_of_the_same_footprint_share_one_sheet():
    packer = SheetPacker()

    ground_key, ground_gids = packer.add_appearance(100, 32, 32)
    object_key, object_gids = packer.add_appearance(200, 32, 32)

    assert ground_key == object_key == "sheet-32"
    assert ground_gids == [0]
    assert object_gids == [1]


def test_a_sheet_within_the_safe_texture_size_is_not_flagged():
    packer = SheetPacker()
    packer.add_appearance(1, 32, 32)

    assert packer.exceeds_safe_texture_size("sheet-32") is False


def test_the_grid_is_wide_enough_to_fill_the_safe_texture_width():
    packer = SheetPacker()

    for bucket in (32, 64, 128):
        columns = packer.columns_for_bucket(bucket)
        # Preencher a largura segura inteira é o que mantém a folha
        # quase quadrada em vez de crescer só para baixo.
        assert columns * bucket == SAFE_TEXTURE_SIZE




def test_a_sheet_taller_than_the_safe_texture_size_is_flagged():
    packer = SheetPacker()
    columns = packer.columns_for_bucket(32)
    # One row past the safe limit: 2048/32 = 64 rows is the last one that fits.
    for i in range(columns * 65):
        packer.add_appearance(i, 32, 32)

    assert packer.sheet_dims("sheet-32")["pixelHeight"] > SAFE_TEXTURE_SIZE
    assert packer.exceeds_safe_texture_size("sheet-32") is True
