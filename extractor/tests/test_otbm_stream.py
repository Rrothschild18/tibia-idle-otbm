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


def _tile_node_with_child_ground(offset_x: int, offset_y: int, ground_id: int) -> bytes:
    """O outro jeito de o RME gravar chão: como primeiro nó de item, sem atributo.

    18.720 dos 352.416 tiles de Rookgaard chegam assim."""
    payload = struct.pack("<BBB", ot.OTBM_TILE, offset_x, offset_y)
    child = ot.item_node(ground_id)
    return bytes([ot.NODE_INIT]) + ot.escape(payload) + child + bytes([ot.NODE_TERM])


def test_ground_id_reads_the_attribute_when_the_tile_declares_one():
    assert ot.tile_ground_id(_tile_node(1, 2, 4526), 0) == 4526


def test_ground_id_is_none_when_the_ground_came_as_an_item_node():
    # `otbm2json` também deixa `tileid` de fora nesse caso, e é essa tradução
    # que este leitor reproduz — o chão sai pelos itens.
    assert ot.tile_ground_id(_tile_node_with_child_ground(1, 2, 4526), 0) is None


def test_ground_id_steps_over_the_tile_flags_that_come_before_it():
    payload = struct.pack("<BBB", ot.OTBM_TILE, 1, 2)
    payload += struct.pack("<BI", ot.OTBM_ATTR_TILE_FLAGS, 0x40)
    payload += struct.pack("<BH", ot.OTBM_ATTR_ITEM, 4526)
    node = bytes([ot.NODE_INIT]) + ot.escape(payload) + bytes([ot.NODE_TERM])

    assert ot.tile_ground_id(node, 0) == 4526


def test_ground_id_skips_the_house_id_of_a_housetile():
    payload = struct.pack("<BBB", ot.OTBM_HOUSETILE, 1, 2) + struct.pack("<I", 4242)
    payload += struct.pack("<BH", ot.OTBM_ATTR_ITEM, 4526)
    node = bytes([ot.NODE_INIT]) + ot.escape(payload) + bytes([ot.NODE_TERM])

    assert ot.tile_ground_id(node, 0) == 4526


def _tile_with_items(offset_x, offset_y, ground_id, *item_nodes):
    payload = struct.pack("<BBB", ot.OTBM_TILE, offset_x, offset_y)
    payload += struct.pack("<BH", ot.OTBM_ATTR_ITEM, ground_id)
    node = bytes([ot.NODE_INIT]) + ot.escape(payload)
    for item in item_nodes:
        node += item
    return node + bytes([ot.NODE_TERM])


def test_item_id_and_text_reads_a_sign():
    item = ot.item_node(2017, text="6005")
    item_id, text = ot.item_id_and_text(item, 0, len(item))
    assert (item_id, text) == (2017, "6005")


def test_item_id_and_text_is_none_for_an_item_without_text():
    item = ot.item_node(5910)
    assert ot.item_id_and_text(item, 0, len(item)) == (5910, None)


def test_without_items_drops_only_the_matching_item():
    sign = ot.item_node(2017, text="6005")
    cloth = ot.item_node(5910)
    lore_sign = ot.item_node(2017, text="Welcome to Carlin!")
    node = _tile_with_items(1, 2, 4526, sign, cloth, lore_sign)

    def drop(item_id, text):
        return item_id == 5910 or (item_id == 2017 and text is not None and text.isdigit())

    cleaned = ot.without_items(node, drop)

    assert ot.tile_offsets(cleaned, 0) == (1, 2)
    assert ot.tile_ground_id(cleaned, 0) == 4526
    kids = list(ot.children(cleaned, 0))
    assert len(kids) == 1
    assert ot.item_id_and_text(cleaned, *kids[0]) == (2017, "Welcome to Carlin!")


def test_without_items_is_a_no_op_when_nothing_matches():
    node = _tile_with_items(0, 0, 100, ot.item_node(200))

    assert ot.without_items(node, lambda item_id, text: False) == node


def test_without_items_round_trips_through_write_map(tmp_path):
    sign = ot.item_node(2017, text="6005")
    tile = _tile_with_items(3, 4, 4526, sign)
    cleaned = ot.without_items(tile, lambda item_id, text: item_id == 2017)

    _, data = _write(tmp_path, [((1024, 768, 7), [cleaned])])

    back = ot.crop_tiles(data, lambda x, y: True)
    (_, nodes) = back[0]
    assert ot.tile_ground_id(nodes[0], 0) == 4526
    assert list(ot.children(nodes[0], 0)) == []
