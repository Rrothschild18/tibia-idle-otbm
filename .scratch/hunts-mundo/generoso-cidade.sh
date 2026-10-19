#!/usr/bin/env bash
# Re-corta uma região com a caixa generosa (+171) e o monstro pela caixa,
# reaponta a curadoria e republica as hunts que ainda não têm máscara.
# Uso: generoso-cidade.sh <CIDADE>
set -uo pipefail
cd /home/rroth/Projects/tibia-idle-otbm
city="$1"
area=$(python3 -I -c "import json;print(json.load(open('extractor/full-maps/$city/source.json'))['area']['name'])")
echo "######## $city — área '$area'"
uv run python .scratch/hunts-mundo/remapear.py "$city" --snapshot || exit 1
uv run python extractor/scripts/cut_city.py "$city" --area "$area" --spawns-box --margin 171 --force || exit 1
node extractor/scripts/dump_otbm.js "$city" || exit 1
uv run python extractor/scripts/build_appearance_flags.py "$city" || exit 1
uv run python extractor/scripts/build_city_minimap.py "$city" > /dev/null || exit 1
uv run python extractor/scripts/build_full_floor_candidates.py "$city" || exit 1
# Sem `tee /dev/stderr` aqui: com stdout e stderr no mesmo arquivo de log, os
# dois offsets brigam e o começo do log vira bytes nulos. O reapontamento vai
# pro arquivo e o resumo sai dele depois.
remap=".scratch/hunts-mundo/${city,,}-remap.log"
uv run python .scratch/hunts-mundo/remapear.py "$city" --apply > "$remap" 2>&1 || exit 1
grep -c '<= mudou' "$remap" | sed "s/^/[OK] $city: /;s/$/ candidata(s) reapontada(s)/"
ids=$(grep '^RECORTAR:' "$remap" | sed 's/^RECORTAR://')
if [ -z "${ids// /}" ]; then echo "[..] $city: nada a re-cortar (tudo com máscara)"; exit 0; fi
only=(); for id in $ids; do only+=(--only "$id"); done
uv run python extractor/scripts/build_curated_hunts.py "$city" \
  --candidates candidates-full.json --all-spawns --margin 24 "${only[@]}" || exit 1
for id in $ids; do
  folder=$(basename "$(ls -d extractor/maps/"$city"/"$id"_* 2>/dev/null | head -1)")
  [ -n "$folder" ] || continue
  node extractor/scripts/build_map.js "$folder" > /dev/null || continue
  uv run python extractor/scripts/publish.py "$folder" | grep -oE "^\[OK\] ${id}[^:]*"
done
