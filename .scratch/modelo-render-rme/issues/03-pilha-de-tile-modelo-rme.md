# 03 — Montar a pilha de tile pelo modelo do editor

**What to build:** O pipeline passa a produzir, para cada tile do mapa, um `draw slot` de ground e
uma `stack order` — no lugar de classificar cada item em um dos oito papéis de renderização
inventados.

A regra é derivada inteiramente das flags do appearances, sem heurística e sem lista de id escrita à
mão: quem tem a flag de banco é ground e ocupa o slot único da tile; todo o resto entra na pilha,
com os itens de fundo ordenados por `top order` e os demais em ordem de inserção.

Isto encerra a detecção de parede por combinação de flags, as listas manuais de id de borda e
telhado, e a noção de que "não é caminhável" implica "não é chão".

**Blocked by:** None — can start immediately.

**Status:** resolved

- [x] Dada uma tile com ground, bordas e objetos, o pipeline produz a pilha na ordem que o editor
      produziria para a mesma tile
- [x] A flag de passagem deixa de influenciar em que categoria de desenho um item cai
- [x] A classificação manual por lista de id não é mais consultada por nenhuma regra de desenho
- [x] Existem testes cobrindo: tile só com ground; tile com itens de fundo de `top order`
      diferentes; tile com item de fundo e item comum; tile cujo chão é intransponível
- [x] As duas aparências que hoje formam a camada "Roof" caem no slot de ground

## Answer

A regra vive em `extractor/scripts/tile_stack.py` — puro, sem I/O, 3 funções: `draw_slot` (flag
`bank`), `top_order` (`clip`=1, `bottom`=2, `top`=3) e `build_tile_stack`. Coberto por
`extractor/tests/test_tile_stack.py` (18 testes), incluindo os quatro casos pedidos e as três
aparências que formavam a camada `Roof` (1128, 4427, 1316) caindo no slot de ground.

Duas medições nos 42 dumps de `raw-maps/` que travam a regra:

- **Todo `tileid` do OTBM carrega `bank`** (583.610 tiles, zero exceções) — o slot de chão do OTBM e
  a flag `bank` são a mesma coisa, então derivar o draw slot da flag não perde nada.
- **Nenhuma tile tem mais de um `bank`.** O modelo trata o caso mesmo assim (o extra volta pra
  pilha, no grupo de inserção) pra ser total, não porque acontece.

**Sobre "a classificação manual por lista de id não é mais consultada":** vale no caminho novo —
nem `tile_stack.py` nem `map_v6.py` importam `item_classifier.py`. O `build_phaser_map.py` ainda o
chama, mas só no emissor v5, que existe apenas até o Phaser migrar (estratégia de migração da spec) e
morre junto com ele. Não há regra de desenho do modelo novo que consulte lista de id.
