# 04 — Unificar fragmento e mesclar no db.json

**What to build:** Uma única CLI que junta a saída dos tickets 02 e 03 (POIs por placa + NPCs) num só fragmento `{locations, travelGraph}`, seguindo o mesmo formato de tooling já existente (`build_hunt_fragment.py`): sem `--write-db`, escreve o fragmento pra revisão manual; com `--write-db`, mescla nas coleções `locations`/`travelGraph` do `db.json` do repo irmão (`tibia-idle/tibia-idle`). Campos mecânicos (posição, shop, tileCount) são sempre upsertados por id; campos que dependem de curação humana (ex: `displayName` de HUNT/TEMPLE/DEPOT/QUEST) são append-only — uma entrada já curada nunca é sobrescrita, só novas entradas são adicionadas como rascunho.

**Blocked by:** 02, 03 — precisa das duas fontes de locations já implementadas.

- [ ] A CLI roda contra Rookgaard e produz um único fragmento com `locations` (placas + NPCs) e `travelGraph`
- [ ] Sem `--write-db`, nada fora de `extractor/` é tocado — fragmento escrito localmente pra revisão
- [ ] Com `--write-db`, `locations` e `travelGraph` são mesclados nas coleções correspondentes do `db.json` do repo irmão
- [ ] Uma Location já existente com campo curado (`displayName`) não é sobrescrita numa nova rodada — só campos mecânicos são atualizados
- [ ] Uma Location nova (id ainda não presente no `db.json`) é adicionada como rascunho, sinalizada pra revisão
- [ ] `travelGraph` é sempre upsertado por par (mecânico, sem curação humana envolvida)
- [x] Comportamento de upsert/append-only coberto por testes, no mesmo estilo dos testes já existentes para `merge_fragment_into_db` em `hunt_fragment.py`

## Comments

Implementado como `extractor/scripts/build_travel_fragment.py` (CLI, mesmo padrão de
`build_hunt_fragment.py`) sobre `merge_locations_into_db`/`merge_travel_graph_into_db`/
`merge_travel_fragment_into_db` em `travel_graph.py`. Diferença importante em relação ao
precedente de `hunts` (append-only por mapId inteiro): aqui o merge é **por campo**, não por
entrada — `merge_locations_into_db` sempre atualiza posição/tipo/shop, mas preserva `displayName`
(e o flag `_todo`) de uma entrada já existente sempre que ela ainda estiver no db, e só usa o
placeholder gerado quando a location é nova. `travelGraph` é upsertado por par não-ordenado
(`frozenset({from, to})`) — sem noção de curação, sempre mecânico.

Sem `--write-db`, escreve fragmento em `extractor/full-maps/<region>/db-fragment.json` (adicionado
ao `.gitignore`, mesmo tratamento do `ready-maps/**` para hunts). Rodado ponta a ponta contra
`rook-full` (dry-run, sem `--write-db`): 15 locations de NPC geradas corretamente; 0 locations de
sign/travelGraph até as 12 placas legadas serem migradas pro novo formato (ver comentário do
ticket 02) — comportamento esperado, não um bug deste ticket.
