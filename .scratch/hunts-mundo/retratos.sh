#!/usr/bin/env bash
# Recalcula o retrato de toda hunt publicada pela regra nova (nome da hunt
# manda, mais frequente como fallback). `--refresh-preview` porque o retrato
# registrado antes da regra é o automático, e preservá-lo congelaria o erro.
set -uo pipefail
ASSETS=/home/rroth/Projects/tibia-idle/apps/tibia-idle-front/public/assets
cd /home/rroth/Projects/tibia-idle
for bundle in "$ASSETS"/*-sprites-v6; do
  folder=$(basename "$bundle")
  case "$folder" in *_window-sprites-v6) continue;; esac
  [ -f "$bundle/db-fragment.json" ] || continue
  out=$(bunx nx run hunt-add:add -- --from "$folder" --refresh-preview 2>&1)
  echo "$out" | grep -qE 'acrescentada|atualizada' || echo "[!!] ${folder%%_*}: $(echo "$out" | grep -iE 'erro|error' | head -1 | cut -c1-120)"
done
echo "=== retratos por espécie:"
python3 -I -c "
import json, collections
d=json.load(open('apps/tibia-idle-api/content/catalog-source.json'))
c=collections.Counter((h.get('monsterPreview') or {}).get('name','SEM') for h in d['hunts'])
print(len(d['hunts']), 'hunts |', len(c), 'espécies distintas no retrato')
for n,k in c.most_common(12): print(f'   {n:<22} {k}')
"
