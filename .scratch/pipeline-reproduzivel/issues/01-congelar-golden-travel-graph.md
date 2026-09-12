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

- [x] `golden/db-fragment.json` e `golden/travel-graph-rejections.txt` commitados
- [x] Um `golden/README.md` de duas linhas registra o comando exato, a data e o commit do Canary
      usado — sem isso o golden não é reproduzível e vira superstição
- [x] O `map.json` v5 de `full-maps/ROOK/` ainda está no git neste ponto (o 06 é quem o remove) —
      conferir antes, porque ele é a entrada que produziu este golden

## Comments

Congelado em `.scratch/pipeline-reproduzivel/golden/`.

```
node extractor/scripts/dump_otbm.js ROOK
python3 extractor/scripts/build_travel_fragment.py ROOK --canary-dir /home/rroth/Projects/canary
```

Saída: 997 ids com floorchange lidos do `items.xml`, 36 locations, 630 arestas de travelGraph,
nenhum nó sem entrada.

```
5823a0ff450e2986f4493f724b5d71d64b5465984d4696b20cb4b98642637509  db-fragment.json
c1c429ce227205fa0141eae58ae2db2661119abc7263d013cad4909e0293f75f  travel-graph-rejections.txt
```

Três coisas verificadas antes de congelar, porque um golden que não é reproduzível é pior que
nenhum golden:

1. **Determinismo** — duas execuções seguidas produziram saída idêntica. Sem isso o critério
   "byte a byte" dos tickets 05 e 06 seria impossível de cumprir.
2. **Procedência gravada** no `golden/README.md`: commit do Canary
   (`06c73ccb993b4625a966d452b7e9f867873d1f55`, v3.6.0-93), data, versões de Python/Node e o
   commit do extractor.
3. **A entrada v5 ainda está no git** — `extractor/full-maps/ROOK/map.json` (20,3 MB) e
   `metadata.json` continuam versionados; é o 06 que os remove. Confirmado com `git ls-files`.

Nenhum código foi alterado neste ticket.
