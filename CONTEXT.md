# Tibia Idle — Pipeline de Mapas e Renderização

Glossário do pipeline de conversão de mapas (OTBM → Phaser) e dos conceitos de renderização em
runtime que ele alimenta.

## Language

**Hunt spot**:
Área delimitada que o jogo carrega como um mapa — não o mundo completo do Tibia. É a unidade de
escopo do pipeline do extractor e do runtime.

**City** (`city`, ex: `ROOK`, `TEST`):
A pasta-pai física de um mapa sob `extractor/maps/<CIDADE>/`, `ready-maps/<CIDADE>/` ou
`full-maps/<CIDADE>/` — nunca adivinhada do nome do mapa. `full-maps/<CIDADE>/` guarda o `.otbm` da
cidade e o `respawn.json`; ele **não produz mapa** — o travel-graph consome a tabela de flags
versionada em `extractor/appearance-flags/<CIDADE>.json`, nunca um `map.json`. Todo hunt/location no catálogo do
`tibia-idle` carrega um campo `city` derivado do próprio id (primeiro segmento), nunca digitado à
mão. `TEST` é uma cidade fictícia pros mapas de teste/descartáveis (mesmo mecanismo, sem sistema de
tag separado) — ver `.scratch/city-scoped-ids/spec.md`.
_Avoid_: region (nome antigo, ambíguo com "região" no sentido geográfico do jogo em si)

**Map id** (`mapId`/`Location.id`, ex: `ROOK-HUNT-0002`):
Formato `CIDADE-TIPO-SEQ`, escolhido à mão (digitado na sign do editor de mapas, copiado pro nome
da pasta) — nunca auto-numerado pelo pipeline. Idêntico entre a coleção `hunts` e a location de
entrada correspondente no travel-graph; não há mais duas strings pra reconciliar.

**Fragmento** (`db-fragment.json`) e **export**:
Duas coisas distintas, e confundi-las é o que faz alguém achar que rodar o extractor mexeu no
back-end. O **fragmento** é a saída local de um CLI (`ready-maps/<CIDADE>/<pasta>/` pros hunts,
`full-maps/<CIDADE>/` pro travel-graph), gitignorada, feita pra revisão — gerar fragmento nunca
toca em nada fora de `extractor/`. O **export** (`--export`) é o passo separado e explícito que
escreve no `tibia-idle`. Ver `content_export.py` e a tabela em `extractor/README.md`.
_Avoid_: `--write-db` (flag antigo) e "escrever no db.json" — ver **Catálogo**

**Catálogo** (`catalog-source.json`):
`apps/tibia-idle-api/content/catalog-source.json` no `tibia-idle`: as três coleções que o extractor
emite e que viram **linha no Postgres** (`hunts`, `locations`, `travelGraph`). Ninguém o lê em
runtime — `import-content` valida com Zod e grava, e `nx run db:reset` chama isso. Não confundir com
`content/hunts/` (`loot.json`, `respawn/<HUNT-ID>.json`, `hunts.json`), que é o conteúdo lido **do
disco em runtime**: a linha entre os dois é a da ADR-0015 — virou coluna o que a tela filtra e
ordena, ficou em arquivo o que se carrega inteiro e não responde a `WHERE`.
_Avoid_: `db.json` (era o destino único, servido por `json-server`; o app foi apagado na fatia 1.8
e as coleções se separaram por como o back-end lê cada uma)

**Merge mecânico** vs. **curado**:
O que um re-export pode sobrescrever sem perguntar, e o que não pode. **Mecânico** é tudo derivado
do mapa (posição, `shop`, `tileCount`, `loot`, respawn): sempre reescrito, porque regenerar dá o
mesmo valor. **Curado** é decisão humana que o mapa não sabe (`displayName`, `huntId`, `name`,
`label`, `portrait`, `seed`, `startPosition`): nunca sobrescrito. O corte não é por coleção, é por
campo — e cada coleção resolve isso do jeito que cabe a ela: `hunts` é append-only (a entrada
inteira fica intacta), `locations` faz merge campo a campo, e `travelGraph` é substituído por
cidade, porque não há nada curado numa aresta. A **tabela de flags por appearance**
(`extractor/appearance-flags/<CIDADE>.json`) aplica o mesmo corte em dois arquivos em vez de dois
campos: o derivado é sobrescrito inteiro a cada regeneração, e o `<CIDADE>.overrides.json` ao lado
nunca é tocado e sempre vence no merge.

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
jogador ficaram de fora sem que ninguém soubesse qual eixo os excluiu. Hoje ela se chama
`has_non_creature_axis` e diz o eixo.

**Player outfit sheet** (sheet de outfit de jogador):
O PNG+JSON que `bake_player_outfit_sheet.py` produz por outfit de jogador, em
`atlases/player-outfits/`. 216 frames numa grade de 24 colunas — uma linha por fase —, com chave
de frame explícita (`128_mask_a0_north_2`) e um bloco `axes` declarando os eixos. É outro formato
que o atlas de criatura de `bake_outfit_atlas.py`, e os dois bakers se distinguem pela presença
do `axes`, não por lista de id.
_Avoid_: assar outfit de jogador com o baker de criatura — ele empacota numa linha só e não
conhece addon nem camada.

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

**Approach tile** (tile de aproximação) e **NPC reach** (alcance):
O tile de onde se **chega** numa location — não o tile dela. Pra tudo que é marcado por placa, os
dois são o mesmo tile e não há o que discutir. Pra **NPC** não: balconista fica atrás de um balcão
`unpass`, num bolsão que ninguém pisa, então o jogador para do lado de fora e negocia atravessando o
balcão. O `NPC reach` é até quantos tiles dele isso ainda conta como ter chegado (default 3). Cada
tile de aproximação custa a própria distância até o NPC, nunca 0 — é o que impede o alcance de
encurtar as distâncias de um NPC que está em rua aberta. Essa distância é a **única** parte medida
em linha reta (Chebyshev, atravessando parede); todo o resto do trajeto é caminho andado.
_Avoid_: "raio de trade" (sugere regra de combate/jogo; isto é só como o grafo representa chegada)

**Nó sem entrada** (rejeição):
Uma location que ninguém consegue alcançar viajando, e que por isso **não entra no fragmento** — sai
num relatório com o que existe dela. Três casos, e a diferença é o que cada um tem pra ser
consertado: POI com coordenada e sem aresta (a placa existe, o tile é que está ilhado), id citado
numa aresta que não é POI (não tem coordenada nenhuma — é id escrito errado), e hunt sem POI (o mapa
existe em `maps/`, mas ninguém marcou a entrada; o `startPosition` dela é posição *dentro* do mapa
da hunt, não coordenada de mundo). Emitir um destino inalcançável custa mais caro que rejeitá-lo:
vira hunt que o jogador não consegue jogar, sem rastro do porquê.
