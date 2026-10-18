#!/usr/bin/env bash
# Recorta uma área da Cyclopedia e gera as candidatas de andar inteiro.
# Uso: cluster.sh <ID-DA-CIDADE> "<Nome da área>"
set -euo pipefail
cd /home/rroth/Projects/tibia-idle-otbm
id="$1"; area="$2"
uv run python extractor/scripts/cut_city.py "$id" --area "$area"
node extractor/scripts/dump_otbm.js "$id"
uv run python extractor/scripts/build_appearance_flags.py "$id"
uv run python extractor/scripts/build_city_minimap.py "$id"
uv run python extractor/scripts/build_full_floor_candidates.py "$id"
