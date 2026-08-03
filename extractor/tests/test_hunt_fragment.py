import hunt_fragment as hf


def _respawn(spawns=None, monster_defs=None):
    return {
        "mapBoundsRef": {"minX": 1000, "minY": 2000, "maxX": 1100, "maxY": 2050},
        "monsterDefs": monster_defs
        if monster_defs is not None
        else {
            "21": {
                "name": "Rat",
                "outfitId": 21,
                "loot": [
                    {"itemId": 3031, "itemName": "gold coin", "dropChance": 1, "countMin": 1, "countMax": 4, "rarity": "always"},
                ],
            },
            "30": {
                "name": "Spider",
                "outfitId": 30,
                "loot": [],
            },
        },
        "spawns": spawns
        if spawns is not None
        else [
            {"name": "Rat", "outfitId": 21, "worldX": 1010, "worldY": 2010},
            {"name": "Rat", "outfitId": 21, "worldX": 1020, "worldY": 2020},
            {"name": "Spider", "outfitId": 30, "worldX": 1030, "worldY": 2030},
        ],
    }


# ======================================================
# build_monsters_entry
# ======================================================


def test_build_monsters_entry_carries_bounds_defs_and_spawns_through():
    respawn = _respawn()

    entry = hf.build_monsters_entry(respawn, "rats-cave", "ROOK-0010")

    assert entry["id"] == "ROOK-0010"
    assert entry["mapId"] == "ROOK-0010"
    assert entry["assetsRoot"] == "assets/rats-cave-sprites/monsters"
    assert entry["mapBoundsRef"] == respawn["mapBoundsRef"]
    assert entry["monsterDefs"] == respawn["monsterDefs"]
    assert entry["spawns"] == respawn["spawns"]


# ======================================================
# build_loot_entry
# ======================================================


def test_build_loot_entry_flattens_loot_across_monster_defs_tagging_monster_name():
    respawn = _respawn()
    monsters_entry = hf.build_monsters_entry(respawn, "rats-cave", "ROOK-0010")

    loot_entry = hf.build_loot_entry(monsters_entry, "ROOK-0010")

    assert loot_entry["id"] == "ROOK-0010"
    assert loot_entry["mapId"] == "ROOK-0010"
    assert loot_entry["drops"] == [
        {"itemId": 3031, "itemName": "gold coin", "dropChance": 1, "countMin": 1, "countMax": 4, "rarity": "always", "monsterName": "Rat"},
    ]


def test_build_loot_entry_empty_when_no_monster_def_has_loot():
    respawn = _respawn(monster_defs={"30": {"name": "Spider", "outfitId": 30, "loot": []}})
    monsters_entry = hf.build_monsters_entry(respawn, "spider-cave", "ROOK-0011")

    loot_entry = hf.build_loot_entry(monsters_entry, "ROOK-0011")

    assert loot_entry["drops"] == []


# ======================================================
# build_hunts_entry
# ======================================================


def test_build_hunts_entry_derives_title_and_paths_from_map_name():
    respawn = _respawn()

    entry = hf.build_hunts_entry(respawn, "rats-cave-rookguard", "ROOK-0010")

    assert entry["name"] == "Rats Cave Rookguard"
    assert entry["label"] == "Rats Cave Rookguard"
    assert entry["assetsRoot"] == "assets/rats-cave-rookguard-sprites"
    assert entry["mapUrl"] == "assets/rats-cave-rookguard-sprites/map.json"
    assert entry["portrait"] == hf.PLACEHOLDER_PORTRAIT
    assert entry["seed"] == hf.PLACEHOLDER_SEED


def test_build_hunts_entry_picks_most_frequent_spawn_as_monster_preview():
    # Rat appears twice, Spider once -> Rat wins, matching every hunt in db.json.
    respawn = _respawn()

    entry = hf.build_hunts_entry(respawn, "rats-cave", "ROOK-0010")

    assert entry["monsterPreview"] == {
        "name": "Rat",
        "icon": "/assets/outfits/21.png",
        "atlas": "/assets/outfits/21.json",
    }


def test_build_hunts_entry_start_position_is_bounds_center():
    respawn = _respawn()

    entry = hf.build_hunts_entry(respawn, "rats-cave", "ROOK-0010")

    assert entry["startPosition"] == [1050, 2025]


def test_build_hunts_entry_flags_missing_preview_when_no_spawns():
    respawn = _respawn(spawns=[])

    entry = hf.build_hunts_entry(respawn, "empty-map", "ROOK-0012")

    assert entry["monsterPreview"] is None
    assert any("monsterPreview" in note for note in entry["_todo"])


def test_build_hunts_entry_always_flags_fields_needing_human_review():
    respawn = _respawn()

    entry = hf.build_hunts_entry(respawn, "rats-cave", "ROOK-0010")

    assert entry["_todo"]  # name/label/portrait/startPosition always need a look


def test_build_hunts_entry_derives_city_from_id_with_no_status_for_a_real_city():
    entry = hf.build_hunts_entry(_respawn(), "rats-cave", "ROOK-HUNT-0010")

    assert entry["city"] == "ROOK"
    assert "status" not in entry


def test_build_hunts_entry_derives_test_status_for_the_test_city():
    entry = hf.build_hunts_entry(_respawn(), "dragon-darashia", "TEST-HUNT-0001")

    assert entry["city"] == "TEST"
    assert entry["status"] == "test"


def test_build_hunts_entry_titles_from_the_descriptive_part_not_the_full_folder_name():
    # map_name is the real ready-maps/<CIDADE>/<pasta> leaf name, id prefix
    # and all — the human-facing title must ignore the id, or a map like
    # ROOK-HUNT-0018_bugs-rookguard gets a garbage title ("Rook Hunt
    # 0018_bugs Rookguard") instead of "Bugs Rookguard".
    entry = hf.build_hunts_entry(_respawn(), "ROOK-HUNT-0018_bugs-rookguard", "ROOK-HUNT-0018")

    assert entry["name"] == "Bugs Rookguard"
    assert entry["label"] == "Bugs Rookguard"
    # assetsRoot/mapUrl DO use the full folder name — that's the real
    # ready-maps output path the game fetches assets from.
    assert entry["assetsRoot"] == "assets/ROOK-HUNT-0018_bugs-rookguard-sprites"


# ======================================================
# build_fragment
# ======================================================


def test_build_fragment_shares_the_same_id_across_all_three_collections():
    respawn = _respawn()

    fragment = hf.build_fragment(respawn, "rats-cave", "ROOK-0010")

    assert fragment["monsters"]["id"] == "ROOK-0010"
    assert fragment["loot"]["id"] == "ROOK-0010"
    assert fragment["hunts"]["id"] == "ROOK-0010"


def test_build_fragment_uses_placeholder_id_and_flags_it_when_map_id_omitted():
    respawn = _respawn()

    fragment = hf.build_fragment(respawn, "rats-cave", None)

    assert fragment["monsters"]["id"] == hf.PLACEHOLDER_MAP_ID
    assert fragment["loot"]["id"] == hf.PLACEHOLDER_MAP_ID
    assert fragment["hunts"]["id"] == hf.PLACEHOLDER_MAP_ID
    assert any("--map-id" in note for note in fragment["hunts"]["_todo"])


# ======================================================
# map_id_from_folder
# ======================================================


def test_map_id_from_folder_takes_everything_before_the_first_underscore():
    assert hf.map_id_from_folder("ROOK-HUNT-0002_bears-rookguard") == "ROOK-HUNT-0002"


def test_map_id_from_folder_handles_test_city_ids_too():
    assert hf.map_id_from_folder("TEST-HUNT-0001_dragon-darashia") == "TEST-HUNT-0001"


# ======================================================
# map_id_exists
# ======================================================


def test_map_id_exists_true_when_present_in_hunts():
    hunts = [{"mapId": "ROOK-HUNT-0002"}]

    assert hf.map_id_exists(hunts, [], "ROOK-HUNT-0002") is True


def test_map_id_exists_true_when_present_only_in_monsters():
    # A hunts entry can be deleted by hand while monsters/loot stay
    # registered under the same id — still counts as "already exists".
    monsters = [{"mapId": "TEST-HUNT-0001"}]

    assert hf.map_id_exists([], monsters, "TEST-HUNT-0001") is True


def test_map_id_exists_false_for_an_unregistered_id():
    hunts = [{"mapId": "ROOK-HUNT-0002"}]

    assert hf.map_id_exists(hunts, [], "ROOK-HUNT-0012") is False


# ======================================================
# merge_fragment_into_db
# ======================================================


def _db(monsters=None, loot=None, hunts=None):
    return {"monsters": monsters or [], "loot": loot or [], "hunts": hunts or []}


def test_merge_fragment_into_db_appends_new_map_to_every_collection():
    respawn = _respawn()
    fragment = hf.build_fragment(respawn, "rats-cave", "ROOK-0010")
    db = _db()

    report = hf.merge_fragment_into_db(db, fragment)

    assert report == {"monsters": "added", "loot": "added", "hunts": "added"}
    assert db["monsters"] == [fragment["monsters"]]
    assert db["loot"] == [fragment["loot"]]
    assert db["hunts"] == [fragment["hunts"]]


def test_merge_fragment_into_db_upserts_monsters_and_loot_for_an_existing_map_id():
    respawn = _respawn()
    fragment = hf.build_fragment(respawn, "rats-cave", "ROOK-0010")
    db = _db(
        monsters=[{"id": "ROOK-0010", "mapId": "ROOK-0010", "monsterDefs": {"stale": True}}],
        loot=[{"id": "ROOK-0010", "mapId": "ROOK-0010", "drops": []}],
    )

    report = hf.merge_fragment_into_db(db, fragment)

    assert report["monsters"] == "updated"
    assert report["loot"] == "updated"
    assert len(db["monsters"]) == 1
    assert db["monsters"][0] == fragment["monsters"]
    assert len(db["loot"]) == 1
    assert db["loot"][0] == fragment["loot"]


def test_merge_fragment_into_db_never_overwrites_an_existing_curated_hunt():
    respawn = _respawn()
    fragment = hf.build_fragment(respawn, "rats-cave", "ROOK-0010")
    curated_hunt = {"id": "ROOK-0010", "mapId": "ROOK-0010", "name": "Rat Sewers", "portrait": "/real-art.png"}
    db = _db(hunts=[curated_hunt])

    report = hf.merge_fragment_into_db(db, fragment)

    assert report["hunts"] == "skipped"
    assert db["hunts"] == [curated_hunt]
