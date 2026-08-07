# 07 — Re-exportar todos os mapas no formato novo

**What to build:** Os 20 mapas existentes regerados no formato novo, conferidos contra os atuais, e
prontos para o repositório do jogo consumir.

Este é o ticket que fecha o lado do pipeline: a partir dele, todo o trabalho restante é no Phaser.

**Blocked by:** 04, 05, 06

**Status:** resolved

- [x] Os 20 mapas existem no formato novo
- [x] Para cada mapa: a contagem de itens por tile bate com a do formato atual, e nenhuma tile
      perdeu ou ganhou conteúdo
- [x] Nenhum mapa produz folha de sprite acima do limite seguro de textura
- [x] Está registrado, por mapa, o antes e depois de: número de folhas, número de objetos no
      arquivo, e tamanho do arquivo
- [x] O diretório consumido hoje pelo jogo continua intacto

## Answer

Os 20 mapas de hunt regerados com `node extractor/scripts/build_map.js --all`. Antes/depois por mapa
em [`reports/07-reexportacao-v6.md`](../reports/07-reexportacao-v6.md), gerado por
`extractor/scripts/map_v6_migration_report.py`:

- **0 tiles divergentes** em 20 mapas — nenhuma tile perdeu ou ganhou conteúdo. A conferência
  compara o **conjunto de aparências** por tile, não a contagem, então uma aparência trocada por
  outra não passaria. O que muda de propósito não conta: a ordem dentro da pilha, e o slot em que
  uma aparência cai (uma com `bank` que o v5 empurrava pra um objectgroup vira o chão da tile).
- **0 folhas acima do limite seguro de textura** (2048px).
- **Folhas: 172 → 40** (4-12 por mapa → 2).
- **Tamanho: 9461 KB → 6153 KB.**

`extractor/ready-maps/` continua intocado — o v6 mora em `ready-maps-v6/`, raiz separada, com
`assetsRoot` próprio. Cada pasta v6 leva também `monsters/respawn.json` (cópia do v5), pra ser
autossuficiente pro jogo consumir.

O mapa da cidade inteira ficou de fora, por decisão: não é renderizado, alimenta o travel-graph pelo
`objectDefs` do v5, e empacotar as ~2000 aparências de uma cidade pediria textura de 512×7936.
