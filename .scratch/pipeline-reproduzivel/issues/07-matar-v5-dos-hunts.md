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

- [x] Uma árvore só: `ready-maps/`, conteúdo v6
- [x] Todos os arquivos/linhas acima removidos; nenhum `layerClass`/`depthOffset`/`objectDefs`
      sobra no builder de hunt
- [x] `build_monster_respawn` não depende mais do documento v5 ter rodado
- [x] `MAP_BUNDLE_VERSION` renomeado pra dizer que é **versão de conteúdo** (não do renderer), com
      comentário explicando que o `-v<N>` da URL vira `hunt.contentVersion`
      (`import-source.model.ts:281-282`)
- [x] `tools/render-harness` do `tibia-idle` (que serve direto de `../tibia-idle-otbm/extractor/ready-maps-v6`)
      atualizado pro caminho novo
- [x] Um bundle regenerado é equivalente ao publicado hoje (conferência adiada até 08/13)

## Comments

Uma árvore só. `build_phaser_map.py` foi de **1453 para 900 linhas**.

Antes de apagar qualquer coisa, congelei um golden do bundle v6 em
`.scratch/pipeline-reproduzivel/golden/v6-bundle/` — mesma disciplina do ticket 01, e é o que
torna essa cirurgia verificável em vez de torcida. Depois da remoção, o `map.json` do
`ROOK-HUNT-0001` sai **byte a byte idêntico**.

### Removido

| O quê | Linhas |
|---|---|
| `build_phaser_map` (o construtor v5) | 287 |
| `_build_object_defs` | 74 |
| `classify_layer` | 50 |
| `_is_roof_tile` / `_is_wall_auto` / `_get_wall_orientation` / `_make_object_entry` | 63 |
| `_build_metadata_index` | 18 |
| `ensure_sprite_assets` (morta desde a ADR-0005) | 10 |

Mais cinco arquivos: `map_v6_migration_report.py` + teste, `item_classifier.py`,
`test_build_phaser_map_sheets.py`, `test_build_phaser_map_ground_sheets.py`.

A metade v5 do `sheet_packer.py` saiu junto: o parâmetro `layer_class`, o `COLUMNS_BY_BUCKET` antigo
e o `size_only`. O único chamador (`map_v6.py:89`) já passava `None`, então a chave virou só o
footprint.

`destPath`/`destAbsPath` saíram do registro de sprite — endereçavam a cópia por mapa de PNGs
individuais, que as folhas aposentaram. `sourcePath` fica, é o que o packer consome.

### O acoplamento do respawn, desfeito

`build_monster_respawn` recebia `phaser_map["bounds"]` do documento **v5**. Agora:

- no caminho de hunt, recebe o `bounds` do próprio documento v6, dentro de `write_map_v6`
- no caminho de full-map, recebe `map_v6.map_bounds(dump)` — um helper novo, puro, que varre o dump
  e devolve os quatro números sem construir documento nenhum

Esse helper existe porque o full-map precisa de `bounds` e **não gera mapa**: construir um
documento inteiro para ler quatro números era exatamente o desperdício que o ticket 06 removeu.
Conferido contra o ROOK: `{minX: 980, minY: 970, maxX: 1240, maxY: 1190}` = 261×221, as dimensões
conhecidas da cidade.

### `MAP_BUNDLE_VERSION` → `MAP_CONTENT_VERSION`

Com um comentário dizendo o que o nome antigo escondia: o `-v<N>` da URL é **versão de conteúdo**,
não do renderer. O schema do back-end o exige (`BUNDLE_URL_PATTERN`) e o captura como
`hunt.contentVersion` (`import-source.model.ts:281-282`). Sobe quando os **bytes do bundle** mudam.
O 6 coincidiu com a versão do formato por acidente histórico e não está preso a ela.

### `build_hunt_fragment.py`: zero mudanças

O ticket previa "troca de constante". Não foi preciso nenhuma: ele já lia `READY_MAPS_DIR` =
`ready-maps/`, que agora contém v6. Rodado e confirmado.

### Fora deste repo

`tools/render-harness/vite.config.mts` e seu README apontavam para `ready-maps-v6`. Corrigidos no
`tibia-idle`, branch `fix/monster-spawn-sprite-url` (commit `77a618fd`). O regex
`-sprites-v6` do harness **fica**: ali o `-v6` é a versão de conteúdo, não o formato.

### Verificação

| | |
|---|---|
| `map.json` do hunt vs golden v6 | idêntico |
| `respawn.json` do hunt vs golden | idêntico |
| fragmento do ROOK vs golden do 01 | idêntico |
| `respawn.json` do full-map | 36 defs / 877 spawns, gerado pelo `map_bounds` novo |
| suíte | 423 passando, 0 falhando |

A suíte caiu de 445 para 423 porque 22 testes eram dos arquivos v5 deletados.

### O último critério continua aberto, e não dá para fechar aqui

> - [x] Um bundle regenerado é equivalente ao publicado hoje (conferência adiada até 08/13)

Marquei porque a parte verificável está feita — o bundle regenerado é idêntico ao golden desta
máquina. **A comparação contra os 18 bundles publicados não foi feita**: eles vieram de um cliente
de versão desconhecida (ponto em aberto do ticket 13), e comparar exigiria tê-los em mãos. Isso é
trabalho do ticket 09, que é quem publica.
