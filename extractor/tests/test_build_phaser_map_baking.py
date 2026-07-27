import build_phaser_map as bpm


def _analysis(appearance_id, *, unpass=False, random=False):
    return {
        "appearanceId": appearance_id,
        "type": "static",
        "hasSprite": False,
        "animated": False,
        "random": random,
        "animation": None,
        "flags": {"unpass": unpass},
        "spriteInfo": {"patternWidth": 1, "patternHeight": 1, "patternDepth": 1, "boundingSquare": 32},
        "sprites": [{"available": False, "sourcePath": None, "spriteId": str(appearance_id), "width": 32, "height": 32}],
        "issues": [],
    }


# 100: plain static object, unpass=True (placed twice on the same row) -> bakeable.
# 200: a "random" variant object (multiple sprite choices picked by hunt seed
# at runtime, see spec) -> excluded from baking even though it's not animated.
ANALYSES = {100: _analysis(100, unpass=True), 200: _analysis(200, random=True)}


def _dump():
    return {
        "data": {
            "nodes": [
                {
                    "features": [
                        {
                            "x": 0, "y": 0, "z": 7,
                            "tiles": [
                                {"x": 2, "y": 5, "items": [{"id": 100}]},
                                {"x": 3, "y": 5, "items": [{"id": 200}]},
                                {"x": 4, "y": 5, "items": [{"id": 100}]},
                            ],
                        }
                    ]
                }
            ]
        }
    }


def _find_layer(layers, name):
    return next(layer for layer in layers if layer["name"] == name)


def test_bakeable_entries_move_to_bakedgroup_and_leave_objectgroup(monkeypatch, tmp_path):
    monkeypatch.setattr(bpm, "ITEM_CACHE", {})
    monkeypatch.setattr(bpm, "BAKED_OUTPUT_DIR", str(tmp_path / "baked"))

    def fake_analyze_item(appearance_id):
        bpm.ITEM_CACHE.setdefault(appearance_id, ANALYSES[appearance_id])
        return bpm.ITEM_CACHE[appearance_id]

    monkeypatch.setattr(bpm, "analyze_item", fake_analyze_item)

    result = bpm.build_phaser_map(_dump())

    layers = result["floors"]["7"]["layers"]

    objects_layer = _find_layer(layers, "Objects")
    # only the non-bakeable item (200, at relative tileX=1) remains dynamic
    assert objects_layer["objects"] == [[1, 0, [200, 0]]]

    baked_layer = _find_layer(layers, "BakedObjects")
    assert baked_layer["type"] == "bakedgroup"
    assert len(baked_layer["rows"]) == 1
    row = baked_layer["rows"][0]
    assert row["tileY"] == 0
    assert row["layerClass"] == "object"
    assert row["depthOffset"] == 10
    # both placements of item 100 (relative tileX 0 and 2) had unpass=True
    assert sorted(row["blockedTiles"]) == ["0,0", "2,0"]

    assert result["objectDefs"]["100"]["bakedOnly"] is True
    assert "spriteIds" not in result["objectDefs"]["100"]
    assert "bakedOnly" not in result["objectDefs"]["200"]
    assert result["objectDefs"]["200"]["spriteIds"] == ["200"]


def test_bakedonly_sprite_is_not_copied_but_dynamic_sprite_is(monkeypatch, tmp_path):
    from PIL import Image

    monkeypatch.setattr(bpm, "ITEM_CACHE", {})
    monkeypatch.setattr(bpm, "COPIED_SPRITES", set())
    monkeypatch.setattr(bpm, "BAKED_OUTPUT_DIR", str(tmp_path / "baked"))

    src_dir = tmp_path / "src"
    src_dir.mkdir()
    dest_dir = tmp_path / "sprites_out"

    def _sourced_analysis(appearance_id, *, unpass=False, random=False):
        analysis = _analysis(appearance_id, unpass=unpass, random=random)
        src_path = src_dir / f"{appearance_id}.png"
        Image.new("RGBA", (32, 32), (255, 0, 0, 255)).save(src_path)
        dest_path = dest_dir / f"{appearance_id}.png"
        analysis["sprites"] = [{
            "available": True,
            "sourcePath": str(src_path),
            "destPath": f"assets/fake-sprites/{appearance_id}.png",
            "destAbsPath": str(dest_path),
            "spriteId": str(appearance_id),
            "width": 32,
            "height": 32,
        }]
        return analysis, dest_path

    analysis_100, dest_100 = _sourced_analysis(100, unpass=True)
    analysis_200, dest_200 = _sourced_analysis(200, random=True)
    analyses = {100: analysis_100, 200: analysis_200}

    def fake_analyze_item(appearance_id):
        bpm.ITEM_CACHE.setdefault(appearance_id, analyses[appearance_id])
        return bpm.ITEM_CACHE[appearance_id]

    monkeypatch.setattr(bpm, "analyze_item", fake_analyze_item)

    result = bpm.build_phaser_map(_dump())

    assert result["objectDefs"]["100"]["bakedOnly"] is True
    assert not dest_100.exists(), "bakedOnly sprite should not be copied to sprites/"
    assert dest_200.exists(), "dynamic sprite must still be copied to sprites/"
