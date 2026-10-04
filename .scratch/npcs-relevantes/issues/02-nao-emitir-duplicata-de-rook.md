Status: ready-for-agent

# 02 — Extractor para de emitir duplicata de Rookgaard

**What to build:** As 25 locations `THAIS-NPC-*` que são cópia posicional de um
`ROOK-NPC-*` deixam de sair do fragmento, e as **2.364 arestas** que as tocam
saem com elas.

## O que está acontecendo

O corte do mapa de Thais pegou a ilha de Rookgaard inteira, com coordenada de
mundo preservada. O resultado é que os 25 NPCs de Rook existem duas vezes, na mesma posição: `ROOK-NPC-obi` **e** `THAIS-NPC-obi`, `ROOK-NPC-cipfried`
**e** `THAIS-NPC-cipfried`, e assim por diante. **11 das duplicatas têm loja**,
então nenhum filtro por relevância as pega.

O `tibia-idle` **já resolve isso no import**: `findRookDuplicateNpcs`, em
`libs/models/content/src/lib/import-source.model.ts`, casa NPC por slug +
posição exata, descarta a cópia que não é de ROOK e devolve um
`DiscardedDuplicateNpc` no resultado do gate. Ou seja: o extractor gastava 2.364
arestas de BFS gerando dado que o back-end joga fora, e a regra de qual cópia
ganha já está decidida — ROOK ganha.

Esta ticket move o mesmo corte para onde o dado nasce.

## A regra

Um NPC de cidade que não é ROOK, cujo **slug e posição (x, y, z)** coincidem com
um NPC de ROOK, não vira location. Slug **e** posição, não só o nome: dois NPCs
homônimos em cidades diferentes (`Junkar`, `Ferryman Kamil`) são NPCs diferentes
e precisam dos dois nós.

O lado de ROOK é lido do `ROOK-npc.xml`, não do fragmento que está sendo gerado —
rodar só a cidade de Thais tem que cortar as duplicatas igual.

**Não** mexa na máscara de subárea que trouxe a ilha para dentro do corte de
Thais. Isso é bug de `cut_city.py` e fatia própria; aqui o escopo é parar de
emitir.

**Blocked by:** nada.

- [ ] Rodar o fragmento de THAIS deixa de emitir os 25 NPCs que são cópia
      posicional de um `ROOK-NPC-*`
- [ ] As arestas que tocavam as duplicatas não existem mais no fragmento
- [ ] Rodar só THAIS (sem ROOK no mesmo comando) corta as mesmas 25
- [ ] Um homônimo em posição diferente **não** é cortado — teste com `Junkar`
- [ ] O fragmento de ROOK sai idêntico ao de antes
