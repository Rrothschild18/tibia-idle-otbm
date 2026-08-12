"""
Pure logic for turning a map's ready-maps/<CIDADE>/<pasta>/monsters/respawn.json
into a `{monsters, loot, hunts}` fragment — see build_hunt_fragment.py for the
CLI that reads/writes files, and content_export.py for where each of the three
lands in the back-end once exported.

`monsters` and `loot` are always fully correct: every field is mechanically
derived from respawn.json plus the map's assigned id, so exporting always
overwrites them. `hunts` cannot be fully correct — name/label/portrait/
startPosition are real human decisions (existing hunts use hand-picked art and
coordinates that don't follow any derivable rule) — so build_hunts_entry()
returns a best-effort scaffold flagged with "_todo", and the export only ever
*appends* a hunts entry whose mapId isn't already there; an existing
hand-curated hunt is never overwritten.
"""

import posixpath
from collections import Counter
from typing import Dict, List, Optional

import city_ids

PLACEHOLDER_MAP_ID = "TODO-ASSIGN-ID"
# The catalog's `seed` field has no known consumer today — every existing hunt
# just has a unique-looking placeholder string. Match that shape.
PLACEHOLDER_SEED = "0" * 22
PLACEHOLDER_PORTRAIT = "/assets/character-default.png"


def _descriptive_name(map_name: str) -> str:
    """`"ROOK-HUNT-0010_bears-rookguard"` -> `"bears-rookguard"` — the
    human-facing title is derived only from the part after the id (see
    map_id_from_folder), never the id itself, or a map like
    `ROOK-HUNT-0018_bugs-rookguard` gets a garbage title like "Rook Hunt
    0018_bugs Rookguard" instead of "Bugs Rookguard". `map_name` without an
    underscore (older call sites, tests) passes through unchanged."""
    return map_name.split("_", 1)[1] if "_" in map_name else map_name


def _title_from_map_name(map_name: str) -> str:
    return " ".join(word.capitalize() for word in _descriptive_name(map_name).split("-"))


def _most_common_spawn(spawns: List[Dict]) -> Optional[Dict]:
    """Picks the spawn entry whose monster name occurs most often — matches
    every existing hunt's monsterPreview (verified against the catalog)."""
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

    city = city_ids.derive_city(map_id)
    status = city_ids.derive_status(city)

    entry = {
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
        "city": city,
        "_todo": todo,
    }
    if status is not None:
        entry["status"] = status
    return entry


def build_fragment(respawn: Dict, map_name: str, map_id: Optional[str]) -> Dict:
    """Assembles the full {monsters, loot, hunts} fragment. `map_id` is the
    game id (e.g. "ROOK-0010") the map should get in the catalog — if omitted,
    a placeholder is used and flagged in hunts._todo."""
    resolved_id = map_id or PLACEHOLDER_MAP_ID
    monsters_entry = build_monsters_entry(respawn, map_name, resolved_id)
    loot_entry = build_loot_entry(monsters_entry, resolved_id)
    hunts_entry = build_hunts_entry(respawn, map_name, resolved_id)
    if map_id is None:
        hunts_entry["_todo"].insert(0, "atribuir um id/mapId real (rode com --map-id)")
    return {"monsters": monsters_entry, "loot": loot_entry, "hunts": hunts_entry}


def map_id_from_folder(map_name: str) -> str:
    """`"<ID>_nome-descritivo"` -> `"<ID>"` — the id is always the folder name
    up to its first underscore, chosen by hand (typed into the map-editor
    sign, mirrored into the folder name) before any script runs. Nothing in
    the pipeline invents or auto-numbers this id anymore; it only reads and
    validates the one already chosen (see build_hunt_fragment.py's
    --map-id comparison)."""
    return map_name.split("_", 1)[0]


class MapIdMismatchError(ValueError):
    """Raised when --map-id disagrees with the id embedded in the map's own
    folder name — the two are meant to be an explicit double-confirmation of
    the same value, never a silent pick-one."""

    def __init__(self, map_id: str, folder_id: str):
        super().__init__(
            f"--map-id {map_id} não bate com o id da pasta ({folder_id})"
        )
        self.map_id = map_id
        self.folder_id = folder_id


class MapIdAlreadyExistsError(ValueError):
    """Raised when a mapId already registered in the back-end content (hunts or loot)
    is about to be written again without --edit — updating curated data must
    always be an explicit, deliberate choice, never a silent upsert."""

    def __init__(self, map_id: str):
        super().__init__(
            f"ID do mapa já existe — use --edit se a intenção é atualizar ({map_id})"
        )
        self.map_id = map_id


# Where a fragment goes once it's exported — and how each collection merges
# with what's already there — lives in content_export.py, next to the paths
# it writes to. It used to live here, back when every collection landed in
# one db.json and "merge" was a single function.
