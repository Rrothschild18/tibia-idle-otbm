import os

from PIL import Image

import build_phaser_map as bpm
from sheet_packer import SheetPacker


def _analysis(appearance_id, *, source_path=None, width=32, height=32,
              pattern_width=1, pattern_height=1, flags=None):
    return {
        "appearanceId": appearance_id,
        "type": "static",
        "hasSprite": source_path is not None,
        "animated": False,
        "animation": None,
        "random": False,
        "flags": dict(flags or {}),
        "spriteInfo": {
            "patternWidth": pattern_width, "patternHeight": pattern_height,
            "patternDepth": 1, "boundingSquare": pattern_width * pattern_height * 32,
        },
        "sprites": [{
            "available": source_path is not None,
            "sourcePath": source_path,
            "destPath": f"assets/fake-sprites/{appearance_id}.png",
            "destAbsPath": f"{source_path}.dest.png" if source_path else None,
            "spriteId": str(appearance_id),
            "width": width,
            "height": height,
        }],
        "issues": [],
    }


def _ground_dump(tiles):
    """tiles: list of (tile_x, tile_y, tileid)."""
    return {
        "data": {
            "nodes": [{
                "features": [{
                    "x": 0, "y": 0, "z": 7,
                    "tiles": [{"x": x, "y": y, "tileid": tid} for x, y, tid in tiles],
                }]
            }]
        }
    }


def _setup(monkeypatch, tmp_path, analyses):
    monkeypatch.setattr(bpm, "ITEM_CACHE", {})
    monkeypatch.setattr(bpm, "SHEET_PACKER", SheetPacker())
    monkeypatch.setattr(bpm, "SHEET_FRAME_SOURCES", {})
    monkeypatch.setattr(bpm, "SHEETS_OUTPUT_DIR", str(tmp_path / "sheets"))
    monkeypatch.setattr(bpm, "COPIED_SPRITES", set())

    def fake_analyze_item(appearance_id):
        bpm.ITEM_CACHE.setdefault(appearance_id, analyses[appearance_id])
        return bpm.ITEM_CACHE[appearance_id]

    monkeypatch.setattr(bpm, "analyze_item", fake_analyze_item)


def _find_layer(layers, name):
    return next(layer for layer in layers if layer["name"] == name)


def test_ground_tiles_share_one_sheet_tileset_instead_of_one_per_appearance(monkeypatch, tmp_path):
    src_a = tmp_path / "100.png"
    src_b = tmp_path / "101.png"
    Image.new("RGBA", (32, 32), (255, 0, 0, 255)).save(src_a)
    Image.new("RGBA", (32, 32), (0, 255, 0, 255)).save(src_b)

    analyses = {
        100: _analysis(100, source_path=str(src_a)),
        101: _analysis(101, source_path=str(src_b)),
    }
    _setup(monkeypatch, tmp_path, analyses)

    dump = _ground_dump([(0, 0, 100), (1, 0, 101)])
    result = bpm.build_phaser_map(dump)

    assert result["version"] == 5
    assert len(result["tilesets"]) == 1
    tileset = result["tilesets"][0]
    assert tileset["name"] == "ground-32"
    assert tileset["firstgid"] == 1
    assert tileset["columns"] == 16
    assert tileset["tilewidth"] == 32
    assert tileset["image"].endswith("sheets/ground-32.png")

    assert "ground-32" in result["sheets"]
    assert result["sheets"]["ground-32"]["cellWidth"] == 32
    assert result["sheets"]["ground-32"]["columns"] == 16

    ground_layer = _find_layer(result["floors"]["7"]["layers"], "Ground")
    width = result["width"]
    gid_a = ground_layer["data"][0 * width + 0]
    gid_b = ground_layer["data"][0 * width + 1]
    assert {gid_a, gid_b} == {1, 2}

    sheet_png = tmp_path / "sheets" / "ground-32.png"
    assert sheet_png.exists()


def test_ground_appearances_in_different_size_buckets_get_two_tilesets(monkeypatch, tmp_path):
    src_small = tmp_path / "200.png"
    src_big = tmp_path / "201.png"
    Image.new("RGBA", (32, 32), (255, 0, 0, 255)).save(src_small)
    Image.new("RGBA", (64, 64), (0, 0, 255, 255)).save(src_big)

    analyses = {
        200: _analysis(200, source_path=str(src_small), width=32, height=32),
        201: _analysis(201, source_path=str(src_big), width=64, height=64),
    }
    _setup(monkeypatch, tmp_path, analyses)

    dump = _ground_dump([(0, 0, 200), (1, 0, 201)])
    result = bpm.build_phaser_map(dump)

    assert len(result["tilesets"]) == 2
    by_name = {t["name"]: t for t in result["tilesets"]}
    assert set(by_name) == {"ground-32", "ground-64"}
    assert by_name["ground-32"]["firstgid"] == 1
    # Second tileset's firstgid starts after the first sheet's full grid capacity.
    assert by_name["ground-64"]["firstgid"] == 1 + by_name["ground-32"]["tilecount"]


def test_roof_reclassified_ground_tile_excluded_from_ground_tilesets(monkeypatch, tmp_path):
    src = tmp_path / "300.png"
    Image.new("RGBA", (64, 64), (255, 255, 0, 255)).save(src)

    analyses = {
        300: _analysis(
            300, source_path=str(src), width=64, height=64,
            pattern_width=2, pattern_height=2,
            flags={"unpass": True, "unmove": True, "unsight": True, "automap": True, "bank": True},
        ),
    }
    _setup(monkeypatch, tmp_path, analyses)

    dump = _ground_dump([(0, 0, 300)])
    result = bpm.build_phaser_map(dump)

    assert result["tilesets"] == []
    assert "ground-32" not in result["sheets"]
    assert "ground-64" not in result["sheets"]

    # It still renders — as an object placement, not a ground tile — since
    # _is_roof_tile() only redirects it out of the Ground tilelayer; the
    # layerClass it lands in is whatever classify_layer() decides (manual
    # item_classifier override or the flag-based rules), orthogonal to this
    # ground-vs-object redirect.
    entry = result["objectDefs"]["300"]
    assert entry["layerClass"] != "ground"
    assert not entry["sheet"].startswith("ground-")

    ground_layer = _find_layer(result["floors"]["7"]["layers"], "Ground")
    assert ground_layer["data"] == [0]


def test_same_ground_appearance_on_two_floors_reuses_same_gid(monkeypatch, tmp_path):
    src = tmp_path / "400.png"
    Image.new("RGBA", (32, 32), (10, 20, 30, 255)).save(src)
    analyses = {400: _analysis(400, source_path=str(src))}
    _setup(monkeypatch, tmp_path, analyses)

    dump = {
        "data": {
            "nodes": [{
                "features": [
                    {"x": 0, "y": 0, "z": 7, "tiles": [{"x": 0, "y": 0, "tileid": 400}]},
                    {"x": 0, "y": 0, "z": 8, "tiles": [{"x": 0, "y": 0, "tileid": 400}]},
                ]
            }]
        }
    }
    result = bpm.build_phaser_map(dump)

    assert len(result["tilesets"]) == 1
    ground_z7 = _find_layer(result["floors"]["7"]["layers"], "Ground")
    ground_z8 = _find_layer(result["floors"]["8"]["layers"], "Ground")
    assert ground_z7["data"] == ground_z8["data"] == [1]
