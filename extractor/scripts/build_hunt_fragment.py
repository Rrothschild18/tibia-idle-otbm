"""
CLI: generate a standalone JSON fragment with the `monsters`/`loot`/`hunts`
entries a map contributes to tibia-idle's back-end content, and optionally
write them there with --export.

The three don't share a destination anymore (see content_export.py): `hunts`
goes to content/catalog-source.json (which `import-content` turns into rows),
while `loot` and the respawn payload go to content/hunts/, read from disk at
runtime. content/hunts/hunts.json is rewritten as a projection of the
catalog's hunts, so the two can't drift.

`monsters` and `loot` are always fully correct (mechanically derived from
ready-maps/<CIDADE>/<pasta>/monsters/respawn.json), so --export always
overwrites them. `hunts` needs real human curation (art, wording, spawn tile
— see hunt_fragment.py), so it's append-only: an existing hunts entry is
never overwritten, only new mapIds get added, as drafts flagged with "_todo"
right in the catalog.

The map's id is never invented by this script — it's read from the map's own
folder name (`<ID>_nome-descritivo` -> `<ID>`, see extractor/README.md) and
must be repeated explicitly via --map-id as a second, independent
confirmation; a mismatch between the two is a hard error. Exporting a mapId
that is already registered requires --edit — without it, that's also a hard
error, and nothing is written.

Without --export (the default) nothing outside extractor/ is touched — the
fragment is written to ready-maps/<CIDADE>/<pasta>/db-fragment.json for you
to review and copy in by hand.

Requires `node build_map.js <nome-da-pasta-do-mapa>` to have run already
(reads ready-maps/<CIDADE>/<pasta>/monsters/respawn.json).

Run: python build_hunt_fragment.py <nome-da-pasta> --map-id ROOK-HUNT-0010 [--export [--edit]]
     python build_hunt_fragment.py --all [--export [--edit]]
"""

import argparse
import json
import os
import sys

import city_ids
import content_export
import map_dirs
from hunt_fragment import (
    MapIdAlreadyExistsError,
    MapIdMismatchError,
    build_fragment,
    map_id_from_folder,
)

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
EXTRACTOR_DIR = os.path.dirname(SCRIPTS_DIR)
READY_MAPS_DIR = os.path.join(EXTRACTOR_DIR, "ready-maps")
MAPS_DIR = os.path.join(EXTRACTOR_DIR, "maps")
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
    _write_json(out_path, fragment)
    return out_path


def _write_json(path: str, payload) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _read_json(path: str, fallback):
    if not os.path.exists(path):
        return fallback
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_export_target(parser, tibia_idle_dir: str) -> dict:
    """Everything --export reads up front, so a run either has all of it or
    stops before touching anything. The catalog must already exist — it's
    versioned next to the API, and creating one from nothing here would more
    likely mean a wrong --tibia-idle-dir than a fresh checkout. The hunt
    content dir doesn't: a checkout can legitimately have no loot exported
    yet."""
    catalog_path = content_export.catalog_source_path(tibia_idle_dir)
    if not os.path.exists(catalog_path):
        parser.error(f"catalog-source.json não encontrado em {catalog_path} (use --tibia-idle-dir)")

    catalog = _read_json(catalog_path, None)
    for collection in content_export.CATALOG_COLLECTIONS:
        catalog.setdefault(collection, [])

    hunts_dir = content_export.hunt_content_dir(tibia_idle_dir)
    return {
        "catalog_path": catalog_path,
        "catalog": catalog,
        "hunts_dir": hunts_dir,
        "loot": _read_json(os.path.join(hunts_dir, "loot.json"), []),
    }


def _export_blocker(map_name: str, map_id: str):
    """Why this map must not reach the back-end catalog, or None if it may.

    Both cases are things a `--all` sweep picks up that a single-map run
    never would, because it walks ready-maps/ — generated output — rather
    than the source tree:

    - a scratch folder with no id in its name (`Nova pasta`, `DEBUG-MAP`),
      whose "map id" is really just the folder name;
    - a folder whose **source map was deleted** but whose build output is
      still sitting in ready-maps/ (gitignored, so nothing ever pruned it).
      That's how `ROOK-HUNT-0013` — a map removed in f67a94c — came back as a
      live hunt in the catalog.

    The local fragment is written either way: it's regenerable, and refusing
    to build it would hide the map instead of the problem."""
    if not city_ids.is_conventional_id(map_id):
        return f"id {map_id!r} fora do formato CIDADE-TIPO-NNNN"
    if map_dirs.find_two_level_dir(MAPS_DIR, map_name) is None:
        return (f"não existe mais fonte em extractor/maps/<CIDADE>/{map_name} — "
                f"o que sobrou é saída velha em ready-maps/")
    return None


def stale_build_warning(map_name: str):
    """A message when the map's source is newer than the build we're about to
    publish, or None.

    `ready-maps/` is gitignored, so nothing forces it to keep up with
    `maps/`. Exporting from a stale build doesn't fail — it quietly publishes
    *older* content over newer, and since a legitimate edit (pruning spawns,
    say) also makes the export shrink things, the diff alone can't tell you
    which one you're looking at. Only a warning, not a blocker: mtimes don't
    survive a fresh clone, and refusing to export on a freshly-cloned
    checkout would be worse than the risk."""
    source_dir = map_dirs.find_two_level_dir(MAPS_DIR, map_name)
    built_dir = map_dirs.find_two_level_dir(READY_MAPS_DIR, map_name)
    if source_dir is None or built_dir is None:
        return None
    respawn_path = os.path.join(built_dir, "monsters", "respawn.json")
    if not os.path.exists(respawn_path):
        return None
    built_at = os.path.getmtime(respawn_path)
    newer = [
        name for name in sorted(os.listdir(source_dir))
        if os.path.getmtime(os.path.join(source_dir, name)) > built_at
    ]
    if not newer:
        return None
    return (f"a fonte mudou depois do último build ({', '.join(newer)}) — "
            f"rode `node build_map.js {map_name}` antes de exportar, ou você publica "
            f"conteúdo mais velho por cima do que já está no back-end")


def _write_respawn_file(hunts_dir: str, map_id: str, monsters_entry: dict) -> None:
    respawn_dir = os.path.join(hunts_dir, "respawn")
    os.makedirs(respawn_dir, exist_ok=True)
    _write_json(os.path.join(respawn_dir, f"{map_id}.json"), content_export.respawn_file(monsters_entry))


def _flush_export_target(target: dict) -> None:
    """Writes the three files that accumulate across maps. hunts.json is
    rebuilt from the catalog rather than accumulated, so it's always exactly
    the catalog's hunts projected — see content_export.hunt_manifest."""
    os.makedirs(target["hunts_dir"], exist_ok=True)
    _write_json(target["catalog_path"], target["catalog"])
    _write_json(os.path.join(target["hunts_dir"], "loot.json"), target["loot"])
    _write_json(
        os.path.join(target["hunts_dir"], "hunts.json"),
        content_export.hunt_manifest(target["catalog"]["hunts"]),
    )


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
        "--export",
        action="store_true",
        help="Além do fragmento, escreve no conteúdo do back-end: hunts vai pro "
        "catalog-source.json (só adicionado se o mapId ainda não existir, nunca sobrescreve um "
        "hunt já curado), loot e respawn vão pro content/hunts/ (sempre atualizados)",
    )
    parser.add_argument(
        "--edit",
        action="store_true",
        help="Confirma a intenção de rodar de novo sobre um mapId que já está registrado no "
        "conteúdo do back-end (sem isso, mapId existente é erro). Não sobrescreve hunts já curado "
        "— só destrava loot/respawn (sempre mecânicos, sempre atualizados)",
    )
    parser.add_argument(
        "--tibia-idle-dir",
        default=DEFAULT_TIBIA_IDLE_DIR,
        help=f"Path do checkout do tibia-idle, usado só com --export (default: {DEFAULT_TIBIA_IDLE_DIR})",
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

    target = _load_export_target(parser, args.tibia_idle_dir) if args.export else None

    generated = 0
    exported_skipped = 0
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

            if target is not None and not args.edit and content_export.hunt_id_exists(
                target["catalog"]["hunts"], target["loot"], map_id
            ):
                raise MapIdAlreadyExistsError(map_id)

            fragment = build_fragment(respawn, map_name, map_id)
            out_path = _write_fragment_file(map_name, fragment)
            generated += 1
            print(f"[OK] {map_name}: {len(fragment['loot']['drops'])} loot rows -> {out_path}")

            blocker = _export_blocker(map_name, map_id) if target is not None else None
            if blocker is not None:
                # The fragment above is fine to keep — it's local, and
                # regenerable. The catalog is what must not take this.
                print(f"[SKIP export] {map_name}: {blocker} — fragmento gerado, "
                      f"mas nada escrito no back-end")
                exported_skipped += 1
                continue

            if target is not None:
                stale = stale_build_warning(map_name)
                if stale is not None:
                    print(f"[WARN] {map_name}: {stale}")
                hunts_state = content_export.merge_hunt_into_catalog(
                    target["catalog"]["hunts"], fragment["hunts"]
                )
                loot_state = content_export.upsert_loot_entry(
                    target["loot"], content_export.loot_file_entry(fragment["loot"])
                )
                _write_respawn_file(target["hunts_dir"], map_id, fragment["monsters"])
                note = (" (já existia, hunts NÃO sobrescrito — edite à mão se quiser atualizar)"
                        if hunts_state == "skipped" else "")
                print(f"     catalog hunts {hunts_state}{note}, loot {loot_state}, respawn/{map_id}.json escrito")
            elif fragment["hunts"]["_todo"]:
                print(f"     hunts precisa de revisão manual: {'; '.join(fragment['hunts']['_todo'])}")
    except (MapIdMismatchError, MapIdAlreadyExistsError) as err:
        print(f"[ERRO] {map_name}: {err}")
        sys.exit(1)

    if target is not None:
        _flush_export_target(target)
        exported = generated - exported_skipped
        print(f"\n{exported}/{len(map_names)} mapa(s) exportado(s) para {args.tibia_idle_dir}.")
        if exported_skipped:
            print(f"     {exported_skipped} pulado(s) no export (ver os [SKIP export] acima) — "
                  f"o fragmento local de cada um foi gerado normalmente.")
        print("     Rode `nx run db:reset` no tibia-idle pra o catálogo virar linha no Postgres.")
    else:
        print(f"\n{generated}/{len(map_names)} fragmento(s) gerado(s). Nada foi escrito no back-end — "
              f"use --export, ou copie manualmente.")


if __name__ == "__main__":
    main()
