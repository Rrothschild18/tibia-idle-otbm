"""
One-off maintenance script (not wired into build_map.js/build_items.js — same
"manual, add-if-needed" spirit as the other avulso bakes) that copies item
sprite assets this pipeline already baked into the sibling tibia-idle repo's
front-end assets:

  1. extractor/atlases/items-static/    -> apps/tibia-idle-front/public/assets/items-static/
     (shared grid sheets, PNG+JSON pairs, for items with no animation)
  2. extractor/atlases/items-animated/  -> apps/tibia-idle-front/public/assets/items-animated/
     (shared grid sheets, PNG+JSON pairs, for animated items — see
     .scratch/item-sprite-sheets/issues/03-consolidate-animated-items-into-sheets.md)
  3. extractor/atlases/items-index.json -> apps/tibia-idle-front/public/assets/items-index.json
     (itemId -> sprite location index — see .scratch/item-sprite-sheets/issues/01-item-sprite-index.md)
  4. extractor/atlases/player-outfits/  -> apps/tibia-idle-front/public/assets/player-outfits/
     (one sheet per player outfit, PNG+JSON pairs — see
     .scratch/outfit-de-personagem/issues/02-baker-de-sheet.md). Skipped when
     the directory doesn't exist, so this stays runnable on a checkout that
     hasn't baked the outfits yet.

extractor/atlases/items/ (the old one-atlas-per-animated-item output from
bake_item_atlas.py) is no longer synced — items-index.json never points at
it anymore, so nothing in tibia-idle should be reading it either.

Copies are content-compared, not blindly overwritten: a file is only
rewritten if its bytes differ from the destination, so re-running this with
unchanged source data doesn't touch mtimes or produce noisy diffs.

Run: python sync_items_to_tibia_idle.py [--tibia-idle-dir PATH]
"""

import argparse
import os
import paths
import shutil

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
EXTRACTOR_DIR = os.path.dirname(SCRIPTS_DIR)
ATLASES_DIR = os.path.join(EXTRACTOR_DIR, "atlases")


def _files_differ(src_path: str, dst_path: str) -> bool:
    if not os.path.exists(dst_path):
        return True
    if os.path.getsize(src_path) != os.path.getsize(dst_path):
        return True
    with open(src_path, "rb") as f:
        src_bytes = f.read()
    with open(dst_path, "rb") as f:
        dst_bytes = f.read()
    return src_bytes != dst_bytes


def _sync_file(src_path: str, dst_path: str) -> bool:
    """Copies src to dst if their contents differ. Returns True if a copy happened."""
    if not _files_differ(src_path, dst_path):
        return False
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    shutil.copyfile(src_path, dst_path)
    return True


def _sync_dir(src_dir: str, dst_dir: str) -> tuple[int, int]:
    """Content-compared sync of every file directly in src_dir into dst_dir
    (flat, matches the extractor's atlas output layout — no subdirectories).
    Returns (copied, unchanged) counts."""
    copied = unchanged = 0
    for name in sorted(os.listdir(src_dir)):
        src_path = os.path.join(src_dir, name)
        if not os.path.isfile(src_path):
            continue
        dst_path = os.path.join(dst_dir, name)
        if _sync_file(src_path, dst_path):
            copied += 1
        else:
            unchanged += 1
    return copied, unchanged


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tibia-idle-dir", default=None,
                         help=f"Path to the tibia-idle repo checkout (default: ${paths.TIBIA_IDLE.env_var} or {paths.TIBIA_IDLE.sibling_default()})")
    args = parser.parse_args()

    index_src = os.path.join(ATLASES_DIR, "items-index.json")
    if not os.path.exists(index_src):
        raise SystemExit(
            f"[ERRO] items-index.json não encontrado em {index_src}.\n"
            "Rode 'npm run build-items' neste repo primeiro."
        )

    try:
        tibia_idle_dir = paths.TIBIA_IDLE.require(args.tibia_idle_dir)
    except paths.MissingRepoError as exc:
        raise SystemExit(f"[ERRO] {exc}")

    front_assets_dir = os.path.join(tibia_idle_dir, "apps", "tibia-idle-front", "public", "assets")

    copied, unchanged = _sync_dir(
        os.path.join(ATLASES_DIR, "items-static"), os.path.join(front_assets_dir, "items-static")
    )
    print(f"[OK] items-static/: {copied} copiados, {unchanged} já atualizados")

    copied, unchanged = _sync_dir(
        os.path.join(ATLASES_DIR, "items-animated"), os.path.join(front_assets_dir, "items-animated")
    )
    print(f"[OK] items-animated/: {copied} copiados, {unchanged} já atualizados")

    index_dst = os.path.join(front_assets_dir, "items-index.json")
    if _sync_file(index_src, index_dst):
        print("[OK] items-index.json: copiado")
    else:
        print("[OK] items-index.json: já atualizado")

    outfits_src = os.path.join(ATLASES_DIR, "player-outfits")
    if os.path.isdir(outfits_src):
        copied, unchanged = _sync_dir(
            outfits_src, os.path.join(front_assets_dir, "player-outfits")
        )
        print(f"[OK] player-outfits/: {copied} copiados, {unchanged} já atualizados")
    else:
        print("[--] player-outfits/: nada a copiar (rode bake_player_outfit_sheet.py)")


if __name__ == "__main__":
    main()
