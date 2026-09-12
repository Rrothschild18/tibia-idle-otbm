import io
import json
import lzma
import os
import sys

import pytest
from PIL import Image

SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import client_sprites as cs


def _encode_sheet(image: Image.Image) -> bytes:
    """Refaz o empacotamento do cliente: 32 bytes de cabeçalho proprietário,
    props do LZMA1, campo de tamanho zerado, payload."""
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="BMP")
    compressed = lzma.compress(
        buffer.getvalue(),
        format=lzma.FORMAT_ALONE,
        filters=[{"id": lzma.FILTER_LZMA1, "preset": 6}],
    )
    props, payload = compressed[:5], compressed[13:]
    return b"\x00" * 24 + b"\x11" * 8 + props + b"\x00" * 8 + payload


def _grid_sheet(sprite_w, sprite_h, columns, rows):
    """Folha em que cada célula tem uma cor única, pra dar pra afirmar *qual*
    célula foi recortada — uma folha de cor sólida passaria com o recorte errado."""
    sheet = Image.new("RGB", (sprite_w * columns, sprite_h * rows))
    for row in range(rows):
        for col in range(columns):
            index = row * columns + col
            cell = Image.new("RGB", (sprite_w, sprite_h), (index * 10 % 256, 40, 90))
            sheet.paste(cell, (col * sprite_w, row * sprite_h))
    return sheet


@pytest.fixture
def assets_dir(tmp_path):
    sheet = _grid_sheet(32, 32, 4, 3)          # 12 sprites, ids 100..111
    (tmp_path / "sprites-fake.bmp.lzma").write_bytes(_encode_sheet(sheet))

    big = _grid_sheet(64, 64, 2, 2)            # 4 sprites, ids 200..203
    (tmp_path / "sprites-big.bmp.lzma").write_bytes(_encode_sheet(big))

    (tmp_path / "catalog-content.json").write_text(json.dumps([
        {"type": "sprite", "file": "sprites-fake.bmp.lzma", "spritetype": 0,
         "firstspriteid": 100, "lastspriteid": 111, "area": 0},
        {"type": "sprite", "file": "sprites-big.bmp.lzma", "spritetype": 3,
         "firstspriteid": 200, "lastspriteid": 203, "area": 0},
        {"type": "appearances", "file": "appearances-deadbeef.dat"},
    ]))
    return str(tmp_path)


def test_decode_sheet_round_trips_the_client_container(assets_dir):
    raw = open(os.path.join(assets_dir, "sprites-fake.bmp.lzma"), "rb").read()

    image = cs.decode_sheet(raw)

    assert image.size == (128, 96)


def test_sprite_size_comes_from_spritetype(assets_dir):
    source = cs.ClientSprites(assets_dir)

    assert source.sprite_image(100).size == (32, 32)
    assert source.sprite_image(200).size == (64, 64)


def test_the_right_cell_is_cropped(assets_dir):
    """O teste que importa: recortar a célula errada ainda devolveria um PNG
    do tamanho certo. Cada célula tem cor própria, então dá pra afirmar qual."""
    source = cs.ClientSprites(assets_dir)

    # id 100 é o offset 0 (linha 0, coluna 0); 105 é o offset 5 (linha 1, coluna 1).
    assert source.sprite_image(100).getpixel((0, 0))[:3] == (0, 40, 90)
    assert source.sprite_image(105).getpixel((0, 0))[:3] == (50, 40, 90)
    assert source.sprite_image(111).getpixel((0, 0))[:3] == (110, 40, 90)


def test_id_outside_every_range_is_none_not_an_error(assets_dir):
    """Appearance apontando pra sprite inexistente é caso conhecido do
    pipeline (`missing_sprite:<id>`), tratado rio abaixo — não pode explodir."""
    source = cs.ClientSprites(assets_dir)

    assert source.sprite_image(150) is None
    assert source.sprite_png(999999) is None


def test_range_boundaries_belong_to_their_sheet(assets_dir):
    source = cs.ClientSprites(assets_dir)

    assert source.sprite_image(111) is not None   # último da primeira folha
    assert source.sprite_image(112) is None       # buraco entre as faixas
    assert source.sprite_image(200) is not None   # primeiro da segunda


def test_sprite_png_is_a_real_png(assets_dir):
    blob = cs.ClientSprites(assets_dir).sprite_png(100)

    assert blob[:8] == b"\x89PNG\r\n\x1a\n"
    assert Image.open(io.BytesIO(blob)).size == (32, 32)


def test_missing_catalog_names_the_fetch_command(tmp_path):
    with pytest.raises(cs.SpriteSheetError) as excinfo:
        cs.ClientSprites(str(tmp_path))

    assert "fetch_assets" in str(excinfo.value)


def test_missing_sheet_file_is_reported_with_its_name(assets_dir):
    os.remove(os.path.join(assets_dir, "sprites-fake.bmp.lzma"))
    source = cs.ClientSprites(assets_dir)

    with pytest.raises(cs.SpriteSheetError) as excinfo:
        source.sprite_image(100)

    assert "sprites-fake.bmp.lzma" in str(excinfo.value)


def test_truncated_sheet_is_reported(assets_dir):
    with pytest.raises(cs.SpriteSheetError):
        cs.decode_sheet(b"\x00" * 10)


def test_cache_evicts_without_losing_correctness(assets_dir):
    source = cs.ClientSprites(assets_dir, cache_size=1)

    first = source.sprite_image(100).getpixel((0, 0))[:3]
    source.sprite_image(200)                      # despeja a primeira folha
    assert source.sprite_image(100).getpixel((0, 0))[:3] == first


# ── contra o cliente real, se estiver baixado ─────────────────────────────────

def _real_assets():
    import paths
    import fetch_assets
    manifest = fetch_assets.load_manifest()
    directory = fetch_assets.assets_dir(paths.TIBIA_CLIENT.resolve(None), manifest)
    return directory if os.path.isdir(directory) else None


def test_real_client_catalog_matches_the_manifest():
    assets = _real_assets()
    if assets is None:
        pytest.skip("cliente não baixado nesta máquina")

    source = cs.ClientSprites(assets)

    assert len(source._entries) == 4927
    assert source.max_sprite_id == 289767
    assert source.appearances_file.endswith(".dat")


@pytest.mark.parametrize("sprite_id,expected", [(0, (32, 32)), (192552, (64, 64))])
def test_real_client_sprites_decode_to_the_declared_size(sprite_id, expected):
    assets = _real_assets()
    if assets is None:
        pytest.skip("cliente não baixado nesta máquina")

    assert cs.ClientSprites(assets).sprite_image(sprite_id).size == expected
