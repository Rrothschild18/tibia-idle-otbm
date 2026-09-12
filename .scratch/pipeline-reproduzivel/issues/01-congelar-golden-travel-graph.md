Status: ready-for-agent

# 01 — Congelar o golden do travel-graph antes de qualquer mudança

**What to build:** Um snapshot versionado da saída atual do travel-graph, pra servir de critério de
aceite dos tickets 05 e 06. Roda hoje, nesta máquina, sem biblioteca de sprites e sem dependência Python além da
stdlib:

    node extractor/scripts/dump_otbm.js ROOK
    python extractor/scripts/build_travel_fragment.py ROOK --canary-dir /home/rroth/Projects/canary

Guardar `db-fragment.json` e `travel-graph-rejections.txt` em
`.scratch/pipeline-reproduzivel/golden/` (versionados — são pequenos e existem justamente pra
sobreviver ao refactor). Este ticket **não muda código nenhum**.

**Blocked by:** nada. É o primeiro passo, e nada mais começa antes dele.

- [ ] `golden/db-fragment.json` e `golden/travel-graph-rejections.txt` commitados
- [ ] Um `golden/README.md` de duas linhas registra o comando exato, a data e o commit do Canary
      usado — sem isso o golden não é reproduzível e vira superstição
- [ ] O `map.json` v5 de `full-maps/ROOK/` ainda está no git neste ponto (o 06 é quem o remove) —
      conferir antes, porque ele é a entrada que produziu este golden
