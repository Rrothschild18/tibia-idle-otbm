# Remover o sistema de bake de cenário estático — usar só sheets (v4)

O bake de cenário estático (ADR 0001) compunha os itens elegíveis de cada `(tileY, layerClass)`
numa única imagem PNG, com o objetivo original de reduzir **custo de instanciação em runtime**
(menos `Phaser.GameObjects.Image` criados por frame, competindo pelo budget de 16ms/60fps).

Depois que o empacotamento em sheets (map.json v4, ADR 0003) foi implementado para os itens
dinâmicos (animados/`random`/`border`/`roof`, que nunca eram elegíveis pra bake), medimos quantos
arquivos o bake de fato gerava por mapa real:

| Mapa | PNGs de bake |
|---|---|
| dragon-darashia | 262 |
| sea-serpent | 243 |
| grim-reaper | 133 |
| troll-rookguard | 161 |
| skeletons-rookguard | 114 |
| larva-ankrah | 97 |
| rats-sewers | 61 |
| rats-rookguard | 41 |

Contra isso, sheets produzem de 4 a 6 arquivos por mapa pra cobrir o mesmo tipo de conteúdo. O
bake nunca foi desenhado pra resolver o problema de **rede** (número de requests) — resolvia
runtime — mas na prática ele **piora** esse eixo em vez de ajudar: uma imagem por linha-com-conteúdo
é, por definição, muitos arquivos num mapa com múltiplas linhas de decoração/parede/objeto.

**Decisão:** remover o sistema de bake inteiramente. Todo item que antes seria elegível pra bake
(estático, não-`random`, não-interativo, fora de `border`/`roof`) passa a seguir o mesmo caminho
dinâmico que qualquer outro item não-bakeável já seguia: vira uma entrada normal de objectgroup, e
sua sprite é resolvida via `sheet`+`gids` como qualquer outro `objectDefs` dinâmico (ADR 0003). O
Phaser continua montando o mapa tile a tile — um `GameObject` por placement — exatamente como já
fazia pros itens não-bakeáveis; a única mudança é que agora **todo** item dinâmico usa sheet, não
só uma parte deles.

**O que se perde:** o ganho de runtime que o bake dava (menos objetos instanciados/desenhados por
frame) deixa de existir — cada placement volta a ser seu próprio `GameObject`, do jeito que já era
antes da ADR 0001 pra itens não-bakeáveis. Isso é uma aposta deliberada: o sistema de chunk
streaming já existente (`ChunkManager`, ver `PHASER_INTEGRATION.md`) já mantém sprites fora de tela
"pooled" em vez de destruídos, e a carga de instanciação por chunk é limitada
(`flushPending(spritesPerFrame=200)`) — o custo de runtime que a ADR 0001 tentava evitar já tinha
essa outra mitigação em paralelo. Se o custo de runtime voltar a ser um problema real e medido, a
resposta correta não é reviver o bake por linha (que perde no eixo de rede), e sim considerar bake
em unidades maiores que ainda preservem sheets como fonte de textura — não avaliado aqui, fica como
trabalho futuro caso a medição justifique.

**Removido:** `_is_bakeable`, `_render_baked_row`, `_baked_entry_sprite`, `BAKED_OUTPUT_DIR`, o
layer `bakedgroup` do `map.json`, `--dump-baked-preview`/`_print_baked_preview`, `INTERACTIVE_IDS`
(`item_classifier.py`, só existia pra alimentar `_is_bakeable`), e os testes
`test_is_bakeable.py`/`test_render_baked_row.py`/`test_build_phaser_map_baking.py`. A distinção
"ground-only vs dinâmico" em `_build_object_defs` (aparências só vistas como `tileid`, nunca
placed via objectgroup, não ganham `sheet`/`gids`) continua existindo — é ortogonal ao bake, não
foi afetada por esta remoção.

Ver [ADR 0001](0001-bake-unit-is-row-plus-layerclass.md) (superseded) e
`.scratch/map-sprite-sheets-v4/issues/04-remove-bake-system.md`.
