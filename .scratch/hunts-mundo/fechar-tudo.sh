#!/usr/bin/env bash
# Espera os retratos, provisiona o banco e roda o routine-sim sozinho.
set -uo pipefail
while pgrep -f "hunt-add:add" > /dev/null; do sleep 15; done
echo "=== retratos terminaram"
tail -16 /home/rroth/Projects/tibia-idle-otbm/.scratch/hunts-mundo/retratos.log
cd /home/rroth/Projects/tibia-idle
echo; echo "=== db:provision"
bunx nx run db:provision 2>&1 | tail -6
echo; echo "=== routine-sim sozinho"
bunx nx run routine-sim:test 2>&1 | sed 's/\x1b\[[0-9;]*m//g' | grep -E "Tests |FAIL |timed out" | head -5
