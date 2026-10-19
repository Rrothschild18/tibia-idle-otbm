#!/usr/bin/env bash
# Re-aplica a máscara com o fundo limitado a 2 andares nas hunts de superfície,
# que pagavam até 6 silhuetas pela régua do cliente.
set -uo pipefail
cd /home/rroth/Projects/tibia-idle-otbm
for id in "$@"; do
  city="${id%%-*}"
  uv run python extractor/scripts/apply_hunt_mask.py "$id" --backdrop 2 2>&1 | grep -E "^\[OK\] re-corte|fundo \(geom" | sed "s/^/$id /"
  folder=$(basename "$(ls -d extractor/maps/"$city"/"$id"_* 2>/dev/null | head -1)")
  [ -n "$folder" ] && uv run python extractor/scripts/publish.py "$folder" | grep -oE "^\[OK\] ${id}[^:]*"
done
