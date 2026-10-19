#!/usr/bin/env bash
# Aplica a máscara e publica, hunt por hunt. Pula as descartadas (todo andar
# excluído: o re-corte morreria em "máscara vazia") e Rookgaard (máscara em
# coordenada local antiga, cortaria 0 tiles).
# Uso: aplicar-e-publicar.sh <CIDADE> [<CIDADE> ...]
set -uo pipefail
cd /home/rroth/Projects/tibia-idle-otbm
for city in "$@"; do
  echo "######## $city"
  for mask in extractor/hunt-masks/"$city"-HUNT-*.json; do
    [ -f "$mask" ] || continue
    id=$(basename "$mask" .json)
    aplicavel=$(python3 -I -c "
import json
d=json.load(open('$mask', encoding='utf-8'))
excl={int(z) for z in (d.get('excludedFloors') or [])}
print('1' if [z for z,c in d['floors'].items() if c and int(z) not in excl] else '0')")
    if [ "$aplicavel" != "1" ]; then echo "[--] $id: descartada (todo andar excluído)"; continue; fi
    if ! uv run python extractor/scripts/apply_hunt_mask.py "$id" > /tmp/mask-$id.log 2>&1; then
      echo "[!!] $id: apply_hunt_mask falhou — $(tail -1 /tmp/mask-$id.log)"; continue
    fi
    grep -E "^\[OK\] re-corte|fundo \(geometria" /tmp/mask-$id.log | sed "s/^/     /"
    folder=$(basename "$(ls -d extractor/maps/"$city"/"$id"_* 2>/dev/null | head -1)")
    [ -n "$folder" ] || { echo "[!!] $id: pasta de recorte não achada"; continue; }
    uv run python extractor/scripts/publish.py "$folder" | grep -oE "^\[OK\] ${id}[^:]*" || echo "[!!] $id: publish falhou"
    rm -f /tmp/mask-$id.log
  done
done
