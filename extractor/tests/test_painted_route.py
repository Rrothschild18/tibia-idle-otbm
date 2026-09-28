import pytest

import painted_route as pr
import travel_graph as tg

BALL = 27869
GROUND = 100
WALL = 900
# GRAVE é mobília que bloqueia: a lápide de verdade que o marcador da Katana
# pegou por baixo. Diferente de WALL só no papel que cumpre no teste.
GRAVE = 800
FLAGS = {
    str(GROUND): {},
    str(WALL): {"unpass": True},
    str(GRAVE): {"unpass": True},
    str(BALL): {},
}


def _dump(rows):
    """rows: [(x, y, z, ground, [item ids])] -> dump cru, uma feature por z."""
    by_z = {}
    for x, y, z, ground, items in rows:
        by_z.setdefault(z, []).append(
            {"x": x, "y": y, "tileid": ground, "items": [{"id": i} for i in items]}
        )
    return {"data": {"nodes": [{"features": [
        {"x": 0, "y": 0, "z": z, "tiles": t} for z, t in sorted(by_z.items())
    ]}]}}


def _route(dump, start, spawns=()):
    tiles = tg.extract_tile_flags(dump, FLAGS)
    graph = tg.build_walkable_graph(tiles)
    return pr.build_painted_route(dump, graph, start, spawns)


def test_a_contiguous_corridor_is_walked_from_the_entrance_to_the_end():
    dump = _dump([(x, 0, 7, GROUND, [BALL] if x > 0 else []) for x in range(5)])

    route = _route(dump, (0, 0, 7))

    assert [(w["x"], w["y"], w["z"]) for w in route["waypoints"]] == [
        (1, 0, 7), (2, 0, 7), (3, 0, 7), (4, 0, 7)
    ]
    assert {w["kind"] for w in route["waypoints"]} == {"path"}
    assert route["painted"] == 4
    assert route["bridged"] == 0


def test_every_painted_tile_shows_up_exactly_once():
    # Bloco 3x3 pintado, com a entrada encostada nele.
    dump = _dump([(x, y, 7, GROUND, [BALL]) for x in range(1, 4) for y in range(3)]
                 + [(0, 0, 7, GROUND, [])])
    route = _route(dump, (0, 0, 7))

    painted = [(w["x"], w["y"], w["z"]) for w in route["waypoints"] if w["kind"] == "path"]
    assert len(painted) == 9
    assert len(set(painted)) == 9


def test_a_gap_between_two_fragments_is_bridged_and_the_bridge_is_labelled():
    # O caminho pintado quebra onde o autor não pintou — no mapa real são as
    # transições de andar. O gerador fecha o vão pelo grafo andável, e marca
    # esses tiles como ponte para que ninguém os confunda com caminho pintado.
    dump = _dump(
        [(0, 0, 7, GROUND, [])]
        + [(x, 0, 7, GROUND, [BALL]) for x in (1, 2)]
        + [(x, 0, 7, GROUND, []) for x in (3, 4)]
        + [(x, 0, 7, GROUND, [BALL]) for x in (5, 6)]
    )

    route = _route(dump, (0, 0, 7))

    kinds = [(w["x"], w["kind"]) for w in route["waypoints"]]
    assert kinds == [(1, "path"), (2, "path"), (3, "bridge"), (4, "bridge"),
                     (5, "path"), (6, "path")]
    assert route["painted"] == 4
    assert route["bridged"] == 2


def test_a_painted_tile_nobody_can_walk_to_is_reported_and_the_route_still_runs():
    # A bola atrás de parede sem monstro atrás é decoração, não quest quebrada:
    # no mapa da Katana são 9, todas atrás de porta trancada. O que não pode é
    # ela desaparecer do relatório — quem pintou precisa saber que não chegou lá.
    dump = _dump(
        [(0, 0, 7, GROUND, []), (1, 0, 7, GROUND, [BALL])]
        + [(x, 5, 7, WALL, []) for x in range(3)]
        + [(1, 6, 7, GROUND, [BALL])]
    )

    route = _route(dump, (0, 0, 7))

    assert route["unreachablePainted"] == [{"x": 1, "y": 6, "z": 7}]
    assert route["paintedTotal"] == 2
    assert route["painted"] == 1


def test_a_spawn_nobody_can_walk_to_is_named():
    # Esta é a cobertura que importa: a quest promete matar todos, e um monstro
    # fora de alcance é a promessa que não fecha.
    dump = _dump(
        [(0, 0, 7, GROUND, []), (1, 0, 7, GROUND, [BALL])]
        + [(x, 5, 7, WALL, []) for x in range(3)]
        + [(1, 6, 7, GROUND, [])]
    )

    route = _route(dump, (0, 0, 7), spawns=[(1, 0, 7), (1, 6, 7)])

    assert route["spawnsTotal"] == 2
    assert route["unreachableSpawns"] == [{"x": 1, "y": 6, "z": 7}]


def test_the_entrance_steps_off_the_marked_tile_when_furniture_blocks_it():
    # O marcador é rótulo, não chão. Com a lápide no tile marcado a entrada ficava
    # fora do grafo e os tiles pintados viravam todos inalcançáveis.
    dump = _dump(
        [(0, 0, 7, GROUND, [GRAVE]), (1, 0, 7, GROUND, [])]
        + [(x, 0, 7, GROUND, [BALL]) for x in (2, 3)]
    )

    route = _route(dump, (0, 0, 7))

    assert route["entranceSnappedFrom"] == {"x": 0, "y": 0, "z": 7}
    assert route["entrance"] == {"x": 1, "y": 0, "z": 7}
    assert route["painted"] == 2
    assert route["unreachablePainted"] == []


def test_the_entrance_steps_to_the_side_that_reaches_the_painted_path():
    # Com a lápide no meio de um corredor os dois lados são andáveis, e só um
    # leva à quest: escolher o primeiro andável entregaria rota vazia.
    dump = _dump(
        [(-1, 0, 7, GROUND, []), (0, 0, 7, GROUND, [GRAVE]), (1, 0, 7, GROUND, [])]
        + [(x, 0, 7, GROUND, [BALL]) for x in (2, 3)]
        + [(0, 5, 7, WALL, [])]
    )

    route = _route(dump, (0, 0, 7))

    assert route["entrance"] == {"x": 1, "y": 0, "z": 7}
    assert route["painted"] == 2


def test_an_entrance_walled_in_on_every_side_is_an_error_not_an_empty_route():
    dump = _dump(
        [(0, 0, 7, GROUND, [GRAVE])]
        + [(x, y, 7, WALL, []) for x in (-1, 0, 1) for y in (-1, 0, 1) if (x, y) != (0, 0)]
        + [(5, 5, 7, GROUND, [BALL])]
    )

    with pytest.raises(pr.EntranceUnreachable) as info:
        _route(dump, (0, 0, 7))

    assert info.value.start == (0, 0, 7)


def test_a_fragment_on_another_floor_is_bridged_through_the_transition():
    # Sem a transição os dois andares são ilhas, e é justamente nas escadas que
    # o caminho pintado quebra no mapa real.
    dump = _dump([
        (0, 0, 7, GROUND, []),
        (1, 0, 7, GROUND, [BALL]),
        (2, 0, 7, GROUND, []),          # o buraco
        (2, 0, 8, GROUND, []),
        (3, 0, 8, GROUND, [BALL]),
    ])
    tiles = tg.extract_tile_flags(dump, FLAGS)
    for tile in tiles:
        if (tile["x"], tile["y"], tile["z"]) == (2, 0, 7):
            tile["isFloorTransition"] = True
    graph = tg.build_walkable_graph(tiles)

    route = pr.build_painted_route(dump, graph, (0, 0, 7))

    assert [(w["x"], w["y"], w["z"], w["kind"]) for w in route["waypoints"]] == [
        (1, 0, 7, "path"), (2, 0, 7, "bridge"), (2, 0, 8, "bridge"), (3, 0, 8, "path")
    ]
    assert sorted(route["floors"]) == [7, 8]


def test_no_painted_tile_at_all_is_an_empty_route_not_an_error():
    dump = _dump([(0, 0, 7, GROUND, [])])

    route = _route(dump, (0, 0, 7))

    assert route["waypoints"] == []
    assert route["painted"] == 0
