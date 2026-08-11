# Tibia Idle — Pipeline de Mapas e Renderização

Glossário do pipeline de conversão de mapas (OTBM → Phaser) e dos conceitos de renderização em
runtime que ele alimenta.

## Language

**Hunt spot**:
Área delimitada que o jogo carrega como um mapa — não o mundo completo do Tibia. É a unidade de
escopo do pipeline do extractor e do runtime.

**City** (`city`, ex: `ROOK`, `TEST`):
A pasta-pai física de um mapa sob `extractor/maps/<CIDADE>/`, `ready-maps/<CIDADE>/` ou
`full-maps/<CIDADE>/` — nunca adivinhada do nome do mapa. Todo hunt/location no `db.json` do
`tibia-idle` carrega um campo `city` derivado do próprio id (primeiro segmento), nunca digitado à
mão. `TEST` é uma cidade fictícia pros mapas de teste/descartáveis (mesmo mecanismo, sem sistema de
tag separado) — ver `.scratch/city-scoped-ids/spec.md`.
_Avoid_: region (nome antigo, ambíguo com "região" no sentido geográfico do jogo em si)

**Map id** (`mapId`/`Location.id`, ex: `ROOK-HUNT-0002`):
Formato `CIDADE-TIPO-SEQ`, escolhido à mão (digitado na sign do editor de mapas, copiado pro nome
da pasta) — nunca auto-numerado pelo pipeline. Idêntico entre a coleção `hunts` e a location de
entrada correspondente no travel-graph; não há mais duas strings pra reconciliar.

**Draw slot** (slot de desenho):
Uma das duas únicas categorias de renderização de um objeto do mapa: **ground**, quando a aparência
carrega a flag `bank` — no máximo um por tile, desenhado primeiro — ou **item**, todo o resto, que
entra na `stack order` da tile. Não diz nada sobre passagem: um `ground` pode ser intransponível
(quem responde por isso é `unpass`), nem sobre tamanho de sprite.
_Avoid_: layer class (modelo anterior, com oito papéis, que misturava desenho, passagem e footprint
numa enum só)

**Stack order** (ordem de pilha):
A posição de um objeto dentro da sua tile, e a única coisa que determina quem desenha na frente de
quem dentro dela: o `ground` primeiro, depois os itens de fundo ordenados por `top order` crescente,
depois os demais em ordem de inserção. Criaturas desenham por último, sempre depois de todo item da
tile.

**Top order** (`topOrder`):
A ordem relativa de um item de fundo dentro da `stack order`, derivada diretamente das flags do
appearances: `clip` = 1, `bottom` = 2, `top` = 3. Qualquer uma das três marca o item como de fundo.
_Avoid_: depth offset (modelo anterior, em que a ordem vinha de uma tabela de constantes por layer
class em vez de sair da flag do próprio item)

**Paint order** (ordem de pintor):
A ordem global de desenho de um mapa: andar, depois **anti-diagonal** (`tileX + tileY` crescente, e
dentro dela `tileX` crescente), depois `stack order`. A profundidade de um sprite é consequência
dessa ordem — nunca uma constante atribuída por categoria. O eixo é obrigatório, não estético:
sprites ancoram no canto inferior-direito e se estendem para cima e para a esquerda, então só uma
varredura que avança para baixo-direita garante que o que um sprite cobre já foi pintado. É a ordem
do cliente; o RME varre por coluna e concorda com ela em todo par que pode se sobrepor.
_Avoid_: z-index; ordem por linha (`tileY`) — foi o que se tentou até a emenda da ADR 0012 do
`tibia-idle`, e põe a parede de oeste por cima da tile a leste dela

**Elevation** (elevação):
O deslocamento em pixels que um item aplica aos itens desenhados **depois** dele na mesma tile,
vindo da flag `height` do appearances. Acumula ao longo da `stack order`, o que faz uma pilha
parecer pilha. Diferente de `shift`, que desloca só o próprio sprite e não acumula.

**Shift** (deslocamento):
O deslocamento em pixels (`{x, y}`) do sprite de uma aparência dentro do próprio quadrado, vindo da
flag `shift` do appearances. É o que põe objeto pequeno no lugar certo da tile. Ao contrário de
`elevation`, não acumula e não afeta nenhum outro item da pilha.

**Interactive** (item interativo):
Um objeto do mapa cuja lógica de jogo pode alterar seu estado (container, item coletável, porta),
mesmo que hoje pareça visualmente estático — independente de onde ele caia na `stack order`.
_Avoid_: static — o campo `type: "static"` do pipeline diz só que a aparência tem um sprite fixo,
não que a lógica de jogo não mexe nela

**Floor** (z-level):
Um dos planos verticais de um `hunt spot` (ex. z=7 chão, z=8 masmorra embaixo). Cada floor tem seu
próprio conjunto independente de tiles; `(tileX, tileY)` significa a mesma coluna física em qualquer
floor do mesmo mapa (bounds são a união de todos os floors, não uma bounding box por floor). Ver
ADR 0002.

**`defaultZ`**:
O floor que deve renderizar por padrão ao carregar um `hunt spot` — `7` se existir, senão o
menor z presente no mapa.

**Pattern axis** (eixo de padrão):
Um dos quatro eixos ao longo dos quais uma appearance guarda variantes da mesma sprite —
`pattern_width`, `pattern_height`, `pattern_depth` e `layers` — mais o eixo do tempo (`fase`). O
que cada um *significa* depende do que a appearance é: num item são posição no mundo (ver ADR 0014
do `tibia-idle`); num outfit são direção, addon, montaria e camada. A lei de índice é a mesma nos
dois casos, e é ela que diz que os frames vêm **intercalados por direção, não agrupados** — ver
`extractor/OUTFIT_SPRITES_DOCUMENTATION.md`.
_Avoid_: "quantidade de sprites" como critério de classificação — foi o que
`outfit_has_addons_or_mounts` usou pra decidir o que extrair, e é por isso que os 22 outfits de
jogador ficaram de fora sem que ninguém soubesse qual eixo os excluiu.

**Outfit layer** (camada de outfit):
Uma das duas metades de cada sprite de outfit de jogador: a **base**, em tons de cinza, e a
**máscara**, quatro cores chapadas que dizem a que região do corpo cada pixel pertence. Cor não é
sprite — é multiplicação da base pela cor da região, feita no cliente. Criaturas têm uma camada só
e não têm o que tingir.

**Floor transition** (tile de transição):
Um tile (escada/buraco) identificado pela flag derivada `isFloorTransition` nas flags da aparência,
calculada a partir de uma combinação de flags do OTBM (não existe flag nativa pra isso — ver
ADR 0002). Pisar num tile assim muda o floor ativo do jogador. É a única flag derivada que sobrevive
no formato novo: as outras duas (`isRoof`, `hookDirection`) respondiam "onde isso desenha?", que
agora é a `stack order` quem responde.
