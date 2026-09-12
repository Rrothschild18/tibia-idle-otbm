# Golden do bundle v6 — congelado antes de deletar o v5

Critério de aceite do ticket 07: depois de remover a árvore v5 e renomear
`ready-maps-v6/` → `ready-maps/`, o bundle do hunt tem que sair igual.

Mapa: `ROOK-HUNT-0001_rats-sewers-2-rookguard` — 5196 tiles, 261 aparências, 2 folhas.

```bash
node extractor/scripts/build_map.js ROOK-HUNT-0001_rats-sewers-2-rookguard
diff extractor/ready-maps/ROOK/ROOK-HUNT-0001_rats-sewers-2-rookguard/map.json \
     .scratch/pipeline-reproduzivel/golden/v6-bundle/map.json
```

| | |
|---|---|
| Data | 2026-09-12 |
| Cliente | 15.25.0a00a0 |
| Biblioteca de sprites | 204.003 PNGs extraídos do cliente |

## Nota sobre o `respawn.json`

O `respawn-v6.json` foi **recongelado** depois do `bake_outfit_atlas.py` rodar. A primeira versão
tinha `"atlas": null` no monsterDef porque o atlas do outfit 21 ainda não existia; com o bake feito,
o campo passou a apontar `assets/outfits/21.{png,json}`. Foi a única diferença entre as duas
execuções, e ela vem do bake, não da remoção do v5 — o `map.json` saiu idêntico nas duas.
