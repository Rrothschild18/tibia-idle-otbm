import json
import os
import struct
import sys

import pytest

import otbm_stream
import transplant_markers as tm
import travel_graph

ROOK_OFFSET = (-30958, -31074, 0)  # mundo -> local
ROOK_OFFSET_BACK = (30958, 31074, 0)  # local -> mundo


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

    assert [(m["kind"], m["source"]) for m in markers] == [
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

    assert [m["source"] for m in markers] == [(10, 20, 7)]


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
    markers = [{"kind": "route", "source": (32146, 32208, 7), "itemId": 27869,
                "uid": None, "text": None}]
    present = {(1188, 1134, 7)}

    injections, refusals = tm.plan_transplant(markers, present, ROOK_OFFSET)

    assert refusals == []
    assert injections[0]["target"] == (1188, 1134, 7)
    assert injections[0]["itemId"] == 27869


def test_plan_names_every_marker_whose_destination_tile_is_absent():
    # Falhar alto: um marcador que cai num tile que não existe no destino é uma
    # rota truncada ou uma quest sem entrada, e o jogo não diria por quê.
    markers = [
        {"kind": "route", "source": (32146, 32208, 7), "itemId": 27869, "uid": None, "text": None},
        {"kind": "quest", "source": (99999, 99999, 7), "itemId": 2014, "uid": 20001,
         "text": "copper_shield_quest"},
    ]
    present = {(1188, 1134, 7)}

    injections, refusals = tm.plan_transplant(markers, present, ROOK_OFFSET)

    assert [i["target"] for i in injections] == [(1188, 1134, 7)]
    assert len(refusals) == 1
    assert refusals[0]["reason"] == tm.REASON_NO_TILE
    assert refusals[0]["target"] == (69041, 68925, 7)
    assert refusals[0]["kind"] == "quest"


def test_plan_is_idempotent_against_a_destination_that_already_has_the_marker():
    # Rodar duas vezes não pode empilhar 219 bolas em cima de 219 bolas.
    markers = [{"kind": "route", "source": (32146, 32208, 7), "itemId": 27869,
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


# ======================================================
# A placa de POI, que vem do snapshot e não do mapa-mundo
# ======================================================

def _snapshot(*signs):
    return {"city": "ROOK", "signCount": len(signs), "signs": list(signs)}


def _sign(uid, poi_id, x, y, z):
    return {"id": poi_id, "type": poi_id.split("-")[1], "x": x, "y": y, "z": z,
            "uid": uid, "text": poi_id}


def test_signs_come_from_the_snapshot_with_uid_and_text_verbatim():
    # O texto é o id do POI: é dele que `parse_marker_signs` cunha o id do
    # outro lado, então reescrevê-lo renomearia a hunt.
    markers = tm.read_signs(_snapshot(_sign(10013, "ROOK-TEMPLE-0001", 1139, 1145, 7)))

    assert markers == [{
        "kind": "sign", "source": (1139, 1145, 7), "itemId": 2016,
        "uid": 10013, "text": "ROOK-TEMPLE-0001", "id": "ROOK-TEMPLE-0001",
    }]


def test_a_sign_below_the_reserved_uid_range_stops_the_run():
    # Fora da faixa, `map_v6` e `minimap` não apagam a placa do bundle e ela
    # aparece desenhada no jogo — defeito que só se acha olhando a tela.
    with pytest.raises(SystemExit):
        tm.read_signs(_snapshot(_sign(9999, "ROOK-HUNT-0001", 1139, 1132, 8)))


def test_read_source_tells_a_snapshot_from_a_raw_dump_by_its_shape():
    dump = _dump([(10, 20, 7, [_ball()])])

    assert [m["kind"] for m in tm.read_source(dump)] == ["route"]
    assert [m["kind"] for m in tm.read_source(
        _snapshot(_sign(10001, "ROOK-HUNT-0001", 1139, 1132, 8))
    )] == ["sign"]


def test_a_sign_whose_destination_tile_is_unpassable_is_refused_by_name():
    # A placa é o tile de onde se chega no POI. Num tile `unpass`,
    # `apply_graph_rejections` derruba o nó — e longe daqui.
    markers = tm.read_signs(_snapshot(_sign(10001, "ROOK-HUNT-0001", 1139, 1132, 8)))
    target = (32097, 32206, 8)

    _, refusals = tm.plan_transplant(
        markers, {target}, ROOK_OFFSET_BACK, unpassable={target}
    )

    assert [(r["text"], r["reason"]) for r in refusals] == [
        ("ROOK-HUNT-0001", tm.REASON_UNPASSABLE)
    ]


def test_an_unpassable_tile_does_not_refuse_a_route_ball():
    # Caminho que não fecha é assunto do `build_painted_route.py`; parar o
    # transplante por isso seria parar por um defeito que não é deste comando.
    markers = [{"kind": "route", "source": (32146, 32208, 7), "itemId": 27869,
                "uid": None, "text": None}]

    injections, refusals = tm.plan_transplant(
        markers, {(1188, 1134, 7)}, ROOK_OFFSET, unpassable={(1188, 1134, 7)}
    )

    assert refusals == []
    assert len(injections) == 1


def test_a_uid_already_worn_by_another_sign_is_refused_and_names_the_owner():
    # Dois marcadores com o mesmo uid cunham o mesmo POI, e o segundo sai como
    # `duplicate-sign-id` num relatório que ninguém lê a tempo.
    markers = tm.read_signs(_snapshot(_sign(10001, "ROOK-HUNT-0001", 1139, 1132, 8)))
    target = (32097, 32206, 8)

    _, refusals = tm.plan_transplant(
        markers, {target}, ROOK_OFFSET_BACK, sign_uid_owner={10001: (32000, 32000, 7)}
    )

    assert refusals[0]["reason"] == tm.REASON_UID_TAKEN
    assert refusals[0]["owner"] == (32000, 32000, 7)


def test_the_same_uid_on_the_same_tile_is_the_second_run_not_a_conflict():
    markers = tm.read_signs(_snapshot(_sign(10001, "ROOK-HUNT-0001", 1139, 1132, 8)))
    target = (32097, 32206, 8)

    injections, refusals = tm.plan_transplant(
        markers, {target}, ROOK_OFFSET_BACK,
        already_there={(target, 2016)}, sign_uid_owner={10001: target},
    )

    assert (injections, refusals) == ([], [])


def test_the_wrong_offset_sign_drops_the_sign_thirty_thousand_tiles_away():
    # O sentido do offset muda quando o destino passa a ser coordenada de mundo.
    # Errar o sinal não pode injetar no vazio — tem de recusar.
    markers = tm.read_signs(_snapshot(_sign(10013, "ROOK-TEMPLE-0001", 1139, 1145, 7)))

    _, refusals = tm.plan_transplant(markers, {(32097, 32219, 7)}, ROOK_OFFSET)

    assert refusals[0]["reason"] == tm.REASON_NO_TILE
    assert refusals[0]["target"] == (-29819, -29929, 7)


def test_nothing_in_the_plan_knows_the_word_rook():
    # Cidade e offset são argumento: outra cidade com outro offset passa pelo
    # mesmo caminho.
    markers = tm.read_signs(_snapshot(_sign(10007, "CARLIN-HUNT-0007", 40, 60, 7)))

    injections, refusals = tm.plan_transplant(markers, {(1040, 2060, 7)}, (1000, 2000, 0))

    assert refusals == []
    assert injections[0]["target"] == (1040, 2060, 7)
    assert injections[0]["text"] == "CARLIN-HUNT-0007"


# ======================================================
# Ida e volta pelo OTBM: o parser do grafo tem de achar a placa
# ======================================================

HEADER = {"version": 4, "width": 2048, "height": 2048,
          "itemsMajorVersion": 4, "itemsMinorVersion": 4}


def _ground_tile(offset_x, offset_y, ground_id=4526):
    payload = struct.pack("<BBB", otbm_stream.OTBM_TILE, offset_x, offset_y)
    payload += struct.pack("<BH", otbm_stream.OTBM_ATTR_ITEM, ground_id)
    return bytes([otbm_stream.NODE_INIT]) + otbm_stream.escape(payload) + bytes([otbm_stream.NODE_TERM])


def _tiny_map(tmp_path, name="ROOK"):
    """Um OTBM de dois tiles, em coordenada de mundo, no lugar onde o templo cai."""
    path = os.path.join(tmp_path, f"{name}.otbm")
    areas = [((32000, 32128, 7), [_ground_tile(97, 91), _ground_tile(98, 91)])]
    otbm_stream.write_map(path, HEADER, "teste", f"{name}-monster.xml",
                          f"{name}-house.xml", areas, [])
    return path


def _run(monkeypatch, source_path, otbm_path, offset, unpass=()):
    monkeypatch.setattr(tm.appearance_flags, "load_flags", lambda city: {})
    if unpass:
        monkeypatch.setattr(tm, "_unpassable_tiles", lambda areas, city: set(unpass))
    monkeypatch.setattr(sys, "argv", [
        "transplant_markers.py", "--from", source_path, "--into", otbm_path,
        "--offset", offset,
    ])
    tm.main()


def _signs_in(otbm_path):
    with open(otbm_path, "rb") as handler:
        areas = otbm_stream.crop_tiles(handler.read(), lambda x, y: True)
    return travel_graph.parse_marker_signs(tm.as_dump(areas))


def test_the_injected_sign_is_found_by_the_graphs_own_parser(tmp_path, monkeypatch):
    # O que prova o transplante não é o que este script relata, é o que
    # `parse_marker_signs` acha depois — é ele que o grafo usa.
    otbm_path = _tiny_map(tmp_path)
    source_path = os.path.join(tmp_path, "snap.json")
    with open(source_path, "w", encoding="utf-8") as handler:
        json.dump(_snapshot(_sign(10013, "ROOK-TEMPLE-0001", 1139, 1145, 7)), handler)

    _run(monkeypatch, source_path, otbm_path, "30958,31074,0")

    locations, issues = _signs_in(otbm_path)
    assert issues == []
    assert locations == [{"id": "ROOK-TEMPLE-0001", "type": "TEMPLE",
                          "x": 32097, "y": 32219, "z": 7}]


def test_running_twice_does_not_duplicate_the_sign(tmp_path, monkeypatch):
    otbm_path = _tiny_map(tmp_path)
    source_path = os.path.join(tmp_path, "snap.json")
    with open(source_path, "w", encoding="utf-8") as handler:
        json.dump(_snapshot(_sign(10013, "ROOK-TEMPLE-0001", 1139, 1145, 7)), handler)

    _run(monkeypatch, source_path, otbm_path, "30958,31074,0")
    _run(monkeypatch, source_path, otbm_path, "30958,31074,0")

    locations, issues = _signs_in(otbm_path)
    assert issues == []
    assert len(locations) == 1


def test_a_wrong_offset_exits_with_an_error_instead_of_writing(tmp_path, monkeypatch, capsys):
    otbm_path = _tiny_map(tmp_path)
    before = open(otbm_path, "rb").read()
    source_path = os.path.join(tmp_path, "snap.json")
    with open(source_path, "w", encoding="utf-8") as handler:
        json.dump(_snapshot(_sign(10013, "ROOK-TEMPLE-0001", 1139, 1145, 7)), handler)

    with pytest.raises(SystemExit) as failure:
        _run(monkeypatch, source_path, otbm_path, "-30958,-31074,0")

    assert failure.value.code
    # Nomear qual placa caiu fora é a diferença entre consertar o sinal do
    # offset e caçar um POI que desapareceu.
    assert "ROOK-TEMPLE-0001" in capsys.readouterr().out
    assert open(otbm_path, "rb").read() == before


def test_an_unpassable_destination_exits_with_an_error(tmp_path, monkeypatch):
    otbm_path = _tiny_map(tmp_path)
    source_path = os.path.join(tmp_path, "snap.json")
    with open(source_path, "w", encoding="utf-8") as handler:
        json.dump(_snapshot(_sign(10013, "ROOK-TEMPLE-0001", 1139, 1145, 7)), handler)

    with pytest.raises(SystemExit) as failure:
        _run(monkeypatch, source_path, otbm_path, "30958,31074,0",
             unpass=[(32097, 32219, 7)])

    assert failure.value.code
    assert _signs_in(otbm_path) == ([], [])
