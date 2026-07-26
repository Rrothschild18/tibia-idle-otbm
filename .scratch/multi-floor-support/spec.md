# Suporte a múltiplos floors (z-levels) — extractor

## Contexto

O mapa `skeletons-rookguard` foi exportado do Canary's Map Editor com **3 floors reais** (z=7:
1848 tiles / z=8: 1812 tiles, com **100% de overlap de (x,y)** com o z=7 — uma masmorra inteira
embaixo do chão / z=9: 50 tiles). `extractor/scripts/build_phaser_map.py` nunca lê `feature.z` do
dump do OTBM — tiles e itens são indexados só por `(x, y)` em `ground_tiles`/`raw_item_stacks`,
então tiles/itens de floors diferentes na mesma coluna colidem e se misturam num único mapa
achatado. Não é um bug visual do Phaser — o extractor descarta a dimensão z antes de gerar o
`map.json`.

Confirmado que isso afeta 3 dos 8 mapas hoje: `skeletons-rookguard` (3 floors), `rats-sewers`
(2 floors, 87% overlap) e `troll-rookguard` (1 tile solto em z=3, ruído/edge case). Os outros 5
mapas são genuinamente single-floor (z=7) e continuam funcionando sem mudança de comportamento.

Esta é a metade **extractor** de um esforço maior que também toca o front-end Phaser
(repo separado `tibia-idle/tibia-idle`, mesma feature slug `multi-floor-support` lá). Os
tickets deste repo produzem os dados floor-aware que o front-end consome.

## Decisões de design

1. **Espaço de coordenadas compartilhado entre floors**: `bounds`/`width`/`height` continuam
   como união de todos os floors, para que `(tileX,tileY)` signifique a mesma coluna física em
   qualquer floor — replica o comportamento real do Tibia (trocar de floor preserva x,y) e evita
   precisar de metadata de "destino" por escada.
2. **Sem versionar o `version` do map.json**: a mudança é estrutural/aditiva (`layers` vira
   `floors: Record<string, {z, layers}>` + `defaultZ`), não um bump de schema — evita colidir com
   a confusão pré-existente de `PHASER_INTEGRATION.md` já se chamar "v3" enquanto o campo
   `version` do JSON é `2`.
3. **Detecção de tile de transição (escada/buraco)**: Tibia não tem uma flag genérica de OTBM
   pra isso — só a heurística já documentada em `extractor/SPRITE_METADATA.md`
   (`bank + fullbank + usable + forceuse + unmove + automap`, ex. IDs 421/12202). O extractor
   hoje descarta `usable`/`forceuse` antes de chegarem no `objectDefs`; isso precisa mudar, e o
   resultado vira uma flag derivada `isFloorTransition` (mesmo padrão que `isRoof` já usa hoje).
4. **Mapas single-floor não podem regredir**: viram só `floors: {"7": {...}}` — sem
   special-casing no front.

## Referência

Plano completo (extractor + front-end) discutido na sessão que originou estes tickets; ver
`docs/adr/0002-map-json-floors-e-defaultz.md` (a ser criado pelo ticket 01) para o registro
formal das decisões acima.
