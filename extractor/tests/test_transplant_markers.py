import pytest

import otbm_stream
import transplant_markers as tm

ROOK_OFFSET = (-30958, -31074, 0)  # world -> local


def _dump(tiles):
    """tiles: [(x, y, z, [item dict])] -> dump cru, uma feature por z."""
    by_z = {}
    for x, y, z, items in tiles:
        by_z.setdefault(z, []).append({"x": x, "y": y, "tileid": 100, "items": items})
    return {"data": {"nodes": [{"features": [
        {"x": 0, "y": 0, "z": z, "tiles": t} for z, t in sorted(by_z.items())
    ]}]}}


def _ball():
    return {"id": 27869}


def _quest(uid, text, item_id=2014):
    return {"id": item_id, "uid": uid, "text": text}


# ======================================================
# Ler os marcadores da fonte
# ======================================================

def test_reads_route_balls_and_quest_markers_and_nothing_else():
    dump = _dump([
        (10, 20, 7, [_ball()]),
        (11, 20, 7, [_quest(20001, "copper_shield_quest")]),
        (12, 20, 7, [{"id": 3031}]),                      # ouro: conteúdo
        (13, 20, 7, [{"id": 7757, "uid": 50080}]),        # uid alto do próprio mapa-mundo
        (14, 20, 7, [{"id": 2016, "uid": 10005, "text": "ROOK-HUNT-0005"}]),  # placa de POI
    ])

    markers = tm.read_markers(dump)

    assert [(m["kind"], m["world"]) for m in markers] == [
        ("route", (10, 20, 7)),
        ("quest", (11, 20, 7)),
    ]


def test_the_quest_band_is_bounded_so_the_world_maps_own_uids_stay_out():
    # otservbr usa uid alto para as coisas dele (50080, 64128 vistos de verdade
    # em Rookgaard). Uma faixa aberta em ">= 20001" engoliria esses objetos e o
    # transplante os copiaria como se fossem marcadores do autor.
    dump = _dump([
        (10, 20, 7, [_quest(20002, "katana_quest", item_id=2012)]),
        (11, 20, 7, [{"id": 2473, "uid": 64129, "text": None}]),
    ])

    markers = tm.read_markers(dump)

    assert [m["world"] for m in markers] == [(10, 20, 7)]


def test_a_quest_marker_without_text_is_an_issue_not_a_marker():
    # O texto é o slug que dá nome à quest; sem ele não há o que cunhar.
    dump = _dump([(10, 20, 7, [{"id": 2014, "uid": 20001}])])

    markers = tm.read_markers(dump)

    assert markers == []


def test_route_balls_keep_every_instance_on_a_stacked_tile():
    # Seis tiles do mapa real têm duas bolas. Perder a segunda não muda a rota,
    # mas muda a contagem que o relatório usa para conferir o transplante.
    dump = _dump([(10, 20, 7, [_ball(), _ball()])])

    assert len(tm.read_markers(dump)) == 2


# ======================================================
# Converter e planejar
# ======================================================

def test_plan_converts_world_to_local_by_the_measured_offset():
    markers = [{"kind": "route", "world": (32146, 32208, 7), "itemId": 27869,
                "uid": None, "text": None}]
    present = {(1188, 1134, 7)}

    injections, missing = tm.plan_transplant(markers, present, ROOK_OFFSET)

    assert missing == []
    assert injections[0]["local"] == (1188, 1134, 7)
    assert injections[0]["itemId"] == 27869


def test_plan_names_every_marker_whose_destination_tile_is_absent():
    # Falhar alto: um marcador que cai num tile que não existe no destino é uma
    # rota truncada ou uma quest sem entrada, e o jogo não diria por quê.
    markers = [
        {"kind": "route", "world": (32146, 32208, 7), "itemId": 27869, "uid": None, "text": None},
        {"kind": "quest", "world": (99999, 99999, 7), "itemId": 2014, "uid": 20001,
         "text": "copper_shield_quest"},
    ]
    present = {(1188, 1134, 7)}

    injections, missing = tm.plan_transplant(markers, present, ROOK_OFFSET)

    assert [i["local"] for i in injections] == [(1188, 1134, 7)]
    assert len(missing) == 1
    assert missing[0]["local"] == (69041, 68925, 7)
    assert missing[0]["kind"] == "quest"


def test_plan_is_idempotent_against_a_destination_that_already_has_the_marker():
    # Rodar duas vezes não pode empilhar 219 bolas em cima de 219 bolas.
    markers = [{"kind": "route", "world": (32146, 32208, 7), "itemId": 27869,
                "uid": None, "text": None}]
    present = {(1188, 1134, 7)}

    injections, _ = tm.plan_transplant(
        markers, present, ROOK_OFFSET, already_there={((1188, 1134, 7), 27869)}
    )

    assert injections == []


# ======================================================
# O nó de item que vai para dentro do OTBM
# ======================================================

def test_item_node_carries_uid_and_text_so_a_quest_marker_survives_the_write():
    node = otbm_stream.item_node(2014, unique_id=20001, text="copper_shield_quest")

    # NODE_INIT ... NODE_TERM, com o payload escapado no meio.
    assert node[0] == otbm_stream.NODE_INIT
    assert node[-1] == otbm_stream.NODE_TERM
    payload = otbm_stream.unescape(node[1:-1])
    assert payload[0] == otbm_stream.OTBM_ITEM
    assert int.from_bytes(payload[1:3], "little") == 2014
    assert otbm_stream.OTBM_ATTR_UNIQUE_ID in payload
    assert b"copper_shield_quest" in payload


def test_item_node_without_attributes_is_just_the_id():
    node = otbm_stream.item_node(27869)
    payload = otbm_stream.unescape(node[1:-1])

    assert len(payload) == 3
    assert int.from_bytes(payload[1:3], "little") == 27869
