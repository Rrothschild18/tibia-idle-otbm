import build_phaser_map as bpm


def _stub_single_spawn(monkeypatch, outfit_id=21, name="Rat"):
    monkeypatch.setattr(bpm, "_load_monster_lookup", lambda: {name.lower(): outfit_id})
    monkeypatch.setattr(bpm, "_parse_spawn_xml", lambda: [
        {"name": name, "worldX": 100, "worldY": 100, "worldZ": 7, "radius": 1, "spawntime": 60}
    ])


def test_monster_def_references_shared_atlas_when_it_exists(tmp_path, monkeypatch):
    atlas_dir = tmp_path / "atlases_outfits"
    atlas_dir.mkdir()
    (atlas_dir / "21.png").write_bytes(b"")
    (atlas_dir / "21.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(bpm, "OUTFITS_ATLAS_DIR", str(atlas_dir))
    monkeypatch.setattr(bpm, "OUTFITS_ATLAS_ASSETS_ROOT", "assets/outfits")
    monkeypatch.setattr(bpm, "MONSTERS_OUTPUT_DIR", str(tmp_path / "monsters"))
    monkeypatch.setattr(bpm, "_load_outfit_json", lambda outfit_id: {
        "frameGroups": [
            {"spriteId": ["21_0", "21_1", "21_2", "21_3"], "frameGroup": "idle",
             "spriteInfo": {"patternWidth": 4}},
        ]
    })
    _stub_single_spawn(monkeypatch)

    result = bpm.build_monster_respawn({"minX": 0, "minY": 0})

    monster_def = result["monsterDefs"]["21"]
    assert monster_def["atlas"] == {
        "image": "assets/outfits/21.png",
        "json": "assets/outfits/21.json",
    }
    assert "assetsPath" not in monster_def
    assert "assetsRoot" not in result
    # frame keys are untouched by the atlas change
    assert monster_def["idle"] == {
        "south": "21_0", "east": "21_1", "north": "21_2", "west": "21_3",
    }


def test_monster_def_atlas_is_none_when_not_yet_baked(tmp_path, monkeypatch):
    monkeypatch.setattr(bpm, "OUTFITS_ATLAS_DIR", str(tmp_path / "no-such-atlas-dir"))
    monkeypatch.setattr(bpm, "OUTFITS_ATLAS_ASSETS_ROOT", "assets/outfits")
    monkeypatch.setattr(bpm, "MONSTERS_OUTPUT_DIR", str(tmp_path / "monsters"))
    monkeypatch.setattr(bpm, "_load_outfit_json", lambda outfit_id: {"spriteId": ["21_0"]})
    _stub_single_spawn(monkeypatch)

    result = bpm.build_monster_respawn({"minX": 0, "minY": 0})

    assert result["monsterDefs"]["21"]["atlas"] is None


def test_no_per_outfit_sprite_folder_is_created_in_map_output(tmp_path, monkeypatch):
    atlas_dir = tmp_path / "atlases_outfits"
    atlas_dir.mkdir()
    (atlas_dir / "21.png").write_bytes(b"")
    (atlas_dir / "21.json").write_text("{}", encoding="utf-8")

    monsters_output_dir = tmp_path / "monsters"
    monkeypatch.setattr(bpm, "OUTFITS_ATLAS_DIR", str(atlas_dir))
    monkeypatch.setattr(bpm, "OUTFITS_ATLAS_ASSETS_ROOT", "assets/outfits")
    monkeypatch.setattr(bpm, "MONSTERS_OUTPUT_DIR", str(monsters_output_dir))
    monkeypatch.setattr(bpm, "_load_outfit_json", lambda outfit_id: {"spriteId": ["21_0"]})
    _stub_single_spawn(monkeypatch)

    bpm.build_monster_respawn({"minX": 0, "minY": 0})

    assert not (monsters_output_dir / "21").exists()
    assert not hasattr(bpm, "_copy_outfit_sprites")
