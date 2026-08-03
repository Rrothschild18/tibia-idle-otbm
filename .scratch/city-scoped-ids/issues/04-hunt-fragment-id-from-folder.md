# 04 — `hunt_fragment.py`/`build_hunt_fragment.py`: id sempre da pasta, `--map-id` obrigatório, `--edit`

**What to build:** Remove `_id_prefix_for_map`/`next_map_id` (auto-numeração/adivinhação de prefixo)
inteiramente — o id de um hunt nunca mais é inventado pelo pipeline, só lido do nome da pasta
(`ROOK-HUNT-0002_bears-rookguard` → id `ROOK-HUNT-0002`, tudo antes do primeiro `_`).
`build_hunt_fragment.py` mantém `--map-id` **obrigatório** (não vira opcional/removido) — o script
compara o id extraído da pasta com o valor passado em `--map-id`; diferença é erro, citando os dois
valores. Sem `--edit`, gravar um `mapId` que já existe em `db.json` é erro
("ID do mapa já existe — use --edit se a intenção é atualizar"); com `--edit`, atualiza
normalmente (mesma lógica de merge mecânico-vs-curado já existente).

**Blocked by:** 02 (build_map.js já precisa reconhecer a nova estrutura de pastas pra essa etapa
rodar contra o output certo).

- [ ] `_id_prefix_for_map`/`next_map_id` removidos — nenhuma lógica de auto-numeração resta no
      código
- [ ] Id do hunt extraído do nome da pasta (`<ID>_nome` → `<ID>`), usado pra `monsters`/`loot`/`hunts`
      igual já fazia antes
- [ ] `--map-id` continua obrigatório; diverge do id da pasta → erro citando os dois valores
      explicitamente (ex: `"--map-id ROOK-HUNT-0013 não bate com o id da pasta (ROOK-HUNT-0014)"`)
- [ ] Sem `--edit`: `mapId` já existente em `db.json` → erro, nada é escrito
- [ ] Com `--edit`: `mapId` já existente é atualizado normalmente (mecânico sempre upsert, curado
      nunca sobrescrito — mesmo comportamento de hoje, só que atrás do novo gate)
- [ ] Coberto por teste: pasta/`--map-id` batendo (sucesso), divergindo (erro), id novo sem `--edit`
      (sucesso, é criação), id existente sem `--edit` (erro), id existente com `--edit` (sucesso)
