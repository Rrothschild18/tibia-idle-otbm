"""
CLI: extract every monster's loot table from a local Canary install into
extractor/monster-loot.json — the checked-in reference file build_phaser_map.py
reads from, so the real pipeline never needs to touch the Canary install again.

Run: python build_monster_loot_index.py [--canary-dir PATH]
     (default PATH: C:\\canary-3.2.1)
"""

import argparse
import json
import os
import paths
import sys

from monster_loot import build_monster_loot_index

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
EXTRACTOR_DIR = os.path.dirname(SCRIPTS_DIR)
OUTPUT_PATH = os.path.join(EXTRACTOR_DIR, "monster-loot.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canary-dir", default=None,
                         help=f"Path to a local Canary server install (default: ${paths.CANARY.env_var} or {paths.CANARY.sibling_default()})")
    args = parser.parse_args()

    try:
        canary_dir = paths.CANARY.require(args.canary_dir)
    except paths.MissingRepoError as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)

    index = build_monster_loot_index(canary_dir)

    with_loot = sum(1 for entry in index.values() if entry["loot"])
    total_issues = sum(len(entry["issues"]) for entry in index.values())

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False, sort_keys=True)
        f.write("\n")

    print(f"[OK] {len(index)} monsters ({with_loot} with loot) -> {OUTPUT_PATH}")
    if total_issues:
        print(f"[WARN] {total_issues} unresolved/invalid loot rows across all monsters — see \"issues\" per monster in the output file")


if __name__ == "__main__":
    main()
