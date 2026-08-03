# 08 — `tibia-idle`: `Hunt.mapId`/rota `/hunt/:huntId`/`GameLayout` aceitam o novo formato de id

**What to build:** Repo `tibia-idle`. `Hunt.mapId` passa a ser `ROOK-HUNT-0002` (com o segmento de
tipo) em vez de `ROOK-0002` — qualquer lugar que hoje assume o formato antigo (parsing, exibição,
comparação) precisa ser conferido. A rota `/hunt/:huntId` e `GameLayout`
(`resolveSelectedHunt$`/`HuntService.getHuntById`) continuam funcionando normalmente — o id só muda
de forma, o mecanismo de lookup por id não muda.

**Blocked by:** 06 (`tibia-idle-otbm`) — precisa do `db.json` já com os ids novos.

- [ ] `Hunt` (tipo TS) e qualquer lugar que documenta/comenta o formato de `mapId` refletem o formato
      novo (`CIDADE-TIPO-SEQ`, ex: `ROOK-HUNT-0002`)
- [ ] `HuntService.getHuntById`/`MonsterService.getMonstersByMapId`/`LootService.getLootByMapId`
      continuam funcionando sem mudança de assinatura — só o valor do id muda de forma
- [ ] Rota `/hunt/:huntId` + `GameLayout` carregam um hunt normalmente com o novo formato de id
- [ ] Nenhum lugar do código faz parsing/assume que `mapId` não tem hífen extra além do padrão
      `CIDADE-NNNN` antigo (grep por regex/`.split('-')` em cima de `mapId` que dependa do formato
      antigo)
- [ ] Regressão: entrar numa hunt pelo botão/URL direta funciona igual antes
