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
import shutil

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
EXTRACTOR_DIR = os.path.dirname(SCRIPTS_DIR)
ATLASES_DIR = os.path.join(EXTRACTOR_DIR, "atlases")
# Sibling repo checkout: <workspace>/tibia-idle-otbm and <workspace>/tibia-idle/tibia-idle.
DEFAULT_TIBIA_IDLE_DIR = os.path.abspath(
    os.path.join(EXTRACTOR_DIR, "..", "..", "tibia-idle", "tibia-idle")
)


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
    parser.add_argument("--tibia-idle-dir", default=DEFAULT_TIBIA_IDLE_DIR,
                         help=f"Path to the tibia-idle repo checkout (default: {DEFAULT_TIBIA_IDLE_DIR})")
    args = parser.parse_args()

    index_src = os.path.join(ATLASES_DIR, "items-index.json")
    if not os.path.exists(index_src):
        raise SystemExit(
            f"[ERRO] items-index.json não encontrado em {index_src}.\n"
            "Rode 'npm run build-items' neste repo primeiro."
        )

    front_assets_dir = os.path.join(args.tibia_idle_dir, "apps", "tibia-idle-front", "public", "assets")
    if not os.path.isdir(args.tibia_idle_dir):
        raise SystemExit(f"[ERRO] tibia-idle não encontrado em {args.tibia_idle_dir} (use --tibia-idle-dir)")

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


if __name__ == "__main__":
    main()
