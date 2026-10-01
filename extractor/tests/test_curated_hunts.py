import os
import sys

SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import curated_hunts as ch


def _candidate(**spawns_by_name):
    spawns = [
        {"name": name, "x": 10 + index, "y": 20, "z": 7}
        for index, name in enumerate(
            name for name, count in spawns_by_name.items() for _ in range(count)
        )
    ]
    return {"spawns": spawns}


def test_chosen_spawns_of_takes_the_whole_pocket_when_species_is_none():
    hunt = {"species": None}
    members = [_candidate(Amazon=2, Minotaur=1)]

    chosen = ch.chosen_spawns_of(hunt, members)

    assert len(chosen) == 3
    assert {name for *_, name in chosen} == {"Amazon", "Minotaur"}


def test_chosen_spawns_of_honours_the_species_filter_from_the_curation_screen():
    """O bug medido na spec: curadoria de "só os Amazons" não pode sair com o
    bolsão inteiro — `species` grava a escolha e precisa restringir de fato."""
    hunt = {"species": ["Amazon"]}
    members = [_candidate(Amazon=2, Minotaur=1)]

    chosen = ch.chosen_spawns_of(hunt, members)

    assert len(chosen) == 2
    assert {name for *_, name in chosen} == {"Amazon"}


def test_chosen_spawns_of_merges_across_every_member_candidate():
    hunt = {"species": ["Ghoul"]}
    members = [_candidate(Ghoul=1), _candidate(Skeleton=1, Ghoul=1)]

    chosen = ch.chosen_spawns_of(hunt, members)

    assert len(chosen) == 2
    assert {name for *_, name in chosen} == {"Ghoul"}


# ---------------------------------------------------------------------------
# entrance_of: o andar mais fundo com spawn, não o spawn mais perto do templo
# ---------------------------------------------------------------------------


def _member(*spawns):
    return {"spawns": [{"name": name, "x": x, "y": y, "z": z} for name, x, y, z in spawns]}


def test_entrance_picks_the_deepest_floor_even_if_farther_from_the_temple():
    """O bug que a spec mede: "mais perto do templo" cai no andar de cima —
    aqui o Deer de z7 está mais perto do templo, e a entrada tem que ir pro
    z8, onde a hunt de verdade mora."""
    members = [_member(("Deer", 1, 1, 7), ("Troll", 5, 5, 8))]
    distances = {(1, 1, 7): 10, (5, 5, 8): 90}

    entrance, cost = ch.entrance_of(members, distances, anchor_of=lambda s: (s["x"], s["y"], s["z"]))

    assert entrance == (5, 5, 8)
    assert cost == 90


def test_entrance_picks_the_cheapest_tile_within_the_deepest_floor():
    members = [_member(("Troll", 1, 1, 8), ("Troll", 9, 9, 8))]
    distances = {(1, 1, 8): 40, (9, 9, 8): 15}

    entrance, cost = ch.entrance_of(members, distances, anchor_of=lambda s: (s["x"], s["y"], s["z"]))

    assert entrance == (9, 9, 8)
    assert cost == 15


def test_entrance_is_none_without_any_reachable_tile():
    members = [_member(("Troll", 1, 1, 8))]

    entrance, cost = ch.entrance_of(members, {}, anchor_of=lambda s: (s["x"], s["y"], s["z"]))

    assert entrance is None
    assert cost is None


def test_entrance_of_an_empty_hunt_is_none():
    entrance, cost = ch.entrance_of([], {}, anchor_of=lambda s: (s["x"], s["y"], s["z"]))

    assert entrance is None
    assert cost is None
