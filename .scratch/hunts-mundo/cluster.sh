#!/usr/bin/env bash
# Recorta uma área da Cyclopedia e gera as candidatas de andar inteiro.
# Uso: cluster.sh <ID-DA-CIDADE> "<Nome da área>"
set -euo pipefail
cd /home/rroth/Projects/tibia-idle-otbm
id="$1"; area="$2"
# Generoso desde o primeiro corte: `--spawns-box` porque a máscara da Cyclopedia
# come metade dos bichos (masmorra embaixo de serra não tem superfície mapeada
# em cima), e margem 171 porque hunt de borda fica truncada e o "Adicionar" do
# editor não tem o que mostrar além do recorte.
uv run python extractor/scripts/cut_city.py "$id" --area "$area" --spawns-box --margin 171
node extractor/scripts/dump_otbm.js "$id"
uv run python extractor/scripts/build_appearance_flags.py "$id"
uv run python extractor/scripts/build_city_minimap.py "$id"
uv run python extractor/scripts/build_full_floor_candidates.py "$id"
