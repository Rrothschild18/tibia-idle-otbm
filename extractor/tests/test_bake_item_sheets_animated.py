import json
import os

from PIL import Image

import bake_item_atlas as bia
import bake_item_sheets as bis
import bake_item_sheets_animated as bisa


# ---------------------------------------------------------------------------
# _list_animated_equipment_items
# ---------------------------------------------------------------------------

def _write_animated_item(sprites_dir, item_id, n_frames=2, market=True):
    item_dir = os.path.join(sprites_dir, str(item_id))
    os.makedirs(item_dir, exist_ok=True)
    keys = [f"{item_id}_{i}" for i in range(n_frames)]
    for key in keys:
        Image.new("RGBA", (32, 32), (1, 2, 3, 255)).save(os.path.join(item_dir, f"{key}.png"))
    flags = {"market": {"category": "ITEM_CATEGORY_SWORDS"}} if market else {"usable": True, "take": True}
    data = {
        "id": item_id,
        "spriteId": keys,
        "spriteInfo": {"animation": {"loopType": "ANIMATION_LOOP_TYPE_INFINITE",
                                      "spritePhase": [{} for _ in range(n_frames)]}},
        "flags": flags,
    }
    with open(os.path.join(item_dir, f"{item_id}.json"), "w", encoding="utf-8") as f:
        json.dump(data, f)


def _write_static_item(sprites_dir, item_id):
    Image.new("RGBA", (32, 32), (10, 20, 30, 255)).save(os.path.join(sprites_dir, f"{item_id}.png"))
    data = {
        "id": item_id, "spriteId": [str(item_id)], "spriteInfo": {},
        "flags": {"market": {"category": "ITEM_CATEGORY_POTIONS"}},
    }
    with open(os.path.join(sprites_dir, f"{item_id}.json"), "w", encoding="utf-8") as f:
        json.dump(data, f)


def _write_scenery_item(sprites_dir, item_id):
    Image.new("RGBA", (32, 32), (1, 2, 3, 255)).save(os.path.join(sprites_dir, f"{item_id}.png"))
    data = {"id": item_id, "spriteId": [str(item_id)], "spriteInfo": {}, "flags": {"clip": True, "unmove": True}}
    with open(os.path.join(sprites_dir, f"{item_id}.json"), "w", encoding="utf-8") as f:
        json.dump(data, f)


def test_list_animated_equipment_items_excludes_static_and_scenery(tmp_path, monkeypatch):
    sprites_dir = tmp_path / "sprites_items"
    sprites_dir.mkdir()
    monkeypatch.setattr(bia, "ITEMS_SPRITES_DIR", str(sprites_dir))
    monkeypatch.setattr(bisa, "ITEMS_SPRITES_DIR", str(sprites_dir))

    _write_animated_item(str(sprites_dir), 100, n_frames=3, market=True)
    _write_animated_item(str(sprites_dir), 101, n_frames=2, market=False)  # usable+take, still a candidate
    _write_static_item(str(sprites_dir), 200)
    _write_scenery_item(str(sprites_dir), 999)

    items = bisa._list_animated_equipment_items()

    assert {item_id for item_id, _ in items} == {100, 101}
    keys_by_id = dict(items)
    assert keys_by_id[100] == ["100_0", "100_1", "100_2"]


# ---------------------------------------------------------------------------
# bake_animated_sheets (end to end against fixture files)
# ---------------------------------------------------------------------------

def test_bake_animated_sheets_writes_expected_files_and_excludes_static_and_scenery(tmp_path, monkeypatch):
    sprites_dir = tmp_path / "sprites_items"
    sheets_dir = tmp_path / "atlases_items_animated"
    sprites_dir.mkdir()
    monkeypatch.setattr(bia, "ITEMS_SPRITES_DIR", str(sprites_dir))
    monkeypatch.setattr(bisa, "ITEMS_SPRITES_DIR", str(sprites_dir))
    monkeypatch.setattr(bisa, "SHEETS_DIR", str(sheets_dir))
    monkeypatch.setattr(bisa, "NUM_SHEETS", 2)
    monkeypatch.setattr(bisa, "COLUMNS", 4)

    _write_animated_item(str(sprites_dir), 100, n_frames=3)
    _write_animated_item(str(sprites_dir), 101, n_frames=2)
    _write_static_item(str(sprites_dir), 200)          # excluded: handled by bake_item_sheets.py
    _write_scenery_item(str(sprites_dir), 999)          # excluded: not an equipment candidate

    atlases = bisa.bake_animated_sheets()

    assert len(atlases) == 2
    all_frame_keys = {key for atlas in atlases for key in atlas["frames"]}
    assert all_frame_keys == {"100_0", "100_1", "100_2", "101_0", "101_1"}

    for i, atlas in enumerate(atlases):
        assert os.path.exists(sheets_dir / f"items-animated-{i}.png")
        with open(sheets_dir / f"items-animated-{i}.json", encoding="utf-8") as f:
            written = json.load(f)
        assert written == atlas


def test_bake_animated_sheets_keeps_item_frames_together_in_one_shard(tmp_path, monkeypatch):
    sprites_dir = tmp_path / "sprites_items"
    sheets_dir = tmp_path / "atlases_items_animated"
    sprites_dir.mkdir()
    monkeypatch.setattr(bia, "ITEMS_SPRITES_DIR", str(sprites_dir))
    monkeypatch.setattr(bisa, "ITEMS_SPRITES_DIR", str(sprites_dir))
    monkeypatch.setattr(bisa, "SHEETS_DIR", str(sheets_dir))
    monkeypatch.setattr(bisa, "NUM_SHEETS", 3)
    monkeypatch.setattr(bisa, "COLUMNS", 4)

    # 12 animation frames -- large enough that a naive cell-count split would
    # slice it across shard boundaries if items weren't kept atomic.
    _write_animated_item(str(sprites_dir), 3555, n_frames=12)
    _write_animated_item(str(sprites_dir), 3556, n_frames=1)

    atlases = bisa.bake_animated_sheets()

    per_shard_keys = [set(atlas["frames"].keys()) for atlas in atlases]
    item_3555_keys = {f"3555_{i}" for i in range(12)}
    assert any(item_3555_keys.issubset(keys) for keys in per_shard_keys)


def test_bake_animated_sheets_is_deterministic_across_runs(tmp_path, monkeypatch):
    sprites_dir = tmp_path / "sprites_items"
    sheets_dir = tmp_path / "atlases_items_animated"
    sprites_dir.mkdir()
    monkeypatch.setattr(bia, "ITEMS_SPRITES_DIR", str(sprites_dir))
    monkeypatch.setattr(bisa, "ITEMS_SPRITES_DIR", str(sprites_dir))
    monkeypatch.setattr(bisa, "SHEETS_DIR", str(sheets_dir))
    monkeypatch.setattr(bisa, "NUM_SHEETS", 2)
    monkeypatch.setattr(bisa, "COLUMNS", 4)

    for i in range(1, 6):
        _write_animated_item(str(sprites_dir), i, n_frames=2)

    bisa.bake_animated_sheets()
    first = [(sheets_dir / f"items-animated-{i}.png").read_bytes() for i in range(2)]

    bisa.bake_animated_sheets()
    second = [(sheets_dir / f"items-animated-{i}.png").read_bytes() for i in range(2)]

    assert first == second


def test_bake_animated_sheets_handles_multi_cell_item(tmp_path, monkeypatch):
    """Multi-cell animated items (e.g. real item 9058: 4x2 cells * 13 frames)
    pack every cell-per-frame block verbatim, same as bake_item_sheets.py
    does for multi-cell static items."""
    sprites_dir = tmp_path / "sprites_items"
    sheets_dir = tmp_path / "atlases_items_animated"
    sprites_dir.mkdir()
    monkeypatch.setattr(bia, "ITEMS_SPRITES_DIR", str(sprites_dir))
    monkeypatch.setattr(bisa, "ITEMS_SPRITES_DIR", str(sprites_dir))
    monkeypatch.setattr(bisa, "SHEETS_DIR", str(sheets_dir))
    monkeypatch.setattr(bisa, "NUM_SHEETS", 1)
    monkeypatch.setattr(bisa, "COLUMNS", 8)

    item_dir = sprites_dir / "9058"
    item_dir.mkdir()
    sprite_ids = [f"9058_{i}" for i in range(16)]  # 4x2 cells * 2 frames
    for name in sprite_ids:
        Image.new("RGBA", (32, 32), (1, 2, 3, 255)).save(item_dir / f"{name}.png")
    data = {
        "id": 9058,
        "spriteId": sprite_ids,
        "spriteInfo": {"patternWidth": 4, "patternHeight": 2, "patternDepth": 1,
                        "animation": {"spritePhase": [{}, {}]}},
        "flags": {"cumulative": True, "market": {"category": "ITEM_CATEGORY_CREATURE_PRODUCTS"}},
    }
    (item_dir / "9058.json").write_text(json.dumps(data), encoding="utf-8")

    atlases = bisa.bake_animated_sheets()

    assert sorted(atlases[0]["frames"].keys()) == sorted(sprite_ids)
