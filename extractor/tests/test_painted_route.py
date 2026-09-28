import pytest

import painted_route as pr
import travel_graph as tg

BALL = 27869
GROUND = 100
WALL = 900
FLAGS = {str(GROUND): {}, str(WALL): {"unpass": True}, str(BALL): {}}


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


def _route(dump, start):
    tiles = tg.extract_tile_flags(dump, FLAGS)
    graph = tg.build_walkable_graph(tiles)
    return pr.build_painted_route(dump, graph, start)


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


def test_a_painted_tile_nobody_can_walk_to_fails_and_names_it():
    # Falhar alto: uma bola atrás de parede é uma rota truncada, e uma quest que
    # exige limpar a área nunca fecharia. O jogo não saberia dizer por quê.
    dump = _dump(
        [(0, 0, 7, GROUND, []), (1, 0, 7, GROUND, [BALL])]
        + [(x, 5, 7, WALL, []) for x in range(3)]
        + [(1, 6, 7, GROUND, [BALL])]
    )

    with pytest.raises(pr.UnreachablePaintedTile) as info:
        _route(dump, (0, 0, 7))

    assert (1, 6, 7) in info.value.tiles


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
