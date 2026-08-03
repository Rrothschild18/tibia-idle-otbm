# 03 — Locations de NPC + extração de shop do Canary

**What to build:** Ler `rook-full-npc.xml` (posição `centerx/centery/centerz` + `name` de cada NPC), gerar um id por slug do nome (`rook-npc-obi`), e casar cada NPC com o `.lua` correspondente em `data-otservbr-global/npc/` do checkout do Canary via slug do nome. Parsear a tabela `npcConfig.shop` desse arquivo (itemName, clientId — usado direto como item id, buy/sell opcionais) e anexar como payload `shop` da Location. Quando não houver `.lua` correspondente, a Location é criada mesmo assim (posição + nome, sem `shop`), e o run avisa no output quais NPCs ficaram sem match.

**Blocked by:** None — can start immediately, independente do grafo/map.json (tickets 01/02).

- [ ] Toda entrada do `npc.xml` vira uma Location tipo `NPC` com id derivado por slug do nome
- [ ] NPCs cujo nome casa com um `.lua` existente recebem o payload `shop` com os itens parseados (`itemName`, `itemId`, `buy` quando presente, `sell` quando presente)
- [ ] NPCs sem `.lua` correspondente ainda geram Location (sem `shop`), e o nome desses NPCs aparece num aviso no output do CLI
- [ ] Nenhuma tabela de conversão de item id é usada — `clientId` do shop é usado direto como item id
- [x] Lógica de parsing do XML e do Lua coberta por testes com fixtures pequenas em memória (nenhum arquivo real de `npc.xml`/`.lua` tocado nos testes)

## Comments

Implementado em `travel_graph.py` (`parse_npc_xml`, `slugify`, `match_npc_lua_filename`,
`parse_npc_shop_lua`, `build_npc_location(s)`) + testes em `test_travel_graph.py`. Um detalhe que
não estava óbvio pelo exemplo do spec (`rook-npc-obi`): os arquivos `.lua` do Canary usam `_` como
separador de palavra (`an_orc_guard.lua`), enquanto `slugify()`/os ids de location usam `-`
(`an-orc-guard`) — `match_npc_lua_filename` normaliza os dois lados pra `-` só na hora de comparar,
mantendo o id final com `-`. Também distingui dois casos que o spec conflava: NPC sem `.lua`
correspondente (gera warning, Location sem `shop`) vs. NPC cujo `.lua` existe mas não tem tabela
`npcConfig.shop` (ex: treinador — Location sem `shop`, mas SEM warning, já que não é um caso de
match faltando).

Rodado contra os 15 NPCs de `rook-full-npc.xml` usando o checkout local do Canary
(`C:\canary-3.2.1`): todos os 15 casaram com um `.lua` (0 warnings) depois do fix do separador
`_`/`-`; `clientId` usado direto como `itemId`, `buy`/`sell` opcionais conforme a tabela de cada
NPC (ex: Obi vende 15 armas, Norma vende comida).
