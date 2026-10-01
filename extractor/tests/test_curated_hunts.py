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
