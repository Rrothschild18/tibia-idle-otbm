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
