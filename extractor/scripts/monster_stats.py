"""Os números de combate de um monstro, lidos do `.lua` do Canary.

Existe porque a tabela do jogo (`MonsterTemplates`) era escrita à mão, com as
33 criaturas de Rookgaard. Todo monstro fora dela — os doze de Carlin, e os de
qualquer cidade nova — caía num placeholder de 20 de vida: a Amazon, que tem
110, morria em dois golpes e dava 5 de experiência no lugar de 60.

**O que é lido e o que é derivado.** `maxHealth` e `experienceReward` saem
crus do `.lua`: são os mesmos números que a tabela à mão já usava nos 33 (Rat
20/5, Troll 50/20, Minotaur 100/50 — conferidos um a um). `attackValue` é
derivado, porque o jogo não guarda dano: ele rola
`ceil(attackSkill * attackValue * 0.05 + attackValue * 0.5)`
(`combat-logic.rollRawMonsterDamage`), então o valor que reproduz o golpe do
Canary é `maxDamage / (attackSkill * 0.05 + 0.5)`. Com `attackSkill` 20 isso
devolve exatamente o que está escrito à mão para o Skeleton (20 -> 13) e para o
Minotaur (45 -> 30).

**Só o melee.** O modelo tem um ataque por criatura, e a tabela à mão já
resolvia assim ("Melee only — lifedrain spell ignored" no Skeleton). Uma
criatura com ataque à distância ganha `attackRange` 3, que é o que Orc Spearman
e Minotaur Mage usam apesar de o Canary dizer 7.
"""

import glob
import os
import re
from typing import Dict, Iterable, List, Optional

MONSTER_RELPATH = os.path.join("data-otservbr-global", "monster")

# O `attackSkill` dos hostis da tabela à mão. Não existe no Canary: lá o dano é
# um intervalo pronto, e aqui ele é fator de uma fórmula.
DEFAULT_ATTACK_SKILL = 20

# Orc Spearman e Minotaur Mage dizem `range = 7` no Canary e 3 na tabela à mão.
RANGED_ATTACK_RANGE = 3

# `range = 1` é ataque adjacente, não ataque à distância: é o que o lifedrain do
# Skeleton usa, e a tabela à mão o trata como melee ("Melee only — lifedrain
# spell ignored").
ADJACENT_RANGE = 1
MELEE_ATTACK_RANGE = 1

_NAME_RE = re.compile(r'Game\.createMonsterType\(\s*"([^"]+)"\s*\)')
_HEALTH_RE = re.compile(r"monster\.health\s*=\s*(\d+)")
_EXPERIENCE_RE = re.compile(r"monster\.experience\s*=\s*(\d+)")
_DEFENSES_RE = re.compile(r"monster\.defenses\s*=\s*\{(.*?)\}", re.S)
_DEFENSE_RE = re.compile(r"defense\s*=\s*(\d+)")
_ARMOR_RE = re.compile(r"armor\s*=\s*(\d+)")
_ATTACKS_RE = re.compile(r"monster\.attacks\s*=\s*\{(.*?)\n\}", re.S)
_MELEE_RE = re.compile(r'name\s*=\s*"melee".*?maxDamage\s*=\s*-?(\d+)', re.S)
_RANGE_RE = re.compile(r"\brange\s*=\s*(\d+)")


def attack_value_for(max_damage: int, attack_skill: int = DEFAULT_ATTACK_SKILL) -> int:
    """O `attackValue` que faz a fórmula do jogo devolver `max_damage`."""
    factor = attack_skill * 0.05 + 0.5

    return max(1, round(max_damage / factor))


def parse_monster_stats_lua(path: str) -> Optional[Dict]:
    """Um `.lua` do Canary -> os números de combate, ou None se não for um.

    Um arquivo sem `health` não é definição de criatura (há lua de script e de
    spell na mesma árvore), e sem vida não há o que importar.
    """
    with open(path, "r", encoding="utf-8", errors="replace") as handler:
        text = handler.read()

    name = _NAME_RE.search(text)
    health = _HEALTH_RE.search(text)
    if not name or not health:
        return None

    defenses = _DEFENSES_RE.search(text)
    defense = _DEFENSE_RE.search(defenses.group(1)) if defenses else None
    armor = _ARMOR_RE.search(defenses.group(1)) if defenses else None

    attacks = _ATTACKS_RE.search(text)
    attacks_text = attacks.group(1) if attacks else ""
    melee = _MELEE_RE.search(attacks_text)
    melee_damage = int(melee.group(1)) if melee else 0
    ranged = any(int(found) > ADJACENT_RANGE for found in _RANGE_RE.findall(attacks_text))

    experience = _EXPERIENCE_RE.search(text)

    return {
        "name": name.group(1),
        "maxHealth": int(health.group(1)),
        "experienceReward": int(experience.group(1)) if experience else 0,
        "defense": int(defense.group(1)) if defense else 0,
        "armor": int(armor.group(1)) if armor else 0,
        "attackSkill": DEFAULT_ATTACK_SKILL if melee_damage else 0,
        "attackValue": attack_value_for(melee_damage) if melee_damage else 0,
        "attackRange": RANGED_ATTACK_RANGE if ranged else MELEE_ATTACK_RANGE,
        "meleeMaxDamage": melee_damage,
    }


def monster_lua_files(canary_dir: str) -> List[str]:
    return sorted(
        glob.glob(os.path.join(canary_dir, MONSTER_RELPATH, "**", "*.lua"), recursive=True)
    )


def build_monster_stats(
    canary_dir: str, names: Optional[Iterable[str]] = None
) -> Dict[str, Dict]:
    """Os números de cada monstro do Canary, por nome.

    `names` restringe ao que interessa — a comparação é sem caixa, porque o
    `respawn.json` guarda "Cave Rat" e o lua escreve "cave rat".
    """
    wanted = {name.lower() for name in names} if names is not None else None
    stats: Dict[str, Dict] = {}

    for path in monster_lua_files(canary_dir):
        parsed = parse_monster_stats_lua(path)
        if parsed is None:
            continue
        if wanted is not None and parsed["name"].lower() not in wanted:
            continue
        stats[parsed["name"]] = parsed

    return stats
