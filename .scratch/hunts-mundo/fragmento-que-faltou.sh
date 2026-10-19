#!/usr/bin/env bash
# As hunts publicadas sem `db-fragment.json`: o `publish.py` não o regera e o
# `build_curated_hunts.py` não o produz, então hunt publicada só por esse
# caminho é recusada pelo `hunt-add`. Aqui o fragmento é gerado, publicado e
# registrado.
set -uo pipefail
cd /home/rroth/Projects/tibia-idle-otbm
ASSETS=/home/rroth/Projects/tibia-idle/apps/tibia-idle-front/public/assets
for city in "$@"; do
  for bundle in "$ASSETS/$city"-HUNT-*-sprites-v6; do
    [ -d "$bundle" ] || continue
    [ -f "$bundle/db-fragment.json" ] && continue
    folder=$(basename "$bundle"); folder=${folder%-sprites-v6}
    id=${folder%%_*}
    uv run python extractor/scripts/build_hunt_fragment.py "$folder" --map-id "$id" > /dev/null 2>&1 \
      || { echo "[!!] $id: build_hunt_fragment falhou"; continue; }
    uv run python extractor/scripts/publish.py "$folder" > /dev/null 2>&1 \
      || { echo "[!!] $id: publish falhou"; continue; }
    out=$(cd /home/rroth/Projects/tibia-idle && bunx nx run hunt-add:add -- --from "${folder}-sprites-v6" 2>&1)
    if echo "$out" | grep -qE 'acrescentada|atualizada'; then
      echo "[OK] $id $(echo "$out" | grep -oE 'acrescentada|atualizada' | head -1)"
    else
      echo "[!!] $id: $(echo "$out" | grep -iE 'erro|error' | head -1 | cut -c1-140)"
    fi
  done
done
