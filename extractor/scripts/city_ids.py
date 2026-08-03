"""Shared `city`/`status` derivation for every hunt/location id.

Both fields are always derived from the id's own first segment — never
hand-authored — so they can never drift from the id they describe. `TEST` is
the fictional city used for throwaway/test maps; `status: "test"` is the only
mirror of that, absent for every real city. See .scratch/city-scoped-ids/spec.md.
"""

TEST_CITY = "TEST"


def derive_city(entry_id: str) -> str:
    """`"ROOK-HUNT-0002"` -> `"ROOK"` — an id's first `-`-separated segment."""
    return entry_id.split("-", 1)[0]


def derive_status(city: str) -> str | None:
    """`"test"` when `city` is the fictional TEST city, absent (None)
    otherwise — never `null`/`false` on the actual db.json entry (callers
    should omit the key entirely when this returns None)."""
    return "test" if city == TEST_CITY else None
