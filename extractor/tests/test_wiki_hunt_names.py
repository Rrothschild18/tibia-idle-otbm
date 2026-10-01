import os
import sys

SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import wiki_hunt_names as whn


def test_a_classic_species_christens_its_cave():
    hunts = ["Rotworm Cave", "Dwarf Mines", "Troll Cave"]

    christened = whn.christened_species(hunts, {"Rotworm", "Dwarf", "Troll"})

    assert christened == {"rotworm", "dwarf", "troll"}


def test_scenery_fauna_never_christens_a_hunt():
    """Deer, Skunk, Butterfly e Seagull não dão nome a nenhuma das 699 hunts
    da wiki — é a medição que separa cenário de bicho de hunt."""
    hunts = ["Rotworm Cave", "Dwarf Mines", "Amazon Camp"]

    christened = whn.christened_species(hunts, {"Deer", "Skunk", "Butterfly", "Seagull"})

    assert christened == set()


def test_a_compound_species_name_matches_as_a_consecutive_phrase():
    # "Mines" não vira "Swamp Troll" só por as duas espécies aparecerem na
    # mesma hunt — a frase precisa ser consecutiva, na ordem.
    hunts = ["Swamp Troll Cave", "Dwarf Mines"]

    christened = whn.christened_species(hunts, {"Swamp Troll", "Dwarf Troll"})

    assert christened == {"swamp troll"}


def test_plural_in_the_hunt_name_still_counts():
    hunts = ["Kazordoon Minotaurs", "Minotaur Camp"]

    christened = whn.christened_species(hunts, {"Minotaur"})

    assert christened == {"minotaur"}


def test_a_substring_that_is_not_a_whole_word_does_not_match():
    # "Rat" não pode casar dentro de "Pirate" — teria de ser palavra inteira.
    hunts = ["Pirate Hideout"]

    christened = whn.christened_species(hunts, {"Rat"})

    assert christened == set()


def test_species_absent_from_every_hunt_name_is_not_christened():
    hunts = ["Rotworm Cave"]

    christened = whn.christened_species(hunts, {"Bug"})

    assert christened == set()
