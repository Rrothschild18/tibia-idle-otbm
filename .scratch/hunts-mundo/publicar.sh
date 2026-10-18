#!/usr/bin/env bash
# Da curadoria ao bundle que o editor lista: recorta, assa e publica.
# Uso: publicar.sh <CIDADE>
set -euo pipefail
cd /home/rroth/Projects/tibia-idle-otbm
city="$1"
uv run python extractor/scripts/build_curated_hunts.py "$city" --candidates candidates-full.json
# As pastas de recorte nascem em maps/; ready-maps/ é saída do build_map.js.
for dir in extractor/maps/"$city"/*/; do
  folder="$(basename "$dir")"
  case "$folder" in *_window) continue;; esac
  node extractor/scripts/build_map.js "$folder"
  uv run python extractor/scripts/publish.py "$folder"
done
