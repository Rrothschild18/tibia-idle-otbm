"""
CLI: generate a standalone JSON fragment with the `monsters`/`loot`/`hunts`
collection entries a map needs in tibia-idle's db.json, and optionally merge
it straight in with --write-db.

`monsters` and `loot` are always fully correct (mechanically derived from
ready-maps/<cidade>/<pasta>/monsters/respawn.json), so --write-db always
upserts them by mapId — same as what the old sync-loot-from-extractor.py did.
`hunts` needs real human curation (art, wording, spawn tile — see
hunt_fragment.py), so it's append-only: an existing hunts entry is never
overwritten, only new mapIds get added, as drafts flagged with "_todo" right
in db.json.

The map's id is never invented by this script — it's read from the map's own
folder name (`<ID>_nome-descritivo` -> `<ID>`, see extractor/README.md) and
must be repeated explicitly via --map-id as a second, independent
confirmation; a mismatch between the two is a hard error. Writing a mapId
that already exists in db.json requires --edit — without it, that's also a
hard error, and nothing is written.

Without --write-db (the default) nothing outside extractor/ is touched — the
fragment is written to ready-maps/<cidade>/<pasta>/db-fragment.json for you
to review and copy in by hand.

Requires `node build_map.js <nome-da-pasta-do-mapa>` to have run already
(reads ready-maps/<cidade>/<pasta>/monsters/respawn.json).

Run: python build_hunt_fragment.py <nome-da-pasta> --map-id ROOK-HUNT-0010 [--write-db [--edit]]
     python build_hunt_fragment.py --all [--write-db [--edit]]
"""

import argparse
import json
import os
import sys

import map_dirs
from hunt_fragment import (
    MapIdAlreadyExistsError,
    MapIdMismatchError,
    build_fragment,
    map_id_exists,
    map_id_from_folder,
    merge_fragment_into_db,
)

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
EXTRACTOR_DIR = os.path.dirname(SCRIPTS_DIR)
READY_MAPS_DIR = os.path.join(EXTRACTOR_DIR, "ready-maps")
# Sibling repo checkout: <workspace>/tibia-idle-otbm and <workspace>/tibia-idle/tibia-idle.
DEFAULT_TIBIA_IDLE_DIR = os.path.abspath(
    os.path.join(EXTRACTOR_DIR, "..", "..", "tibia-idle", "tibia-idle")
)


def discover_map_names():
    return map_dirs.discover_two_level_names(READY_MAPS_DIR, os.path.join("monsters", "respawn.json"))


def _load_respawn(map_name: str):
    map_dir = map_dirs.find_two_level_dir(READY_MAPS_DIR, map_name)
    if map_dir is None:
        return None
    respawn_path = os.path.join(map_dir, "monsters", "respawn.json")
    if not os.path.exists(respawn_path):
        return None
    with open(respawn_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_fragment_file(map_name: str, fragment: dict) -> str:
    map_dir = map_dirs.find_two_level_dir(READY_MAPS_DIR, map_name)
    out_path = os.path.join(map_dir, "db-fragment.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(fragment, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return out_path


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("map_name", nargs="?", help="Nome da pasta do mapa (em extractor/ready-maps/<cidade>/)")
    parser.add_argument("--all", action="store_true", help="Processa todos os mapas com respawn.json")
    parser.add_argument(
        "--map-id",
        help="ID do jogo a confirmar (ex: ROOK-HUNT-0010) — obrigatório com um único mapa, "
        "precisa bater com o id embutido no nome da pasta",
    )
    parser.add_argument(
        "--write-db",
        action="store_true",
        help="Além do fragmento, mescla direto no db.json do tibia-idle: monsters/loot sempre "
        "atualizados por mapId, hunts só é adicionado se o mapId ainda não existir (nunca sobrescreve "
        "um hunt já curado)",
    )
    parser.add_argument(
        "--edit",
        action="store_true",
        help="Confirma a intenção de rodar de novo sobre um mapId que já existe em db.json (sem "
        "isso, mapId existente é erro). Não sobrescreve hunts já curado — só destrava monsters/loot "
        "(sempre mecânicos, sempre atualizados)",
    )
    parser.add_argument(
        "--tibia-idle-dir",
        default=DEFAULT_TIBIA_IDLE_DIR,
        help=f"Path do checkout do tibia-idle, usado só com --write-db (default: {DEFAULT_TIBIA_IDLE_DIR})",
    )
    args = parser.parse_args()

    if not args.all and not args.map_name:
        parser.error("informe <nome-da-pasta> ou --all")
    if args.all and args.map_id:
        parser.error("--map-id não pode ser usado com --all (cada mapa tem seu próprio id, embutido na pasta)")
    if not args.all and not args.map_id:
        parser.error("--map-id é obrigatório (confirma o id embutido no nome da pasta)")

    map_names = discover_map_names() if args.all else [args.map_name]
    if not map_names:
        print(f"Nenhum mapa com respawn.json encontrado em {READY_MAPS_DIR}")
        sys.exit(1)

    db = None
    db_path = None
    if args.write_db:
        db_path = os.path.join(args.tibia_idle_dir, "apps", "tibia-idle-mock-api", "db.json")
        if not os.path.exists(db_path):
            parser.error(f"db.json não encontrado em {db_path} (use --tibia-idle-dir)")
        with open(db_path, "r", encoding="utf-8") as f:
            db = json.load(f)

    generated = 0
    try:
        for map_name in map_names:
            respawn = _load_respawn(map_name)
            if respawn is None:
                print(f"[SKIP] {map_name}: sem monsters/respawn.json (mapa sem spawns, ou build_map.js não rodado)")
                continue

            folder_id = map_id_from_folder(map_name)
            if args.map_id and args.map_id != folder_id:
                raise MapIdMismatchError(args.map_id, folder_id)
            map_id = args.map_id or folder_id

            if db is not None and not args.edit and map_id_exists(db["hunts"], db["monsters"], map_id):
                raise MapIdAlreadyExistsError(map_id)

            fragment = build_fragment(respawn, map_name, map_id)
            out_path = _write_fragment_file(map_name, fragment)
            generated += 1
            print(f"[OK] {map_name}: {len(fragment['loot']['drops'])} loot rows -> {out_path}")

            if db is not None:
                report = merge_fragment_into_db(db, fragment)
                note = " (já existia, hunts NÃO sobrescrito — edite à mão se quiser atualizar)" if report["hunts"] == "skipped" else ""
                print(f"     db.json: monsters {report['monsters']}, loot {report['loot']}, hunts {report['hunts']}{note}")
            elif fragment["hunts"]["_todo"]:
                print(f"     hunts precisa de revisão manual: {'; '.join(fragment['hunts']['_todo'])}")
    except (MapIdMismatchError, MapIdAlreadyExistsError) as err:
        print(f"[ERRO] {map_name}: {err}")
        sys.exit(1)

    if db is not None:
        with open(db_path, "w", encoding="utf-8") as f:
            json.dump(db, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"\n{generated}/{len(map_names)} mapa(s) mesclado(s) em {db_path}.")
    else:
        print(f"\n{generated}/{len(map_names)} fragmento(s) gerado(s). Nada foi escrito em db.json — copie manualmente.")


if __name__ == "__main__":
    main()
