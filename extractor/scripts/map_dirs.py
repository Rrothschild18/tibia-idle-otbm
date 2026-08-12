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


def discover_city_map_names(root: str, city: str) -> List[str]:
    """Every pasta name under `root/<city>/`, sorted. Unlike
    `discover_two_level_names` this is scoped to one city and asks for no
    marker file — the caller wants the folders that exist, including one
    that's missing whatever a marker would prove (see
    build_travel_fragment.discover_hunt_maps, where a hunt with nothing
    generated yet still needs to be noticed). Empty list if the city has no
    folder under `root`."""
    city_dir = os.path.join(root, city)
    if not os.path.isdir(city_dir):
        return []
    return sorted(
        entry for entry in os.listdir(city_dir)
        if os.path.isdir(os.path.join(city_dir, entry))
    )


def discover_two_level_names(root: str, marker_relpath: str) -> List[str]:
    """Every pasta name under `root/<city>/<pasta>/` whose folder contains
    `marker_relpath` (e.g. "monsters/respawn.json"), across every city,
    sorted. Used by --all-style CLI discovery."""
    names = []
    for city in discover_cities(root):
        city_dir = os.path.join(root, city)
        for entry in sorted(os.listdir(city_dir)):
            candidate = os.path.join(city_dir, entry)
            if os.path.isdir(candidate) and os.path.exists(os.path.join(candidate, marker_relpath)):
                names.append(entry)
    return names
