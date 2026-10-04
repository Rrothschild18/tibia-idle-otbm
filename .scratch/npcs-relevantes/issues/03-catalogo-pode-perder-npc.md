Status: ready-for-agent

# 03 — Catálogo passa a poder perder NPC

**What to build:** `merge_locations_into_catalog` deleta do catálogo a location
de `type == "NPC"` que o run da cidade não emitiu, em vez de só marcá-la
`stale`. HUNT, TEMPLE e DEPOT seguem como estão: reportadas e preservadas.

## Por que, e por que só NPC

Hoje a função nunca remove nada. A docstring explica: uma location guarda campo
curado, e um nó rejeitado num run é muitas vezes uma placa que o usuário está no
meio de consertar. Isso está certo — para POI.

Para NPC não existe campo curado para proteger. O `displayName` é o nome do
próprio Canary, a posição vem do `-npc.xml`, o `shop` e o `outfit` vêm do `.lua`.
Regenerar dá exatamente o mesmo valor; não há decisão humana em lugar nenhum da
entrada. E os 355 NPCs do catálogo estão **sem `_todo`**, o que faz o merge atual
tratá-los como "totalmente curados" e protegê-los — exatamente o oposto do que
eles são.

**Sem esta ticket, as issues 02 e 04 não mudam uma linha do que o jogo carrega:**
o fragmento encolhe, o merge reporta 184 `stale`, e o catálogo continua com 38,5
MB.

## A ADR

Registre o corte em `docs/adr/`: **location de NPC é mecânica e deletável;
location de POI é curada e só fica stale**. Não é pelo filtro — esse é assunto de
README. É porque "o merge deleta, mas só para um tipo" é uma exceção que, sem a
razão escrita, o próximo agente que ler a função não sabe distinguir de
gambiarra. A ADR-0015 já documentou uma vez a linha mecânico/curado deste
pipeline; esta estende a mesma linha para dentro de uma coleção.

**Blocked by:** nada.

- [ ] Rodar com `--export` uma cidade cujo `-npc.xml` perdeu um NPC remove a
      location dele do `catalog-source.json`
- [ ] Location de HUNT, TEMPLE ou DEPOT ausente do run continua no catálogo e
      continua reportada como `stale`
- [ ] O relatório do merge distingue removida de stale, e o CLI imprime as duas
      contagens
- [ ] Location de NPC de **outra** cidade não é tocada quando se exporta uma
      cidade
- [ ] ADR escrita, com o caso concreto (355 NPCs sem `_todo` tratados como
      curados) como motivação
