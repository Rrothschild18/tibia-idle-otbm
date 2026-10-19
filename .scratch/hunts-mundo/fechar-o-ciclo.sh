#!/usr/bin/env bash
# Fecha o ciclo das 10 regiões: fork vira POI, fragmento de viagem de novo,
# hunt-add em tudo e provision no banco.
#
# Espera o `levar-pro-jogo.sh` acabar — os dois escrevem no catalog-source.json.
# O pgrep aqui não corre o risco de achar a si mesmo porque este script é um
# arquivo: a linha de processo dele é o nome do arquivo, não o padrão.
set -uo pipefail
cd /home/rroth/Projects/tibia-idle-otbm
REGIOES="ZAO YALAHAR DARASHIA ANKRAHMUN LIBERTYBAY SVARGROND PORTHOPE EDRON ABDENDRIEL GRAYBEACH"
ASSETS=/home/rroth/Projects/tibia-idle/apps/tibia-idle-front/public/assets

# Sem espera por pgrep aqui. A tentativa anterior travou pra sempre porque o
# `bash -c` que CRIOU este arquivo (heredoc) carrega o texto do script na
# própria linha de processo — inclusive o padrão — então o pgrep achava o avô.
# Encadeamento agora é responsabilidade de quem chama.

echo; echo "######## 1/4 forks como POI"
for city in $REGIOES; do uv run python .scratch/hunts-mundo/forks-como-poi.py "$city" --write | tail -1; done

echo; echo "######## 2/4 fragmento de viagem com os forks dentro"
for city in $REGIOES; do
  uv run python extractor/scripts/build_travel_fragment.py "$city" --export 2>&1 \
    | grep -E "POIs de hunt curados|POIs mecânicos|arestas|rejeit" | sed "s/^/$city /"
done

echo; echo "######## 3/4 hunt-add"
ok=0; falha=0
for city in $REGIOES; do
  for bundle in "$ASSETS/$city"-HUNT-*-sprites-v6; do
    [ -d "$bundle" ] || continue
    folder=$(basename "$bundle")
    case "$folder" in *_window-sprites-v6) continue;; esac
    out=$(cd /home/rroth/Projects/tibia-idle && bunx nx run hunt-add:add -- --from "$folder" 2>&1)
    # A saída do hunt-add é em português: "✔ <ID> acrescentada|atualizada como".
    if echo "$out" | grep -qE 'acrescentada|atualizada'; then
      ok=$((ok+1))
    else
      falha=$((falha+1))
      echo "[!!] $folder: $(echo "$out" | grep -iE 'error|HuntAddError|não tem|sem ' | head -1 | cut -c1-160)"
    fi
  done
done
echo "hunt-add: $ok ok, $falha recusadas"

echo; echo "######## 4/4 db:provision (sem reset: preserva personagem)"
cd /home/rroth/Projects/tibia-idle && bunx nx run db:provision 2>&1 | tail -25
