#!/usr/bin/env bash
# Re-corta generoso (3 andares + todo spawn da caixa) as hunts que ainda não
# têm máscara salva. Quem já foi curado no editor fica como está.
# Uso: regerar.sh <CIDADE> [<CIDADE> ...]
set -uo pipefail
cd /home/rroth/Projects/tibia-idle-otbm
for city in "$@"; do
  ids=$(uv run python .scratch/hunts-mundo/generoso.py "$city" --write)
  if [ -z "$ids" ]; then echo "=== $city: nada a re-cortar (tudo com máscara ou já generoso)"; continue; fi
  echo "=== $city: $ids"
  only=()
  for id in $ids; do only+=(--only "$id"); done
  uv run python extractor/scripts/build_curated_hunts.py "$city" \
    --candidates candidates-full.json --all-spawns --margin 24 "${only[@]}" || continue
  for id in $ids; do
    folder=$(basename "$(ls -d extractor/maps/"$city"/"$id"_* | head -1)")
    node extractor/scripts/build_map.js "$folder" > /dev/null || continue
    uv run python extractor/scripts/publish.py "$folder" | grep -E "^\[OK\] $id" || true
  done
done
