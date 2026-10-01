"""Quais espécies dão nome a uma hunt da wiki — lógica pura.

Alimenta a regra de monstro fraco (`.scratch/hunts-por-subarea/spec.md`,
decisão 6-8): "bate o teto de XP, **ou** batiza hunt na wiki". O sinal que a
decisão 9 reprovou era "citado no `creatures` da hunt" — esse campo lista o
que existe na área (965 espécies, incluindo Deer, Seagull, Bug e Rat), não o
que dá nome a ela. Este módulo mede o segundo: se "Rotworm" aparece como
palavra (ou frase, para nome composto como "Swamp Troll") no `name` de alguma
das 699 hunts do catálogo (`extractor/hunt-catalog/catalog.json`).
"""

import re
from typing import Iterable, Set

_WORD_RE = re.compile(r"[a-z0-9]+")


def _words(text: str) -> list:
    return _WORD_RE.findall(text.lower())


def christened_species(hunt_names: Iterable[str], species_names: Iterable[str]) -> Set[str]:
    """O subconjunto (minúsculo) de `species_names` que batiza alguma hunt.

    Casamento é por palavra inteira, não substring — "Rat" não pode casar
    dentro de "Pirate". Nome composto ("Swamp Troll") casa como frase: as
    palavras precisam aparecer consecutivas, na ordem, em algum nome de hunt.
    Plural ("Minotaurs") conta: a última palavra da espécie aceita um "s" a
    mais no fim.
    """
    hunt_word_lists = [_words(name) for name in hunt_names]
    result: Set[str] = set()

    for species in species_names:
        species_words = _words(species)
        if not species_words:
            continue
        if _appears_in_any(species_words, hunt_word_lists):
            result.add(species.lower())

    return result


def _appears_in_any(species_words: list, hunt_word_lists: list) -> bool:
    length = len(species_words)
    *head, last = species_words
    for words in hunt_word_lists:
        for start in range(len(words) - length + 1):
            window = words[start : start + length]
            if window[:-1] != head:
                continue
            candidate = window[-1]
            if candidate == last or candidate == f"{last}s":
                return True
    return False
