import json
import os

from PIL import Image

import bake_item_atlas as bia
import bake_item_sheets as bis
import bake_item_sheets_animated as bisa
import build_item_index as bii


# ---------------------------------------------------------------------------
# build_item_index (pure)
# ---------------------------------------------------------------------------

def test_build_item_index_animated_single_cell_item():
    items = [(3555, {
        "spriteId": [f"3555_{i}" for i in range(12)],
        "spriteInfo": {"patternWidth": 1, "patternHeight": 1, "patternDepth": 1,
                        "animation": {"spritePhase": [{} for _ in range(12)]}},
        "flags": {"market": {"category": "ITEM_CATEGORY_BOOTS"}},
    })]

    index = bii.build_item_index(items, static_shard_of={}, animated_shard_of={3555: 0})

    assert index["3555"] == {
        "kind": "animated-sheet",
        "file": "items-animated/items-animated-0.json",
        "frameKeys": [f"3555_{i}" for i in range(12)],
        "stackable": False,
        "spriteCount": 1,
    }


def test_build_item_index_animated_multi_cell_item_sprite_count_excludes_frames():
    # 9058: 8 cells (4x2) * 13 animation frames = 104 sprites. spriteCount must
    # be the CELL count (8), not the total sprite count (104).
    items = [(9058, {
        "spriteId": [f"9058_{i}" for i in range(104)],
        "spriteInfo": {"patternWidth": 4, "patternHeight": 2, "patternDepth": 1,
                        "animation": {"spritePhase": [{} for _ in range(13)]}},
        "flags": {"cumulative": True, "market": {"category": "ITEM_CATEGORY_CREATURE_PRODUCTS"}},
    })]

    index = bii.build_item_index(items, static_shard_of={}, animated_shard_of={9058: 3})

    assert index["9058"]["spriteCount"] == 8
    assert index["9058"]["stackable"] is True
    assert len(index["9058"]["frameKeys"]) == 104
    assert index["9058"]["kind"] == "animated-sheet"
    assert index["9058"]["file"] == "items-animated/items-animated-3.json"


def test_build_item_index_static_single_cell_item_resolves_shard_file():
    items = [(49094, {
        "spriteId": ["49094"],
        "spriteInfo": {"patternWidth": 1, "patternHeight": 1, "patternDepth": 1},
        "flags": {"cumulative": True, "market": {"category": "ITEM_CATEGORY_POTIONS"}},
    })]

    index = bii.build_item_index(items, static_shard_of={49094: 2}, animated_shard_of={})

    assert index["49094"] == {
        "kind": "static-sheet",
        "file": "items-static/items-static-2.json",
        "frameKeys": ["49094"],
        "stackable": True,
        "spriteCount": 1,
    }


def test_build_item_index_static_multi_cell_item_sprite_count_is_frame_count():
    items = [(130, {
        "spriteId": [f"130_{i}" for i in range(8)],
        "spriteInfo": {"patternWidth": 4, "patternHeight": 2, "patternDepth": 1},
        "flags": {"market": {"category": "ITEM_CATEGORY_OTHERS"}},
    })]

    index = bii.build_item_index(items, static_shard_of={130: 0}, animated_shard_of={})

    assert index["130"]["spriteCount"] == 8
    assert index["130"]["kind"] == "static-sheet"
    assert index["130"]["file"] == "items-static/items-static-0.json"


def test_build_item_index_stackable_independent_of_sprite_count():
    # cumulative item with only 1 sprite: stackable True, spriteCount 1.
    items = [(3031, {
        "spriteId": ["3031"],
        "spriteInfo": {"patternWidth": 1, "patternHeight": 1, "patternDepth": 1},
        "flags": {"cumulative": True, "market": {"category": "ITEM_CATEGORY_VALUABLES"}},
    })]

    index = bii.build_item_index(items, static_shard_of={3031: 0}, animated_shard_of={})

    assert index["3031"]["stackable"] is True
    assert index["3031"]["spriteCount"] == 1


# ---------------------------------------------------------------------------
# _compute_shard_of
# ---------------------------------------------------------------------------

def test_compute_shard_of_keeps_multi_cell_item_in_one_shard():
    items = [(1, ["1"]), (2, ["2"]), (100, ["100_0", "100_1", "100_2"]), (3, ["3"])]

    shard_of = bii._compute_shard_of(items, columns=8, num_sheets=2)

    assert set(shard_of.keys()) == {1, 2, 100, 3}
    # every id present, values are valid shard indices
    assert all(0 <= v < 2 for v in shard_of.values())


# ---------------------------------------------------------------------------
# generate_item_index (end to end against fixture files)
# ---------------------------------------------------------------------------

def _write_animated_item(sprites_dir, item_id, n_frames=2):
    item_dir = os.path.join(sprites_dir, str(item_id))
    os.makedirs(item_dir, exist_ok=True)
    keys = [f"{item_id}_{i}" for i in range(n_frames)]
    for key in keys:
        Image.new("RGBA", (32, 32), (1, 2, 3, 255)).save(os.path.join(item_dir, f"{key}.png"))
    data = {
        "id": item_id,
        "spriteId": keys,
        "spriteInfo": {"animation": {"loopType": "ANIMATION_LOOP_TYPE_INFINITE",
                                      "spritePhase": [{} for _ in range(n_frames)]}},
        "flags": {"market": {"category": "ITEM_CATEGORY_SWORDS"}},
    }
    with open(os.path.join(item_dir, f"{item_id}.json"), "w", encoding="utf-8") as f:
        json.dump(data, f)


def _write_static_item(sprites_dir, item_id, market=True):
    Image.new("RGBA", (32, 32), (10, 20, 30, 255)).save(os.path.join(sprites_dir, f"{item_id}.png"))
    flags = {"market": {"category": "ITEM_CATEGORY_POTIONS"}} if market else {"usable": True, "take": True}
    data = {"id": item_id, "spriteId": [str(item_id)], "spriteInfo": {}, "flags": flags}
    with open(os.path.join(sprites_dir, f"{item_id}.json"), "w", encoding="utf-8") as f:
        json.dump(data, f)


def _write_scenery_item(sprites_dir, item_id):
    Image.new("RGBA", (32, 32), (1, 2, 3, 255)).save(os.path.join(sprites_dir, f"{item_id}.png"))
    data = {"id": item_id, "spriteId": [str(item_id)], "spriteInfo": {}, "flags": {"clip": True, "unmove": True}}
    with open(os.path.join(sprites_dir, f"{item_id}.json"), "w", encoding="utf-8") as f:
        json.dump(data, f)


def test_generate_item_index_covers_animated_and_static_excludes_scenery(tmp_path, monkeypatch):
    sprites_dir = tmp_path / "sprites_items"
    sprites_dir.mkdir()
    monkeypatch.setattr(bia, "ITEMS_SPRITES_DIR", str(sprites_dir))
    monkeypatch.setattr(bis, "ITEMS_SPRITES_DIR", str(sprites_dir))
    monkeypatch.setattr(bis, "NUM_SHEETS", 2)
    monkeypatch.setattr(bis, "COLUMNS", 4)
    monkeypatch.setattr(bisa, "ITEMS_SPRITES_DIR", str(sprites_dir))
    monkeypatch.setattr(bisa, "NUM_SHEETS", 2)
    monkeypatch.setattr(bisa, "COLUMNS", 4)

    _write_animated_item(str(sprites_dir), 100, n_frames=3)
    _write_static_item(str(sprites_dir), 200, market=True)
    _write_static_item(str(sprites_dir), 201, market=False)
    _write_scenery_item(str(sprites_dir), 999)

    index = bii.generate_item_index()

    assert set(index.keys()) == {"100", "200", "201"}
    assert index["100"]["kind"] == "animated-sheet"
    assert index["100"]["file"] == "items-animated/items-animated-0.json"
    assert index["200"]["kind"] == "static-sheet"
    assert index["201"]["kind"] == "static-sheet"


def test_generate_item_index_no_orphan_frame_keys_against_real_data():
    """Every frameKey in the real generated index resolves to a frame that
    actually exists in the referenced atlas/sheet JSON on disk."""
    index = bii.generate_item_index()
    assert len(index) > 0

    checked_files = {}
    for item_id, entry in index.items():
        file_path = os.path.join(bii.ATLASES_DIR, entry["file"])
        if file_path not in checked_files:
            with open(file_path, "r", encoding="utf-8") as f:
                checked_files[file_path] = json.load(f)["frames"]
        frames = checked_files[file_path]
        for key in entry["frameKeys"]:
            assert key in frames, f"item {item_id}: frame key {key} missing from {entry['file']}"


def test_main_writes_items_index_json(tmp_path, monkeypatch):
    sprites_dir = tmp_path / "sprites_items"
    sprites_dir.mkdir()
    out_path = tmp_path / "items-index.json"
    monkeypatch.setattr(bia, "ITEMS_SPRITES_DIR", str(sprites_dir))
    monkeypatch.setattr(bis, "ITEMS_SPRITES_DIR", str(sprites_dir))
    monkeypatch.setattr(bisa, "ITEMS_SPRITES_DIR", str(sprites_dir))
    monkeypatch.setattr(bii, "INDEX_PATH", str(out_path))

    _write_static_item(str(sprites_dir), 200, market=True)

    bii.main()

    assert out_path.exists()
    with open(out_path, encoding="utf-8") as f:
        written = json.load(f)
    assert "200" in written
