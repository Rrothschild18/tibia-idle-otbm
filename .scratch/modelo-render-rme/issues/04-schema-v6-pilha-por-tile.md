# 04 — Schema de mapa v6: pilha por tile

**What to build:** O pipeline passa a emitir um formato de mapa novo, em diretório separado do
atual, cuja unidade é a **tile com sua pilha ordenada** — não mais sete grupos de objetos separados
por papel de renderização.

O formato novo não carrega papel de renderização, nem constante de profundidade, nem camada de
telhado. Quem lê o arquivo consegue reconstruir a ordem de desenho apenas percorrendo tiles por
linha e itens por posição na pilha.

O diretório de saída atual permanece intacto e continua sendo o que o jogo consome — a troca é o
último ticket do esforço.

**Blocked by:** 03

**Status:** resolved

- [x] O formato novo sai em diretório próprio, sem tocar o diretório consumido hoje pelo jogo
- [x] Cada tile carrega seu ground e sua pilha ordenada
- [x] Nenhum campo de papel de renderização ou de constante de profundidade sobrevive no arquivo
- [x] A camada de telhado não existe no formato novo; as aparências que a compunham aparecem como
      ground das suas tiles
- [x] Para cada mapa, a contagem total de itens por tile no formato novo bate com a do formato atual
- [x] O formato novo está documentado, incluindo como derivar a ordem de desenho a partir dele

## Answer

`extractor/scripts/map_v6.py` (puro) monta o documento; `build_phaser_map.py` o grava em
`extractor/ready-maps-v6/<CIDADE>/<pasta>/`, raiz separada — `ready-maps/` fica byte a byte intacto.
`assetsRoot` também é distinto (`assets/<mapa>-sprites-v6`), pros dois formatos poderem coexistir no
front durante a migração.

Formato documentado em [`extractor/MAP_JSON_V6.md`](../../../extractor/MAP_JSON_V6.md), incluindo o
pseudocódigo de como derivar a ordem de desenho (varredura andar → linha → pilha) e como acumular
`elevation`. Decisão em [ADR 0006](../../../docs/adr/0006-map-json-v6-pilha-por-tile.md).

Um teste afirma diretamente que nenhum dos termos `layerClass`, `depthOffset`, `roof`, `Roof`,
`objectgroup` ou `tilelayer` sobrevive na serialização do documento.

**Conteúdo por tile:** `extractor/scripts/map_v6_migration_report.py` compara o conjunto de
aparências de cada tile entre os dois formatos. Nos 20 mapas: **0 tiles divergentes, 0 tiles só num
dos formatos** — relatório em [`reports/07-reexportacao-v6.md`](../reports/07-reexportacao-v6.md).

**Escopo:** só mapas de hunt. O `map.json` da cidade inteira não ganha v6 — nunca é renderizado
(existe pro `build_travel_fragment.py` ler o `objectDefs`) e as ~2000 aparências de uma cidade
pediriam textura de 512×7936.
