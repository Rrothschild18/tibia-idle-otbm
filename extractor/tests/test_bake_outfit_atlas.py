import json
import os

from PIL import Image

import bake_outfit_atlas as boa


def _make_png(path, size, color):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.new("RGBA", size, color).save(path)
    return str(path)


# ---------------------------------------------------------------------------
# pack_outfit_frames
# ---------------------------------------------------------------------------

def test_pack_outfit_frames_lays_out_single_row_with_padding(tmp_path):
    a = _make_png(tmp_path / "a.png", (32, 32), (255, 0, 0, 255))
    b = _make_png(tmp_path / "b.png", (32, 32), (0, 255, 0, 255))

    image, frame_map = boa.pack_outfit_frames([("2_0", a), ("2_1", b)])

    # cell = 32 + 2*1px padding = 34; 2 frames side by side, single row.
    assert image.size == (68, 34)
    assert frame_map == {
        "2_0": {"frame": {"x": 1, "y": 1, "w": 32, "h": 32}},
        "2_1": {"frame": {"x": 35, "y": 1, "w": 32, "h": 32}},
    }


def test_pack_outfit_frames_single_frame(tmp_path):
    a = _make_png(tmp_path / "a.png", (32, 32), (255, 0, 0, 255))

    image, frame_map = boa.pack_outfit_frames([("1", a)])

    assert image.size == (34, 34)
    assert frame_map == {"1": {"frame": {"x": 1, "y": 1, "w": 32, "h": 32}}}


def test_pack_outfit_frames_empty_list(tmp_path):
    image, frame_map = boa.pack_outfit_frames([])

    assert image.size == (0, 0)
    assert frame_map == {}


def test_pack_outfit_frames_preserves_order_not_sorted_by_key(tmp_path):
    a = _make_png(tmp_path / "a.png", (32, 32), (255, 0, 0, 255))
    b = _make_png(tmp_path / "b.png", (32, 32), (0, 255, 0, 255))

    # Deliberately out-of-alphabetical-order keys — pack must follow input
    # order (the outfit's documented frame index order), not sort by key.
    _, frame_map = boa.pack_outfit_frames([("2_10", a), ("2_2", b)])

    assert frame_map["2_10"]["frame"]["x"] == 1
    assert frame_map["2_2"]["frame"]["x"] == 35


# ---------------------------------------------------------------------------
# build_atlas_json
# ---------------------------------------------------------------------------

def test_build_atlas_json_shape():
    frame_map = {"2_0": {"frame": {"x": 1, "y": 1, "w": 32, "h": 32}}}

    atlas = boa.build_atlas_json("2.png", (34, 34), frame_map)

    assert atlas == {
        "frames": frame_map,
        "meta": {"image": "2.png", "size": {"w": 34, "h": 34}},
    }


# ---------------------------------------------------------------------------
# _list_outfit_ids
# ---------------------------------------------------------------------------

def test_list_outfit_ids_finds_multi_frame_dirs_and_single_frame_files(tmp_path, monkeypatch):
    monkeypatch.setattr(boa, "OUTFITS_SPRITES_DIR", str(tmp_path))

    # Multi-frame outfit: subdirectory.
    (tmp_path / "100").mkdir()
    (tmp_path / "100" / "100.json").write_text("{}", encoding="utf-8")

    # Single-frame outfit: top-level json + png.
    (tmp_path / "1.json").write_text("{}", encoding="utf-8")
    (tmp_path / "1.png").write_bytes(b"")

    ids = boa._list_outfit_ids()

    assert ids == [1, 100]


# ---------------------------------------------------------------------------
# bake_outfit (end to end against fixture files)
# ---------------------------------------------------------------------------

def _write_multi_frame_outfit(sprites_dir, outfit_id, num_frames):
    outfit_dir = os.path.join(sprites_dir, str(outfit_id))
    os.makedirs(outfit_dir, exist_ok=True)
    sprite_ids = [f"{outfit_id}_{i}" for i in range(num_frames)]
    for name in sprite_ids:
        Image.new("RGBA", (32, 32), (10, 20, 30, 255)).save(os.path.join(outfit_dir, f"{name}.png"))
    data = {
        "id": outfit_id,
        "frameGroups": [
            {"spriteId": sprite_ids[:4], "frameGroup": "idle"},
            {"spriteId": sprite_ids[4:], "frameGroup": "moving"},
        ],
    }
    with open(os.path.join(outfit_dir, f"{outfit_id}.json"), "w", encoding="utf-8") as f:
        json.dump(data, f)


def _write_single_frame_outfit(sprites_dir, outfit_id):
    Image.new("RGBA", (32, 32), (10, 20, 30, 255)).save(
        os.path.join(sprites_dir, f"{outfit_id}.png")
    )
    data = {"id": outfit_id, "spriteId": [str(outfit_id)]}
    with open(os.path.join(sprites_dir, f"{outfit_id}.json"), "w", encoding="utf-8") as f:
        json.dump(data, f)


def test_bake_outfit_writes_png_and_json_matching_sprite_ids(tmp_path, monkeypatch):
    sprites_dir = tmp_path / "sprites_outfits"
    atlas_dir = tmp_path / "atlases_outfits"
    sprites_dir.mkdir()
    monkeypatch.setattr(boa, "OUTFITS_SPRITES_DIR", str(sprites_dir))
    monkeypatch.setattr(boa, "OUTFITS_ATLAS_DIR", str(atlas_dir))

    _write_multi_frame_outfit(str(sprites_dir), 100, 6)

    atlas = boa.bake_outfit(100)

    png_path = atlas_dir / "100.png"
    json_path = atlas_dir / "100.json"
    assert png_path.exists()
    assert json_path.exists()

    with open(json_path, encoding="utf-8") as f:
        written = json.load(f)
    assert written == atlas
    assert sorted(atlas["frames"].keys()) == sorted(f"100_{i}" for i in range(6))
    # frame order follows the documented idle(0-3)/moving(4+) index order.
    assert list(atlas["frames"].keys()) == [f"100_{i}" for i in range(6)]


def test_bake_outfit_single_frame_outfit(tmp_path, monkeypatch):
    sprites_dir = tmp_path / "sprites_outfits"
    atlas_dir = tmp_path / "atlases_outfits"
    sprites_dir.mkdir()
    monkeypatch.setattr(boa, "OUTFITS_SPRITES_DIR", str(sprites_dir))
    monkeypatch.setattr(boa, "OUTFITS_ATLAS_DIR", str(atlas_dir))

    _write_single_frame_outfit(str(sprites_dir), 1)

    atlas = boa.bake_outfit(1)

    assert list(atlas["frames"].keys()) == ["1"]
    assert (atlas_dir / "1.png").exists()


def test_bake_outfit_finds_frames_split_between_subdir_and_top_level(tmp_path, monkeypatch):
    # Real quirk in extract_sprites.py: an outfit with multiple frame groups
    # that each have exactly one sprite (1 idle + 1 moving, no walk-cycle)
    # gets its JSON written into the subdirectory but its PNGs written to
    # the top-level sprites/outfits/ dir instead (verified against outfit
    # 1015 in the real extracted data).
    sprites_dir = tmp_path / "sprites_outfits"
    atlas_dir = tmp_path / "atlases_outfits"
    sprites_dir.mkdir()
    monkeypatch.setattr(boa, "OUTFITS_SPRITES_DIR", str(sprites_dir))
    monkeypatch.setattr(boa, "OUTFITS_ATLAS_DIR", str(atlas_dir))

    outfit_dir = sprites_dir / "1015"
    outfit_dir.mkdir()
    data = {
        "id": 1015,
        "frameGroups": [
            {"spriteId": ["1015_0"], "frameGroup": "idle"},
            {"spriteId": ["1015_1"], "frameGroup": "moving"},
        ],
    }
    (outfit_dir / "1015.json").write_text(json.dumps(data), encoding="utf-8")
    # PNGs land at the top level, NOT inside outfit_dir.
    Image.new("RGBA", (32, 32), (1, 2, 3, 255)).save(sprites_dir / "1015_0.png")
    Image.new("RGBA", (32, 32), (4, 5, 6, 255)).save(sprites_dir / "1015_1.png")

    atlas = boa.bake_outfit(1015)

    assert list(atlas["frames"].keys()) == ["1015_0", "1015_1"]


def test_bake_outfit_returns_none_when_json_missing(tmp_path, monkeypatch):
    sprites_dir = tmp_path / "sprites_outfits"
    atlas_dir = tmp_path / "atlases_outfits"
    sprites_dir.mkdir()
    monkeypatch.setattr(boa, "OUTFITS_SPRITES_DIR", str(sprites_dir))
    monkeypatch.setattr(boa, "OUTFITS_ATLAS_DIR", str(atlas_dir))

    assert boa.bake_outfit(999) is None
    assert not atlas_dir.exists()


def test_bake_outfit_is_deterministic_across_runs(tmp_path, monkeypatch):
    sprites_dir = tmp_path / "sprites_outfits"
    atlas_dir = tmp_path / "atlases_outfits"
    sprites_dir.mkdir()
    monkeypatch.setattr(boa, "OUTFITS_SPRITES_DIR", str(sprites_dir))
    monkeypatch.setattr(boa, "OUTFITS_ATLAS_DIR", str(atlas_dir))

    _write_multi_frame_outfit(str(sprites_dir), 100, 6)

    boa.bake_outfit(100)
    first_png = (atlas_dir / "100.png").read_bytes()
    first_json = (atlas_dir / "100.json").read_bytes()

    boa.bake_outfit(100)
    second_png = (atlas_dir / "100.png").read_bytes()
    second_json = (atlas_dir / "100.json").read_bytes()

    assert first_png == second_png
    assert first_json == second_json
