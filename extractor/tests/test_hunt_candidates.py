import os
import sys

SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import hunt_candidates as hc

SPAWN_XML = """<?xml version="1.0"?>
<monsters>
\t<monster centerx="100" centery="100" centerz="7" radius="2">
\t\t<monster name="Rat" x="0" y="1" z="7" spawntime="90" />
\t\t<monster name="Rat" x="1" y="0" z="7" spawntime="90" />
\t</monster>
\t<monster centerx="200" centery="100" centerz="8" radius="2">
\t\t<monster name="Bug" x="-1" y="0" z="8" spawntime="90" />
\t</monster>
</monsters>
"""


def _floor(x_range, y_range, z):
    return {(x, y, z) for x in x_range for y in y_range}


def test_parse_spawn_xml_uses_the_absolute_floor_of_the_child():
    points = hc.parse_spawn_xml(SPAWN_XML)

    assert len(points) == 3
    assert points[0] == {
        "name": "Rat",
        "x": 100,
        "y": 101,
        "z": 7,
        "spawntime": 90,
        "radius": 2,
    }
    assert points[2]["z"] == 8


def test_same_floor_components_never_join_two_floors():
    walkable = _floor(range(0, 3), range(0, 3), 7) | _floor(range(0, 3), range(0, 3), 8)

    components = hc.same_floor_components(walkable)

    assert len({components[(0, 0, 7)], components[(0, 0, 8)]}) == 2
    assert components[(0, 0, 7)] == components[(2, 2, 7)]


def test_anchor_tile_falls_back_to_a_neighbour():
    walkable = {(5, 5, 7)}

    assert hc.anchor_tile({"x": 5, "y": 5, "z": 7}, walkable) == (5, 5, 7)
    assert hc.anchor_tile({"x": 6, "y": 5, "z": 7}, walkable) == (5, 5, 7)
    assert hc.anchor_tile({"x": 20, "y": 20, "z": 7}, walkable) is None


def test_candidates_split_by_walkable_component_not_by_distance():
    # Dois bolsões a 4 tiles um do outro — dentro do raio de agrupamento — mas
    # em componentes diferentes: a parede entre eles é o que os separa.
    left = _floor(range(0, 3), range(0, 3), 7)
    right = _floor(range(6, 9), range(0, 3), 7)
    walkable = left | right
    components = hc.same_floor_components(walkable)
    points = [
        {"name": "Rat", "x": 1, "y": 1, "z": 7},
        {"name": "Rat", "x": 2, "y": 2, "z": 7},
        {"name": "Rat", "x": 7, "y": 1, "z": 7},
        {"name": "Rat", "x": 7, "y": 2, "z": 7},
    ]

    candidates, orphans = hc.build_candidates(
        "TEST", points, walkable, components, radius=10, min_creatures=2
    )

    assert orphans == []
    assert len(candidates) == 2
    assert {c["creatures"] for c in candidates} == {2}


def test_candidate_carries_the_species_split_and_a_stable_id():
    walkable = _floor(range(0, 12), range(0, 12), 9)
    components = hc.same_floor_components(walkable)
    points = [
        {"name": "Orc", "x": 1, "y": 1, "z": 9},
        {"name": "Orc", "x": 2, "y": 1, "z": 9},
        {"name": "Wolf", "x": 3, "y": 3, "z": 9},
    ]

    candidates, _ = hc.build_candidates(
        "TEST", points, walkable, components, radius=10, min_creatures=3
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["id"] == "TEST-C09-001"
    assert candidate["floor"] == 9
    assert candidate["species"] == [
        {"name": "Orc", "count": 2},
        {"name": "Wolf", "count": 1},
    ]
    assert [piece["name"] for piece in candidate["splitBySpecies"]] == ["Orc", "Wolf"]
    assert candidate["extent"]["minX"] == 1
    assert candidate["extent"]["maxY"] == 3


def test_orphan_spawn_is_reported_instead_of_silently_dropped():
    walkable = _floor(range(0, 3), range(0, 3), 7)
    components = hc.same_floor_components(walkable)
    points = [
        {"name": "Rat", "x": 1, "y": 1, "z": 7},
        {"name": "Rat", "x": 1, "y": 2, "z": 7},
        {"name": "Rat", "x": 60, "y": 60, "z": 7},
    ]

    candidates, orphans = hc.build_candidates(
        "TEST", points, walkable, components, radius=10, min_creatures=2
    )

    assert len(candidates) == 1
    assert candidates[0]["creatures"] == 2
    assert [p["x"] for p in orphans] == [60]


def test_walk_distance_is_the_closest_spawn_of_the_candidate():
    walkable = _floor(range(0, 12), range(0, 12), 7)
    components = hc.same_floor_components(walkable)
    points = [
        {"name": "Rat", "x": 4, "y": 4, "z": 7},
        {"name": "Rat", "x": 8, "y": 8, "z": 7},
        {"name": "Rat", "x": 5, "y": 5, "z": 7},
    ]
    candidates, _ = hc.build_candidates(
        "TEST", points, walkable, components, radius=10, min_creatures=3
    )
    distances = {(4, 4, 7): 12, (8, 8, 7): 30, (5, 5, 7): 15}

    hc.attach_walk_distance(
        candidates, distances, anchor_of=lambda spawn: (spawn["x"], spawn["y"], spawn["z"])
    )

    assert candidates[0]["walkTilesFromTemple"] == 12


def test_walk_distance_is_none_when_nothing_is_reachable():
    walkable = _floor(range(0, 6), range(0, 6), 7)
    components = hc.same_floor_components(walkable)
    points = [
        {"name": "Rat", "x": 1, "y": 1, "z": 7},
        {"name": "Rat", "x": 2, "y": 2, "z": 7},
    ]
    candidates, _ = hc.build_candidates(
        "TEST", points, walkable, components, radius=10, min_creatures=2
    )

    hc.attach_walk_distance(
        candidates, {}, anchor_of=lambda spawn: (spawn["x"], spawn["y"], spawn["z"])
    )

    assert candidates[0]["walkTilesFromTemple"] is None


def test_weak_monsters_are_dropped_before_clustering():
    walkable = _floor(range(0, 12), range(0, 12), 7)
    components = hc.same_floor_components(walkable)
    points = [
        {"name": "Snake", "x": x, "y": 4, "z": 7} for x in range(1, 6)
    ] + [{"name": "Dragon", "x": x, "y": 8, "z": 7} for x in range(1, 4)]

    candidates, _ = hc.build_candidates(
        "TEST",
        points,
        walkable,
        components,
        radius=10,
        min_creatures=3,
        experience_by_name={"snake": 20, "dragon": 700},
    )

    assert [c["species"][0]["name"] for c in candidates] == ["Dragon"]
    assert all(s["name"] != "Snake" for c in candidates for s in c["species"])


def test_unknown_experience_keeps_the_monster():
    walkable = _floor(range(0, 12), range(0, 12), 7)
    components = hc.same_floor_components(walkable)
    points = [{"name": "Bicho Novo", "x": x, "y": 4, "z": 7} for x in range(1, 4)]

    candidates, _ = hc.build_candidates(
        "TEST", points, walkable, components, radius=10, min_creatures=3,
        experience_by_name={"snake": 20},
    )

    assert len(candidates) == 1


def test_notable_monsters_lead_the_species_list_even_with_fewer_spawns():
    walkable = _floor(range(0, 12), range(0, 12), 7)
    components = hc.same_floor_components(walkable)
    points = [
        {"name": "Poison Spider", "x": x, "y": 4, "z": 7} for x in range(1, 7)
    ] + [{"name": "Rotworm", "x": x, "y": 5, "z": 7} for x in range(1, 3)]

    candidates, _ = hc.build_candidates(
        "TEST", points, walkable, components, radius=10, min_creatures=3
    )

    assert [s["name"] for s in candidates[0]["species"]] == ["Rotworm", "Poison Spider"]


def test_notable_monster_survives_the_experience_cut():
    """Rotworm vale 40 e dá nome a caverna: o corte de 50 não pode levá-lo."""
    walkable = _floor(range(0, 12), range(0, 12), 7)
    components = hc.same_floor_components(walkable)
    points = [{"name": "Rotworm", "x": x, "y": 4, "z": 7} for x in range(1, 5)]

    candidates, _ = hc.build_candidates(
        "TEST", points, walkable, components, radius=10, min_creatures=3,
        experience_by_name={"rotworm": 40},
    )

    assert len(candidates) == 1
    assert candidates[0]["species"][0]["name"] == "Rotworm"


def test_scenery_fauna_still_goes_even_though_it_is_weak():
    walkable = _floor(range(0, 12), range(0, 12), 7)
    components = hc.same_floor_components(walkable)
    points = [{"name": "Snake", "x": x, "y": 4, "z": 7} for x in range(1, 5)]

    candidates, _ = hc.build_candidates(
        "TEST", points, walkable, components, radius=10, min_creatures=3,
        experience_by_name={"snake": 20},
    )

    assert candidates == []


def test_kept_weak_monster_does_not_outrank_a_notable_one():
    """Poison Spider sobrevive ao corte, mas não lidera na frente do Rotworm."""
    walkable = _floor(range(0, 12), range(0, 12), 7)
    components = hc.same_floor_components(walkable)
    points = [
        {"name": "Poison Spider", "x": x, "y": 4, "z": 7} for x in range(1, 7)
    ] + [{"name": "Rotworm", "x": x, "y": 5, "z": 7} for x in range(1, 3)]

    candidates, _ = hc.build_candidates(
        "TEST", points, walkable, components, radius=10, min_creatures=3,
        experience_by_name={"poison spider": 44, "rotworm": 40},
    )

    assert [s["name"] for s in candidates[0]["species"]] == ["Rotworm", "Poison Spider"]
