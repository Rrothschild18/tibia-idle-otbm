Status: needs-triage

# 06 — Parser de shop: grafias alternativas de tabela

**What to build:** O parser de `npcConfig.shop` reconhece as grafias de campo que
hoje ignora, e registra a moeda quando ela não é ouro.

**Adiada de propósito** — o usuário pediu para resolver depois. Black Bert e Yana
entram à mão na allowlist da 04 como paliativo. Esta ticket **não** está marcada
para agente.

## O que está quebrado

`_parse_shop_entries` (em `extractor/scripts/travel_graph.py`) só aceita entrada
com `itemName` **e** `clientId`, nessa grafia exata. O Canary escreve de outros
jeitos, e **12 dos 1035 `.lua` saem com `"shop": []`** — não `null`, que seria
"não tem loja", mas lista vazia, que é "tem loja e ela está vazia". Três têm
itens de verdade:

| NPC | cidade | itens no `.lua` | grafia |
| --- | --- | --- | --- |
| Black Bert | THAIS | **129** | `itemname` / `clientid`, tudo minúsculo |
| Yana | THAIS | 14 | `name` / `clientId`, mais `npcConfig.currency = 22721` |
| Harog, Pompan | fora das 5 cidades | 3, 54 | `clientId` |

Black Bert compra raridades e troféus; Yana vende pacotes de imbuement por gold
token. **Nenhum dos dois é NPC de quest** — são comerciantes que o parser lê
errado, e o filtro da 04 os mataria como "não vende nada" se não fossem à mão.

## O corte

Ler a grafia certa é esta ticket. **Moeda não-gold é outra.** `npcConfig.currency`
(gold token em Yana, Hunting Task Points em Walter Jaeger) muda o que uma linha de
loja significa para o jogo, e isso é contrato de back-end com tela do lado.
Registre o campo e pare aí.

Os outros 9 arquivos com `shop: []` precisam ser olhados antes de decidir: lista
vazia pode ser tabela vazia de verdade no upstream, e nesse caso o certo é sair
`null`.

**Blocked by:** nada.

- [ ] As três grafias (`itemName`/`itemname`, `clientId`/`clientid`) produzem a
      mesma entrada
- [ ] Black Bert sai com 129 itens e Yana com 14
- [ ] `npcConfig.currency` é registrado no extrato quando existe
- [ ] Os 9 arquivos restantes com `shop: []` estão classificados: tabela vazia de
      verdade sai `null`
- [ ] As linhas de Black Bert e Yana saem da `npc-allowlist.json` no mesmo commit
