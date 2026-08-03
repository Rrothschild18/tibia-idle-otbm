"""
Pure logic for turning a map's ready-maps/<map>/monsters/respawn.json into a
tibia-idle db.json fragment, and for merging that fragment into an in-memory
db.json — see build_hunt_fragment.py for the CLI that reads/writes files.

`monsters` and `loot` are always fully correct: every field is mechanically
derived from respawn.json plus the map's assigned id, so merge_fragment_into_db()
always upserts them by mapId (matches what the old sync-loot-from-extractor.py
did). `hunts` cannot be fully correct — name/label/portrait/startPosition are
real human decisions (existing hunts use hand-picked art and coordinates that
don't follow any derivable rule) — so build_hunts_entry() returns a
best-effort scaffold flagged with "_todo", and merge_fragment_into_db() only
ever *appends* a hunts entry for a mapId that isn't already present; an
existing hand-curated hunt is never overwritten.
"""

import posixpath
import re
from collections import Counter
from typing import Dict, List, Optional

PLACEHOLDER_MAP_ID = "TODO-ASSIGN-ID"
# db.json's `seed` field has no known consumer today — every existing hunt
# just has a unique-looking placeholder string. Match that shape.
PLACEHOLDER_SEED = "0" * 22
PLACEHOLDER_PORTRAIT = "/assets/character-default.png"


def _title_from_map_name(map_name: str) -> str:
    return " ".join(word.capitalize() for word in map_name.split("-"))


def _most_common_spawn(spawns: List[Dict]) -> Optional[Dict]:
    """Picks the spawn entry whose monster name occurs most often — matches
    every existing hunt's monsterPreview (verified against db.json)."""
    if not spawns:
        return None
    top_name, _ = Counter(s["name"] for s in spawns).most_common(1)[0]
    return next(s for s in spawns if s["name"] == top_name)


def build_monsters_entry(respawn: Dict, map_name: str, map_id: str) -> Dict:
    return {
        "id": map_id,
        "mapId": map_id,
        "assetsRoot": posixpath.join("assets", f"{map_name}-sprites", "monsters"),
        "mapBoundsRef": respawn["mapBoundsRef"],
        "monsterDefs": respawn["monsterDefs"],
        "spawns": respawn["spawns"],
    }


def build_loot_entry(monsters_entry: Dict, map_id: str) -> Dict:
    drops = []
    for monster_def in monsters_entry["monsterDefs"].values():
        for loot_row in monster_def.get("loot", []):
            drops.append({**loot_row, "monsterName": monster_def["name"]})
    return {"id": map_id, "mapId": map_id, "drops": drops}


def build_hunts_entry(respawn: Dict, map_name: str, map_id: str) -> Dict:
    assets_root = posixpath.join("assets", f"{map_name}-sprites")
    bounds = respawn["mapBoundsRef"]
    preview_spawn = _most_common_spawn(respawn.get("spawns", []))

    todo = [
        "confirmar name/label (título gerado automaticamente do nome da pasta)",
        "criar a arte de portrait e apontar o path",
        "revisar startPosition (centro geométrico do mapBoundsRef, pode cair fora de área andável)",
    ]
    if preview_spawn is None:
        todo.insert(0, "sem spawns no mapa — monsterPreview precisa ser preenchido manualmente")

    return {
        "id": map_id,
        "mapId": map_id,
        "name": _title_from_map_name(map_name),
        "label": _title_from_map_name(map_name),
        "seed": PLACEHOLDER_SEED,
        "assetsRoot": assets_root,
        "mapUrl": posixpath.join(assets_root, "map.json"),
        "portrait": PLACEHOLDER_PORTRAIT,
        "monsterPreview": (
            {
                "name": preview_spawn["name"],
                "icon": f"/assets/outfits/{preview_spawn['outfitId']}.png",
                "atlas": f"/assets/outfits/{preview_spawn['outfitId']}.json",
            }
            if preview_spawn
            else None
        ),
        "startPosition": [
            round((bounds["minX"] + bounds["maxX"]) / 2),
            round((bounds["minY"] + bounds["maxY"]) / 2),
        ],
        "_todo": todo,
    }


def build_fragment(respawn: Dict, map_name: str, map_id: Optional[str]) -> Dict:
    """Assembles the full {monsters, loot, hunts} fragment. `map_id` is the
    game id (e.g. "ROOK-0010") the map should get in db.json — if omitted,
    a placeholder is used and flagged in hunts._todo."""
    resolved_id = map_id or PLACEHOLDER_MAP_ID
    monsters_entry = build_monsters_entry(respawn, map_name, resolved_id)
    loot_entry = build_loot_entry(monsters_entry, resolved_id)
    hunts_entry = build_hunts_entry(respawn, map_name, resolved_id)
    if map_id is None:
        hunts_entry["_todo"].insert(0, "atribuir um id/mapId real (rode com --map-id)")
    return {"monsters": monsters_entry, "loot": loot_entry, "hunts": hunts_entry}


def _id_prefix_for_map(map_name: str) -> str:
    """Every "-rookguard" map so far uses the "ROOK" prefix; anything else
    (dragon-darashia -> DRAGON, grim-reaper -> GRIM, ...) is a one-off area,
    so falling back to its first hyphen segment is the closest guess without
    a real taxonomy — still worth a glance before trusting it blindly."""
    if map_name.endswith("-rookguard"):
        return "ROOK"
    return re.split(r"[-_]", map_name)[0].upper()


def find_existing_map_id(hunts: List[Dict], monsters: List[Dict], map_name: str) -> Optional[str]:
    """Looks up whether map_name is already registered in db.json, matching on
    `assetsRoot` (convention-derived, stable) rather than mapId (hand-assigned
    per map, follows no rule map_name could reproduce — e.g. the "rats-sewers"
    folder is registered as "ROOK-0002"). Callers MUST try this before
    next_map_id(), or an already-registered map gets a second, duplicate entry
    under a freshly minted id instead of being recognized and upserted.

    Checks both `hunts` and `monsters` (not just `hunts`): a map can have its
    hunts entry removed by hand while monsters/loot are still registered under
    the old id — matching hunts alone would silently orphan that id and mint
    a new, colliding one instead of reusing it."""
    hunts_root = posixpath.join("assets", f"{map_name}-sprites")
    for entry in hunts:
        if entry.get("assetsRoot") == hunts_root:
            return entry.get("mapId")

    monsters_root = posixpath.join("assets", f"{map_name}-sprites", "monsters")
    for entry in monsters:
        if entry.get("assetsRoot") == monsters_root:
            return entry.get("mapId")

    return None


def next_map_id(hunts: List[Dict], map_name: str) -> str:
    """Next free id for map_name's prefix, based on the highest sequence
    number already used by that prefix in `hunts` (db.json's hunts collection)."""
    prefix = _id_prefix_for_map(map_name)
    max_seq = 0
    for entry in hunts:
        match = re.fullmatch(rf"{re.escape(prefix)}-(\d+)", entry.get("mapId", ""))
        if match:
            max_seq = max(max_seq, int(match.group(1)))
    return f"{prefix}-{max_seq + 1:04d}"


def _upsert_by_map_id(collection: List[Dict], entry: Dict) -> str:
    for i, existing in enumerate(collection):
        if existing.get("mapId") == entry["mapId"]:
            collection[i] = entry
            return "updated"
    collection.append(entry)
    return "added"


def merge_fragment_into_db(db: Dict, fragment: Dict) -> Dict[str, str]:
    """Merges a fragment into db's monsters/loot/hunts collections in place.
    Returns a {"monsters": ..., "loot": ..., "hunts": ...} status report, each
    one of "added"/"updated" ("hunts" can also be "skipped" — see module docstring)."""
    report = {
        "monsters": _upsert_by_map_id(db["monsters"], fragment["monsters"]),
        "loot": _upsert_by_map_id(db["loot"], fragment["loot"]),
    }

    map_id = fragment["hunts"]["mapId"]
    if any(entry.get("mapId") == map_id for entry in db["hunts"]):
        report["hunts"] = "skipped"
    else:
        db["hunts"].append(fragment["hunts"])
        report["hunts"] = "added"
    return report
