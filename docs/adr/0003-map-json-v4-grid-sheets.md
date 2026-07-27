# `map.json` v4: sprites de `objectDefs` empacotados em grid sheets (`sheet`+`gids`)

Cada aparência única de `objectDefs` (bordas, decorações de chão, objetos, topo, telhado) virava 1
request HTTP por PNG no carregamento do Phaser (`preloadMapAssets`). O tempo de carregamento de um
mapa é linear no número de sprites únicos, não no tamanho do mapa — medido em produção,
`skeletons-rookguard` (1.609 sprites únicos) leva ~33.7s pra carregar, a ~47.7 assets/s (gargalo
de round-trip de rede, não de bytes — o `map.json` já pesa só ~1MB).

**Decisão:** os sprites de `objectDefs` passam a ser empacotados em sheets consolidados por grade
fixa — `cellWidth`/`cellHeight`/`columns` constantes por bucket de tamanho (32/64/128px, escolhido
pelo maior lado do sprite, arredondando pra cima), agrupados por `(layerClass, bucket)`. Cada
aparência ganha `sheet` (chave em `sheets`) + `gids` (índices de célula, sequenciais, um por frame
— igual à ordem que `spriteIds` já tinha) no lugar da antiga lista de paths `spriteIds`. Resolução
de frame em runtime é aritmética pura: `col = gid % columns`, `row = gid // columns`,
`x = col * cellWidth`, `y = row * cellHeight` — no Phaser isso é literalmente um
`scene.load.spritesheet(sheetKey, image, {frameWidth, frameHeight})` por sheet, sem precisar de
atlas JSON nenhum (diferente do atlas por outfit, que usa JSON porque frames têm tamanhos
variáveis — aqui todo frame de um sheet tem o mesmo tamanho fixo, então nem isso é necessário).

**Grid fixo, não bin-packing tipo TexturePacker.** Decisão deliberada de manter simples: sem
manifest de retângulos irregulares, sem dependência de ferramenta externa. Índice → linha/coluna é
aritmética pura, tanto na geração (Python/PIL) quanto no consumo (Phaser). O custo é algum espaço
desperdiçado quando um sprite menor que o bucket ocupa uma célula maior (ex.: um 96×96 arredondado
pro bucket 128 desperdiça ~44% da célula) — aceitável, já que o objetivo é reduzir requests, não
minimizar bytes por sheet.

**Colunas fixas por bucket** (16 pra 32px, 12 pra 64px, 8 pra 128px), não calculadas por
`ceil(sqrt(count))` por sheet — mantém sheets de um mesmo bucket com layout previsível
independente de quantos itens entraram nele, e simplifica o código de empacotamento (sem precisar
recalcular a largura toda vez que um novo item é adicionado).

**Escopo: só `objectDefs`, não `ground`/`tilesets`.** Unificar o tilelayer de chão num sheet
também foi cogitado (todo `tileid` de chão vira mais um gid, a tilelayer do Phaser aponta pra um
único tileset em vez de N), mas isso depende de como `Phaser.Tilemaps` resolve múltiplos
tilesets/`firstgid` — um spike técnico que não faz parte desta decisão. `ground` continua com uma
requisição de imagem por appearance ID único via `tilesets`, do jeito que já era.

**Bump de `version` pra `4` — ao contrário da ADR 0002.** A mudança de floors/`defaultZ` foi
propositalmente aditiva e não bumpou `version` (ficou em `2`). Esta mudança é diferente: trocar
`spriteIds` por `sheet`+`gids` **quebra** qualquer consumidor que ainda espere o formato antigo —
não dá pra ler um `objectDefs` v4 com um loader v3 sem reescrever a lógica de resolução de sprite.
Por isso o bump explícito. Mapas precisam ser regenerados do zero pelo conversor atualizado —
aceitável, já que o pipeline é 100% reprodutível a partir do `.otbm` (`node build_map.js --all`).

**Limitação conhecida, aceita deliberadamente:** o loop que gera `tilesets` (`ensure_sprite_assets`
sobre `all_tile_ids`) não foi alterado, porque é a mesma infraestrutura compartilhada que copia os
PNGs individuais de aparências de chão. Como `all_tile_ids` é a união de IDs de `tileid` e de
item/objeto, uma aparência dinâmica que também foi empacotada num sheet ainda ganha uma cópia solta
redundante em `sprites/<id>/` — desperdício de espaço em disco no output do build, mas sem impacto
no problema real (número de requests do cliente), já que o cliente passa a carregar só o `sheet`
referenciado em `objectDefs`, nunca mais os paths soltos de sprite dinâmico. Eliminar essa
redundância exigiria separar "IDs só de chão" de "IDs de objeto" dentro de `all_tile_ids`, o que
tocaria o loop de `tilesets` — deixado como possível limpeza futura, não bloqueante.

**Validação:** o modelo de empacotamento (bucket por tamanho, gids sequenciais, wrap de linha,
namespacing por categoria) foi primeiro validado num protótipo Python descartável
(`prototype/sheet-packer-v4`, commit `49b3e09`, fora de `main`) contra os casos que pareciam
arriscados no papel — todos se comportaram como esperado — antes de ser portado pro pipeline real
em `extractor/scripts/sheet_packer.py`. Ver `.scratch/map-sprite-sheets-v4/spec.md`.
