# 01 — Processar o rook-full.otbm inteiro no pipeline existente, filtrando as placas marcadoras

**What to build:** Rodar o pipeline OTBM→`map.json` já existente (`dump_otbm.js` + `build_phaser_map.py`) contra o mapa completo de Rookgaard (`extractor/full-maps/rook-full/rook-full.otbm`), produzindo um `map.json` versionado com todos os floors da cidade. As placas marcadoras (item 2016, uid na faixa reservada 10001+) usadas pra marcar POIs devem ser filtradas dessa saída — esse `map.json` é um artefato intermediário/de inspeção, nunca o mapa que o client renderiza (os mapas de hunt continuam sendo os recortes pequenos já existentes, sem conexão com este).

**Blocked by:** None — can start immediately.

- [ ] O pipeline roda de ponta a ponta contra `rook-full.otbm` sem erros, produzindo um `map.json` com todos os floors exportados
- [ ] O `map.json` resultante é versionado no Git
- [ ] Itens com uid na faixa 10001+ (as placas marcadoras) não aparecem no `map.json` gerado
- [ ] O restante do conteúdo do mapa (tiles, `objectDefs`, `unpass`/`isFloorTransition`) segue o mesmo formato já documentado na ADR 0002, sem mudança de schema
- [ ] Regressão: os mapas de hunt pequenos já existentes continuam sendo gerados/servidos normalmente, sem qualquer alteração de comportamento
