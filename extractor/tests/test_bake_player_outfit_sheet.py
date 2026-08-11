"""Tests for the player-outfit sheet baker.

Same split of responsibility the creature baker already uses: decoding the
.aec and packing a grid are separate things, tested separately. Here that
means the packing function never opens an outfit — it takes (key, png) pairs
and gives back an image and a mapping.
"""

import json
import os

from PIL import Image

import bake_player_outfit_sheet as bp


def _make_png(path, size=(8, 8), color=(255, 0, 0, 255)):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.new("RGBA", size, color).save(path)
    return str(path)


def _frames(tmp_path, count, size=(8, 8)):
    return [
        (f"k{index}", _make_png(tmp_path / f"{index}.png", size, (index % 256, 0, 0, 255)))
        for index in range(count)
    ]


# ---------------------------------------------------------------------------
# pack_player_frames — the grid
# ---------------------------------------------------------------------------

def test_padding_is_a_shared_gutter_not_a_border_per_cell(tmp_path):
    # Cells are pitched one frame + one gutter apart, with a single gutter of
    # margin around the whole grid. That is what makes 216 frames of 64px in
    # 24 columns come out at 1561x586 and not 1584x594.
    image, frame_map = bp.pack_player_frames(_frames(tmp_path, 3), columns=2)

    assert image.size == (1 + 2 * 9, 1 + 2 * 9)
    assert frame_map["k0"]["frame"] == {"x": 1, "y": 1, "w": 8, "h": 8}
    assert frame_map["k1"]["frame"] == {"x": 10, "y": 1, "w": 8, "h": 8}
    assert frame_map["k2"]["frame"] == {"x": 1, "y": 10, "w": 8, "h": 8}


def test_a_full_player_outfit_is_1561_by_586(tmp_path):
    image, frame_map = bp.pack_player_frames(_frames(tmp_path, 216, size=(64, 64)))

    assert image.size == (1561, 586)
    assert len(frame_map) == 216


def test_one_row_per_phase(tmp_path):
    # 3 addons x 4 directions x 2 layers = 24 frames, and the grid is 24 wide,
    # so row N is phase N. That is the point of the column count: the sheet is
    # readable by eye against the documented axes.
    image, _ = bp.pack_player_frames(_frames(tmp_path, 216, size=(64, 64)))

    assert bp.COLUMNS == 24
    assert image.height == 1 + 9 * 65


def test_pack_preserves_input_order(tmp_path):
    frames = [
        ("128_base_a0_north_0", _make_png(tmp_path / "a.png")),
        ("128_mask_a0_north_0", _make_png(tmp_path / "b.png")),
    ]

    _, frame_map = bp.pack_player_frames(frames, columns=24)

    assert list(frame_map) == ["128_base_a0_north_0", "128_mask_a0_north_0"]
    assert frame_map["128_base_a0_north_0"]["frame"]["x"] == 1


def test_pack_empty_list(tmp_path):
    image, frame_map = bp.pack_player_frames([])

    assert image.size == (0, 0)
    assert frame_map == {}


def test_pack_places_each_frames_pixels_at_its_mapped_rect(tmp_path):
    frames = _frames(tmp_path, 3)

    image, frame_map = bp.pack_player_frames(frames, columns=2)

    for index, (key, _) in enumerate(frames):
        rect = frame_map[key]["frame"]
        assert image.getpixel((rect["x"], rect["y"])) == (index, 0, 0, 255)


# ---------------------------------------------------------------------------
# build_sheet_json
# ---------------------------------------------------------------------------

def test_sheet_json_carries_frames_axes_and_meta():
    frame_map = {"128_base_a0_north_0": {"frame": {"x": 1, "y": 1, "w": 64, "h": 64}}}
    axes = {"directions": 4, "phases": 9, "layers": 2, "addons": 3, "mounts": 1}

    sheet = bp.build_sheet_json("128.png", (1561, 586), frame_map, axes)

    assert sheet == {
        "frames": frame_map,
        "axes": axes,
        "meta": {"image": "128.png", "size": {"w": 1561, "h": 586}},
    }


# ---------------------------------------------------------------------------
# bake_player_outfit — against extracted-shaped fixtures
# ---------------------------------------------------------------------------

def _write_extracted_outfit(sprites_dir, outfit_id, axes=None, size=(64, 64)):
    """Write what extract_sprites.py's player path produces: one PNG per
    explicit frame key plus a JSON carrying spriteId and axes."""
    axes = axes or {"directions": 4, "phases": 9, "layers": 2, "addons": 3, "mounts": 1}
    outfit_dir = os.path.join(sprites_dir, str(outfit_id))
    os.makedirs(outfit_dir, exist_ok=True)

    keys = []
    for phase in range(axes["phases"]):
        for addon in range(axes["addons"]):
            for direction in ("north", "east", "south", "west"):
                for layer in ("base", "mask"):
                    keys.append(f"{outfit_id}_{layer}_a{addon}_{direction}_{phase}")

    for key in keys:
        Image.new("RGBA", size, (1, 2, 3, 255)).save(os.path.join(outfit_dir, f"{key}.png"))

    with open(os.path.join(outfit_dir, f"{outfit_id}.json"), "w", encoding="utf-8") as handle:
        json.dump({"id": outfit_id, "spriteId": keys, "axes": axes}, handle)

    return keys


def _redirect(monkeypatch, tmp_path):
    sprites_dir = tmp_path / "sprites"
    sheets_dir = tmp_path / "sheets"
    sprites_dir.mkdir()
    monkeypatch.setattr(bp, "OUTFITS_SPRITES_DIR", str(sprites_dir))
    monkeypatch.setattr(bp, "SHEETS_DIR", str(sheets_dir))
    return sprites_dir, sheets_dir


def test_bake_writes_png_and_json_for_all_216_frames(tmp_path, monkeypatch):
    sprites_dir, sheets_dir = _redirect(monkeypatch, tmp_path)
    keys = _write_extracted_outfit(str(sprites_dir), 128)

    sheet = bp.bake_player_outfit(128)

    assert (sheets_dir / "128.png").exists()
    written = json.loads((sheets_dir / "128.json").read_text(encoding="utf-8"))
    assert written == sheet
    assert list(sheet["frames"]) == keys
    assert sheet["meta"] == {"image": "128.png", "size": {"w": 1561, "h": 586}}


def test_bake_declares_mounts_as_one_and_packs_no_mount_frame(tmp_path, monkeypatch):
    sprites_dir, _ = _redirect(monkeypatch, tmp_path)
    _write_extracted_outfit(str(sprites_dir), 128)

    sheet = bp.bake_player_outfit(128)

    assert sheet["axes"]["mounts"] == 1
    # The declared axes multiply out to exactly the frames packed — which is
    # only true if the mount axis really was dropped upstream.
    axes = sheet["axes"]
    assert (axes["directions"] * axes["phases"] * axes["layers"]
            * axes["addons"] * axes["mounts"]) == len(sheet["frames"]) == 216


def test_bake_refuses_an_outfit_whose_frames_contradict_its_axes(tmp_path, monkeypatch):
    sprites_dir, sheets_dir = _redirect(monkeypatch, tmp_path)
    _write_extracted_outfit(str(sprites_dir), 128)

    # Drop one frame from the JSON: the count no longer matches the axes.
    path = sprites_dir / "128" / "128.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["spriteId"] = data["spriteId"][:-1]
    path.write_text(json.dumps(data), encoding="utf-8")

    assert bp.bake_player_outfit(128) is None
    assert not (sheets_dir / "128.json").exists()


def test_bake_skips_an_outfit_without_axes(tmp_path, monkeypatch):
    # A creature atlas has no axes block. It belongs to bake_outfit_atlas.py,
    # and this baker must not claim it.
    sprites_dir, _ = _redirect(monkeypatch, tmp_path)
    outfit_dir = sprites_dir / "33"
    outfit_dir.mkdir()
    (outfit_dir / "33.json").write_text(
        json.dumps({"id": 33, "spriteId": ["33_0"]}), encoding="utf-8"
    )

    assert bp.bake_player_outfit(33) is None


def test_bake_returns_none_when_the_outfit_was_never_extracted(tmp_path, monkeypatch):
    _redirect(monkeypatch, tmp_path)

    assert bp.bake_player_outfit(999) is None


def test_bake_is_deterministic_byte_for_byte(tmp_path, monkeypatch):
    sprites_dir, sheets_dir = _redirect(monkeypatch, tmp_path)
    _write_extracted_outfit(str(sprites_dir), 128)

    bp.bake_player_outfit(128)
    first = ((sheets_dir / "128.png").read_bytes(), (sheets_dir / "128.json").read_bytes())

    bp.bake_player_outfit(128)
    second = ((sheets_dir / "128.png").read_bytes(), (sheets_dir / "128.json").read_bytes())

    assert first == second


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def test_player_outfit_ids_only_lists_extracted_ones(tmp_path, monkeypatch):
    sprites_dir, _ = _redirect(monkeypatch, tmp_path)
    _write_extracted_outfit(str(sprites_dir), 128)
    _write_extracted_outfit(str(sprites_dir), 143)
    (sprites_dir / "33").mkdir()  # a creature, never a player outfit

    assert bp.extracted_player_outfit_ids() == [128, 143]
