import json
import os

from PIL import Image

import bake_item_atlas as bia


def _make_png(path, size, color):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.new("RGBA", size, color).save(path)
    return str(path)


# ---------------------------------------------------------------------------
# pack_item_frames
# ---------------------------------------------------------------------------

def test_pack_item_frames_lays_out_single_row_with_padding(tmp_path):
    a = _make_png(tmp_path / "a.png", (32, 32), (255, 0, 0, 255))
    b = _make_png(tmp_path / "b.png", (32, 32), (0, 255, 0, 255))

    image, frame_map = bia.pack_item_frames([("3555_0", a), ("3555_1", b)])

    # cell = 32 + 2*1px padding = 34; 2 frames side by side, single row.
    assert image.size == (68, 34)
    assert frame_map == {
        "3555_0": {"frame": {"x": 1, "y": 1, "w": 32, "h": 32}},
        "3555_1": {"frame": {"x": 35, "y": 1, "w": 32, "h": 32}},
    }


def test_pack_item_frames_single_frame(tmp_path):
    a = _make_png(tmp_path / "a.png", (32, 32), (255, 0, 0, 255))

    image, frame_map = bia.pack_item_frames([("49094", a)])

    assert image.size == (34, 34)
    assert frame_map == {"49094": {"frame": {"x": 1, "y": 1, "w": 32, "h": 32}}}


def test_pack_item_frames_empty_list(tmp_path):
    image, frame_map = bia.pack_item_frames([])

    assert image.size == (0, 0)
    assert frame_map == {}


def test_pack_item_frames_preserves_order_not_sorted_by_key(tmp_path):
    a = _make_png(tmp_path / "a.png", (32, 32), (255, 0, 0, 255))
    b = _make_png(tmp_path / "b.png", (32, 32), (0, 255, 0, 255))

    # Deliberately out-of-alphabetical-order keys — pack must follow input
    # order (the item's spriteId order from the extracted metadata), not
    # sort by key. This matters for multi-cell items where cell position
    # within a frame is meaningful even though we don't interpret it.
    _, frame_map = bia.pack_item_frames([("9058_10", a), ("9058_2", b)])

    assert frame_map["9058_10"]["frame"]["x"] == 1
    assert frame_map["9058_2"]["frame"]["x"] == 35


# ---------------------------------------------------------------------------
# build_atlas_json
# ---------------------------------------------------------------------------

def test_build_atlas_json_shape():
    frame_map = {"3555_0": {"frame": {"x": 1, "y": 1, "w": 32, "h": 32}}}

    atlas = bia.build_atlas_json("3555.png", (34, 34), frame_map)

    assert atlas == {
        "frames": frame_map,
        "meta": {"image": "3555.png", "size": {"w": 34, "h": 34}},
    }


# ---------------------------------------------------------------------------
# is_market_item
# ---------------------------------------------------------------------------

def test_is_market_item_true_when_market_flag_present():
    assert bia.is_market_item({"flags": {"market": {"category": "ITEM_CATEGORY_BOOTS"}}})


def test_is_market_item_false_when_market_flag_missing():
    assert not bia.is_market_item({"flags": {"clip": True, "unmove": True}})


def test_is_market_item_false_when_no_flags():
    assert not bia.is_market_item({})


# ---------------------------------------------------------------------------
# is_wearable_without_market
# ---------------------------------------------------------------------------

def test_is_wearable_without_market_true_for_quest_reward_clothes():
    assert bia.is_wearable_without_market(
        {"flags": {"take": True, "clothes": {"slot": 1}, "expire": True}}
    )


def test_is_wearable_without_market_false_when_market_also_present():
    # market present is handled by is_market_item; avoid double-counting.
    assert not bia.is_wearable_without_market(
        {"flags": {"clothes": {"slot": 1}, "market": {"category": "ITEM_CATEGORY_BOOTS"}}}
    )


def test_is_wearable_without_market_false_without_clothes():
    assert not bia.is_wearable_without_market({"flags": {"take": True}})


# ---------------------------------------------------------------------------
# is_portable_consumable_without_market
# ---------------------------------------------------------------------------

def test_is_portable_consumable_without_market_true_for_quest_potion():
    assert bia.is_portable_consumable_without_market(
        {"flags": {"usable": True, "take": True, "multiuse": True}}
    )


def test_is_portable_consumable_without_market_false_when_corpse():
    # usable+take corpses are lootable but not equipment/consumables.
    assert not bia.is_portable_consumable_without_market(
        {"flags": {"usable": True, "take": True, "corpse": True, "container": True}}
    )


def test_is_portable_consumable_without_market_false_when_scenery_container():
    assert not bia.is_portable_consumable_without_market(
        {"flags": {"usable": True, "take": True, "unpass": True, "automap": {"color": 1}}}
    )


def test_is_portable_consumable_without_market_false_when_market_also_present():
    assert not bia.is_portable_consumable_without_market(
        {"flags": {"usable": True, "take": True, "market": {"category": "ITEM_CATEGORY_POTIONS"}}}
    )


def test_is_portable_consumable_without_market_false_without_take_or_usable():
    assert not bia.is_portable_consumable_without_market({"flags": {"usable": True}})
    assert not bia.is_portable_consumable_without_market({"flags": {"take": True}})


def test_is_portable_consumable_without_market_true_for_cumulative_currency_without_usable():
    # Real gold coin (id 3031): cumulative + take, no usable flag at all —
    # would otherwise be excluded despite being core inventory content.
    assert bia.is_portable_consumable_without_market(
        {"flags": {"cumulative": True, "take": True, "cyclopediaitem": {"cyclopedia_type": 3031}}}
    )


def test_is_portable_consumable_without_market_false_for_cumulative_scenery():
    assert not bia.is_portable_consumable_without_market(
        {"flags": {"cumulative": True, "take": True, "container": True, "corpse": True}}
    )


# ---------------------------------------------------------------------------
# is_equipment_candidate
# ---------------------------------------------------------------------------

def test_is_equipment_candidate_true_for_market_item():
    assert bia.is_equipment_candidate({"flags": {"market": {"category": "ITEM_CATEGORY_SWORDS"}}})


def test_is_equipment_candidate_true_for_wearable_without_market():
    assert bia.is_equipment_candidate({"flags": {"clothes": {"slot": 1}}})


def test_is_equipment_candidate_true_for_portable_consumable_without_market():
    assert bia.is_equipment_candidate({"flags": {"usable": True, "take": True}})


def test_is_equipment_candidate_false_for_scenery():
    assert not bia.is_equipment_candidate({"flags": {"clip": True, "unmove": True}})


def test_is_equipment_candidate_false_for_corpse():
    assert not bia.is_equipment_candidate(
        {"flags": {"usable": True, "take": True, "corpse": True, "container": True}}
    )


# ---------------------------------------------------------------------------
# _list_item_ids
# ---------------------------------------------------------------------------

def test_list_item_ids_finds_multi_frame_dirs_and_single_frame_files(tmp_path, monkeypatch):
    monkeypatch.setattr(bia, "ITEMS_SPRITES_DIR", str(tmp_path))

    # Multi-frame item: subdirectory.
    (tmp_path / "3555").mkdir()
    (tmp_path / "3555" / "3555.json").write_text("{}", encoding="utf-8")

    # Single-frame item: top-level json + png.
    (tmp_path / "49094.json").write_text("{}", encoding="utf-8")
    (tmp_path / "49094.png").write_bytes(b"")

    ids = bia._list_item_ids()

    assert ids == [3555, 49094]


# ---------------------------------------------------------------------------
# bake_item (end to end against fixture files)
# ---------------------------------------------------------------------------

def _write_animated_market_item(sprites_dir, item_id, num_frames, category="ITEM_CATEGORY_BOOTS"):
    item_dir = os.path.join(sprites_dir, str(item_id))
    os.makedirs(item_dir, exist_ok=True)
    sprite_ids = [f"{item_id}_{i}" for i in range(num_frames)]
    for name in sprite_ids:
        Image.new("RGBA", (32, 32), (10, 20, 30, 255)).save(os.path.join(item_dir, f"{name}.png"))
    data = {
        "id": item_id,
        "spriteId": sprite_ids,
        "spriteInfo": {"patternWidth": 1, "patternHeight": 1, "patternDepth": 1, "layers": 1},
        "flags": {"take": True, "market": {"category": category}},
    }
    with open(os.path.join(item_dir, f"{item_id}.json"), "w", encoding="utf-8") as f:
        json.dump(data, f)


def _write_single_frame_market_item(sprites_dir, item_id, category="ITEM_CATEGORY_POTIONS"):
    Image.new("RGBA", (32, 32), (10, 20, 30, 255)).save(
        os.path.join(sprites_dir, f"{item_id}.png")
    )
    data = {
        "id": item_id,
        "spriteId": [str(item_id)],
        "flags": {"cumulative": True, "market": {"category": category}},
    }
    with open(os.path.join(sprites_dir, f"{item_id}.json"), "w", encoding="utf-8") as f:
        json.dump(data, f)


def _write_non_market_scenery_item(sprites_dir, item_id):
    Image.new("RGBA", (32, 32), (10, 20, 30, 255)).save(
        os.path.join(sprites_dir, f"{item_id}.png")
    )
    data = {
        "id": item_id,
        "spriteId": [str(item_id)],
        "flags": {"clip": True, "unmove": True},
    }
    with open(os.path.join(sprites_dir, f"{item_id}.json"), "w", encoding="utf-8") as f:
        json.dump(data, f)


def test_bake_item_writes_png_and_json_matching_sprite_ids(tmp_path, monkeypatch):
    sprites_dir = tmp_path / "sprites_items"
    atlas_dir = tmp_path / "atlases_items"
    sprites_dir.mkdir()
    monkeypatch.setattr(bia, "ITEMS_SPRITES_DIR", str(sprites_dir))
    monkeypatch.setattr(bia, "ITEMS_ATLAS_DIR", str(atlas_dir))

    _write_animated_market_item(str(sprites_dir), 3555, 12)

    atlas = bia.bake_item(3555)

    png_path = atlas_dir / "3555.png"
    json_path = atlas_dir / "3555.json"
    assert png_path.exists()
    assert json_path.exists()

    with open(json_path, encoding="utf-8") as f:
        written = json.load(f)
    assert written == atlas
    assert list(atlas["frames"].keys()) == [f"3555_{i}" for i in range(12)]


def test_bake_item_single_frame_item(tmp_path, monkeypatch):
    sprites_dir = tmp_path / "sprites_items"
    atlas_dir = tmp_path / "atlases_items"
    sprites_dir.mkdir()
    monkeypatch.setattr(bia, "ITEMS_SPRITES_DIR", str(sprites_dir))
    monkeypatch.setattr(bia, "ITEMS_ATLAS_DIR", str(atlas_dir))

    _write_single_frame_market_item(str(sprites_dir), 49094)

    atlas = bia.bake_item(49094)

    assert list(atlas["frames"].keys()) == ["49094"]
    assert (atlas_dir / "49094.png").exists()


def test_bake_item_skips_non_market_items(tmp_path, monkeypatch):
    sprites_dir = tmp_path / "sprites_items"
    atlas_dir = tmp_path / "atlases_items"
    sprites_dir.mkdir()
    monkeypatch.setattr(bia, "ITEMS_SPRITES_DIR", str(sprites_dir))
    monkeypatch.setattr(bia, "ITEMS_ATLAS_DIR", str(atlas_dir))

    _write_non_market_scenery_item(str(sprites_dir), 100)

    assert bia.bake_item(100) is None
    assert not atlas_dir.exists()


def test_bake_item_returns_none_when_json_missing(tmp_path, monkeypatch):
    sprites_dir = tmp_path / "sprites_items"
    atlas_dir = tmp_path / "atlases_items"
    sprites_dir.mkdir()
    monkeypatch.setattr(bia, "ITEMS_SPRITES_DIR", str(sprites_dir))
    monkeypatch.setattr(bia, "ITEMS_ATLAS_DIR", str(atlas_dir))

    assert bia.bake_item(999) is None
    assert not atlas_dir.exists()


def test_bake_item_is_deterministic_across_runs(tmp_path, monkeypatch):
    sprites_dir = tmp_path / "sprites_items"
    atlas_dir = tmp_path / "atlases_items"
    sprites_dir.mkdir()
    monkeypatch.setattr(bia, "ITEMS_SPRITES_DIR", str(sprites_dir))
    monkeypatch.setattr(bia, "ITEMS_ATLAS_DIR", str(atlas_dir))

    _write_animated_market_item(str(sprites_dir), 3555, 12)

    bia.bake_item(3555)
    first_png = (atlas_dir / "3555.png").read_bytes()
    first_json = (atlas_dir / "3555.json").read_bytes()

    bia.bake_item(3555)
    second_png = (atlas_dir / "3555.png").read_bytes()
    second_json = (atlas_dir / "3555.json").read_bytes()

    assert first_png == second_png
    assert first_json == second_json


def test_bake_item_multi_cell_item_packs_all_cells_verbatim(tmp_path, monkeypatch):
    """Multi-cell market items (patternWidth/Height/Depth > 1, e.g. stack-count
    or hook-direction variants like real item 9058) still bake correctly:
    every cell in the original spriteId order gets its own addressable
    frame, with no attempt to interpret what the extra cells mean."""
    sprites_dir = tmp_path / "sprites_items"
    atlas_dir = tmp_path / "atlases_items"
    sprites_dir.mkdir()
    monkeypatch.setattr(bia, "ITEMS_SPRITES_DIR", str(sprites_dir))
    monkeypatch.setattr(bia, "ITEMS_ATLAS_DIR", str(atlas_dir))

    item_dir = sprites_dir / "9058"
    item_dir.mkdir()
    sprite_ids = [f"9058_{i}" for i in range(16)]  # 4x2 cells * 2 frames
    for name in sprite_ids:
        Image.new("RGBA", (32, 32), (1, 2, 3, 255)).save(item_dir / f"{name}.png")
    data = {
        "id": 9058,
        "spriteId": sprite_ids,
        "spriteInfo": {"patternWidth": 4, "patternHeight": 2, "patternDepth": 1, "layers": 1},
        "flags": {"cumulative": True, "market": {"category": "ITEM_CATEGORY_CREATURE_PRODUCTS"}},
    }
    (item_dir / "9058.json").write_text(json.dumps(data), encoding="utf-8")

    atlas = bia.bake_item(9058)

    assert list(atlas["frames"].keys()) == sprite_ids
