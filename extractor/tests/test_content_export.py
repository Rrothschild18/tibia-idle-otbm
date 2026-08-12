import re

import content_export as ce

# Copied verbatim from the back-end's BUNDLE_URL_PATTERN
# (libs/models/content/src/lib/import-source.model.ts). A `mapUrl` that
# doesn't match is rejected at import — this is the rule that let a hunt
# built without the `-v<N>` suffix break `nx run db:reset`.
BUNDLE_URL_PATTERN = re.compile(r"^(assets/.+-v(\d+))/map\.json$")


def test_map_bundle_url_matches_the_back_ends_bundle_pattern():
    assert BUNDLE_URL_PATTERN.match(ce.map_bundle_url("ROOK-HUNT-0013_rats-rookguard"))


def test_map_bundle_url_carries_the_version_in_the_folder_name():
    assert ce.map_bundle_url("ROOK-HUNT-0013_rats-rookguard") == (
        "assets/ROOK-HUNT-0013_rats-rookguard-sprites-v6/map.json"
    )
    assert ce.map_bundle_root("ROOK-HUNT-0013_rats-rookguard") == (
        "assets/ROOK-HUNT-0013_rats-rookguard-sprites-v6"
    )


def _hunt(map_id, **overrides):
    entry = {
        "id": map_id,
        "mapId": map_id,
        "name": "Rat Sewers",
        "label": "Rat Sewers",
        "seed": "000000123456789abcdef",
        "assetsRoot": "assets/rats-sewers-sprites",
        "mapUrl": f"assets/{map_id}_rats-sewers-sprites-v6/map.json",
        "portrait": "/assets/rats-sewers-portrait.png",
        "startPosition": [2368, 800],
        "city": "ROOK",
    }
    entry.update(overrides)
    return entry


def test_empty_catalog_has_every_collection_so_callers_never_check_for_a_key():
    assert ce.empty_catalog() == {"hunts": [], "locations": [], "travelGraph": []}


# ======================================================
# content/hunts/hunts.json — a projection, never a second copy
# ======================================================


def test_hunt_manifest_keeps_only_what_the_simulator_reads():
    manifest = ce.hunt_manifest([_hunt("ROOK-HUNT-0001")])

    assert manifest == [{
        "id": "ROOK-HUNT-0001",
        "mapId": "ROOK-HUNT-0001",
        "mapUrl": "assets/ROOK-HUNT-0001_rats-sewers-sprites-v6/map.json",
        "startPosition": [2368, 800],
    }]


def test_hunt_manifest_follows_a_curated_start_position_because_it_is_a_view():
    # The manifest can't drift from the catalog: editing the hunt's
    # startPosition by hand is enough, nothing has to be re-synced.
    manifest = ce.hunt_manifest([_hunt("ROOK-HUNT-0001", startPosition=[1, 2])])

    assert manifest[0]["startPosition"] == [1, 2]


def test_hunt_manifest_omits_a_field_the_hunt_does_not_carry():
    manifest = ce.hunt_manifest([{"id": "ROOK-HUNT-0001", "mapId": "ROOK-HUNT-0001"}])

    assert manifest == [{"id": "ROOK-HUNT-0001", "mapId": "ROOK-HUNT-0001"}]


# ======================================================
# content/hunts/respawn/<HUNT-ID>.json and loot.json
# ======================================================


def test_respawn_file_drops_the_wrapper_the_back_end_no_longer_reads():
    monsters_entry = {
        "id": "ROOK-HUNT-0001",
        "mapId": "ROOK-HUNT-0001",
        "assetsRoot": "assets/rats-sewers-sprites/monsters",
        "mapBoundsRef": {"minX": 998, "minY": 1018, "maxX": 1113, "maxY": 1080},
        "monsterDefs": {"rat": {"name": "Rat"}},
        "spawns": [{"name": "Rat"}],
    }

    assert ce.respawn_file(monsters_entry) == {
        "mapBoundsRef": {"minX": 998, "minY": 1018, "maxX": 1113, "maxY": 1080},
        "monsterDefs": {"rat": {"name": "Rat"}},
        "spawns": [{"name": "Rat"}],
    }


def test_loot_file_entry_is_keyed_by_map_id_alone():
    drops = [{"itemId": 3031, "itemName": "gold coin", "monsterName": "Rat"}]

    entry = ce.loot_file_entry({"id": "ROOK-HUNT-0001", "mapId": "ROOK-HUNT-0001", "drops": drops})

    assert entry == {"mapId": "ROOK-HUNT-0001", "drops": drops}


# ======================================================
# Merging into the catalog
# ======================================================


def test_merge_hunt_into_catalog_appends_a_hunt_whose_id_is_new():
    catalog_hunts = []

    state = ce.merge_hunt_into_catalog(catalog_hunts, _hunt("ROOK-HUNT-0001"))

    assert state == "added"
    assert [h["mapId"] for h in catalog_hunts] == ["ROOK-HUNT-0001"]


def test_merge_hunt_into_catalog_never_overwrites_a_curated_hunt():
    curated = _hunt("ROOK-HUNT-0001", name="Esgoto dos Ratos", portrait="/assets/real-art.png")
    catalog_hunts = [curated]

    state = ce.merge_hunt_into_catalog(catalog_hunts, _hunt("ROOK-HUNT-0001"))

    assert state == "skipped"
    assert catalog_hunts == [curated]


def test_upsert_loot_entry_always_takes_the_fresh_drops():
    loot_entries = [{"mapId": "ROOK-HUNT-0001", "drops": []}]
    fresh = {"mapId": "ROOK-HUNT-0001", "drops": [{"itemId": 3031}]}

    state = ce.upsert_loot_entry(loot_entries, fresh)

    assert state == "updated"
    assert loot_entries == [fresh]


def test_upsert_loot_entry_appends_a_map_id_it_has_not_seen():
    loot_entries = []

    state = ce.upsert_loot_entry(loot_entries, {"mapId": "ROOK-HUNT-0002", "drops": []})

    assert state == "added"
    assert len(loot_entries) == 1


# ======================================================
# hunt_id_exists
# ======================================================


def test_hunt_id_exists_true_when_the_catalog_has_it():
    assert ce.hunt_id_exists([_hunt("ROOK-HUNT-0002")], [], "ROOK-HUNT-0002") is True


def test_hunt_id_exists_true_when_only_the_loot_still_has_it():
    # A hunts entry deleted by hand while its loot stayed behind still counts
    # as registered — otherwise a re-export would look like a fresh creation.
    loot_entries = [{"mapId": "TEST-HUNT-0001", "drops": []}]

    assert ce.hunt_id_exists([], loot_entries, "TEST-HUNT-0001") is True


def test_hunt_id_exists_false_for_an_unregistered_id():
    assert ce.hunt_id_exists([_hunt("ROOK-HUNT-0002")], [], "ROOK-HUNT-0012") is False
