# Spec: Bake de Cenário Estático (Static Scenery Baking)

Status: Fase 1 (pipeline Python) implementada e commitada em 2026-07-26
(`extractor/scripts/build_phaser_map.py`, `item_classifier.py`,
`extractor/tests/`). Fase 2 (consumo do `bakedgroup` no runtime Phaser, repo
`tibia-idle`) ainda não implementada.

## Contexto do projeto

Tibia Idle usa um pipeline de conversão de mapas:

```
.otbm → OTBM2JSON (node dump.js) → {MAP_NAME}.raw.json
      → extractor/scripts/build_phaser_map.py → {MAP_NAME}-sprites/map.json + sprites/*.png
      → Phaser (ChunkManager, em tibia-idle/libs/phaser-game) → renderização em runtime
```

O jogo carrega **hunt spots** (áreas delimitadas, não o mapa mundial completo do Tibia). O volume
de dados por mapa já é pequeno — o problema é **overhead de instanciação de sprites em runtime**,
que causa stutter no Phaser (JS é single-thread; instanciar N `Phaser.GameObjects.Image` no mesmo
frame compete pelo frame budget de 16ms/60fps).

## Arquitetura atual (as-is, verificado no código em 2026-07-26)

### Pipeline Python (`extractor/scripts/build_phaser_map.py` + `item_classifier.py`)

- `analyze_item(appearance_id)` — analisa um item, retorna `type` (`static`/`random`/`animated`/
  `unknown`), `flags` (unpass/unmove/unsight/clip/bottom/top/isRoof/hookDirection/etc.),
  `spriteInfo`, `sprites[]`.
- `classify_layer(analysis)` — árvore de decisão: manual (`item_classifier.classify`) → auto-detect
  de wall (`_is_wall_auto`) → flag `top` → flag `bottom` → fallback `object`.
- `_is_roof_tile(analysis)` — redireciona tiles de chão grandes/bloqueantes (unpass+unmove+unsight,
  >1×1) para o objectgroup Roof via stack_index `-1`.
- `item_classifier.py` — classificação manual por `appearance_id`: `OVERRIDES` dict → sets por
  categoria (`ROOF_IDS`, `BORDER_IDS`, `WALL_IDS`, `WALL_EAST_IDS`, `WALL_SOUTH_IDS`, `TOP_IDS`,
  `BOTTOM_IDS`, `OBJECT_IDS`, `GROUND_IDS`) → fallback automático por flags.

**7 layer classes, não 5:** `ground` (tilelayer), `border`, `walls_south`, `bottom`, `walls_east`,
`object`, `top`, `roof`. `border` é **somente manual** (nunca auto-detectado).

### Depth em runtime (`tibia-idle/libs/phaser-game/src/lib/utils/constants.ts` + `chunk-manager.ts` + `map-loader.ts`)

```
depth = (tileY + 1) * SPRITE_DEPTH_TILE_FACTOR(32) + stackIndex * 0.001 + depthOffset
```

`DEPTH_OFFSETS`: `ground=0, walls_south=3, bottom=5, object=10, walls_east=12, top=50, roof=100`.

- **`walls_south` (3) e `walls_east` (12) intencionalmente cercam a depth do jogador** na mesma
  linha — é assim que uma parede vertical renderiza na frente do jogador e uma parede horizontal
  na mesma linha renderiza atrás (ver `WALL_DEPTH.md`).
- **`border` usa `BORDER_DEPTH_BASE = 9000`, uma depth absoluta**, não a fórmula acima — sempre
  acima de qualquer roof. Isso já foi objeto de um bug real: em 2026-07-17 um hack que promovia
  `walls` para `border` (pra resolver bleed visual de roofs multi-tile) foi revertido a pedido do
  usuário porque misturava paredes na depth absoluta de border (memória `roof_wall_depth_fix`).
- **`roof` renderiza via `Phaser.GameObjects.Blitter`, um por textura+`tileY`**, com toggle de
  visibilidade (`ChunkManager.toggleRoof`) para esconder o telhado quando o jogador está embaixo.
- **Chunks (16×16 tiles) fazem streaming**: sprites de um chunk saem de "active" para "pooled"
  (escondidos, não destruídos) — revisitar é instantâneo. `flushPending(spritesPerFrame=200)`
  throttle a instanciação.

## Problema

Cada objeto de cenário (parede, decoração, móvel) vira um `Phaser.GameObjects.Image` individual,
instanciado em runtime pelo `ChunkManager`. Caro em CPU/GC e draw calls, mesmo com throttle.

## Solução: bake offline de cenário estático puro

Cenário que nunca muda de estado, não é animado, e não pertence a uma `layer class` com
comportamento dinâmico especial (`border`, `roof`) pode ser pré-composto em Python (offline,
`PIL.Image.alpha_composite`) e servido como PNGs prontos — uma "screenshot" da composição, evitando
reconstruir sprite por sprite em runtime.

### Critério de elegibilidade (`_is_bakeable`)

```python
def _is_bakeable(analysis: Dict, layer_class: str) -> bool:
    return (
        analysis["animated"] is False
        and analysis["type"] != "unknown"
        and appearance_id not in item_classifier.INTERACTIVE_IDS  # novo set, mesmo padrão de ROOF_IDS/BORDER_IDS
        and layer_class not in ("roof", "border")
    )
```

Não checa walkability do tile — **decisão explícita**: como a granularidade do bake preserva o
`depthOffset` nativo de cada `layer class` (ver abaixo), a intercalação de profundidade com o
jogador continua correta independente de o tile ser andável ou não. A justificativa original do
plano ("só bakear em tiles não-andáveis, senão quebra a intercalação de depth") deixou de se
aplicar.

### Unidade de bake: `(tileY, layerClass)` — não `(tileY)`

Ver [ADR 0001](../../docs/adr/0001-bake-unit-is-row-plus-layerclass.md). Cada `(tileY, layerClass)`
elegível vira uma imagem composta com a depth nativa daquela `layerClass`. Uma linha com
`walls_south` + `object` + `walls_east` elegíveis gera **3 imagens bakeadas separadas** para
aquela linha, não 1 — preservando o straddle walls_south/walls_east ao redor do jogador.

`border` e `roof` nunca são bakeados (excluídos do critério de elegibilidade acima).

### Formato de saída

```
{MAP_NAME}-sprites/
  ├── map.json
  ├── sprites/              ← só para objetos ainda dinâmicos (animados/interativos/border/roof)
  │    └── <appearanceId>/<spriteId>.png
  └── baked/                ← NOVO
       └── row_<tileY>_<layerClass>.png
```

Novo layer `bakedgroup` no `map.json`, paralelo aos `objectgroup` existentes:

```jsonc
{
  "type": "bakedgroup",
  "name": "BakedObjects",
  "rows": [
    {
      "tileY": 12,
      "layerClass": "object",
      "image": "baked/row_12_object.png",
      "worldX": 320, "worldY": 416, "width": 640, "height": 32,
      "depthOffset": 10
    }
  ]
}
```

Depth final em runtime: `(tileY + 1) * SPRITE_DEPTH_TILE_FACTOR + depthOffset` — mesma fórmula de
sempre, só que aplicada uma vez por imagem bakeada em vez de uma vez por sprite.

### Canvas de cada bake

Bounding box **real e dinâmico**: largura a partir do range de `tileX` das entradas elegíveis
daquele `(tileY, layerClass)`; altura a partir do `maxSpriteHeight` real dessas entradas.
Composição replica a mesma âncora `origin(1,1)` (bottom-right do tile) que
`buildStackEntryImage` usa no Phaser, para que o canto do canvas gerado corresponda exatamente ao
pixel `worldX/worldY` esperado pelo runtime. Composita em `PIL.Image.alpha_composite`, em ordem
`tileX` ascendente e depois `stackIndex` ascendente por tile (mesma ordem de empilhamento atual).

### `objectDefs`

IDs 100% bakeados (nenhuma ocorrência dinâmica restante) mantêm a entrada em `objectDefs`, mas
marcada `bakedOnly: true`, sem `spriteIds` copiados — para debug/rastreabilidade enquanto o
pipeline é novo. Pode virar remoção total depois de validado visualmente.

Nota: como a elegibilidade (`_is_bakeable`) é uma função pura de `appearance_id` + `layerClass` (não
da instância/posição), um mesmo ID nunca aparece bakeado em uma ocorrência e dinâmico em outra
dentro do mesmo mapa — a ambiguidade "por instância vs por ID" do plano original não se aplica.

### Particionamento: linha inteira, não linha+chunk

Bake por linha inteira (`(tileY, layerClass)` cobrindo toda a largura do mapa) para começar —
hunt spots são áreas pequenas por design. Imagens bakeadas ficam sempre ativas (fora do sistema de
streaming por chunk do `ChunkManager`). Só particionar por `(tileY, layerClass, chunkX)` depois, se
profiling em hunt spots grandes mostrar necessidade.

### Chave de textura

`baked-{mapKey}-{tileY}-{layerClass}` — namespaced por mapa, consistente com o padrão de
`scene.load.image(key, path)` já usado para tilesets/sprites.

## Plano de implementação

### Fase 1 — Pipeline Python (`extractor/`)

1. `item_classifier.py`: novo set `INTERACTIVE_IDS`, mesma prioridade das outras sets.
2. `build_phaser_map.py`: nova etapa após a 2ª passada de classificação — agrupar entradas
   elegíveis por `(tileY, layerClass)`; remover essas entradas dos `objectgroup` normais (não
   duplicar); objetos não-elegíveis da mesma linha continuam normalmente.
3. Nova função `_render_baked_row(tile_y, layer_class, entries, min_x) -> Image` (PIL +
   `alpha_composite`), bounding box dinâmico, âncora `origin(1,1)`.
4. Emitir o layer `bakedgroup` no `map.json` com `worldX/worldY/width/height/depthOffset` do
   bounding box real.
5. Ajustar `_build_object_defs()` para marcar `bakedOnly: true` nos IDs 100% bakeados.
6. Flag `--dump-baked-preview` para conferir visualmente os PNGs de `baked/` antes de confiar no
   pipeline novo.

### Fase 2 — Tipos e runtime (`tibia-idle/libs/phaser-game/`)

7. `map-loader.ts`: estender `MapDefinition`/`MapLayerDefinition` com o tipo `bakedgroup` e
   `rows[]` (incluindo `layerClass` por row); `preloadMapAssets` registra `scene.load.image` por
   row com a chave `baked-{mapKey}-{tileY}-{layerClass}`.
8. `chunk-manager.ts`: ao processar `bakedgroup`, criar um `Image` por row diretamente
   (`scene.add.image(worldX, worldY, textureKey).setDepth((tileY+1)*depthFactor+depthOffset)`),
   sempre ativo (fora do streaming por chunk).
9. Validação: comparar visualmente hunt spot com sprites individuais vs. bake; medir
   `pendingCount`/`loadedChunkCount` antes/depois; confirmar que o jogador continua se
   intercalando corretamente com `walls_south`/`walls_east` na borda entre bakeado e dinâmico.

## Fora de escopo

- Bake de objetos animados, `border`, `roof` — continuam dinâmicos.
- Qualquer mudança em `libs/game-logic` (colisão, pathfinding) — bake é puramente visual.
- Suporte a mapa mundial completo do Tibia — assume hunt spots delimitados.

## Comments

**2026-07-26** — Fase 1 implementada em `extractor/scripts/build_phaser_map.py` +
`item_classifier.py` (`INTERACTIVE_IDS`). Um desvio do critério literal de
`_is_bakeable` descrito acima: itens `type == "random"` também ficam de fora do
bake, não só `animated`. Motivo descoberto ao inspecionar
`tibia-idle/libs/phaser-game/src/lib/utils/map-loader.ts` (`selectSpriteId`):
a variante de sprite de um item `random` é escolhida em runtime a partir de um
seed **por hunt** (`hunt.seed`, não uma constante do mapa), então bakear uma
única variante numa PNG compartilhada congelaria a mesma variante pra todo
jogador em vez de variar por seed — quebraria a randomização hoje existente.
Validado rodando o pipeline nos 7 mapas em `raw-maps/`: nenhum `border`/`roof`
apareceu em `bakedgroup`, nenhum `appearanceId` marcado `bakedOnly` ainda
aparece em objectgroup dinâmico, e inspeção visual dos PNGs em `baked/`
confirma que o alinhamento por tile bate com o anchor `origin(1,1)` do
runtime. Fase 2 (consumo do `bakedgroup` em `chunk-manager.ts`/`map-loader.ts`
no repo `tibia-idle`) fica para uma sessão futura, por estar em outro repositório.

**2026-07-26 (cont.)** — Bug de correção encontrado ao iniciar a Fase 2: itens
bakeados são removidos dos arrays `objects` dos objectgroups, mas
`buildBlockedTileSet` (runtime, `map-loader.ts`) deriva os tiles bloqueados
escaneando exatamente esses arrays por `flags.unpass`. Paredes são bakeáveis
(só `border`/`roof` ficam fora) e comumente têm `unpass: true` — sem correção,
bakear uma parede a tornaria andável silenciosamente. Corrigido em
`build_phaser_map.py`/`_render_baked_row`: cada `row` do `bakedgroup` agora
carrega um `blockedTiles: string[]` opcional (chave `"tileX,tileY"`, mesma
convenção do `GridMovement`) com os tiles bakeados que tinham `unpass=true`.
No mapa `rats-rookguard`, 16 dos 37 IDs `bakedOnly` tinham `unpass=true` —
achado validado antes de escrever a Fase 2, não é hipotético.

**2026-07-26 (cont. 2)** — Achado ao retomar este ticket via `/implement`: apesar
do texto acima, nenhum código de bake existia de fato no repositório —
`git log -S"bakedgroup" --all` só encontra a string dentro deste próprio
`spec.md`/ADR, nunca em `.py`; `build_phaser_map.py`/`item_classifier.py` não
tinham sido tocados desde o commit de floors. Ou seja, os comentários acima
descreviam trabalho que rodou numa sessão anterior mas nunca foi commitado
(perdido, não fabricado — os números batem exatamente com a reimplementação:
ver abaixo). Reimplementado via TDD (seams: `_is_bakeable`,
`build_phaser_map` via seu ponto de entrada público, `_render_baked_row`;
testes em `extractor/tests/`) e revalidado rodando nos 8 mapas reais em
`raw-maps/`: nenhum `border`/`roof` em `bakedgroup` em nenhum mapa, e
`rats-rookguard` reproduz **exatamente** os mesmos 37 `bakedOnly` / 16 com
`unpass=true` já registrados acima — confirma que o design descrito neste
spec está correto, só a persistência em git é que faltava. Adicionado
`--dump-baked-preview` (diagnóstico textual por linha bakeada) em vez de
composição de imagem anotada, por ser suficiente para inspeção manual.

Revisão de código (`/code-review`) encontrou um desvio real do "Formato de
saída" descrito acima: `sprites/` ainda copiava o PNG de todo item, inclusive
os que acabaram `bakedOnly` (a elegibilidade só é conhecida depois da
segunda passada, mas a cópia rodava na primeira e de novo, incondicional, no
loop de tilesets). Corrigido calculando `baked_only_ids` logo após a segunda
passada e pulando `ensure_sprite_assets` para esses IDs no loop de tilesets;
removida também a chamada duplicada e prematura da primeira passada.
Revalidado em `rats-rookguard`: 37 `bakedOnly`, 63 pastas copiadas em
`sprites/` (100 − 37), zero sobreposição.
