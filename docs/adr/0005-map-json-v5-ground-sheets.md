# `map.json` v5: `ground`/`tilesets` empacotado em grid sheets

A migração v4 (ADR 0003) empacotou `objectDefs` em sheets, mas deixou `ground`/`tilesets`
deliberadamente fora de escopo — cada aparência única de chão continuava gerando 1 entrada de
`tilesets` (`tilecount: 1, columns: 1`) e 1 request HTTP própria. Isso sobrou como o gargalo de
requests dominante: de 89 a 325 requests por mapa, 90%+ do total mesmo depois da v4 (sheets de
objeto: 7-9 requests; atlas de monstro: 0-3).

**Decisão:** as aparências de `ground` passam a ser empacotadas pelo mesmo `SheetPacker` já usado
para `objectDefs` (`extractor/scripts/sheet_packer.py`), sob `layerClass: "ground"` — mesmos buckets
de tamanho (32/64/128px) e colunas fixas por bucket. `tilesets` vira 1 entrada por sheet de ground
efetivamente usado (tipicamente 1-2), no lugar de 1 por aparência. A tilelayer `Ground` é
renumerada: cada célula referencia `firstgid_do_sheet + gid_local_da_aparência` em vez do
`firstgid` de um tileset dedicado.

Redução projetada de requests por mapa (ground: antes → depois, sheets de objeto e atlas de
monstro já existentes somados):

| mapa | total hoje | total proposto |
|---|---|---|
| skeletons-rookguard | 262 | 12 |
| troll-rookguard | 337 | 14 |
| rats-sewers | 142 | 12 |
| dragon-darashia | 113 | 11 |
| rats-rookguard | 110 | 12 |
| grim-reaper | 97 | 10 |
| sea-serpent | 100 | 10 |
| larva-ankrah | 114 | 9 |

**`firstgid` sequencial por capacidade total do sheet, não por aparências ocupadas.** O `tilecount`
de cada entrada de `tilesets` é `columns × rows` do grid do `SheetPacker` (a capacidade cheia da
imagem), não o número de aparências de fato empacotadas nela. O próximo sheet começa seu `firstgid`
depois dessa capacidade cheia — padrão Tiled, e evita qualquer sobreposição de faixa de gid mesmo
quando a última linha do sheet fica parcialmente vazia.

**`tilesets` agora só contém ground — nunca objetos.** Antes da v4 (e ainda depois dela, até esta
mudança), o loop que construía `tilesets` iterava sobre `all_tile_ids`, a união de tileids de chão
e IDs de item/objeto — todo appearance ID já visto em qualquer lugar do mapa ganhava uma entrada de
tileset e uma cópia solta de PNG em `sprites/<id>/`, mesmo que nunca fosse referenciado pela
tilelayer `Ground` (objetos são desenhados via `objectDefs`/`sheets`, nunca via `tilesets`) — esse
desperdício já estava documentado como uma limitação aceita na ADR 0003. Com o ground agora vindo
de um conjunto próprio (`ground_tiles`, coletado durante a primeira passada, apenas os `tileid` que
não foram redirecionados pro Roof — ver `_is_roof_tile`), `tilesets` deixa de incluir qualquer ID
que só existe como objeto. Como efeito colateral, a chamada a `ensure_sprite_assets` para tileids de
chão (que só existia para alimentar o antigo `image`/`destPath` por aparência) foi removida — o
sheet lê o PNG fonte diretamente (`sourcePath`), do mesmo jeito que os sheets de objeto já faziam.

**Sem consumo pelo cliente nesta mudança de formato isoladamente.** Empacotar é uma mudança pura de
dados no `map.json`; o cliente Phaser (`libs/phaser-game`) que hoje espera 1 tileset por aparência
precisa ser adaptado para carregar os sheets via `scene.load.spritesheet()` — ver ticket 02 de
`.scratch/ground-tile-sheets/`.

**Bump de `version` pra `5`.** Mesma razão da v4 (ADR 0003): o formato de `tilesets` muda de forma
incompatível (gid agora resolve contra um sheet compartilhado, não mais 1:1 por aparência) — não dá
pra ler um `tilesets` v5 com um client v4. Corte seco, sem suporte paralelo ao formato antigo;
mapas são 100% reprodutíveis a partir do `.otbm` (`node build_map.js --all`).

**Validação:** o empacotamento foi primeiro confirmado num protótipo descartável rodando o
`SheetPacker` real, sem nenhuma modificação, contra os `tilesets` já existentes de cada mapa
publicado (`extractor/scripts/prototype_ground_sheets.py`) — todos os 8 mapas colapsaram para 1-2
sheets. Ver `.scratch/ground-tile-sheets/spec.md`.
