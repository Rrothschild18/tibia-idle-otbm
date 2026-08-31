import json
import os

from PIL import Image

import bake_corpse_atlas as bca


def _write_item(sprites_dir, item_id, size=(32, 32)):
    """Mirror what extract_sprites.py writes for a single-sprite item:
    sprites/items/<id>.png + <id>.json, flat."""
    os.makedirs(sprites_dir, exist_ok=True)
    sprite_id = f"{item_id}_0"
    Image.new("RGBA", size, (10, 20, 30, 255)).save(os.path.join(sprites_dir, f"{sprite_id}.png"))
    data = {
        "id": item_id,
        "spriteId": [sprite_id],
        "spriteInfo": {"patternWidth": 1, "patternHeight": 1, "patternDepth": 1, "layers": 1},
        "flags": {"corpse": {}},
    }
    with open(os.path.join(sprites_dir, f"{item_id}.json"), "w", encoding="utf-8") as f:
        json.dump(data, f)


def _write_respawn(root, city, folder, names_by_outfit):
    monsters_dir = os.path.join(root, city, folder, "monsters")
    os.makedirs(monsters_dir, exist_ok=True)
    respawn = {
        "monsterDefs": {
            str(outfit_id): {"name": name, "outfitId": outfit_id}
            for outfit_id, name in names_by_outfit.items()
        }
    }
    with open(os.path.join(monsters_dir, "respawn.json"), "w", encoding="utf-8") as f:
        json.dump(respawn, f)


def _corpse(item_id, *stage_ids):
    return {
        "itemId": item_id,
        "stages": [{"durationSeconds": 10, "itemId": sid} for sid in (item_id,) + stage_ids],
    }


def _redirect(monkeypatch, tmp_path, monster_loot):
    sprites_dir = tmp_path / "sprites_items"
    atlas_dir = tmp_path / "atlases_corpses"
    ready_maps = tmp_path / "ready-maps"
    sprites_dir.mkdir()
    ready_maps.mkdir()

    monkeypatch.setattr(bca.bia, "ITEMS_SPRITES_DIR", str(sprites_dir))
    monkeypatch.setattr(bca, "CORPSES_ATLAS_DIR", str(atlas_dir))
    monkeypatch.setattr(bca, "READY_MAPS_DIRS", (str(ready_maps),))
    monkeypatch.setattr(bca, "_load_monster_loot", lambda: monster_loot)
    return sprites_dir, atlas_dir, ready_maps


# The Rat's full chain, straight out of monster-loot.json.
RAT_LOOT = {"Rat": {"corpse": _corpse(5964, 3994, 3995, 3996), "loot": [], "issues": []}}


# ---------------------------------------------------------------------------
# spawned_monster_names / corpse_item_ids
# ---------------------------------------------------------------------------

def test_spawned_monster_names_dedupes_across_maps_and_roots(tmp_path, monkeypatch):
    _, _, ready_maps = _redirect(monkeypatch, tmp_path, RAT_LOOT)
    _write_respawn(str(ready_maps), "ROOK", "ROOK-HUNT-0002_rats-sewers", {21: "Rat"})
    _write_respawn(str(ready_maps), "ROOK", "ROOK-HUNT-0013_rats", {21: "Rat", 25: "Wolf"})

    assert bca.spawned_monster_names() == ["Rat", "Wolf"]


def test_corpse_item_ids_keeps_the_whole_decay_chain_contiguous(tmp_path, monkeypatch):
    _redirect(monkeypatch, tmp_path, RAT_LOOT)

    # Body first, then every stage — a decay tick that lands on a stage with
    # no texture would blank the corpse mid-rot.
    assert bca.corpse_item_ids(["Rat"], RAT_LOOT) == [5964, 3994, 3995, 3996]


def test_corpse_item_ids_skips_a_monster_that_leaves_no_body(tmp_path, monkeypatch):
    loot = dict(RAT_LOOT)
    loot["A Shielded Astral Glyph"] = {"loot": [], "issues": []}
    _redirect(monkeypatch, tmp_path, loot)

    assert bca.corpse_item_ids(["A Shielded Astral Glyph", "Rat"], loot) == [5964, 3994, 3995, 3996]


# ---------------------------------------------------------------------------
# pack_corpse_frames
# ---------------------------------------------------------------------------

def test_pack_corpse_frames_wraps_into_a_grid_instead_of_one_long_row(tmp_path):
    sprites_dir = tmp_path / "sprites"
    sprites_dir.mkdir()
    frames = []
    for i in range(35):
        path = sprites_dir / f"{i}.png"
        Image.new("RGBA", (64, 64), (0, 0, 0, 255)).save(path)
        frames.append((str(i), str(path)))

    canvas, frame_map = bca.pack_corpse_frames(frames)

    # cell = 64 + 2*1px padding = 66 -> 2048 // 66 = 31 columns, 2 rows.
    assert canvas.size == (31 * 66, 2 * 66)
    assert frame_map["0"]["frame"] == {"x": 1, "y": 1, "w": 64, "h": 64}
    assert frame_map["31"]["frame"] == {"x": 1, "y": 67, "w": 64, "h": 64}


def test_pack_corpse_frames_sizes_the_cell_from_the_biggest_sprite(tmp_path):
    sprites_dir = tmp_path / "sprites"
    sprites_dir.mkdir()
    frames = []
    for i, size in enumerate([(32, 32), (64, 32)]):
        path = sprites_dir / f"{i}.png"
        Image.new("RGBA", size, (0, 0, 0, 255)).save(path)
        frames.append((str(i), str(path)))

    canvas, frame_map = bca.pack_corpse_frames(frames)

    # Widest is 64, tallest 32 — the cell is 66x34, not square.
    assert canvas.size == (2 * 66, 34)
    # The frame rect stays the sprite's own size, so a 32px corpse isn't stretched.
    assert frame_map["0"]["frame"] == {"x": 1, "y": 1, "w": 32, "h": 32}


# ---------------------------------------------------------------------------
# bake_corpse_atlas
# ---------------------------------------------------------------------------

def test_bake_corpse_atlas_keys_every_stage_by_item_id(tmp_path, monkeypatch):
    sprites_dir, atlas_dir, ready_maps = _redirect(monkeypatch, tmp_path, RAT_LOOT)
    _write_respawn(str(ready_maps), "ROOK", "ROOK-HUNT-0002_rats-sewers", {21: "Rat"})
    for item_id in (5964, 3994, 3995, 3996):
        _write_item(str(sprites_dir), item_id)

    atlas = bca.bake_corpse_atlas()

    json_path = atlas_dir / "corpses.json"
    assert (atlas_dir / "corpses.png").exists()
    with open(json_path, encoding="utf-8") as f:
        assert json.load(f) == atlas

    # Keyed by itemId, not by the sprite's own id — that's what the client has.
    assert list(atlas["frames"].keys()) == ["5964", "3994", "3995", "3996"]
    assert atlas["meta"] == {"image": "corpses.png", "size": {"w": 136, "h": 34}}


def test_bake_corpse_atlas_skips_a_stage_with_no_extracted_png(tmp_path, monkeypatch, capsys):
    sprites_dir, _, ready_maps = _redirect(monkeypatch, tmp_path, RAT_LOOT)
    _write_respawn(str(ready_maps), "ROOK", "ROOK-HUNT-0002_rats-sewers", {21: "Rat"})
    for item_id in (5964, 3994, 3996):
        _write_item(str(sprites_dir), item_id)

    atlas = bca.bake_corpse_atlas()

    assert list(atlas["frames"].keys()) == ["5964", "3994", "3996"]
    assert "[skip] corpse 3995" in capsys.readouterr().out


def test_bake_corpse_atlas_packs_only_what_the_built_maps_spawn(tmp_path, monkeypatch):
    loot = dict(RAT_LOOT)
    loot["Abyssador"] = {"corpse": _corpse(16067, 16068), "loot": [], "issues": []}
    sprites_dir, _, ready_maps = _redirect(monkeypatch, tmp_path, loot)
    _write_respawn(str(ready_maps), "ROOK", "ROOK-HUNT-0002_rats-sewers", {21: "Rat"})
    for item_id in (5964, 3994, 3995, 3996, 16067, 16068):
        _write_item(str(sprites_dir), item_id)

    atlas = bca.bake_corpse_atlas()

    # monster-loot.json has 1391 monsters with a corpse; no map spawns
    # Abyssador, so its chain never costs a cell (see the module docstring).
    assert list(atlas["frames"].keys()) == ["5964", "3994", "3995", "3996"]


def test_bake_corpse_atlas_writes_nothing_when_no_map_was_built(tmp_path, monkeypatch, capsys):
    _, atlas_dir, _ = _redirect(monkeypatch, tmp_path, RAT_LOOT)

    atlas = bca.bake_corpse_atlas()

    assert atlas["frames"] == {}
    assert not atlas_dir.exists()
    assert "rode build_map.js primeiro" in capsys.readouterr().out


def test_bake_corpse_atlas_writes_nothing_when_the_sprites_were_never_extracted(tmp_path, monkeypatch, capsys):
    _, atlas_dir, ready_maps = _redirect(monkeypatch, tmp_path, RAT_LOOT)
    _write_respawn(str(ready_maps), "ROOK", "ROOK-HUNT-0002_rats-sewers", {21: "Rat"})

    atlas = bca.bake_corpse_atlas()

    assert atlas["frames"] == {}
    assert not atlas_dir.exists()
    assert "rode extract_sprites.py primeiro" in capsys.readouterr().out


def test_bake_corpse_atlas_is_deterministic_across_runs(tmp_path, monkeypatch):
    sprites_dir, atlas_dir, ready_maps = _redirect(monkeypatch, tmp_path, RAT_LOOT)
    _write_respawn(str(ready_maps), "ROOK", "ROOK-HUNT-0002_rats-sewers", {21: "Rat"})
    for item_id in (5964, 3994, 3995, 3996):
        _write_item(str(sprites_dir), item_id)

    bca.bake_corpse_atlas()
    first_png = (atlas_dir / "corpses.png").read_bytes()
    first_json = (atlas_dir / "corpses.json").read_bytes()

    bca.bake_corpse_atlas()

    assert (atlas_dir / "corpses.png").read_bytes() == first_png
    assert (atlas_dir / "corpses.json").read_bytes() == first_json
