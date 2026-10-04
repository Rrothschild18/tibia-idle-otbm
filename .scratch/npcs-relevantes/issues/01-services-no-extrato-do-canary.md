Status: ready-for-agent

# 01 — Serviço de motor no extrato do Canary

**What to build:** O `npc-lua-facts.json` passa a dizer, por NPC, **quais
serviços de motor o `.lua` dele chama** — ao lado do `shop` e do `outfit` que já
estão lá. O pipeline lê esse campo ponta a ponta.

**Nada filtra ainda.** Esta ticket não muda nenhum fragmento nem nenhuma
location: ela só coloca o fato na mesa para a 04 poder decidir. É de propósito —
o campo novo e o corte que o usa são duas coisas que falham por motivos
diferentes, e misturá-las faz um diff onde não se distingue "detectei errado" de
"cortei errado".

## As cinco assinaturas

O motor do Canary tem exatamente 5 funções que prestam serviço cobrado, e cada
uma é uma chamada única e inequívoca:

| serviço | assinatura | arquivos nos 1035 |
| --- | --- | --- |
| `travel` | `StdModule.travel` | 73 |
| `bank` | `:parseBank(` | 25 |
| `bless` | `StdModule.bless` | 27 |
| `promote` | `StdModule.promotePlayer` | 6 |
| `spell` | `StdModule.learnSpell` | 51 |

Definidas em `data/npclib/npc_system/modules.lua` (linhas 92, 128, 157, 198) e
`data/npclib/npc_system/bank_system.lua` (linha 39).

**O `(` em `:parseBank(` não é decoração**: `parseBankMessages` é outra função,
chamada pelos mesmos NPCs, e um grep por `parseBank` solto casa com as duas.

## Por que assinatura e não nome

**Captain Tiberius** (`captain_tiberius.lua`) diz no diálogo `"I transport my
passengers back to the continent."` e **não tem mecânica nenhuma** — nenhum
keyword, nenhum `teleportTo`. **Captain Kurt** (`captain_kurt.lua`) são 58 linhas
de config sem um único keyword. Os dois parecem barqueiro pelo nome e pelo texto;
nenhum dos dois é. Heurística de nome aceita ambos, `StdModule.travel` não.

Pelo mesmo motivo, **não** detecte serviço por `removeMoneyBank`, `addItem`,
`teleportTo` ou `addExperience`: esses padrões não separam loja repetível de
quest de uma vez só. Quem precisa disso vai à mão na allowlist da 04.

## O prefactor

`build_npc_locations` recebe hoje `shops_by_name` e `outfits_by_name`, dois dicts
paralelos chaveados pelo mesmo nome. `services` seria o terceiro, e três dicts
paralelos é a forma errada do dado — são três campos de **um** fato sobre o NPC.

Troque os dois parâmetros por **um** dict de facts por nome. `_build_npc_lua_facts`
já lê os três do mesmo lugar (eles vivem lado a lado no mesmo arquivo do Canary),
então ele passa a devolver o fato inteiro em vez de uma tupla que o chamador
desmonta.

## O que a location NÃO recebe

**`services` não entra na location.** `npcSourceSchema`, em
`libs/models/content/src/lib/import-source.model.ts` do `tibia-idle`, descreve o
que uma location de NPC é, e um campo novo ali é mudança de contrato de
back-end — fatia própria, com a tela que o consome. Aqui o campo serve ao
**filtro**, dentro do extractor, e para no extractor.

**Blocked by:** nada.

- [ ] `extract_npc_facts` grava `services` para todo `.lua`, inclusive os sem
      nenhum serviço (lista vazia, não ausente — a mesma razão pela qual os
      arquivos sem shop nem outfit continuam no extrato)
- [ ] `npc-lua-facts.json` regenerado do clone, e o `MANIFEST.json` continua
      apontando o mesmo commit do Canary
- [ ] Contagem no extrato regenerado: 73 `travel`, 25 `bank`, 27 `bless`,
      6 `promote`, 51 `spell`
- [ ] `--canary-dir` relê `services` do checkout, igual a `shop` e `outfit`
- [ ] `build_npc_locations` recebe um dict de facts, não dicts paralelos
- [ ] Teste: `parseBankMessages` sozinho **não** marca `bank`
- [ ] Teste: `.lua` que só fala de viagem no diálogo, sem `StdModule.travel`,
      sai com `services` vazio (caso Captain Tiberius)
- [ ] Nenhum `db-fragment.json` muda: rode uma cidade antes e depois e compare
