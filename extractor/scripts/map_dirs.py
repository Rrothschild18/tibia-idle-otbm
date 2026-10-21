"""Shared two-level (city/pasta) directory discovery for the maps pipeline.

Every map folder lives under `<root>/<CIDADE>/<pasta>/` — the city is always
the physical parent folder, never guessed from the map's own name. See
extractor/README.md, "Convenção de pastas".
"""

import os
from typing import List, Optional


def discover_cities(root: str) -> List[str]:
    """Every subdirectory directly under `root`, sorted. Empty list if
    `root` doesn't exist yet (a brand new checkout before any map is added)."""
    if not os.path.isdir(root):
        return []
    return sorted(
        entry for entry in os.listdir(root)
        if os.path.isdir(os.path.join(root, entry))
    )


def find_two_level_dir(root: str, name: str) -> Optional[str]:
    """`root/<city>/<name>` for whichever city folder has it, or None if no
    city under `root` has a `name` subfolder."""
    for city in discover_cities(root):
        candidate = os.path.join(root, city, name)
        if os.path.isdir(candidate):
            return candidate
    return None


def _is_window_folder(name: str) -> bool:
    """`<ID>_window` — a preview-only crop that `build_hunt_window.py` gera
    pro brush do editor adicionar vizinhos, nunca uma hunt própria. Ela
    carrega o `<ID>` de uma hunt real (`EDRON-HUNT-0105_window` extrai
    `EDRON-HUNT-0105`, a mesma da pasta de verdade), então uma varredura
    `--all` que não a filtra processa o mesmo id duas vezes: o
    `build_hunt_fragment.py --all --export` trava em `MapIdAlreadyExistsError`
    na primeira que encontrar, e o `publish.py --all` publicaria a janela como
    bundle próprio em `public/assets/`. Só entra aqui, nas duas enumerações
    usadas por `--all`/relatório em lote — um lookup direto pelo nome exato
    (`find_two_level_dir`) continua achando a pasta normalmente, porque aí
    quem pediu sabe que é uma janela."""
    return name.endswith("_window")


def discover_city_map_names(root: str, city: str) -> List[str]:
    """Every pasta name under `root/<city>/`, sorted, minus `_window` crops
    (see `_is_window_folder`). Unlike `discover_two_level_names` this is
    scoped to one city and asks for no marker file — the caller wants the
    folders that exist, including one that's missing whatever a marker would
    prove (see build_travel_fragment.discover_hunt_maps, where a hunt with
    nothing generated yet still needs to be noticed). Empty list if the city
    has no folder under `root`."""
    city_dir = os.path.join(root, city)
    if not os.path.isdir(city_dir):
        return []
    return sorted(
        entry for entry in os.listdir(city_dir)
        if os.path.isdir(os.path.join(city_dir, entry)) and not _is_window_folder(entry)
    )


def discover_two_level_names(root: str, marker_relpath: str) -> List[str]:
    """Every pasta name under `root/<city>/<pasta>/` whose folder contains
    `marker_relpath` (e.g. "monsters/respawn.json"), across every city,
    sorted, minus `_window` crops (see `_is_window_folder`). Used by
    --all-style CLI discovery."""
    names = []
    for city in discover_cities(root):
        city_dir = os.path.join(root, city)
        for entry in sorted(os.listdir(city_dir)):
            if _is_window_folder(entry):
                continue
            candidate = os.path.join(city_dir, entry)
            if os.path.isdir(candidate) and os.path.exists(os.path.join(candidate, marker_relpath)):
                names.append(entry)
    return names
