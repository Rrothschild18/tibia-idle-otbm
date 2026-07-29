import textwrap

import monster_loot as ml


# ======================================================
# load_items_index
# ======================================================


def test_load_items_index_resolves_single_and_ranged_ids(tmp_path):
    items_xml = tmp_path / "items.xml"
    items_xml.write_text(
        textwrap.dedent(
            """\
            <?xml version="1.0" encoding="ISO-8859-1"?>
            <items>
                <item id="3031" name="gold coin"/>
                <item fromid="108" toid="110" name="flowers"/>
            </items>
            """
        ),
        encoding="utf-8",
    )

    name_to_id, id_to_name = ml.load_items_index(str(items_xml))

    assert name_to_id["gold coin"] == 3031
    assert id_to_name[3031] == "gold coin"
    # ranged entry resolves both the canonical (first) id and every id it spans
    assert name_to_id["flowers"] == 108
    assert id_to_name[108] == "flowers"
    assert id_to_name[109] == "flowers"
    assert id_to_name[110] == "flowers"


def test_load_items_index_missing_file_returns_empty():
    name_to_id, id_to_name = ml.load_items_index("does/not/exist.xml")
    assert name_to_id == {}
    assert id_to_name == {}


# ======================================================
# parse_monster_loot_lua
# ======================================================


def test_parse_monster_loot_lua_reads_name_and_rows(tmp_path):
    lua_file = tmp_path / "rat.lua"
    lua_file.write_text(
        textwrap.dedent(
            """\
            local mType = Game.createMonsterType("Rat")
            local monster = {}

            monster.loot = {
                { name = "gold coin", chance = 100000, maxCount = 4 },
                { id = 3607, chance = 39410 }, -- cheese
            }

            monster.attacks = {
                { name = "melee", interval = 2000, chance = 100, minDamage = 0, maxDamage = -8 },
            }
            """
        ),
        encoding="utf-8",
    )

    name, rows = ml.parse_monster_loot_lua(str(lua_file))

    assert name == "Rat"
    assert rows == [
        {"name": "gold coin", "chance": 100000, "maxCount": 4},
        {"id": 3607, "chance": 39410},
    ]


def test_parse_monster_loot_lua_handles_same_line_empty_table(tmp_path):
    """Regression: an empty `monster.loot = {}` (no newline before the
    closing brace) must not bleed into whatever section follows it — this
    tripped up a naive "find the next '\\n}'" approach during development."""
    lua_file = tmp_path / "trainer.lua"
    lua_file.write_text(
        textwrap.dedent(
            """\
            local mType = Game.createMonsterType("Practice Target")
            local monster = {}

            monster.loot = {}

            monster.attacks = {
                { name = "melee", interval = 2000, chance = 100, skill = 10, attack = 5 },
            }
            """
        ),
        encoding="utf-8",
    )

    name, rows = ml.parse_monster_loot_lua(str(lua_file))

    assert name == "Practice Target"
    assert rows == []


def test_parse_monster_loot_lua_no_loot_table(tmp_path):
    lua_file = tmp_path / "no_loot.lua"
    lua_file.write_text('local mType = Game.createMonsterType("Ghost")\n', encoding="utf-8")

    name, rows = ml.parse_monster_loot_lua(str(lua_file))

    assert name == "Ghost"
    assert rows == []


# ======================================================
# normalize_loot_entry / merge_duplicate_loot_entries / build_monster_loot
# ======================================================

NAME_TO_ID = {"gold coin": 3031, "cheese": 3607, "worm": 3687}
ID_TO_NAME = {v: k for k, v in NAME_TO_ID.items()}


def test_normalize_loot_entry_resolves_name_to_id():
    entry, issue = ml.normalize_loot_entry(
        {"name": "gold coin", "chance": 100000, "maxCount": 4}, NAME_TO_ID, ID_TO_NAME
    )
    assert issue is None
    assert entry == {
        "itemId": 3031,
        "itemName": "gold coin",
        "dropChance": 1.0,
        "rarity": "always",
        "countMin": 1,
        "countMax": 4,
    }


def test_normalize_loot_entry_resolves_display_name_for_id_only_rows():
    entry, issue = ml.normalize_loot_entry({"id": 3607, "chance": 39410}, NAME_TO_ID, ID_TO_NAME)
    assert issue is None
    assert entry["itemName"] == "cheese"


def test_normalize_loot_entry_flags_unresolved_name_instead_of_dropping():
    entry, issue = ml.normalize_loot_entry(
        {"name": "rotten shmeat", "chance": 15000}, NAME_TO_ID, ID_TO_NAME
    )
    assert entry is None
    assert issue == {"reason": "unresolved-item", "raw": {"name": "rotten shmeat", "chance": 15000}}


def test_normalize_loot_entry_handles_lowercase_count_field_variants():
    entry, issue = ml.normalize_loot_entry(
        {"name": "gold coin", "chance": 100000, "mincount": 10, "maxcount": 50}, NAME_TO_ID, ID_TO_NAME
    )
    assert issue is None
    assert entry["countMin"] == 10
    assert entry["countMax"] == 50


def test_merge_duplicate_loot_entries_sums_chance_and_widens_count():
    entries = [
        {"itemId": 3687, "itemName": "worm", "dropChance": 0.03, "rarity": "rare", "countMin": 1, "countMax": 1},
        {"itemId": 3687, "itemName": "worm", "dropChance": 0.005, "rarity": "very-rare", "countMin": 1, "countMax": 5},
    ]
    merged = ml.merge_duplicate_loot_entries(entries)
    assert len(merged) == 1
    assert merged[0]["dropChance"] == 0.035
    assert merged[0]["countMax"] == 5


def test_merge_duplicate_loot_entries_caps_combined_chance_at_one():
    entries = [
        {"itemId": 1, "itemName": "x", "dropChance": 0.9, "rarity": "always", "countMin": 1, "countMax": 1},
        {"itemId": 1, "itemName": "x", "dropChance": 0.5, "rarity": "always", "countMin": 1, "countMax": 1},
    ]
    merged = ml.merge_duplicate_loot_entries(entries)
    assert merged[0]["dropChance"] == 1.0


def test_build_monster_loot_sorts_by_chance_and_collects_issues():
    raw_rows = [
        {"name": "cheese", "chance": 39410},
        {"name": "gold coin", "chance": 100000, "maxCount": 4},
        {"name": "rotten shmeat", "chance": 15000},
    ]
    result = ml.build_monster_loot(raw_rows, NAME_TO_ID, ID_TO_NAME)

    assert [e["itemName"] for e in result["loot"]] == ["gold coin", "cheese"]
    assert len(result["issues"]) == 1
    assert result["issues"][0]["reason"] == "unresolved-item"


def test_build_monster_loot_empty_rows():
    result = ml.build_monster_loot([], NAME_TO_ID, ID_TO_NAME)
    assert result == {"loot": [], "issues": []}


# ======================================================
# build_monster_loot_index (small fake install on disk)
# ======================================================


def test_build_monster_loot_index_walks_a_fake_install(tmp_path):
    items_dir = tmp_path / "data" / "items"
    items_dir.mkdir(parents=True)
    (items_dir / "items.xml").write_text(
        '<?xml version="1.0"?><items><item id="3031" name="gold coin"/></items>',
        encoding="utf-8",
    )

    monster_dir = tmp_path / "data-otservbr-global" / "monster" / "mammals"
    monster_dir.mkdir(parents=True)
    (monster_dir / "rat.lua").write_text(
        textwrap.dedent(
            """\
            local mType = Game.createMonsterType("Rat")
            local monster = {}
            monster.loot = {
                { name = "gold coin", chance = 100000, maxCount = 4 },
            }
            """
        ),
        encoding="utf-8",
    )
    (monster_dir / "dummy.lua").write_text(
        'local mType = Game.createMonsterType("Practice Target")\nlocal monster = {}\nmonster.loot = {}\n',
        encoding="utf-8",
    )

    index = ml.build_monster_loot_index(str(tmp_path))

    assert set(index.keys()) == {"Rat", "Practice Target"}
    assert index["Rat"]["loot"][0]["itemName"] == "gold coin"
    assert index["Practice Target"]["loot"] == []
