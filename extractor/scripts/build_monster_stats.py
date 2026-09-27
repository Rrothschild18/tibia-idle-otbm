"""Escreve `content/hunts/monster-stats.json` com os números de quem nasce nos mapas.

Roda depois de `build_map.js`, como o `bake_corpse_atlas.py`: quem decide o que
entra são os `respawn.json` construídos, e não a árvore inteira do Canary — o
jogo não precisa dos 1.400 monstros para desenhar dez hunts.

O arquivo é acumulativo por natureza: rodar de novo com uma cidade a mais só
acrescenta. Cada execução reescreve o arquivo inteiro a partir dos mapas que
existem, então um monstro que deixou de nascer sai junto.

    uv run python extractor/scripts/build_monster_stats.py
"""

import argparse
import glob
import json
import os
import sys
from typing import Dict, List, Set

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import monster_stats  # noqa: E402
import paths  # noqa: E402

EXTRACTOR_DIR = os.path.dirname(SCRIPTS_DIR)
READY_MAPS_DIR = os.path.join(EXTRACTOR_DIR, "ready-maps")
RESPAWN_RELPATH = os.path.join("monsters", "respawn.json")
OUTPUT_RELPATH = os.path.join("apps", "tibia-idle-api", "content", "hunts", "monster-stats.json")


def spawned_monster_names(root: str = READY_MAPS_DIR) -> Set[str]:
    """Os nomes que algum spawn usa. É o `spawn`, não o `monsterDef`: um outfit
    serve mais de uma criatura (o 15 cobre Troll e Young Troll), e quem diz o
    que a criatura é são os spawns — a mesma leitura que o Phaser faz."""
    names: Set[str] = set()
    for path in glob.glob(os.path.join(root, "*", "*", RESPAWN_RELPATH)):
        with open(path, "r", encoding="utf-8") as handler:
            respawn = json.load(handler)
        for spawn in respawn.get("spawns", []):
            if spawn.get("name"):
                names.add(spawn["name"])
    return names


def missing_names(names: Set[str], stats: Dict[str, Dict]) -> List[str]:
    found = {name.lower() for name in stats}

    return sorted(name for name in names if name.lower() not in found)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canary-dir", default=None, help=paths.CANARY.env_var)
    parser.add_argument("--tibia-idle-dir", default=None, help=paths.TIBIA_IDLE.env_var)
    args = parser.parse_args()

    try:
        canary = paths.CANARY.require(args.canary_dir)
        front = paths.TIBIA_IDLE.require(args.tibia_idle_dir)
    except paths.MissingRepoError as error:
        print(f"[ERRO] {error}")
        return 1

    monster_dir = os.path.join(canary, monster_stats.MONSTER_RELPATH)
    if not os.path.isdir(monster_dir):
        print(f"[ERRO] {monster_dir} não existe — {paths.CANARY.flag} aponta para um clone do Canary?")
        return 1

    names = spawned_monster_names()
    if not names:
        print(f"[ERRO] nenhum {RESPAWN_RELPATH} em {READY_MAPS_DIR} — rode build_map.js antes")
        return 1

    stats = monster_stats.build_monster_stats(canary, names)
    absent = missing_names(names, stats)

    output = os.path.join(front, OUTPUT_RELPATH)
    os.makedirs(os.path.dirname(output), exist_ok=True)
    with open(output, "w", encoding="utf-8") as handler:
        json.dump(
            {name: stats[name] for name in sorted(stats)},
            handler,
            indent=2,
            ensure_ascii=False,
        )
        handler.write("\n")

    print(f"[OK] {len(stats)} de {len(names)} monstro(s) spawnado(s) -> {output}")
    if absent:
        print(f"  [!] sem .lua no Canary, vão cair no placeholder: {absent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
