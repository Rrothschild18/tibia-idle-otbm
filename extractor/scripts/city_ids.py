"""Shared `city`/`status` derivation for every hunt/location id.

Both fields are always derived from the id's own first segment — never
hand-authored — so they can never drift from the id they describe. `TEST` is
the fictional city used for throwaway/test maps; `status: "test"` is the only
mirror of that, absent for every real city. See .scratch/city-scoped-ids/spec.md.
"""

import re

TEST_CITY = "TEST"

# CIDADE-TIPO-NNNN, with NNNN exactly four digits — the shape every hunt and
# location id follows. Same convention travel_graph.py validates marker signs
# against; this one doesn't constrain the TIPO segment, because a hunt's comes
# from a folder name rather than the sign's fixed set of POI types.
_ENTRY_ID_RE = re.compile(r"^[A-Z]+-[A-Z]+-\d{4}$")


def derive_city(entry_id: str) -> str:
    """`"ROOK-HUNT-0002"` -> `"ROOK"` — an id's first `-`-separated segment."""
    return entry_id.split("-", 1)[0]


def derive_status(city: str) -> str | None:
    """`"test"` when `city` is the fictional TEST city, absent (None)
    otherwise — never `null`/`false` on the actual catalog entry (callers
    should omit the key entirely when this returns None)."""
    return "test" if city == TEST_CITY else None


def is_conventional_id(entry_id: str) -> bool:
    """Whether `entry_id` follows CIDADE-TIPO-NNNN.

    Scratch folders under ready-maps (`DEBUG-MAP`, `Nova pasta`, a map saved
    before its id was chosen) have a respawn.json like any other, so a
    `--all` sweep finds them and derives a "map id" that is really just the
    folder name. Harmless in a local fragment, not harmless in the back-end
    catalog — this is what the export checks before writing one."""
    return bool(_ENTRY_ID_RE.match(entry_id))
