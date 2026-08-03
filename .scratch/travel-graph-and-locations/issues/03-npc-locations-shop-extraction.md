# 03 — Locations de NPC + extração de shop do Canary

**What to build:** Ler `rook-full-npc.xml` (posição `centerx/centery/centerz` + `name` de cada NPC), gerar um id por slug do nome (`rook-npc-obi`), e casar cada NPC com o `.lua` correspondente em `data-otservbr-global/npc/` do checkout do Canary via slug do nome. Parsear a tabela `npcConfig.shop` desse arquivo (itemName, clientId — usado direto como item id, buy/sell opcionais) e anexar como payload `shop` da Location. Quando não houver `.lua` correspondente, a Location é criada mesmo assim (posição + nome, sem `shop`), e o run avisa no output quais NPCs ficaram sem match.

**Blocked by:** None — can start immediately, independente do grafo/map.json (tickets 01/02).

- [ ] Toda entrada do `npc.xml` vira uma Location tipo `NPC` com id derivado por slug do nome
- [ ] NPCs cujo nome casa com um `.lua` existente recebem o payload `shop` com os itens parseados (`itemName`, `itemId`, `buy` quando presente, `sell` quando presente)
- [ ] NPCs sem `.lua` correspondente ainda geram Location (sem `shop`), e o nome desses NPCs aparece num aviso no output do CLI
- [ ] Nenhuma tabela de conversão de item id é usada — `clientId` do shop é usado direto como item id
- [ ] Lógica de parsing do XML e do Lua coberta por testes com fixtures pequenas em memória (nenhum arquivo real de `npc.xml`/`.lua` tocado nos testes)
