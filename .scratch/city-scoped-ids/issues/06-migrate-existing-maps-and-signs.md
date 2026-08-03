# 06 — Migrar os 20 mapas existentes + re-marcar as signs no `rook-full.otbm`

**What to build:** Reorganização física dos dados hoje existentes, seguindo a convenção fechada nos
tickets 01-05:

- Os 20 mapas em `extractor/maps/` (flat) movem para `extractor/maps/ROOK/` (16 mapas Rookgaard reais)
  ou `extractor/maps/TEST/` (`dragon-darashia`, `grim-reaper`, `larva-ankrah`, `sea-serpent`),
  renomeados pro formato `<CIDADE-TIPO-SEQ>_nome-descritivo/` — os 9 hunts já com location resolvida
  reaproveitam a sequência que já têm (`ROOK-0001` → pasta `ROOK-HUNT-0001_...`); os demais recebem
  um id novo escolhido à mão, seguindo a ordem que já existe.
- `extractor/full-maps/rook-full/` move para `extractor/full-maps/ROOK/`, arquivos renomeados
  (`ROOK.otbm`, `ROOK-house.xml`, etc).
- As 12 signs já colocadas no `rook-full.otbm` são editadas à mão (no editor de mapa) pra bater com
  os novos ids de pasta — inclui corrigir a duplicata (`ROOK-HUNT-0006` colocada duas vezes) e o
  typo de 5 dígitos (`ROOK-HUNT-00015`) encontrados durante os testes da feature de travel time.
- Fragmentos são regenerados via `build_hunt_fragment.py --edit`/`build_travel_fragment.py --edit`
  pra cada mapa reorganizado, e o `db.json` do `tibia-idle` é reescrito por completo pras coleções
  afetadas (`hunts`, `monsters`, `loot`, `locations`, `travelGraph`) — regenerar e substituir, não
  merge incremental cuidadoso.

**Blocked by:** 02, 03, 04, 05 (a migração só faz sentido depois que o pipeline novo existe pra
gerar os fragmentos corretos).

- [ ] Todos os 20 mapas estão sob `maps/ROOK/` ou `maps/TEST/`, cada um com o nome de pasta no
      formato novo
- [ ] `full-maps/rook-full/` não existe mais — só `full-maps/ROOK/`
- [ ] As signs do `rook-full.otbm` batem exatamente com os novos nomes de pasta (sem divergência,
      sem duplicata, sem typo de dígitos)
- [ ] `node build_map.js --all` roda de ponta a ponta sem erro contra a estrutura nova
- [ ] `db.json` do `tibia-idle` tem `hunts`/`monsters`/`loot`/`locations`/`travelGraph` regenerados
      com os ids novos — os 9 hunts já resolvidos aparecem com `mapId` no formato `ROOK-HUNT-000N`
- [ ] `displayName`/outros campos curados (não derivados do id) sobrevivem à migração sem perda
