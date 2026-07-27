# 04 — Remover o sistema de bake, usar só sheets

**What to build:** Remover completamente o sistema de bake de cenário estático (ADR 0001,
`.scratch/static-scenery-baking/`): `_is_bakeable`, `_render_baked_row`, o layer `bakedgroup`,
`BAKED_OUTPUT_DIR`, `--dump-baked-preview`/`_print_baked_preview`, e `INTERACTIVE_IDS` em
`item_classifier.py`. Todo item que hoje seria bakeável passa a seguir o caminho dinâmico normal
(objectgroup + `objectDefs[id].sheet`/`.gids`), do mesmo jeito que qualquer outro item não-bakeável
já segue hoje. O Phaser continua montando o mapa tile a tile (um `GameObject` por placement,
comportamento de runtime inalterado) — a única coisa que muda é que a sprite de cada placement
vem de um sheet compartilhado em vez de um arquivo individual.

**Motivo:** medido nos 8 mapas reais, o bake gera de 41 a 262 PNGs por mapa (uma imagem por
`(tileY, layerClass)` com conteúdo) — mais requests de rede do que os ~3-8 sheets que o v4 já
produz pro mesmo conteúdo. O bake nunca resolveu o problema de rede (resolvia custo de
instanciação em runtime); agora que sheets cobrem o carregamento de forma muito mais barata, manter
os dois sistemas em paralelo não se justifica. Ver `docs/adr/0004-remover-bake-usar-so-sheets.md`.

**Blocked by:** 02

**Status:** ready-for-agent

- [x] `build_phaser_map.py`: remover `_is_bakeable`, `_render_baked_row`, `BAKED_OUTPUT_DIR`,
      `DUMP_BAKED_PREVIEW`, `_print_baked_preview`, a flag de CLI `--dump-baked-preview`.
- [x] `build_phaser_map()`: remover `floor_baked`, `baked_appearance_ids`, `baked_only_ids`, o
      branch `if _is_bakeable(...): ... continue` na segunda passada (todo item vira dinâmico
      incondicionalmente), a construção do layer `BakedObjects`/`bakedgroup` por floor, e o guard
      `if appearance_id not in baked_only_ids` no loop de `tilesets` (`ensure_sprite_assets` roda
      incondicionalmente de novo, como antes do bake existir).
- [x] `_build_object_defs()`: assinatura simplificada pra `_build_object_defs(dynamic_ids)` (sem
      `baked_ids`); remove o branch `bakedOnly`. Toda aparência ou está em `dynamic_ids` (ganha
      `sheet`+`gids`) ou não está (ground-only, sem referência de sprite) — sem terceiro caso.
- [x] `item_classifier.py`: remover `INTERACTIVE_IDS` (só era usado por `_is_bakeable`).
- [x] Remover `extractor/tests/test_is_bakeable.py` e `extractor/tests/test_render_baked_row.py`
      (testam funções que deixam de existir); remover `extractor/tests/test_build_phaser_map_baking.py`
      (testava especificamente o split bake/dinâmico, que não existe mais — a cobertura de "item
      dinâmico ganha sheet+gids" já existe em `test_build_phaser_map_sheets.py`).
- [x] `docs/adr/0001-bake-unit-is-row-plus-layerclass.md`: marcar como superseded por
      `docs/adr/0004-...` no topo do arquivo (não apagar — histórico).
- [x] Nova `docs/adr/0004-remover-bake-usar-so-sheets.md` documentando a decisão, com os números
      reais (41-262 PNGs de bake por mapa) como evidência.
- [x] `.scratch/static-scenery-baking/spec.md`: adicionar `Status: superseded por
      map-sprite-sheets-v4/04` no topo.
- [x] `extractor/CONVERTER_DOCS.md`: remover a seção "Bakedgroup layer", substituir por nota curta
      de que baking foi removido e todo `objectDefs` dinâmico usa `sheet`+`gids` uniformemente.
- [x] `node build_map.js --all` rodado nos 8 mapas reais: confirmar que nenhum `map.json` tem mais
      layer `bakedgroup`, que nenhum diretório `baked/` é gerado, e que os itens antes bakeados
      agora aparecem com `sheet`+`gids` em `objectDefs` (contagem de entradas dinâmicas deve subir
      pelo tanto que antes era `bakedOnly`).

## Comments

**2026-07-27** — Removido inteiramente. `build_phaser_map.py`: `_is_bakeable`, `_render_baked_row`,
`_baked_entry_sprite`, `BAKED_OUTPUT_DIR`, `--dump-baked-preview`/`_print_baked_preview` removidos;
`floor_baked`/`baked_appearance_ids`/`baked_only_ids` removidos da segunda passada — todo item
placed via objectgroup vira dinâmico incondicionalmente; `_build_object_defs()` simplificada pra
`_build_object_defs(dynamic_ids)`, sem branch `bakedOnly`. `item_classifier.INTERACTIVE_IDS`
removido (só existia pra `_is_bakeable`). 3 arquivos de teste removidos
(`test_is_bakeable.py`, `test_render_baked_row.py`, `test_build_phaser_map_baking.py`) — suite foi
de 38 pra 26 testes, todos passando.

`docs/adr/0001-...md` marcada superseded no topo (corpo mantido por histórico). Nova
`docs/adr/0004-remover-bake-usar-so-sheets.md` com a tabela real de PNGs de bake por mapa (41-262).
`.scratch/static-scenery-baking/spec.md` marcada `Status: superseded`. `CONVERTER_DOCS.md` e
`PHASER_INTEGRATION.md` atualizados (seção "Bakedgroup layer" virou "— removed"; checklist de
migração ganhou um item pra remover código de `bakedgroup`/`bakedOnly` de loaders existentes).

Rodado `node build_map.js --all` nos 8 mapas reais após `rm -rf ready-maps/*/baked`: nenhum
`map.json` tem mais `bakedgroup`/`bakedOnly`, nenhum diretório `baked/` foi recriado. Contagem de
arquivos de sheet por mapa (que agora cobre o que antes era baked + o que já era dinâmico):
dragon-darashia 6, grim-reaper 6, larva-ankrah 6, rats-rookguard 4, rats-sewers 4, sea-serpent 6,
skeletons-rookguard 6, troll-rookguard 5 — contra os 262/133/97/41/61/243/114/161 arquivos de bake
que esses mesmos mapas geravam antes (ver tabela na ADR 0004).
