import json
import os

import monster_stats
import build_monster_stats


AMAZON_LUA = '''
local mType = Game.createMonsterType("Amazon")
local monster = {}
monster.experience = 60
monster.health = 110
monster.maxHealth = 110
monster.corpse = 18042
monster.Bestiary = {
\tclass = "Humanoid",
\trace = BESTY_RACE_HUMANOID,
\ttoKill = 500,
}
monster.attacks = {
\t{ name = "melee", interval = 2000, chance = 100, minDamage = 0, maxDamage = -45 },
\t{ name = "combat", interval = 2000, chance = 15, maxDamage = -40, range = 5, target = false },
}
monster.defenses = {
\tdefense = 10,
\tarmor = 10,
\tmitigation = 0.28,
}
'''

SKELETON_LUA = '''
local mType = Game.createMonsterType("Skeleton")
local monster = {}
monster.experience = 35
monster.health = 50
monster.attacks = {
\t{ name = "melee", interval = 2000, chance = 100, minDamage = 0, maxDamage = -20 },
\t{ name = "combat", interval = 2000, chance = 15, maxDamage = -13, range = 1, target = false },
}
monster.defenses = {
\tdefense = 10,
\tarmor = 2,
}
'''

NOT_A_MONSTER_LUA = 'local spell = Spell("instant")\nspell:name("Light Healing")\n'


def _write(tmp_path, relpath, text):
    path = tmp_path / "data-otservbr-global" / "monster" / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------------------
# attack_value_for
# ---------------------------------------------------------------------------

def test_attack_value_reproduz_o_golpe_do_canary():
    # A fórmula do jogo é ceil(skill * value * 0.05 + value * 0.5); com skill
    # 20 ela devolve exatamente o que a tabela à mão já tinha para o Skeleton
    # (golpe 20 -> 13) e para o Minotaur (45 -> 30).
    assert monster_stats.attack_value_for(20) == 13
    assert monster_stats.attack_value_for(45) == 30


def test_attack_value_nunca_zera_um_monstro_que_bate():
    assert monster_stats.attack_value_for(1) == 1


# ---------------------------------------------------------------------------
# parse_monster_stats_lua
# ---------------------------------------------------------------------------

def test_parse_le_vida_e_experiencia_cruas(tmp_path):
    path = _write(tmp_path, "humans/amazon.lua", AMAZON_LUA)

    stats = monster_stats.parse_monster_stats_lua(path)

    assert stats["name"] == "Amazon"
    assert stats["maxHealth"] == 110
    assert stats["experienceReward"] == 60
    assert stats["defense"] == 10
    assert stats["armor"] == 10


def test_parse_deriva_o_ataque_do_melee_e_ignora_a_magia(tmp_path):
    path = _write(tmp_path, "humans/amazon.lua", AMAZON_LUA)

    stats = monster_stats.parse_monster_stats_lua(path)

    # O golpe é o melee (45), não o arremesso (40): o modelo tem um ataque por
    # criatura, e é assim que a tabela à mão já resolvia.
    assert stats["meleeMaxDamage"] == 45
    assert stats["attackValue"] == 30
    assert stats["attackSkill"] == monster_stats.DEFAULT_ATTACK_SKILL


def test_parse_le_a_classe_do_bestiary(tmp_path):
    path = _write(tmp_path, "humans/amazon.lua", AMAZON_LUA)

    assert monster_stats.parse_monster_stats_lua(path)["bestiaryClass"] == "Humanoid"


def test_parse_sem_bestiary_nao_quebra(tmp_path):
    """Nem todo .lua tem o bloco Bestiary (bosses, por exemplo) — ausência não
    é motivo de erro, só "não sei a família"."""
    path = _write(tmp_path, "undeads/skeleton.lua", SKELETON_LUA)

    assert monster_stats.parse_monster_stats_lua(path)["bestiaryClass"] is None


def test_parse_trata_range_1_como_corpo_a_corpo(tmp_path):
    # O lifedrain do Skeleton tem `range = 1`, que é adjacente — a tabela à mão
    # o trata como melee.
    path = _write(tmp_path, "undeads/skeleton.lua", SKELETON_LUA)

    assert monster_stats.parse_monster_stats_lua(path)["attackRange"] == 1


def test_parse_marca_alcance_quando_o_ataque_passa_de_um_tile(tmp_path):
    path = _write(tmp_path, "humans/amazon.lua", AMAZON_LUA)

    assert (
        monster_stats.parse_monster_stats_lua(path)["attackRange"]
        == monster_stats.RANGED_ATTACK_RANGE
    )


def test_parse_devolve_none_para_lua_que_nao_e_criatura(tmp_path):
    path = _write(tmp_path, "spells/light_healing.lua", NOT_A_MONSTER_LUA)

    assert monster_stats.parse_monster_stats_lua(path) is None


# ---------------------------------------------------------------------------
# build_monster_stats
# ---------------------------------------------------------------------------

def test_build_filtra_por_nome_sem_olhar_caixa(tmp_path):
    _write(tmp_path, "humans/amazon.lua", AMAZON_LUA)
    _write(tmp_path, "undeads/skeleton.lua", SKELETON_LUA)

    stats = monster_stats.build_monster_stats(str(tmp_path), ["amazon"])

    assert list(stats) == ["Amazon"]


def test_build_sem_filtro_traz_todos(tmp_path):
    _write(tmp_path, "humans/amazon.lua", AMAZON_LUA)
    _write(tmp_path, "undeads/skeleton.lua", SKELETON_LUA)

    assert sorted(monster_stats.build_monster_stats(str(tmp_path))) == ["Amazon", "Skeleton"]


# ---------------------------------------------------------------------------
# spawned_monster_names / missing_names
# ---------------------------------------------------------------------------

def test_spawned_names_le_o_spawn_e_nao_o_monster_def(tmp_path):
    # Um outfit serve mais de uma criatura: no respawn dos trolls o mesmo 15
    # cobre Troll e Young Troll, e é o spawn que diz qual é qual.
    respawn = tmp_path / "ROOK" / "ROOK-HUNT-0003_trolls" / "monsters"
    respawn.mkdir(parents=True)
    (respawn / "respawn.json").write_text(
        json.dumps(
            {
                "monsterDefs": {"15": {"name": "Troll", "outfitId": 15}},
                "spawns": [{"name": "Troll"}, {"name": "Young Troll"}],
            }
        ),
        encoding="utf-8",
    )

    assert build_monster_stats.spawned_monster_names(str(tmp_path)) == {
        "Troll",
        "Young Troll",
    }


def test_missing_names_aponta_quem_o_canary_nao_tem():
    faltando = build_monster_stats.missing_names(
        {"Amazon", "Bicho Inventado"}, {"Amazon": {}}
    )

    assert faltando == ["Bicho Inventado"]
