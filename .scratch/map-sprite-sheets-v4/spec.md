# Spec: `map.json` v4 — Sprite Sheets em Grid + GIDs

Status: ready-for-agent

## Problem Statement

O `map.json` v3 já é compacto em dados de posicionamento (`objectDefs` + arrays `[appearanceId,
stackIndex]` por tile), mas cada aparência única de item/decoração/parede/telhado do mapa ainda
vira **1 request HTTP por PNG** no carregamento do Phaser (`preloadMapAssets`, via
`registerObjectTextures`/`registerTilesetTextures`). O tempo de carregamento de um mapa é linear
no número de sprites únicos, não no tamanho do mapa em tiles — medido em produção, o mapa
`skeletons-rookguard` (1.609 sprites únicos) leva ~33.7s pra carregar, a uma taxa efetiva de
~47.7 assets/s (gargalo de round-trip de rede, não de bytes — o `map.json` já pesa só ~1MB). Todo
mapa novo com mais conteúdo visual piora nessa mesma proporção.

## Solution

Empacotar os sprites de `objectDefs` (bordas, decorações de chão, objetos, topo, telhado) em
sheets consolidados por grade fixa (`cellWidth`/`cellHeight`/`columns` constantes, sem bin-packing
tipo TexturePacker), agrupados por `(layerClass, bucket de tamanho)`. Cada aparência passa a
referenciar `sheet` + `gids` (índices de célula) em vez de uma lista de paths de PNG individuais.
Resolução de frame em runtime vira aritmética pura (`col = gid % columns`, `row = gid // columns`)
— no Phaser, isso mapeia direto pra um único `scene.load.spritesheet()` por sheet, eliminando a
necessidade de um atlas JSON por grupo.

**Escopo desta versão:** só os sprites de `objectDefs` (as 5 categorias de objectgroup:
`border`, `bottom`, `object`, `top`, `roof`; `walls_south`/`walls_east` também, por serem a mesma
família de objectgroup). O tilelayer de `ground` continua usando o `tilesets` do v3, sem
alteração — unificar `ground` num sheet também foi cogitado na proposta original, mas exige um
spike técnico em cima de `Phaser.Tilemaps` (múltiplos tilesets/`firstgid`) que não faz parte
deste spec. Outfits de monstro **não são afetados** — já usam o atlas-por-outfit implementado em
[[outfit-sprite-atlas]], que é um mecanismo separado e já validado em produção.

O modelo de empacotamento (bucket por tamanho, gids sequenciais, wrap de linha) foi validado num
protótipo descartável antes de escrever este spec — ver `## Further Notes`.

## User Stories

1. Como jogador, quero que um mapa com muitos sprites únicos (ex.: skeletons-rookguard, 1.609
   sprites) carregue em poucos segundos, para não esperar ~34s antes de poder jogar.
2. Como desenvolvedor do cliente Phaser, quero carregar cada categoria de sprite do mapa com uma
   única chamada `scene.load.spritesheet()`, para trocar N requests por `sheets.length` requests.
3. Como desenvolvedor do cliente Phaser, quero resolver o frame de uma aparência por aritmética
   pura (`gid % columns`, `gid // columns`) em vez de precisar de um JSON de atlas por grupo, para
   manter o runtime mais simples (nem `scene.load.atlas` é necessário aqui).
4. Como mantenedor do pipeline de extração, quero que sprites de tamanhos incomuns (ex.: 96×96)
   arredondem para o bucket mais próximo que os comporte (128), em vez de quebrar o pipeline ou
   truncar o sprite.
5. Como mantenedor do pipeline de extração, quero que uma aparência animada (múltiplos frames)
   receba gids consecutivos dentro do mesmo sheet, para que a lógica de animação existente
   (`anim.frames`) continue funcionando só trocando "path" por "gid".
6. Como mantenedor do pipeline de extração, quero que a atribuição de gid seja determinística e
   estável entre builds (mesma ordenação de appearance ID), para não invalidar cache/diffs
   desnecessariamente entre gerações do mesmo mapa.
7. Como mantenedor do pipeline de extração, quero que duas `layerClass` diferentes com sprites do
   mesmo tamanho (ex.: `object` e `bottom`, ambos 32×32) fiquem em sheets separados, para não
   misturar categorias com comportamento de profundidade/render diferente na mesma textura.
8. Como mantenedor do pipeline de extração, quero manter o tilelayer de `ground` exatamente como
   está hoje (`tilesets` do v3), para não precisar resolver o spike de múltiplos
   tilesets/`firstgid` do Phaser Tilemaps dentro deste trabalho.
9. Como mantenedor do repositório, quero que a mudança de formato (`spriteIds` → `sheet`+`gids`)
   seja documentada como breaking change explícito (bump de `version` pra 4), para diferenciar da
   mudança aditiva de floors/`defaultZ` (que propositalmente não bumpou version — ver ADR 0002).
10. Como mantenedor do repositório, quero uma nova ADR documentando a decisão de sheets em grid
    fixo (em vez de packer tipo TexturePacker), para registrar o trade-off do mesmo jeito que as
    ADRs 0001/0002 já documentam decisões anteriores de formato.
11. Como desenvolvedor do cliente Phaser (repositório `tibia-idle`), quero um contrato claro de
    `sheets` na raiz do `map.json` (chave → `image`/`cellWidth`/`cellHeight`/`columns`) e de
    `sheet`+`gids` por `objectDef`, para implementar o loader v4 sem adivinhar a convenção.
12. Como mantenedor do pipeline, quero rodar o build nos mapas reais existentes e confirmar
    visualmente que os sheets gerados batem com os sprites originais (nenhum gid trocado/says
    errado), antes de considerar o v4 pronto para o cliente consumir.

## Implementation Decisions

- **Escopo de empacotamento**: só aparências que hoje viram entradas de `objectDefs`
  (`border`/`bottom`/`object`/`top`/`roof`/`walls_south`/`walls_east`). `ground` (tilelayer) e
  `tilesets` continuam no formato v3, sem mudança.
- **Bucket de tamanho**: 32/64/128px, escolhido pelo maior lado do sprite (`max(width, height)`),
  arredondando para cima até o bucket que o comporta; qualquer coisa maior que 128 fica clampada
  no bucket de 128 (não existe, na prática, nenhum sprite de objectgroup maior que 128×128 nos
  dados reais — confirmado em `SPRITE_METADATA.md`, seção "Combinações de Pattern": o maior padrão
  observado é 4×4×1/128×128, e esses já são redirecionados para `roof` antes de chegar aqui).
- **Chave de sheet**: `{layerClass}-{bucket}` (ex.: `object-32`, `roof-64`, `roof-128`) — cada
  combinação de categoria + tamanho vira seu próprio sheet, nunca misturando categorias.
- **Colunas fixas por bucket** (não calculadas por `ceil(sqrt(count))`): grade fixa e previsível
  por tamanho de célula, validada no protótipo. Um sheet cresce em altura (mais linhas) conforme
  mais aparências entram nele, largura fixa.
- **Atribuição de gid**: sequencial, na ordem em que as aparências são visitadas durante o build
  (mesma ordenação de appearance ID que o pipeline já usa hoje para outras estruturas) — cada
  aparência recebe `frame_count` gids consecutivos dentro do sheet de destino, onde
  `frame_count` é a mesma contagem que hoje vira o tamanho do array `spriteIds`.
- **Resolução de frame**: `col = gid % columns`, `row = gid // columns`; pixel
  `x = col * cellWidth`, `y = row * cellHeight`. Cálculo simétrico usado tanto pra gerar o PNG do
  sheet (Python/PIL) quanto pro cliente resolver o frame em runtime.
- **Formato de imagem**: PNG (mantém canal alpha; a maioria dos sprites do Tibia tem
  transparência). Sem avaliação de WebP nesta versão.
- **`objectDefs`**: campo `spriteIds: string[]` (paths) substituído por `sheet: string` (chave em
  `sheets`) + `gids: number[]` (mesma ordem/semântica que `spriteIds` tinha, incluindo sprites
  animados — cada frame de animação é um gid consecutivo, igual ao protótipo validou).
- **Novo campo raiz `sheets`**: dict `{sheetKey: {image, cellWidth, cellHeight, columns}}`, um
  entry por combinação `(layerClass, bucket)` que teve pelo menos uma aparência.
- **Sheets são por mapa**, não compartilhados entre mapas nesta versão — mantém cada mapa
  auto-contido em `assets/<map>-sprites/`, igual ao padrão já existente. Compartilhar sheets entre
  mapas com sprites em comum fica como otimização futura, não bloqueante.
- **Bump de `version` para `4`**: breaking change de formato explícito, diferente da decisão
  registrada na ADR 0002 (floors/`defaultZ` foi aditivo, não bumpou version). Mapas precisam ser
  regenerados do zero pelo conversor atualizado — aceitável, já que o pipeline é 100%
  reprodutível a partir do `.otbm`.
- **Nova ADR** (`docs/adr/0003-...`) documentando a escolha de grid fixo em vez de packer
  otimizado, seguindo o mesmo estilo curto e focado em decisão das ADRs 0001/0002.
- **`extractor/CONVERTER_DOCS.md`/`PHASER_INTEGRATION.md`** atualizados com o novo formato de
  `objectDefs`, o campo `sheets`, e o exemplo de resolução de frame em runtime
  (`scene.load.spritesheet` + `frame: gid`).

## Testing Decisions

- Módulo de empacotamento puro (bucket, atribuição de gid, dimensões de sheet, resolução
  gid→retângulo) testável isoladamente, sem I/O — mesmo padrão de `_render_baked_row`/`_is_bakeable`
  já usado em `extractor/tests/`: funções/classe pura, fixtures de PNG via PIL em `tmp_path` só
  onde a geração de imagem real precisa ser exercitada.
- Casos de borda a cobrir (já validados manualmente no protótipo descartável, ver `## Further
  Notes` — agora precisam virar testes automatizados reais):
  - Tamanho ímpar (96×96) arredonda para o bucket 128, não 64.
  - Aparência com múltiplos frames recebe gids consecutivos no mesmo sheet.
  - Um sheet que ultrapassa `columns` quebra pra próxima linha corretamente (gid→(row,col) continua
    correto atravessando a quebra).
  - Duas `layerClass` diferentes com o mesmo tamanho de sprite vão para sheets distintos.
  - Determinismo: rodar o build duas vezes sobre a mesma entrada produz os mesmos gids e o mesmo
    PNG de sheet byte a byte.
- Teste de integração no estilo `test_build_phaser_map_baking.py`: `build_phaser_map()` com
  fixtures pequenas, checando que `objectDefs` emite `sheet`+`gids` (não mais `spriteIds`) e que a
  raiz do `map.json` tem `sheets` com as chaves esperadas.
- Rodar `node build_map.js --all` nos 8 mapas reais depois de implementado, e inspecionar
  visualmente pelo menos um sheet gerado por mapa (abrindo o PNG) pra confirmar que os sprites
  aparecem intactos nas células esperadas.

## Out of Scope

- Unificar `ground`/`tilesets` num sheet (seção 6 da proposta original) — precisa de spike técnico
  em `Phaser.Tilemaps` antes de ser considerado.
- Sheets compartilhados entre mapas.
- WebP ou qualquer formato além de PNG.
- Compatibilidade dupla v3/v4 no cliente (loader por `map.version`) — decisão de manter ou não o
  loader v3 em paralelo fica para quem implementar o lado Phaser no repositório `tibia-idle`.
- Qualquer mudança no atlas de outfit de monstro — já é um mecanismo separado e funcionando.
- Implementação do lado cliente (Phaser/TypeScript) — vive no repositório `tibia-idle`, que não
  está acessível nesta sessão. Este spec produz o contrato (`sheets` + `sheet`/`gids`) que aquele
  repositório vai consumir.

## Further Notes

Antes de escrever este spec, o modelo de empacotamento (bucket por `(layerClass, cellSize)` +
gids sequenciais + grid de colunas fixas) foi validado num protótipo Python descartável
(`extractor/_prototypes/sheet_packer_prototype.py`, preservado na branch `prototype/sheet-packer-v4`,
commit `49b3e09`, fora de `main`). Rodado interativamente contra os 4 casos que pareciam
arriscados no papel — arredondamento de bucket ímpar, frames consecutivos de animação, quebra de
linha, e namespacing por categoria — todos os quatro se comportaram como esperado. Ver o commit da
branch para o código exato e o transcript de verificação.
