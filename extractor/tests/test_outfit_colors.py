from PIL import Image

import outfit_colors


def _grid(size, pixels):
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    image.putdata(pixels)
    return image


# ---------------------------------------------------------------------------
# enabled_addons
# ---------------------------------------------------------------------------

def test_enabled_addons_reads_the_bitmask():
    assert outfit_colors.enabled_addons(0) == [0]
    assert outfit_colors.enabled_addons(1) == [0, 1]
    assert outfit_colors.enabled_addons(2) == [0, 2]
    assert outfit_colors.enabled_addons(3) == [0, 1, 2]


# ---------------------------------------------------------------------------
# compose_frame
# ---------------------------------------------------------------------------

def test_compose_frame_paints_the_addon_over_the_base():
    # Base inteira em região de corpo (vermelho na máscara); addon cobrindo só
    # o segundo pixel, em região de pernas (verde).
    base = _grid((2, 1), [(200, 200, 200, 255), (200, 200, 200, 255)])
    base_mask = _grid((2, 1), [(255, 0, 0, 255), (255, 0, 0, 255)])
    addon = _grid((2, 1), [(0, 0, 0, 0), (100, 100, 100, 255)])
    addon_mask = _grid((2, 1), [(0, 0, 0, 0), (0, 255, 0, 255)])

    colors = outfit_colors.region_colors(
        {"head": 0, "body": 94, "legs": 77, "feet": 0}
    )
    out = outfit_colors.compose_frame([(base, base_mask), (addon, addon_mask)], colors)

    body_only = outfit_colors.tint_frame(base, base_mask, colors)
    legs_only = outfit_colors.tint_frame(addon, addon_mask, colors)

    # Onde o addon é transparente sobra a base; onde ele pinta, ele ganha — e
    # com a cor de pernas do monstro, não com a do desenho.
    assert out.getpixel((0, 0)) == body_only.getpixel((0, 0))
    assert out.getpixel((1, 0)) == legs_only.getpixel((1, 0))
    assert out.getpixel((1, 0)) != body_only.getpixel((1, 0))


def test_compose_frame_of_a_single_layer_is_just_the_tint():
    base = _grid((1, 1), [(200, 100, 50, 255)])
    mask = _grid((1, 1), [(255, 0, 0, 255)])
    colors = outfit_colors.region_colors({"head": 0, "body": 94, "legs": 0, "feet": 0})

    assert (
        outfit_colors.compose_frame([(base, mask)], colors).getpixel((0, 0))
        == outfit_colors.tint_frame(base, mask, colors).getpixel((0, 0))
    )


def test_compose_frame_refuses_an_empty_stack():
    try:
        outfit_colors.compose_frame([], {})
    except ValueError as error:
        assert "vazia" in str(error)
    else:
        raise AssertionError("uma pilha vazia tem de estourar")


# ---------------------------------------------------------------------------
# needs_appearance_atlas
# ---------------------------------------------------------------------------

def test_needs_appearance_atlas_covers_cor_e_addon():
    plain = {"looktype": 131, "head": 0, "body": 0, "legs": 0, "feet": 0, "addons": 0}
    assert not outfit_colors.needs_appearance_atlas(plain)
    assert outfit_colors.needs_appearance_atlas({**plain, "body": 94})
    # O addon sozinho já pede atlas próprio: o atlas por looktype é do outfit
    # e não sabe de addon.
    assert outfit_colors.needs_appearance_atlas({**plain, "addons": 1})


def test_appearance_key_carries_the_addon():
    assert (
        outfit_colors.appearance_key(
            {"looktype": 132, "head": 98, "body": 96, "legs": 39, "feet": 38, "addons": 1}
        )
        == "132-98-96-39-38-1"
    )


# ---------------------------------------------------------------------------
# outfit_color — a volta do círculo de matiz
# ---------------------------------------------------------------------------

def test_outfit_color_fecha_o_circulo_no_vermelho():
    # O último passo de matiz é 18/18 = 1, a volta inteira: o mesmo ponto que
    # 0. Preso no setor 5 ele saía magenta, e a paleta ficava sem vermelho
    # nenhum — o 94 é o vermelho puro do Tibia, e o 113 (cabelo da Amazon) o
    # vermelho escuro.
    assert outfit_colors.outfit_color(94) == (255, 0, 0)
    assert outfit_colors.outfit_color(113) == (191, 0, 0)
    assert outfit_colors.outfit_color(132) == (128, 0, 0)
    assert outfit_colors.outfit_color(18) == (255, 191, 191)


def test_outfit_color_da_coluna_cinza_e_das_bordas():
    assert outfit_colors.outfit_color(0) == (255, 255, 255)
    assert outfit_colors.outfit_color(132 + 1) == (255, 255, 255)
    assert outfit_colors.outfit_color(-1) == (255, 255, 255)
