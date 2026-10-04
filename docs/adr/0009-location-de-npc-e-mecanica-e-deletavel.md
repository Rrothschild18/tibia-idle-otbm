# Location de NPC é mecânica e deletável; POI é curada e só fica stale

`merge_locations_into_catalog` **remove** do `catalog-source.json` a location de `type == "NPC"` que
o run da cidade não emitiu. Para `HUNT`, `TEMPLE`, `DEPOT` e `QUEST` nada mudou: elas continuam
sendo reportadas como `stale` e preservadas.

Registrado porque "o merge deleta, mas só para um tipo" é uma exceção que, sem a razão escrita, não
se distingue de gambiarra — e a primeira leitura da função convida a "arrumar" a inconsistência.

## O corte é por quem decidiu o valor, não por coleção

É a mesma linha que o `CONTEXT.md` traça entre **merge mecânico** e **curado**, aplicada agora
dentro de uma coleção. Uma location de POI guarda decisão humana que o mapa não sabe: o
`displayName` foi escolhido, o `huntId` amarra a location à hunt. Apagá-la porque um run não a
emitiu destrói essa decisão — e um nó rejeitado num run é muitas vezes uma placa que alguém está no
meio de consertar. Daí o `stale`: reporta, não mexe.

Uma location de NPC não tem nada disso. O `displayName` é o nome do próprio Canary, a posição vem do
`<CIDADE>-npc.xml`, `shop` e `outfit` vêm do `.lua`. Regenerar produz exatamente o mesmo valor, em
qualquer ordem, quantas vezes se rode. Não existe curadoria para preservar, então `stale` não está
protegendo nada — está só acumulando.

## O que forçou a decisão

O `_todo` é o sinal que o merge usa para saber se uma entrada já foi revisada por gente: enquanto
está presente, a entrada é rascunho e se regenera inteira; quando alguém o remove, ela passa a ser
tratada como curada e os campos de `CURATED_LOCATION_FIELDS` ficam intocáveis.

Os 355 NPCs do catálogo estavam **todos sem `_todo`** — porque `build_npc_location` nunca o escreve,
já que não há nada ali para revisar. O resultado é que o mecanismo lia "totalmente curado" em
exatamente as entradas que são 100% derivadas, e as protegia. Era o oposto da intenção, invisível
enquanto nada precisava sair.

O que precisou foi o filtro de NPC (`.scratch/npcs-relevantes/`): 184 NPCs que não vendem nada nem
prestam serviço param de ser emitidos. Sem esta ADR o fragmento encolhia, o merge imprimia 184
`stale`, e o catálogo continuava com 38,5 MB — o trabalho inteiro sem efeito nenhum sobre o jogo.

## Alternativas recusadas

**Flag `--prune-npc`.** Deleção só quando pedida. Recusada porque uma flag que alguém precisa
lembrar de passar é divergência esperando acontecer: o catálogo ficaria certo ou errado conforme
como o comando foi digitado, e os dois estados são indistinguíveis depois do fato.

**Escrever `_todo` nas locations de NPC.** Faria o merge regenerá-las inteiras e resolveria a
proteção indevida, mas não a remoção — entrada ausente do run continuaria `stale`. E `_todo`
significa "alguém precisa olhar isto", o que é falso para um NPC.

**Limpeza manual uma vez, ou script de migração descartável.** Resolvem o catálogo de hoje e deixam
o problema voltar no próximo `-npc.xml` que mudar.

## O que isto não autoriza

Remover aresta já era o comportamento de `merge_travel_graph_into_catalog`, por outro motivo (o
fragmento é o conjunto completo de arestas da cidade), e nada aqui muda. Nenhuma outra coleção ganha
remoção: `hunts` segue append-only, e POI segue `stale`. A pergunta que decide, para uma coleção
futura, é a desta ADR — **o run consegue reproduzir este valor sozinho?**
