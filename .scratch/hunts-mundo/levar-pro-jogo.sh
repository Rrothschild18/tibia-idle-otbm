#!/usr/bin/env bash
# POI + arestas de viagem de cada região, e depois hunt-add de cada hunt
# publicada dela. Sequencial de propósito: os dois escrevem no
# catalog-source.json do jogo.
# Uso: levar-pro-jogo.sh <CIDADE> [<CIDADE> ...]
set -uo pipefail
cd /home/rroth/Projects/tibia-idle-otbm
ASSETS=/home/rroth/Projects/tibia-idle/apps/tibia-idle-front/public/assets
for city in "$@"; do
  echo "######## $city — fragmento de viagem"
  uv run python extractor/scripts/build_travel_fragment.py "$city" --export 2>&1 \
    | grep -E "POIs|arestas|rejeit|\[OK\]|\[WARN\]|\[ERROR\]" | head -12
done
echo
for city in "$@"; do
  echo "######## $city — hunt-add"
  for bundle in "$ASSETS/$city"-HUNT-*-sprites-v6; do
    [ -d "$bundle" ] || continue
    folder=$(basename "$bundle")
    out=$(cd /home/rroth/Projects/tibia-idle && bunx nx run hunt-add:add -- --from "$folder" 2>&1)
    if echo "$out" | grep -qE "added|updated"; then
      echo "[OK] $folder  $(echo "$out" | grep -oE "(added|updated)" | head -1)"
    else
      echo "[!!] $folder  $(echo "$out" | grep -iE "error|recusa|não tem|sem " | head -1)"
    fi
  done
done
