"""
Pure logic for the contract between this pipeline and tibia-idle's back-end:
which file each collection lands in, and how a re-export merges with what's
already there.

There used to be one destination — `apps/tibia-idle-mock-api/db.json`, served
by json-server. That app was deleted (fatia 1.8) and the collections it held
were split by *how the back-end reads them*, which is the shape this module
encodes:

1. `apps/tibia-idle-api/content/catalog-source.json` — `hunts`, `locations`
   and `travelGraph`, the three collections that become **rows in Postgres**.
   Nothing reads this file at runtime: `import-content` validates it with Zod
   and writes the catalog (`nx run db:reset` calls it). It's versioned next to
   the API so recreating the database is one command instead of "find the
   extractor dump first" — see that script's own docstring.
2. `apps/tibia-idle-api/content/hunts/` — read from disk at runtime, never a
   row: `loot.json` and `respawn/<HUNT-ID>.json`. These are loaded whole per
   hunt and answer no `WHERE`, which is the line ADR-0015 draws between the
   two; `hunts.json` sits here too, as a small manifest the simulator reads.

`hunts.json` is *derived* from the catalog's `hunts` rather than merged on its
own — it's the same hunts, projected to four fields, and two independently
merged copies of one thing is how they drift.

The old `monsters` collection has no destination anymore. Its payload still
matters (it's where the respawn file comes from, see `respawn_file`), but the
wrapper around it — `id`/`mapId`/`assetsRoot` — is read by nobody now that the
back-end loads `respawn/<HUNT-ID>.json` directly.
"""

import os
import posixpath
from typing import Dict, List

# The renderer format whose bundle the front actually serves. It lives in the
# folder name (`<pasta>-sprites-v6`), and the back-end's schema *requires* it:
# `mapUrl` must match `assets/<pasta>-v<N>/map.json` or the import rejects the
# hunt, because the `-v<N>` is how a content version reaches the client.
# Bumping the renderer's format means bumping this — and re-baking the maps.
MAP_BUNDLE_VERSION = 6

# Relative to the tibia-idle checkout root.
CATALOG_SOURCE_RELPATH = os.path.join("apps", "tibia-idle-api", "content", "catalog-source.json")
HUNT_CONTENT_RELDIR = os.path.join("apps", "tibia-idle-api", "content", "hunts")

# The three collections catalog-source.json carries, in the order the
# back-end's own schema lists them.
CATALOG_COLLECTIONS = ("hunts", "locations", "travelGraph")

# What content/hunts/hunts.json carries per hunt — the simulator needs the map
# and where to drop the character in it, and nothing else. The rest of a hunt
# (name, portrait, seed, city) is catalog, because that's what the selection
# screen filters and orders by.
HUNT_MANIFEST_FIELDS = ("id", "mapId", "mapUrl", "startPosition")

# Fields on a `hunts` entry that only a human can get right — art, wording,
# and a spawn tile the geometric centre only guesses at. They're the reason
# hunts is append-only on export (see merge_hunt_into_catalog): there is no
# per-field merge here, the whole entry is left alone once it exists.
CURATED_HUNT_FIELDS = ("name", "label", "portrait", "seed", "startPosition")


def map_bundle_root(map_name: str) -> str:
    """`"ROOK-HUNT-0013_rats-rookguard"` ->
    `"assets/ROOK-HUNT-0013_rats-rookguard-sprites-v6"` — the folder the front
    serves this map's bundle from, and the one build_phaser_map.py bakes into."""
    return posixpath.join("assets", f"{map_name}-sprites-v{MAP_BUNDLE_VERSION}")


def map_bundle_url(map_name: str) -> str:
    """The `mapUrl` a hunt carries into the catalog. Always versioned — a
    `mapUrl` without `-v<N>` is rejected by the back-end's schema, which is
    how a hunt built before this rule silently failed to import."""
    return posixpath.join(map_bundle_root(map_name), "map.json")


def catalog_source_path(tibia_idle_dir: str) -> str:
    """Where catalog-source.json lives inside a tibia-idle checkout."""
    return os.path.join(tibia_idle_dir, CATALOG_SOURCE_RELPATH)


def hunt_content_dir(tibia_idle_dir: str) -> str:
    """Where the runtime-read hunt files live inside a tibia-idle checkout."""
    return os.path.join(tibia_idle_dir, HUNT_CONTENT_RELDIR)


def empty_catalog() -> Dict[str, List[Dict]]:
    """A catalog-source.json with every collection present and empty — what a
    checkout with no exported content yet should look like, so callers never
    have to special-case a missing key."""
    return {collection: [] for collection in CATALOG_COLLECTIONS}


def hunt_manifest(catalog_hunts: List[Dict]) -> List[Dict]:
    """The catalog's `hunts` -> content/hunts/hunts.json. A projection, so the
    manifest can never disagree with the catalog about a hunt's map or start
    position: there is one merged copy, and this is a view of it."""
    return [
        {field: hunt[field] for field in HUNT_MANIFEST_FIELDS if field in hunt}
        for hunt in catalog_hunts
    ]


def respawn_file(monsters_entry: Dict) -> Dict:
    """The fragment's `monsters` entry -> content/hunts/respawn/<HUNT-ID>.json.
    Only the three keys the back-end reads: it passes the payload straight to
    Phaser, so the wrapper fields the old `monsters` collection added
    (`id`/`mapId`/`assetsRoot`) have nowhere to go."""
    return {
        "mapBoundsRef": monsters_entry["mapBoundsRef"],
        "monsterDefs": monsters_entry["monsterDefs"],
        "spawns": monsters_entry["spawns"],
    }


def loot_file_entry(loot_entry: Dict) -> Dict:
    """The fragment's `loot` entry -> a content/hunts/loot.json row. Keyed by
    `mapId` alone; the `id` the old db.json collection carried was a
    json-server requirement, and json-server is gone."""
    return {"mapId": loot_entry["mapId"], "drops": loot_entry["drops"]}


def hunt_id_exists(catalog_hunts: List[Dict], loot_entries: List[Dict], map_id: str) -> bool:
    """Whether `map_id` is registered anywhere the export writes — checked
    against loot as well as hunts, since a hunts entry can be deleted by hand
    while its loot stays behind, and that still counts as "already exists"."""
    return any(entry.get("mapId") == map_id for entry in catalog_hunts) or any(
        entry.get("mapId") == map_id for entry in loot_entries
    )


def merge_hunt_into_catalog(catalog_hunts: List[Dict], hunts_entry: Dict) -> str:
    """Appends a hunt to the catalog if its mapId is new -> "added", or leaves
    the existing entry untouched -> "skipped".

    Append-only rather than upsert because every interesting field on a hunt
    is curated (see CURATED_HUNT_FIELDS): re-exporting would hand back the
    generated title and the placeholder seed. A hunt that genuinely needs
    updating is a hand edit — the mechanical half of a hunt (loot, respawn,
    and the map/startPosition the manifest projects) is upserted separately
    and does stay fresh."""
    map_id = hunts_entry["mapId"]
    if any(entry.get("mapId") == map_id for entry in catalog_hunts):
        return "skipped"
    catalog_hunts.append(hunts_entry)
    return "added"


def upsert_loot_entry(loot_entries: List[Dict], entry: Dict) -> str:
    """Upserts a loot row by mapId -> "added"/"updated". Purely mechanical —
    every drop is derived from the monster defs, so a re-export always wins."""
    for i, existing in enumerate(loot_entries):
        if existing.get("mapId") == entry["mapId"]:
            loot_entries[i] = entry
            return "updated"
    loot_entries.append(entry)
    return "added"
