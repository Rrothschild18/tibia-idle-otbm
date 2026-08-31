# 02 — `monster.corpse` + cadeia de decay do Canary local, anexados ao `monster-loot.json`

**What to build:** Para cada monstro já processado por
`build_monster_loot_index.py`, capturar o item de corpse (`monster.corpse = N`
no `.lua`) e resolver a cadeia de decay a partir do `items.xml` do Canary
local (`decayTo`/`duration` por item, seguindo até `decayTo` ausente/`0`).
Anexar o resultado como uma chave nova `"corpse"` em cada entrada de
`monster-loot.json`, sem alterar `loot`/`issues`.

**Blocked by:** Nenhum — pode começar imediatamente

**Status:** ready-for-agent

- [x] ~~Confirmar o casing exato dos atributos em `items.xml`~~ — já
      confirmado nesta spec (2026-08-30): é `decayTo` (camelCase) e
      `duration`, verificado ao vivo contra
      `C:\canary-3.2.1\data\items\items.xml` (itens 5964 e 4022). Pode
      implementar direto com esses nomes.
- [ ] Regex novo em `monster_loot.py` (ao lado de `_MONSTER_NAME_RE`/
      `_LOOT_BLOCK_START_RE`) que captura `monster.corpse = N` do mesmo `text`
      já lido em `parse_monster_loot_lua()`
- [ ] `load_items_index()` (ou função irmã que reaproveita o mesmo `ET.parse`)
      passa a também indexar, por item id, `decayTo`/`durationSeconds` a
      partir dos `<attribute key="..." value="..."/>` filhos de cada `<item>`
- [ ] Função que resolve a cadeia a partir do `corpse` do monstro:
      `id → decayTo → decayTo → ...` até `decayTo` ausente ou `0`, retornando
      `[{itemId, durationSeconds}, ...]` em ordem. Guarda de profundidade
      máxima contra ciclo malformado no dado de origem (não trava, loga e
      corta)
- [ ] `build_monster_loot()` anexa `"corpse": {"itemId": N, "stages": [...]}`
      por monstro (omitir a chave, não escrever `null`, para monstro sem
      `monster.corpse` definido no Lua)
- [ ] `monster-loot.json` regenerado e comparado antes/depois — `loot`/
      `issues` de cada entrada permanecem byte-a-byte iguais, só a chave nova
      aparece
- [ ] Conferir pelo menos 3 monstros manualmente contra o `.lua`/`items.xml`
      de origem (ex.: um caso de 1 estágio como rato, um caso de cadeia longa
      como humano) para validar que a cadeia resolvida bate com o dado real

## Comments

Design fechado numa sessão de `/grilling` (2026-08-30). Alternativa recusada:
esquema genérico de decay (N estágios fixos, mesmos tempos pra todo monstro) —
descartada porque a cadeia real varia demais por monstro (1 estágio vs. 5+) e
o pipeline já sabe ler do Canary local pra loot, então puxar de lá é mais
barato e mais fiel ao mesmo tempo.
