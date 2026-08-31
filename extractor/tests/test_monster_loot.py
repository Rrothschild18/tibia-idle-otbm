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
# load_item_decay_index / resolve_corpse_decay_chain
# ======================================================

DECAY_ITEMS_XML = """<?xml version="1.0" encoding="ISO-8859-1"?>
<items>
    <item id="5964" article="a" name="dead rat">
        <attribute key="fluidsource" value="blood"/>
        <attribute key="duration" value="10"/>
        <attribute key="decayTo" value="3994"/>
    </item>
    <item id="3994" article="a" name="dead rat">
        <attribute key="duration" value="300"/>
        <attribute key="decayTo" value="3996"/>
    </item>
    <item id="3996" article="a" name="dead rat">
        <attribute key="duration" value="60"/>
        <attribute key="decayTo" value="0"/>
    </item>
    <item id="5965" article="a" name="dead human">
        <attribute key="containersize" value="10"/>
    </item>
    <item fromid="4240" toid="4242" name="rotten pile">
        <attribute key="duration" value="45"/>
    </item>
</items>
"""


def _decay_index(tmp_path):
    items_xml = tmp_path / "items.xml"
    items_xml.write_text(DECAY_ITEMS_XML, encoding="utf-8")
    return ml.load_item_decay_index(str(items_xml))


def test_load_item_decay_index_reads_child_attributes(tmp_path):
    decay_index = _decay_index(tmp_path)

    assert decay_index[5964] == {"decayTo": 3994, "durationSeconds": 10}
    # decayTo="0" is kept as 0 (end of chain), not dropped
    assert decay_index[3996] == {"decayTo": 0, "durationSeconds": 60}
    # an item with neither attribute is not indexed at all
    assert 5965 not in decay_index
    # ranged entries carry the decay data across every id they span
    assert decay_index[4241] == {"decayTo": None, "durationSeconds": 45}


def test_load_item_decay_index_missing_file_returns_empty():
    assert ml.load_item_decay_index("does/not/exist.xml") == {}


def test_resolve_corpse_decay_chain_walks_until_decay_to_zero(tmp_path):
    stages = ml.resolve_corpse_decay_chain(5964, _decay_index(tmp_path))

    assert stages == [
        {"itemId": 5964, "durationSeconds": 10},
        {"itemId": 3994, "durationSeconds": 300},
        {"itemId": 3996, "durationSeconds": 60},
    ]


def test_resolve_corpse_decay_chain_single_stage_for_item_without_decay(tmp_path):
    """A corpse the source data gives no duration/decayTo for is still a stage —
    it just never ages (dead human, 5965)."""
    stages = ml.resolve_corpse_decay_chain(5965, _decay_index(tmp_path))
    assert stages == [{"itemId": 5965, "durationSeconds": None}]


def test_resolve_corpse_decay_chain_truncates_a_malformed_cycle():
    cyclic = {
        1: {"decayTo": 2, "durationSeconds": 5},
        2: {"decayTo": 1, "durationSeconds": 5},
    }
    stages = ml.resolve_corpse_decay_chain(1, cyclic)
    assert len(stages) == ml._MAX_DECAY_CHAIN_DEPTH


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

            monster.corpse = 5964
            monster.race = "blood"

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

    name, corpse_id, race, rows = ml.parse_monster_loot_lua(str(lua_file))

    assert name == "Rat"
    assert corpse_id == 5964
    assert race == "blood"
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

    name, corpse_id, race, rows = ml.parse_monster_loot_lua(str(lua_file))

    assert name == "Practice Target"
    assert corpse_id is None
    assert race is None
    assert rows == []


def test_parse_monster_loot_lua_no_loot_table(tmp_path):
    lua_file = tmp_path / "no_loot.lua"
    lua_file.write_text('local mType = Game.createMonsterType("Ghost")\n', encoding="utf-8")

    name, corpse_id, race, rows = ml.parse_monster_loot_lua(str(lua_file))

    assert name == "Ghost"
    assert corpse_id is None
    assert race is None
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


def test_build_monster_loot_attaches_corpse_with_resolved_chain():
    decay_index = {
        5964: {"decayTo": 3994, "durationSeconds": 10},
        3994: {"decayTo": 0, "durationSeconds": 300},
    }
    result = ml.build_monster_loot([], NAME_TO_ID, ID_TO_NAME, 5964, decay_index)

    assert result["corpse"] == {
        "itemId": 5964,
        "stages": [
            {"itemId": 5964, "durationSeconds": 10},
            {"itemId": 3994, "durationSeconds": 300},
        ],
    }


def test_build_monster_loot_omits_corpse_key_for_bodyless_monster():
    result = ml.build_monster_loot([], NAME_TO_ID, ID_TO_NAME, None, {})
    assert "corpse" not in result


def test_build_monster_loot_keeps_the_race_string_raw():
    """A raca decide o fluido da poca (blood/venom/ink pintam, undead/fire/
    energy nao pintam nada) — o indice guarda a string do Canary como veio e
    deixa a traducao pro jogo."""
    result = ml.build_monster_loot([], NAME_TO_ID, ID_TO_NAME, None, {}, "venom")
    assert result["race"] == "venom"


def test_build_monster_loot_omits_race_key_when_the_lua_never_declares_one():
    result = ml.build_monster_loot([], NAME_TO_ID, ID_TO_NAME, None, {}, None)
    assert "race" not in result


# ======================================================
# build_monster_loot_index (small fake install on disk)
# ======================================================


def test_build_monster_loot_index_walks_a_fake_install(tmp_path):
    items_dir = tmp_path / "data" / "items"
    items_dir.mkdir(parents=True)
    (items_dir / "items.xml").write_text(
        '<?xml version="1.0"?><items>'
        '<item id="3031" name="gold coin"/>'
        '<item id="5964" name="dead rat"><attribute key="duration" value="10"/></item>'
        "</items>",
        encoding="utf-8",
    )

    monster_dir = tmp_path / "data-otservbr-global" / "monster" / "mammals"
    monster_dir.mkdir(parents=True)
    (monster_dir / "rat.lua").write_text(
        textwrap.dedent(
            """\
            local mType = Game.createMonsterType("Rat")
            local monster = {}
            monster.corpse = 5964
            monster.race = "blood"
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
    assert index["Rat"]["corpse"] == {"itemId": 5964, "stages": [{"itemId": 5964, "durationSeconds": 10}]}
    assert index["Rat"]["race"] == "blood"
    assert index["Practice Target"]["loot"] == []
    assert "corpse" not in index["Practice Target"]
    assert "race" not in index["Practice Target"]
