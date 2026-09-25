# Transições de andar no `map.json` v6

Lado extractor da feature `hunt-multi-andar`. A spec completa, com o porquê e o resto
dos tickets, vive no repo irmão:
`tibia-idle.worktrees/hunt-multi-andar/.scratch/hunt-multi-andar/spec.md`.

## O que sai daqui

O `map.json` v6 passa a carregar as arestas de mudança de andar já resolvidas:

```json
"transitions": [[15,16,11, 15,17,10], [16,17,10, 16,18,9]]
```

Tile local do bundle, não-direcionado, só com as duas pontas caminháveis. O consumidor é
o A* do gerador de rota no `tibia-idle`, que não sabe o que é escada — ele só segue
aresta.

A regra já existe e roda: `extract_tile_flags`, `FLOORCHANGE_DELTAS` e
`build_walkable_graph` em `extractor/scripts/travel_graph.py`, que alimentam o grafo de
viagem. O trabalho é **expor**, não descobrir. Reusar, não reimplementar.

## Duas correções de geometria entram junto

**`southalt` / `eastalt` são 2 tiles, não 1.** São escadas de largura dupla.
`Tile::queryDestination` do Canary (`src/items/tile.cpp:1018-1026`); no TFS 0.3.7 a
mesma família se chama `*_EX` (`src/tile.cpp:817-843`), e `southex`/`eastex` são aliases
literais em `TFS-0.2` (`items.cpp:667-674`). Afeta `855`, `856`, `7888`, `20255`,
`20256`; destes só `7888` existe no ROOK. Nenhum aparece em mapa de hunt — é correção
para o grafo de viagem e para a próxima cidade.

**A ladder sobe para o sul.** Hoje `build_walkable_graph` liga `isFloorTransition` ao
mesmo `(x,y)` em `z-1` e `z+1`; as duas pontas estão erradas.

```
isFloorTransition AND type="ladder"   →  (x, y+1, z-1)
isFloorTransition AND NOT ladder      →  (x, y,   z+1)
```

`<attribute key="type" value="ladder"/>` marca 20 ids no `items.xml` vendorizado, entre
eles `1948` e `5542` — os únicos dois `isFloorTransition` presentes em qualquer mapa de
hunt. Fonte: `data/scripts/actions/items/ladder_up.lua:5-18` →
`data/libs/functions/position.lua:22-50` (`z -= 1`, depois
`directionOffset[DIRECTION_SOUTH]` = `{x=0, y=1}`, com varredura de fallback).

Esta segunda correção não é opcional: as duas ladders são 100% das transições dos mapas
de hunt.

## Nota sobre a ADR 0002

A premissa de que a direção de `isFloorTransition` não é derivável vale para a **flag**
— o `appearances.dat` do cliente carrega só um booleano (`opentibiabr/otclient`,
`thingtype.h:138`, `tile.cpp:529`). Mas é derivável do `items.xml`, via `type="ladder"`.
Atualizar a ADR.

O grafo continua **não-direcionado**, e agora por decisão registrada: o Orcs Fortress
não tem um único `floorchange` `down`, então direcionado ele perderia 7 dos 13 spawns
por buraco de extração, não por desenho de mapa.

## Critério de pronto

- `ROOK-HUNT-0017` sai com aresta z11↔z10 de `(15,16)` para `(15,17)`, e o `down` de
  z10, z9 e z8 como aresta para `(x, y, z+1)`.
- `ROOK-HUNT-0009` sai com as três rope-ladders (z9 em `(14,26)` e `(25,26)`, z10 em
  `(19,12)`) mais `north`×2 em z9, `north`×2 em z8 e `east`×15 em z10.
- Mapa de andar único sai com `transitions: []`.
- O `travelGraph` regerado não perde aresta.
