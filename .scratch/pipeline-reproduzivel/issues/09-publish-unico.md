Status: ready-for-agent

# 09 — `publish`: o único comando que escreve no `tibia-idle`

**What to build:** Hoje **nenhum script** leva um bundle pro repo irmão — a cópia é manual. A prova:
os bundles publicados têm `map.json` + `sheets/`, mas não o `monsters/respawn.json` que
`write_map_v6` também escreve (`build_phaser_map.py:1395-1398`) — cópia seletiva de humano, não sync.
`content_export.py` não faz I/O nenhum (só monta a string do `mapUrl`), e `--export` escreve quatro
JSONs e nenhum binário. O `README.md:337` nem lista o bundle na tabela de destinos.

E a cobertura de atlas está invertida: `sync_items_to_tibia_idle.py` cobre `items-static/`,
`items-animated/`, `items-index.json` e `player-outfits/`; **não cobre** `outfits/`, `effects/`,
`corpses/`, `pools/`. Mas no front existem `effects/`, `corpses/` e `pools/` (foram na mão) e
**não** existem `items-animated/`, `player-outfits/` e `outfits/` — enquanto `respawn.json` aponta
os monstros justamente pra `assets/outfits/...`.

Um `publish` só, cobrindo bundle + todos os atlases + os quatro JSONs do catálogo. Ele passa a ser o
**único ponto de escrita** no repo irmão — invariante mais forte que a de hoje, não mais fraca: o
`CONTEXT.md:24-31` separa fragmento (local, gitignorado, pra revisão) de export (explícito, escreve
no irmão), e essa separação continua intacta.

**Blocked by:** 03 (paths), 07 (uma árvore só pra publicar).

- [ ] `publish` copia o bundle do mapa (`map.json` + `sheets/`) pro
      `apps/tibia-idle-front/public/assets/<MAP>-sprites-v<N>/`
- [ ] Copia os oito destinos de atlas, incluindo `outfits/`, `effects/`, `corpses/`, `pools/`
- [ ] Escreve os quatro JSONs de catálogo/conteúdo que o `--export` já escrevia
- [ ] **Falha alto** quando um atlas referenciado não foi bakeado, listando o que falta e o comando
      que gera — o caso do `assets/outfits/` de hoje deve virar erro, não silêncio
- [ ] `--prune` remove do destino o que o catálogo não referencia, **listando antes**; sem a flag,
      nunca remove
- [ ] Cópia comparada por conteúdo (não sobrescreve bytes iguais), como `sync_items` já faz
- [ ] `sync_items_to_tibia_idle.py` deixa de existir como comando separado
