# 02 — Detectar tiles de transição de floor (escada/buraco)

**What to build:** Itens do mapa que funcionam como escada/buraco (transição entre floors) ficam
identificáveis no `map.json` gerado, para que o front-end possa detectar quando o jogador pisa
num deles. Não existe flag genérica de OTBM pra isso — a heurística é `usable + forceuse +
unmove + automap` (validada contra os 8 mapas existentes: combina com exatamente 4 appearance
IDs — 386, 421, 1948, 12202 — todos escadas/buracos reais, incluindo a escada de
`skeletons-rookguard`, e nenhum item não-relacionado. Ver ADR 0002 pra como esse conjunto de
flags foi escolhido, incluindo por que `bank` — presente na heurística originalmente documentada
em `extractor/SPRITE_METADATA.md` — acabou não entrando: sem ele a escada real de
`skeletons-rookguard`, ID 1948, não era detectada).

**Blocked by:** 01 (mesmo arquivo/função, e reusa a regeneração dos 8 mapas feita ali).

**Status:** ready-for-agent

- [ ] `analyze_item()` (`extractor/scripts/build_phaser_map.py`) passa a ler `usable` e
      `forceuse` de `flags` (hoje descartados) e preservá-los em `info["flags"]`
- [ ] `analyze_item()` deriva `is_floor_transition = has_usable and has_forceuse and has_unmove
      and has_automap` (sem exigir `has_bank` — ver ADR 0002 pra evidência de por que isso ficou
      de fora) (mesmo padrão de derivação já usado para `is_roof`) e expõe como
      `isFloorTransition` em `info["flags"]`
- [ ] `_build_object_defs()` não precisa mudar — já propaga qualquer flag truthy de
      `analysis["flags"]` para `objectDefs[id].flags` automaticamente
- [ ] `extractor/PHASER_MONSTERS.md` ganha um parágrafo explicando `respawn.spawns[i].worldZ`
      (hoje o campo aparece no JSON de exemplo mas não é mencionado na prosa) e como ele se
      relaciona com o floor ativo no front-end
- [ ] `CONTEXT.md` ganha os termos de glossário: floor / z-level, floor transition, `defaultZ`
- [ ] `node extractor/scripts/build_map.js --all` rodado novamente após a mudança
- [ ] Verificação: grep no `objectDefs` regerado dos 8 mapas confirma `flags.isFloorTransition
      === true` nos 4 IDs reais — 421/12202 (`larva-ankrah`), 386 (`troll-rookguard`) e,
      principalmente, **1948 em `skeletons-rookguard`** (o mapa de 3 floors que motivou o
      ticket) — e em nenhum outro item desses mapas
- [ ] Verificação: `python item_classifier.py --dump-unknown <map.json regenerado>` não mostra
      regressão na classificação de layer de nenhum item (a nova flag é ortogonal a `layerClass`)

## Comments

Implementado e commitado em `4827601` (junto com o ticket 01). A heurística originalmente
especificada (`bank + usable + forceuse + unmove + automap`) foi testada contra os itens
realmente usados nos 8 mapas existentes e **não detectava a escada real de
`skeletons-rookguard`** (appearance ID 1948 — o mapa de 3 floors que motivou este ticket).
Investigação encontrou que `1948` tem `usable + forceuse + unmove + automap` mas não tem `bank`;
checando todo item dos 8 mapas, esse conjunto de 4 flags (sem `bank`) combina com exatamente 386,
421, 1948 e 12202 — todas escadas/buracos reais, nenhum falso positivo. A heurística final
implementada dropa a exigência de `bank`. Detalhes e a evidência completa em
`docs/adr/0002-map-json-floors-e-defaultz.md`.
