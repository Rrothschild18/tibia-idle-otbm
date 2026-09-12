Status: ready-for-agent

# 07 — Matar o v5 dos hunts: uma árvore só

**What to build:** `build_phaser_map.py` gera duas árvores em todo run (`ready-maps/` v5 e
`ready-maps-v6/`) e não tem flag pra escolher — não tem `argparse`, é `sys.argv[1]`
(`:23-28`). O `tibia-idle` é v6-only e **lança exceção** em qualquer outra coisa
(`map-definition.ts:62-71`), então a árvore v5 é bakeada todo run pra ninguém.

`ready-maps-v6/` passa a ser `ready-maps/`. Sai o v5 inteiro:

- `build_phaser_map.py`: `89-103`, `152`, `160-165`, `224-236` (`ensure_sprite_assets` — **já é
  código morto**: definido e nunca chamado desde a ADR-0005, mas `:152` ainda cria a pasta
  `sprites/` vazia todo run), `553-638`, `657-772`, `773-1063`, `1065-1090`, `1414-1432`
- `map_v6_migration_report.py` + `tests/test_map_v6_migration_report.py` (só existem pra comparar as
  duas árvores)
- `item_classifier.py` (v5-only pelo próprio README, `:409`)
- a metade v5 do `sheet_packer.py` (`BUCKET_SIZES`/`COLUMNS_BY_BUCKET`, agrupamento por `layerClass`)
- `tests/test_build_phaser_map_sheets.py`, `tests/test_build_phaser_map_ground_sheets.py`

Cuidado com dois acoplamentos: `build_monster_respawn` escreve na árvore **v5**
(`MONSTERS_OUTPUT_DIR`, `:126`, `:1345-1349`) e recebe `phaser_map["bounds"]` do documento v5
(`:1433`) — o v6 calcula bounds idêntico em `map_v6.py:264`. E `build_hunt_fragment.py` lê
`ready-maps/<...>/monsters/respawn.json` (`:63-73`): com a renomeação, é troca de constante.

**Blocked by:** 06. **Verificável só com uma biblioteca de sprites em mãos** (tickets 08/13) —
escrever pode; provar que um bundle regenerado bate com o publicado, não.

- [ ] Uma árvore só: `ready-maps/`, conteúdo v6
- [ ] Todos os arquivos/linhas acima removidos; nenhum `layerClass`/`depthOffset`/`objectDefs`
      sobra no builder de hunt
- [ ] `build_monster_respawn` não depende mais do documento v5 ter rodado
- [ ] `MAP_BUNDLE_VERSION` renomeado pra dizer que é **versão de conteúdo** (não do renderer), com
      comentário explicando que o `-v<N>` da URL vira `hunt.contentVersion`
      (`import-source.model.ts:281-282`)
- [ ] `tools/render-harness` do `tibia-idle` (que serve direto de `../tibia-idle-otbm/extractor/ready-maps-v6`)
      atualizado pro caminho novo
- [ ] Um bundle regenerado é equivalente ao publicado hoje (conferência adiada até 08/13)
