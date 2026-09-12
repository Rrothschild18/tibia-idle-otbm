"""Gera `extractor/appearance-flags/<CIDADE>.json` a partir dos metadados de appearance.

Sem construir documento de mapa nenhum: lê o dump cru da cidade para saber
**quais** appearances aparecem nela, e a biblioteca de sprites para saber as
flags de cada uma. Não toca em sheets, tilesets, animações nem PNG.

Precisa de `extractor/sprites/` (os `.json` por appearance — **não** os PNGs;
`spriteWidth`/`spriteHeight`, que vêm da imagem, o grafo não usa). Num clone sem
a biblioteca de sprites a tabela versionada continua servindo: é exatamente por
isso que ela é versionada.

Run: node extractor/scripts/dump_otbm.js ROOK
     uv run python extractor/scripts/build_appearance_flags.py ROOK
"""

import argparse
import json
import os
import sys

import appearance_derivation
import appearance_flags

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
EXTRACTOR_DIR = os.path.dirname(SCRIPTS_DIR)
RAW_MAPS_DIR = os.path.join(EXTRACTOR_DIR, "raw-maps")

# As mesmas raízes que build_phaser_map.py procura, na mesma ordem.
ITEM_JSON_ROOTS = [
    os.path.join(EXTRACTOR_DIR, "sprites", "items"),
    os.path.join(EXTRACTOR_DIR, "sprites", "missiles"),
    os.path.join(EXTRACTOR_DIR, "sprites"),
]


def appearance_ids_in_dump(dump: dict):
    """Todo appearance id que a cidade usa: o `tileid` do chão e o `id` de cada
    item empilhado. É o mesmo conjunto que alimentava o `objectDefs`."""
    ids = set()

    # O dump é uma árvore OTBM; varrer recursivamente é mais simples e imune a
    # mudança de profundidade do que caminhar níveis nomeados.
    def walk(value):
        if isinstance(value, dict):
            if "tileid" in value and isinstance(value["tileid"], int):
                ids.add(value["tileid"])
            if "id" in value and isinstance(value["id"], int):
                ids.add(value["id"])
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(dump)
    return ids


def load_appearance_flags(appearance_id: int):
    """Flags de um appearance **como o pipeline as consome**, ou None se o
    `.json` dele não foi extraído.

    Não são as flags cruas do `appearances.dat`: `isFloorTransition` e `isRoof`
    não existem lá, são derivadas (ver `appearance_derivation.py`). Dumpar o
    cru foi o primeiro erro desta tabela — o grafo perdeu as escadas em
    silêncio, porque `unpass` batia e `isFloorTransition` vinha vazio.
    """
    for root in ITEM_JSON_ROOTS:
        for candidate in (
            os.path.join(root, f"{appearance_id}.json"),
            os.path.join(root, str(appearance_id), f"{appearance_id}.json"),
        ):
            if os.path.exists(candidate):
                with open(candidate, "r", encoding="utf-8") as handler:
                    data = json.load(handler)
                return appearance_derivation.pipeline_flags(
                    data.get("flags", {}), data.get("spriteInfo", {})
                )
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("city", help="Código da cidade (ex: ROOK)")
    args = parser.parse_args()

    dump_path = os.path.join(RAW_MAPS_DIR, f"{args.city}.raw.json")
    if not os.path.exists(dump_path):
        print(f"[ERROR] dump não encontrado em {dump_path}")
        print(f"        rode 'node extractor/scripts/dump_otbm.js {args.city}' primeiro")
        sys.exit(1)

    if not any(os.path.isdir(root) for root in ITEM_JSON_ROOTS):
        print("[ERROR] biblioteca de sprites não encontrada em extractor/sprites/.")
        print("        A tabela versionada em extractor/appearance-flags/ continua válida —")
        print("        regenerá-la é que exige os metadados de appearance (ver ticket 08).")
        sys.exit(1)

    with open(dump_path, "r", encoding="utf-8") as handler:
        dump = json.load(handler)

    ids = appearance_ids_in_dump(dump)
    flags_by_id = {}
    missing = 0
    for appearance_id in sorted(ids):
        flags = load_appearance_flags(appearance_id)
        if flags is None:
            missing += 1
            continue
        flags_by_id[appearance_id] = flags

    path = appearance_flags.write_table(args.city, flags_by_id)
    written = len(json.load(open(path, encoding="utf-8")))
    print(f"[OK] {written} appearances com flag -> {path}")
    print(f"     ({len(ids)} ids na cidade, {missing} sem metadado extraído)")

    overrides = appearance_flags.overrides_path(args.city)
    if os.path.exists(overrides):
        count = len(json.load(open(overrides, encoding="utf-8")))
        print(f"[OK] {count} override(s) preservado(s) -> {overrides}")


if __name__ == "__main__":
    main()
