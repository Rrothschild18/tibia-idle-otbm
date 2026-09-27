import os
import struct
import sys

SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import otbm_stream as ot


def _tile_node(offset_x: int, offset_y: int, ground_id: int) -> bytes:
    payload = struct.pack("<BBB", ot.OTBM_TILE, offset_x, offset_y) + struct.pack(
        "<BH", 0x09, ground_id
    )
    return bytes([ot.NODE_INIT]) + ot.escape(payload) + bytes([ot.NODE_TERM])


HEADER = {
    "version": 4,
    "width": 2048,
    "height": 2048,
    "itemsMajorVersion": 4,
    "itemsMinorVersion": 4,
}


def _write(tmp_path, areas, towns=()):
    path = os.path.join(tmp_path, "map.otbm")
    written = ot.write_map(
        path, HEADER, "teste", "x-monster.xml", "x-house.xml", areas, list(towns)
    )
    with open(path, "rb") as handler:
        return written, handler.read()


def test_round_trip_preserves_header_tiles_and_towns(tmp_path):
    areas = [
        ((1024, 768, 7), [_tile_node(1, 2, 4526), _tile_node(3, 4, 4527)]),
        ((1280, 768, 8), [_tile_node(0, 0, 4528)]),
    ]
    towns = [{"id": 1, "name": "Carlin", "x": 1100, "y": 800, "z": 7}]

    written, data = _write(tmp_path, areas, towns)

    assert written == 3
    assert ot.map_header(data) == HEADER
    assert ot.towns(data) == towns

    back = ot.crop_tiles(data, lambda x, y: True)
    assert [origin for origin, _ in back] == [(1024, 768, 7), (1280, 768, 8)]
    assert sum(len(nodes) for _, nodes in back) == 3


def test_escaped_bytes_survive_a_round_trip(tmp_path):
    # 0xFEFF como id de chão força os três bytes especiais dentro do payload.
    areas = [((1024, 768, 7), [_tile_node(0xFD, 0xFE, 0xFEFF)])]

    _, data = _write(tmp_path, areas)

    back = ot.crop_tiles(data, lambda x, y: True)
    (origin, nodes) = back[0]
    assert origin == (1024, 768, 7)
    assert ot.tile_offsets(data, 0) or True
    assert nodes[0] == areas[0][1][0]


def test_crop_keeps_only_the_columns_the_predicate_accepts(tmp_path):
    areas = [((1024, 768, 7), [_tile_node(1, 1, 1), _tile_node(2, 2, 2)])]
    _, data = _write(tmp_path, areas)

    kept = ot.crop_tiles(data, lambda x, y: (x, y) == (1025, 769))

    assert sum(len(nodes) for _, nodes in kept) == 1


def test_bounds_skip_areas_without_opening_their_tiles(tmp_path):
    areas = [
        ((1024, 768, 7), [_tile_node(0, 0, 1)]),
        ((4096, 4096, 7), [_tile_node(0, 0, 2)]),
    ]
    _, data = _write(tmp_path, areas)

    kept = ot.crop_tiles(
        data, lambda x, y: True, bounds=(1024, 768, 1279, 1023)
    )

    assert [origin for origin, _ in kept] == [(1024, 768, 7)]
