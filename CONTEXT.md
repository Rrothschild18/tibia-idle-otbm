# Tibia Idle — Pipeline de Mapas e Renderização

Glossário do pipeline de conversão de mapas (OTBM → Phaser) e dos conceitos de renderização em
runtime que ele alimenta.

## Language

**Hunt spot**:
Área delimitada que o jogo carrega como um mapa — não o mundo completo do Tibia. É a unidade de
escopo do pipeline do extractor e do runtime.

**Layer class** (`layerClass`):
O papel de renderização atribuído a um objeto ou tile do mapa (`ground`, `border`, `bottom`,
`object`, `top`, `roof`, `walls_south`, `walls_east`). Determina ordem de desenho e comportamento
de profundidade.
_Avoid_: layer type, categoria (quando o assunto é especificamente o papel de renderização)

**Depth offset**:
A contribuição de uma `layer class` para a profundidade (z-depth) de um sprite renderizado,
somada a uma base relativa à linha (`tileY`), de forma que diferentes `layer classes` se intercalem
corretamente com entidades na mesma linha do mapa (ex.: uma parede vertical renderiza na frente do
jogador, uma parede horizontal na mesma linha renderiza atrás).
_Avoid_: z-index

**Bakeable** (cenário bakeável):
Um objeto do mapa elegível para pré-composição offline em uma única imagem estática, por nunca
mudar de estado, não ser animado, e não pertencer a uma `layer class` com comportamento dinâmico
especial (`border`, `roof`).
_Avoid_: static — o campo `type: "static"` do pipeline não implica bakeável (um item estático pode
ainda ser `roof`, `border` ou marcado como interativo)

**Bakedgroup**:
Um tipo de layer do `map.json` que contém imagens de cenário pré-renderizadas, uma por combinação
de `(tileY, layerClass)`, como alternativa a instanciar sprites individuais em runtime.

**Interactive** (item interativo):
Um objeto do mapa cuja lógica de jogo pode alterar seu estado (container, item coletável, porta),
mesmo que hoje pareça visualmente estático. Nunca é `bakeable`, independente de `layer class`.

**Floor** (z-level):
Um dos planos verticais de um `hunt spot` (ex. z=7 chão, z=8 masmorra embaixo). Cada floor tem
seu próprio conjunto independente de `layer classes`; `(tileX, tileY)` significa a mesma coluna
física em qualquer floor do mesmo mapa (bounds são a união de todos os floors, não uma bounding
box por floor). Ver ADR 0002.

**`defaultZ`**:
O floor que deve renderizar por padrão ao carregar um `hunt spot` — `7` se existir, senão o
menor z presente no mapa.

**Floor transition** (tile de transição):
Um tile (escada/buraco) identificado pela flag derivada `isFloorTransition` em
`objectDefs[id].flags`, calculada a partir de uma combinação de flags do OTBM (não existe flag
nativa pra isso — ver ADR 0002). Pisar num tile assim muda o floor ativo do jogador.
