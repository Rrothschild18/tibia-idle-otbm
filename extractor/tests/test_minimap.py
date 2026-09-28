import os
import sys

SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import minimap


# ======================================================
# A paleta — fórmula, não tabela
# ======================================================


def test_palette_index_zero_is_black():
    assert minimap.palette_rgb(0) == (0, 0, 0)


def test_palette_is_the_6x6x6_cube_in_steps_of_51():
    assert minimap.palette_rgb(129) == (3 * 51, 3 * 51, 3 * 51)
    assert minimap.palette_rgb(186) == (5 * 51, 1 * 51, 0)


def test_palette_last_index_is_white():
    assert minimap.palette_rgb(215) == (255, 255, 255)


def test_palette_index_out_of_range_is_black():
    """216 é o primeiro índice que não existe, e negativo nunca deveria chegar
    aqui — os dois são ausência de cor, não um erro que explode o render."""
    assert minimap.palette_rgb(216) == (0, 0, 0)
    assert minimap.palette_rgb(-1) == (0, 0, 0)


def test_palette_bytes_has_one_triple_per_slot_of_a_png_palette():
    data = minimap.palette_bytes()

    assert len(data) == 256 * 3
    assert tuple(data[129 * 3:129 * 3 + 3]) == minimap.palette_rgb(129)
    assert tuple(data[216 * 3:]) == tuple(bytes((256 - 216) * 3))


# ======================================================
# A cor de um tile
# ======================================================


def test_topmost_item_with_color_wins_over_the_ground():
    assert minimap.tile_minimap_color(24, [186, 129]) == 129


def test_an_item_without_color_does_not_hide_the_one_below_it():
    """Cor 0 é "não pinta": o item existe na pilha e simplesmente não entra
    na disputa — senão uma caixa em cima da grama apagaria o tile."""
    assert minimap.tile_minimap_color(24, [129, 0, 0]) == 129


def test_ground_wins_when_no_item_has_color():
    assert minimap.tile_minimap_color(24, [0, 0]) == 24


def test_ground_alone_is_the_ground_color():
    assert minimap.tile_minimap_color(24, []) == 24


def test_a_tile_with_nothing_colored_is_empty():
    assert minimap.tile_minimap_color(0, [0]) == 0
    assert minimap.tile_minimap_color(0, []) == 0


# ======================================================
# Mundo -> pixel
# ======================================================


BOUNDS = {"minX": 980, "minY": 970, "maxX": 1240, "maxY": 1190}


def test_world_to_pixel_is_a_plain_translation():
    assert minimap.world_to_pixel(980, 970, BOUNDS) == (0, 0)
    assert minimap.world_to_pixel(1240, 1190, BOUNDS) == (260, 220)


def test_bounds_document_carries_the_size_the_conversion_implies():
    document = minimap.bounds_document("ROOK", BOUNDS, [6, 7, 8])

    assert document == {
        "city": "ROOK",
        "minX": 980, "minY": 970, "maxX": 1240, "maxY": 1190,
        "width": 261, "height": 221,
        "floors": [6, 7, 8],
        "surfaceZ": 7,
    }


# ======================================================
# A cidade inteira, do dump
# ======================================================


def _dump(tiles):
    """tiles: [(x, y, z, tileid, [item id ou (id, uid)])] -> uma feature por z."""
    def _item(entry):
        return {"id": entry[0], "uid": entry[1]} if isinstance(entry, tuple) else {"id": entry}

    by_z: dict = {}
    for x, y, z, tileid, items in tiles:
        by_z.setdefault(z, []).append(
            {"x": x, "y": y, "tileid": tileid, "items": [_item(e) for e in items]}
        )
    return {"data": {"nodes": [{"features": [
        {"x": 0, "y": 0, "z": z, "tiles": tile_list} for z, tile_list in by_z.items()
    ]}]}}


COLORS = {100: 24, 200: 129, 300: 0, 2016: 210}


def test_city_minimap_keeps_one_map_per_floor_that_has_a_tile():
    floors = minimap.city_minimap(
        _dump([(10, 20, 7, 100, []), (10, 20, 8, 100, [])]), COLORS
    )

    assert sorted(floors) == [7, 8]


def test_city_minimap_resolves_the_stack_of_each_tile():
    floors = minimap.city_minimap(
        _dump([(10, 20, 7, 100, [300, 200]), (11, 20, 7, 100, [300])]), COLORS
    )

    assert floors[7] == {(10, 20): 129, (11, 20): 24}


def test_city_minimap_ignores_travel_graph_marker_signs():
    """A placa é entrada de ferramenta, some da saída real da cidade — e não
    pode pintar um pixel que o jogo não mostra."""
    floors = minimap.city_minimap(
        _dump([(10, 20, 7, 100, [(2016, 10001)])]), COLORS
    )

    assert floors[7] == {(10, 20): 24}


def test_city_minimap_keeps_an_uncolored_tile_so_the_floor_still_counts():
    floors = minimap.city_minimap(_dump([(10, 20, 7, None, [])]), COLORS)

    assert floors[7] == {(10, 20): 0}


def test_floor_pixels_lays_the_floor_out_row_major_with_holes_empty():
    bounds = {"minX": 10, "minY": 20, "maxX": 11, "maxY": 21}

    pixels = minimap.floor_pixels({(10, 20): 24, (11, 21): 129}, bounds)

    assert pixels == [24, 0, 0, 129]


def test_city_minimap_ignores_a_route_marker_item_without_uid():
    """A bola de energia da rota é entrada de ferramenta como a placa, e não
    tem uid — o corte é pelo id do item."""
    floors = minimap.city_minimap(
        _dump([(10, 20, 7, 100, [27869])]), {**COLORS, 27869: 200}
    )

    assert floors[7] == {(10, 20): 24}
