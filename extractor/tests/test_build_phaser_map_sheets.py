import json
import os

from PIL import Image

import build_phaser_map as bpm
from sheet_packer import SheetPacker


def _analysis(appearance_id, *, layer_class_flags=None, available=True, source_path=None,
              width=32, height=32, frame_count=1, animated=False):
    flags = dict(layer_class_flags or {})
    sprites = [
        {
            "available": available,
            "sourcePath": source_path,
            "destPath": f"assets/fake-sprites/{appearance_id}_{i}.png",
            "destAbsPath": f"{source_path}.dest.png" if source_path else None,
            "spriteId": f"{appearance_id}_{i}",
            "width": width,
            "height": height,
        }
        for i in range(frame_count)
    ]
    return {
        "appearanceId": appearance_id,
        "type": "static",
        "hasSprite": available,
        "animated": animated,
        "animation": {"loopType": "infinite"} if animated else None,
        "random": False,
        "flags": flags,
        "spriteInfo": {"patternWidth": 1, "patternHeight": 1, "patternDepth": 1, "boundingSquare": 32},
        "sprites": sprites,
        "issues": [],
    }


def _dump_with_one_object(tile_x=2, tile_y=5, appearance_id=100):
    return {
        "data": {
            "nodes": [
                {
                    "features": [
                        {
                            "x": 0, "y": 0, "z": 7,
                            "tiles": [
                                {"x": tile_x, "y": tile_y, "items": [{"id": appearance_id}]},
                            ],
                        }
                    ]
                }
            ]
        }
    }


def _find_layer(layers, name):
    return next(layer for layer in layers if layer["name"] == name)


def test_object_def_gets_sheet_and_gids_instead_of_sprite_ids(monkeypatch, tmp_path):
    monkeypatch.setattr(bpm, "ITEM_CACHE", {})
    monkeypatch.setattr(bpm, "SHEET_PACKER", SheetPacker())
    monkeypatch.setattr(bpm, "SHEET_FRAME_SOURCES", {})
    monkeypatch.setattr(bpm, "SHEETS_OUTPUT_DIR", str(tmp_path / "sheets"))

    src = tmp_path / "100.png"
    Image.new("RGBA", (32, 32), (255, 0, 0, 255)).save(src)
    analysis_100 = _analysis(100, source_path=str(src))

    def fake_analyze_item(appearance_id):
        bpm.ITEM_CACHE.setdefault(appearance_id, analysis_100)
        return bpm.ITEM_CACHE[appearance_id]

    monkeypatch.setattr(bpm, "analyze_item", fake_analyze_item)

    result = bpm.build_phaser_map(_dump_with_one_object())

    entry = result["objectDefs"]["100"]
    assert "spriteIds" not in entry
    assert entry["sheet"] == "object-32"
    assert entry["gids"] == [0]

    assert "object-32" in result["sheets"]
    assert result["sheets"]["object-32"]["cellWidth"] == 32
    assert result["sheets"]["object-32"]["columns"] == 16
    assert result["version"] == 5

    sheet_png = tmp_path / "sheets" / "object-32.png"
    assert sheet_png.exists()


def test_ground_only_appearance_gets_no_sprite_reference_in_object_defs(monkeypatch, tmp_path):
    # An appearance used ONLY as a ground tileid (never placed as an object)
    # never appears in a stack entry, so its objectDefs record is otherwise
    # dead data — packing it into a sheet would just bloat the sheet with a
    # sprite the renderer never looks up there (ground uses `tilesets`).
    monkeypatch.setattr(bpm, "ITEM_CACHE", {})
    monkeypatch.setattr(bpm, "SHEET_PACKER", SheetPacker())
    monkeypatch.setattr(bpm, "SHEET_FRAME_SOURCES", {})
    monkeypatch.setattr(bpm, "SHEETS_OUTPUT_DIR", str(tmp_path / "sheets"))
    monkeypatch.setattr(bpm, "COPIED_SPRITES", set())

    src = tmp_path / "200.png"
    Image.new("RGBA", (32, 32), (0, 255, 0, 255)).save(src)
    analysis_200 = _analysis(200, source_path=str(src))

    def fake_analyze_item(appearance_id):
        bpm.ITEM_CACHE.setdefault(appearance_id, analysis_200)
        return bpm.ITEM_CACHE[appearance_id]

    monkeypatch.setattr(bpm, "analyze_item", fake_analyze_item)

    dump = {
        "data": {
            "nodes": [{
                "features": [{
                    "x": 0, "y": 0, "z": 7,
                    "tiles": [{"x": 1, "y": 1, "tileid": 200}],
                }]
            }]
        }
    }

    result = bpm.build_phaser_map(dump)

    entry = result["objectDefs"]["200"]
    assert "sheet" not in entry
    assert "gids" not in entry
    assert "spriteIds" not in entry
    assert "object-32" not in result["sheets"]


def test_two_objects_same_size_different_layer_class_get_separate_sheets(monkeypatch, tmp_path):
    monkeypatch.setattr(bpm, "ITEM_CACHE", {})
    monkeypatch.setattr(bpm, "SHEET_PACKER", SheetPacker())
    monkeypatch.setattr(bpm, "SHEET_FRAME_SOURCES", {})
    monkeypatch.setattr(bpm, "SHEETS_OUTPUT_DIR", str(tmp_path / "sheets"))

    src_a = tmp_path / "a.png"
    src_b = tmp_path / "b.png"
    Image.new("RGBA", (32, 32), (255, 0, 0, 255)).save(src_a)
    Image.new("RGBA", (32, 32), (0, 0, 255, 255)).save(src_b)

    analyses = {
        300: _analysis(300, source_path=str(src_a)),  # plain -> "object"
        400: _analysis(400, source_path=str(src_b), layer_class_flags={"bottom": True}),  # -> "bottom"
    }

    def fake_analyze_item(appearance_id):
        bpm.ITEM_CACHE.setdefault(appearance_id, analyses[appearance_id])
        return bpm.ITEM_CACHE[appearance_id]

    monkeypatch.setattr(bpm, "analyze_item", fake_analyze_item)

    dump = {
        "data": {
            "nodes": [{
                "features": [{
                    "x": 0, "y": 0, "z": 7,
                    "tiles": [
                        {"x": 0, "y": 0, "items": [{"id": 300}]},
                        {"x": 1, "y": 0, "items": [{"id": 400}]},
                    ],
                }]
            }]
        }
    }

    result = bpm.build_phaser_map(dump)

    assert result["objectDefs"]["300"]["sheet"] == "object-32"
    assert result["objectDefs"]["400"]["sheet"] == "bottom-32"
    assert set(result["sheets"].keys()) == {"object-32", "bottom-32"}


def test_render_sheet_pastes_frames_at_gid_positions(monkeypatch, tmp_path):
    packer = SheetPacker()
    src_a = tmp_path / "a.png"
    src_b = tmp_path / "b.png"
    Image.new("RGBA", (32, 32), (255, 0, 0, 255)).save(src_a)
    Image.new("RGBA", (32, 32), (0, 0, 255, 255)).save(src_b)

    sheet_key, gids_a = packer.add_appearance(1, "object", 32, 32)
    _, gids_b = packer.add_appearance(2, "object", 32, 32)
    frame_sources = {gids_a[0]: str(src_a), gids_b[0]: str(src_b)}

    image = bpm._render_sheet(packer, sheet_key, frame_sources)

    dims = packer.sheet_dims(sheet_key)
    assert image.size == (dims["pixelWidth"], dims["pixelHeight"])
    assert image.getpixel((0, 0)) == (255, 0, 0, 255)
    assert image.getpixel((32, 0)) == (0, 0, 255, 255)
