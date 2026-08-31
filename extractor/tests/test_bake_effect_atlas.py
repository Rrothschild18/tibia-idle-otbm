import json
import os

from PIL import Image

import bake_effect_atlas as bea


def _write_effect(sprites_dir, effect_id, num_frames):
    """Mirror what extract_sprites.py writes for an animated effect:
    sprites/effects/<id>/ with one PNG per animation phase + the JSON."""
    effect_dir = os.path.join(sprites_dir, str(effect_id))
    os.makedirs(effect_dir, exist_ok=True)
    sprite_ids = [f"{effect_id}_{i}" for i in range(num_frames)]
    for name in sprite_ids:
        Image.new("RGBA", (32, 32), (10, 20, 30, 255)).save(os.path.join(effect_dir, f"{name}.png"))
    data = {
        "id": effect_id,
        "spriteId": sprite_ids,
        "spriteInfo": {
            "patternWidth": 1,
            "patternHeight": 1,
            "patternDepth": 1,
            "layers": 1,
            "patternFrames": 0,
            "animation": {
                "synchronized": False,
                "loopType": "ANIMATION_LOOP_TYPE_COUNTED",
                "spritePhase": [{"durationMin": 70, "durationMax": 70}] * num_frames,
            },
        },
        "frameGroup": "initial",
    }
    with open(os.path.join(effect_dir, f"{effect_id}.json"), "w", encoding="utf-8") as f:
        json.dump(data, f)


def _redirect(monkeypatch, tmp_path):
    sprites_dir = tmp_path / "sprites_effects"
    atlas_dir = tmp_path / "atlases_effects"
    sprites_dir.mkdir()
    monkeypatch.setattr(bea, "EFFECTS_SPRITES_DIR", str(sprites_dir))
    monkeypatch.setattr(bea, "EFFECTS_ATLAS_DIR", str(atlas_dir))
    return sprites_dir, atlas_dir


# ---------------------------------------------------------------------------
# _effect_frame_list
# ---------------------------------------------------------------------------

def test_effect_frame_list_follows_the_animation_phase_order(tmp_path, monkeypatch):
    sprites_dir, _ = _redirect(monkeypatch, tmp_path)
    _write_effect(str(sprites_dir), 11, 11)

    frames = bea._effect_frame_list(11, bea._load_effect_json(11))

    # Not sorted by key: 11_10 comes last, where the animation puts it.
    assert [key for key, _ in frames] == [f"11_{i}" for i in range(11)]


# ---------------------------------------------------------------------------
# bake_effect_atlas
# ---------------------------------------------------------------------------

def test_bake_effect_atlas_writes_png_and_json_for_the_teleport_effect(tmp_path, monkeypatch):
    sprites_dir, atlas_dir = _redirect(monkeypatch, tmp_path)
    _write_effect(str(sprites_dir), 11, 11)

    atlas = bea.bake_effect_atlas()

    json_path = atlas_dir / "effects.json"
    assert (atlas_dir / "effects.png").exists()
    with open(json_path, encoding="utf-8") as f:
        assert json.load(f) == atlas

    assert list(atlas["frames"].keys()) == [f"11_{i}" for i in range(11)]
    # cell = 32 + 2*1px padding = 34; 11 frames in a single row.
    assert atlas["meta"] == {"image": "effects.png", "size": {"w": 374, "h": 34}}


def test_bake_effect_atlas_packs_only_the_allow_listed_ids(tmp_path, monkeypatch):
    sprites_dir, _ = _redirect(monkeypatch, tmp_path)
    _write_effect(str(sprites_dir), 11, 3)
    # Extraction writes the whole category; the atlas takes only what the
    # game asks for (see ATLAS_EFFECT_IDS).
    _write_effect(str(sprites_dir), 12, 3)

    atlas = bea.bake_effect_atlas()

    assert list(atlas["frames"].keys()) == ["11_0", "11_1", "11_2"]


def test_bake_effect_atlas_writes_nothing_when_the_category_was_never_extracted(tmp_path, monkeypatch, capsys):
    _, atlas_dir = _redirect(monkeypatch, tmp_path)

    atlas = bea.bake_effect_atlas()

    assert atlas["frames"] == {}
    assert not atlas_dir.exists()
    assert "JSON não encontrado" in capsys.readouterr().out


def test_bake_effect_atlas_is_deterministic_across_runs(tmp_path, monkeypatch):
    sprites_dir, atlas_dir = _redirect(monkeypatch, tmp_path)
    _write_effect(str(sprites_dir), 11, 11)

    bea.bake_effect_atlas()
    first_png = (atlas_dir / "effects.png").read_bytes()
    first_json = (atlas_dir / "effects.json").read_bytes()

    bea.bake_effect_atlas()

    assert (atlas_dir / "effects.png").read_bytes() == first_png
    assert (atlas_dir / "effects.json").read_bytes() == first_json
