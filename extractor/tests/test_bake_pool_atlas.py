import json
import os

from PIL import Image

import bake_pool_atlas as bpa


def _write_pool_item(sprites_dir, item_id, variants=range(12)):
    """Mirror what extract_sprites.py writes for a splash item: a 4x3 pattern
    grid of fluid colours in sprites/items/<id>/, one PNG per cell."""
    item_dir = os.path.join(sprites_dir, str(item_id))
    os.makedirs(item_dir, exist_ok=True)
    sprite_ids = [f"{item_id}_{v}" for v in variants]
    for name in sprite_ids:
        Image.new("RGBA", (32, 32), (10, 20, 30, 255)).save(os.path.join(item_dir, f"{name}.png"))
    data = {
        "id": item_id,
        "spriteId": sprite_ids,
        "spriteInfo": {
            "patternWidth": 4,
            "patternHeight": 3,
            "patternDepth": 1,
            "layers": 1,
            "patternFrames": 0,
        },
        "frameGroup": "initial",
        "flags": {"bottom": True, "liquidpool": True, "unmove": True},
    }
    with open(os.path.join(item_dir, f"{item_id}.json"), "w", encoding="utf-8") as f:
        json.dump(data, f)


def _write_every_pool_item(sprites_dir):
    for _, chain in bpa.POOL_DECAY_CHAINS:
        for item_id in chain:
            _write_pool_item(sprites_dir, item_id)


def _redirect(monkeypatch, tmp_path):
    sprites_dir = tmp_path / "sprites_items"
    atlas_dir = tmp_path / "atlases_pools"
    sprites_dir.mkdir()
    monkeypatch.setattr(bpa.bia, "ITEMS_SPRITES_DIR", str(sprites_dir))
    monkeypatch.setattr(bpa, "POOLS_ATLAS_DIR", str(atlas_dir))
    return sprites_dir, atlas_dir


# ---------------------------------------------------------------------------
# pool_frame_keys
# ---------------------------------------------------------------------------

def test_pool_frame_keys_covers_both_chains_in_every_fluid():
    pairs = bpa.pool_frame_keys()

    # 3 fluidos (blood/venom/ink) x 6 estágios (full 2886-2888, small 2889-2891).
    assert len(pairs) == 18
    assert set(pairs) == {
        (item_id, variant)
        for _, variant in bpa.FLUID_VARIANTS
        for _, chain in bpa.POOL_DECAY_CHAINS
        for item_id in chain
    }


def test_pool_frame_keys_keeps_a_fluid_decay_sequence_contiguous():
    pairs = bpa.pool_frame_keys()

    # Sangue inteiro primeiro, na ordem do decay das duas cadeias, e só então
    # o próximo fluido — é a sequência que o cliente percorre.
    assert pairs[:6] == [(2886, 2), (2887, 2), (2888, 2), (2889, 2), (2890, 2), (2891, 2)]
    assert pairs[6] == (2886, 4)
    assert pairs[12] == (2886, 8)


# ---------------------------------------------------------------------------
# bake_pool_atlas
# ---------------------------------------------------------------------------

def test_bake_pool_atlas_keys_every_frame_by_item_id_and_variant(tmp_path, monkeypatch):
    sprites_dir, atlas_dir = _redirect(monkeypatch, tmp_path)
    _write_every_pool_item(str(sprites_dir))

    atlas = bpa.bake_pool_atlas()

    json_path = atlas_dir / "pools.json"
    assert (atlas_dir / "pools.png").exists()
    with open(json_path, encoding="utf-8") as f:
        assert json.load(f) == atlas

    # itemId sozinho não basta (não diz o fluido), variante sozinha não basta
    # (não diz o estágio) — a chave carrega os dois.
    assert list(atlas["frames"].keys()) == [
        "2886_2", "2887_2", "2888_2", "2889_2", "2890_2", "2891_2",
        "2886_4", "2887_4", "2888_4", "2889_4", "2890_4", "2891_4",
        "2886_8", "2887_8", "2888_8", "2889_8", "2890_8", "2891_8",
    ]
    # cell = 32 + 2*1px de padding = 34; 18 frames numa linha só.
    assert atlas["meta"] == {"image": "pools.png", "size": {"w": 612, "h": 34}}
    assert atlas["frames"]["2886_2"]["frame"] == {"x": 1, "y": 1, "w": 32, "h": 32}


def test_bake_pool_atlas_packs_only_the_three_fluids_the_game_can_ask_for(tmp_path, monkeypatch):
    sprites_dir, _ = _redirect(monkeypatch, tmp_path)
    _write_every_pool_item(str(sprites_dir))

    atlas = bpa.bake_pool_atlas()

    # A extração escreve as 12 células de cor; undead/fire/energy não deixam
    # poça nenhuma, então as outras 9 variantes nunca custam um frame.
    assert len(atlas["frames"]) == 18
    assert "2889_0" not in atlas["frames"]


def test_bake_pool_atlas_skips_a_variant_with_no_extracted_png(tmp_path, monkeypatch, capsys):
    sprites_dir, _ = _redirect(monkeypatch, tmp_path)
    _write_every_pool_item(str(sprites_dir))
    os.remove(os.path.join(str(sprites_dir), "2890", "2890_4.png"))

    atlas = bpa.bake_pool_atlas()

    assert "2890_4" not in atlas["frames"]
    assert len(atlas["frames"]) == 17
    assert "[skip] pool 2890 variante 4" in capsys.readouterr().out


def test_bake_pool_atlas_skips_a_variant_the_appearance_does_not_declare(tmp_path, monkeypatch, capsys):
    sprites_dir, _ = _redirect(monkeypatch, tmp_path)
    _write_every_pool_item(str(sprites_dir))
    # Um item de poça sem o grid 4x3 completo: a variante 8 não existe nele.
    _write_pool_item(str(sprites_dir), 2891, variants=range(4))

    atlas = bpa.bake_pool_atlas()

    assert "2891_8" not in atlas["frames"]
    assert "[skip] pool 2891 variante 8" in capsys.readouterr().out


def test_bake_pool_atlas_writes_nothing_when_the_sprites_were_never_extracted(tmp_path, monkeypatch, capsys):
    _, atlas_dir = _redirect(monkeypatch, tmp_path)

    atlas = bpa.bake_pool_atlas()

    assert atlas["frames"] == {}
    assert not atlas_dir.exists()
    assert "rode extract_sprites.py primeiro" in capsys.readouterr().out


def test_bake_pool_atlas_is_deterministic_across_runs(tmp_path, monkeypatch):
    sprites_dir, atlas_dir = _redirect(monkeypatch, tmp_path)
    _write_every_pool_item(str(sprites_dir))

    bpa.bake_pool_atlas()
    first_png = (atlas_dir / "pools.png").read_bytes()
    first_json = (atlas_dir / "pools.json").read_bytes()

    bpa.bake_pool_atlas()

    assert (atlas_dir / "pools.png").read_bytes() == first_png
    assert (atlas_dir / "pools.json").read_bytes() == first_json
