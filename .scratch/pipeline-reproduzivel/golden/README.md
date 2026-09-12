# Golden do travel-graph — congelado antes do refactor

Critério de aceite dos tickets 05 e 06: depois de trocar a fonte das flags
(`full-maps/<CIDADE>/map.json` → `appearance-flags/<CIDADE>.json`) e de deletar o
caminho v5, o fragmento do ROOK tem que sair **byte a byte igual** a estes arquivos.

## Como foi gerado

```bash
node extractor/scripts/dump_otbm.js ROOK
python3 extractor/scripts/build_travel_fragment.py ROOK --canary-dir /home/rroth/Projects/canary
```

Saída copiada de `extractor/full-maps/ROOK/`.

| | |
|---|---|
| Data | 2026-09-12 |
| Canary | `06c73ccb993b4625a966d452b7e9f867873d1f55` (v3.6.0-93-g06c73ccb9, 2026-09-10) |
| Canary origin | https://github.com/opentibiabr/canary.git |
| Extractor | `f87991d` |
| Python | 3.14.7 |
| Node | v26.8.1 |
| Entrada v5 | `extractor/full-maps/ROOK/map.json` (20,3 MB, ainda no git neste ponto) |

Resultado registrado na geração: 997 ids com floorchange lidos do `items.xml`,
36 locations, 630 arestas de travelGraph, nenhum nó sem entrada.

## Checksums

```
5823a0ff450e2986f4493f724b5d71d64b5465984d4696b20cb4b98642637509  db-fragment.json
c1c429ce227205fa0141eae58ae2db2661119abc7263d013cad4909e0293f75f  travel-graph-rejections.txt
```

Determinismo verificado: duas execuções seguidas produziram saída idêntica.

## Conferir

```bash
node extractor/scripts/dump_otbm.js ROOK
python3 extractor/scripts/build_travel_fragment.py ROOK
diff .scratch/pipeline-reproduzivel/golden/db-fragment.json \
     extractor/full-maps/ROOK/db-fragment.json
diff .scratch/pipeline-reproduzivel/golden/travel-graph-rejections.txt \
     extractor/full-maps/ROOK/travel-graph-rejections.txt
```
