import json
import os

from PIL import Image

import bake_item_atlas as bia
import bake_item_sheets as bis


def _make_png(path, size, color):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.new("RGBA", size, color).save(path)
    return str(path)


# ---------------------------------------------------------------------------
# plan_static_sheets
# ---------------------------------------------------------------------------

def test_plan_static_sheets_empty_input_returns_empty_shards():
    plans = bis.plan_static_sheets([], columns=4, num_sheets=3)

    assert len(plans) == 3
    for plan in plans:
        assert plan["frames"] == {}
        assert plan["size"] == (0, 0)


def test_plan_static_sheets_single_cell_items_balanced_across_shards():
    # 8 single-cell items, columns=4, 2 shards -> 4 items (4 cells) per shard.
    items = [(i, [str(i)]) for i in range(8)]

    plans = bis.plan_static_sheets(items, columns=4, num_sheets=2)

    assert len(plans[0]["frames"]) == 4
    assert len(plans[1]["frames"]) == 4
    # first shard: single row of 4 at columns 0-3.
    assert plans[0]["frames"]["0"] == {"x": 0, "y": 0, "w": 32, "h": 32}
    assert plans[0]["frames"]["3"] == {"x": 96, "y": 0, "w": 32, "h": 32}
    assert plans[0]["size"] == (128, 32)


def test_plan_static_sheets_wraps_to_next_row(monkeypatch):
    items = [(i, [str(i)]) for i in range(5)]

    plans = bis.plan_static_sheets(items, columns=4, num_sheets=1)

    assert plans[0]["frames"]["4"] == {"x": 0, "y": 32, "w": 32, "h": 32}
    assert plans[0]["size"] == (128, 64)


def test_plan_static_sheets_keeps_multi_cell_item_together_in_one_shard():
    # Item 100 needs 3 cells; splitting the target evenly (say target=2)
    # must not cut it across the shard boundary.
    items = [(1, ["1"]), (2, ["2"]), (100, ["100_0", "100_1", "100_2"]), (3, ["3"])]

    plans = bis.plan_static_sheets(items, columns=8, num_sheets=2)

    all_keys_per_shard = [set(p["frames"].keys()) for p in plans]
    multi_cell_keys = {"100_0", "100_1", "100_2"}
    # all three cells of item 100 land in the SAME shard.
    assert any(multi_cell_keys.issubset(keys) for keys in all_keys_per_shard)


def test_plan_static_sheets_never_drops_or_duplicates_frames():
    items = [(i, [f"{i}_0", f"{i}_1"]) for i in range(6)]

    plans = bis.plan_static_sheets(items, columns=5, num_sheets=3)

    all_keys = [key for plan in plans for key in plan["frames"]]
    expected = [key for _, keys in items for key in keys]
    assert sorted(all_keys) == sorted(expected)
    assert len(all_keys) == len(set(all_keys))


def test_plan_static_sheets_last_shard_absorbs_remainder():
    # 10 items, 3 shards, columns irrelevant here: target = ceil(10/3) = 4.
    # Shards should end up 4/4/2, not overflow past num_sheets.
    items = [(i, [str(i)]) for i in range(10)]

    plans = bis.plan_static_sheets(items, columns=10, num_sheets=3)

    counts = [len(p["frames"]) for p in plans]
    assert counts == [4, 4, 2]


# ---------------------------------------------------------------------------
# _is_static
# ---------------------------------------------------------------------------

def test_is_static_true_without_animation():
    assert bis._is_static({"spriteInfo": {"patternWidth": 1}})


def test_is_static_false_with_animation():
    assert not bis._is_static({"spriteInfo": {"animation": {"loopType": "ANIMATION_LOOP_TYPE_INFINITE"}}})


# ---------------------------------------------------------------------------
# bake_static_sheets (end to end against fixture files)
# ---------------------------------------------------------------------------

def _write_static_item(sprites_dir, item_id, market=True, n_cells=1):
    keys = [str(item_id)] if n_cells == 1 else [f"{item_id}_{i}" for i in range(n_cells)]
    if n_cells == 1:
        Image.new("RGBA", (32, 32), (10, 20, 30, 255)).save(
            os.path.join(sprites_dir, f"{item_id}.png")
        )
        json_path = os.path.join(sprites_dir, f"{item_id}.json")
    else:
        item_dir = os.path.join(sprites_dir, str(item_id))
        os.makedirs(item_dir, exist_ok=True)
        for key in keys:
            Image.new("RGBA", (32, 32), (10, 20, 30, 255)).save(os.path.join(item_dir, f"{key}.png"))
        json_path = os.path.join(item_dir, f"{item_id}.json")

    flags = {"market": {"category": "ITEM_CATEGORY_POTIONS"}} if market else {"usable": True, "take": True}
    data = {"id": item_id, "spriteId": keys, "spriteInfo": {}, "flags": flags}
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def _write_animated_item(sprites_dir, item_id):
    item_dir = os.path.join(sprites_dir, str(item_id))
    os.makedirs(item_dir, exist_ok=True)
    keys = [f"{item_id}_0", f"{item_id}_1"]
    for key in keys:
        Image.new("RGBA", (32, 32), (1, 2, 3, 255)).save(os.path.join(item_dir, f"{key}.png"))
    data = {
        "id": item_id,
        "spriteId": keys,
        "spriteInfo": {"animation": {"loopType": "ANIMATION_LOOP_TYPE_INFINITE", "spritePhase": [{}, {}]}},
        "flags": {"market": {"category": "ITEM_CATEGORY_SWORDS"}},
    }
    with open(os.path.join(item_dir, f"{item_id}.json"), "w", encoding="utf-8") as f:
        json.dump(data, f)


def _write_scenery_item(sprites_dir, item_id):
    Image.new("RGBA", (32, 32), (1, 2, 3, 255)).save(os.path.join(sprites_dir, f"{item_id}.png"))
    data = {"id": item_id, "spriteId": [str(item_id)], "spriteInfo": {}, "flags": {"clip": True, "unmove": True}}
    with open(os.path.join(sprites_dir, f"{item_id}.json"), "w", encoding="utf-8") as f:
        json.dump(data, f)


def test_bake_static_sheets_writes_expected_files_and_excludes_animated_and_scenery(tmp_path, monkeypatch):
    sprites_dir = tmp_path / "sprites_items"
    sheets_dir = tmp_path / "atlases_items_static"
    sprites_dir.mkdir()
    monkeypatch.setattr(bia, "ITEMS_SPRITES_DIR", str(sprites_dir))
    monkeypatch.setattr(bis, "ITEMS_SPRITES_DIR", str(sprites_dir))
    monkeypatch.setattr(bis, "SHEETS_DIR", str(sheets_dir))
    monkeypatch.setattr(bis, "NUM_SHEETS", 2)
    monkeypatch.setattr(bis, "COLUMNS", 4)

    _write_static_item(str(sprites_dir), 1, market=True)
    _write_static_item(str(sprites_dir), 2, market=True)
    _write_static_item(str(sprites_dir), 3, market=False)  # usable+take, still a candidate
    _write_animated_item(str(sprites_dir), 100)            # excluded: handled by bake_item_atlas.py
    _write_scenery_item(str(sprites_dir), 999)              # excluded: not an equipment candidate

    atlases = bis.bake_static_sheets()

    assert len(atlases) == 2
    all_frame_keys = {key for atlas in atlases for key in atlas["frames"]}
    assert all_frame_keys == {"1", "2", "3"}

    for i, atlas in enumerate(atlases):
        assert os.path.exists(sheets_dir / f"items-static-{i}.png")
        with open(sheets_dir / f"items-static-{i}.json", encoding="utf-8") as f:
            written = json.load(f)
        assert written == atlas


def test_bake_static_sheets_is_deterministic_across_runs(tmp_path, monkeypatch):
    sprites_dir = tmp_path / "sprites_items"
    sheets_dir = tmp_path / "atlases_items_static"
    sprites_dir.mkdir()
    monkeypatch.setattr(bia, "ITEMS_SPRITES_DIR", str(sprites_dir))
    monkeypatch.setattr(bis, "ITEMS_SPRITES_DIR", str(sprites_dir))
    monkeypatch.setattr(bis, "SHEETS_DIR", str(sheets_dir))
    monkeypatch.setattr(bis, "NUM_SHEETS", 2)
    monkeypatch.setattr(bis, "COLUMNS", 4)

    for i in range(1, 6):
        _write_static_item(str(sprites_dir), i, market=True)

    bis.bake_static_sheets()
    first = [(sheets_dir / f"items-static-{i}.png").read_bytes() for i in range(2)]

    bis.bake_static_sheets()
    second = [(sheets_dir / f"items-static-{i}.png").read_bytes() for i in range(2)]

    assert first == second


def test_bake_static_sheets_handles_multi_cell_item(tmp_path, monkeypatch):
    sprites_dir = tmp_path / "sprites_items"
    sheets_dir = tmp_path / "atlases_items_static"
    sprites_dir.mkdir()
    monkeypatch.setattr(bia, "ITEMS_SPRITES_DIR", str(sprites_dir))
    monkeypatch.setattr(bis, "ITEMS_SPRITES_DIR", str(sprites_dir))
    monkeypatch.setattr(bis, "SHEETS_DIR", str(sheets_dir))
    monkeypatch.setattr(bis, "NUM_SHEETS", 1)
    monkeypatch.setattr(bis, "COLUMNS", 8)

    _write_static_item(str(sprites_dir), 130, market=True, n_cells=8)

    atlases = bis.bake_static_sheets()

    assert sorted(atlases[0]["frames"].keys()) == sorted(f"130_{i}" for i in range(8))
