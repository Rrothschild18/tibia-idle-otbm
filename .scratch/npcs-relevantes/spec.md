# NPCs relevantes: cortar quem não faz nada no idle

## O problema

O `catalog-source.json` do `tibia-idle` tem **38,5 MB** e **16.307** arestas de
travel graph. 355 das suas 432 locations são `type: NPC`, e **15.764 arestas
(96,7%) tocam um NPC**. Cada aresta carrega o `path` inteiro em coordenadas de
mundo, então o tamanho do arquivo é essencialmente o produto "quantos NPCs" ×
"quão conectada é a cidade".

A maioria desses NPCs não faz nada que um jogo idle possa oferecer: são
roleplay, lore, guarda que castiga insulto, e quest de uma vez só. Eles entram
porque a única coisa que o extractor sabe sobre um NPC é **onde ele está**.

## A regra

Um NPC entra no fragmento quando vale **uma** destas:

1. É de **ROOK**. Rookgaard é a área inicial e precisa de volume — todos os 24
   ficam, com ou sem função.
2. Tem `shop` (`npcConfig.shop` no `.lua` do Canary). Se vende, é comerciante,
   e o tamanho do inventário não importa: um shop de 1 item é mecanicamente o
   mesmo nó que um de 129.
3. Tem **serviço de motor** numa categoria aprovada: viagem, banco, bênção,
   promoção.
4. Está na **allowlist curada** (`extractor/npc-allowlist.json`), com motivo.

Fora, por decisão explícita: **magia** (`StdModule.learnSpell` — ensina spell
por ouro, mas não é loop de idle), **cura grátis** (teto de 40 HP fora de
Rookgaard; dinheiro nenhum troca de mão), **addon de quest** (one-shot), e
**gate de teleporte de boss** (não existe no jogo hoje).

## Mecânico vs. curado

O corte respeita a linha do `CONTEXT.md`. **Mecânico**: `shop` e `services` saem
do `.lua` do Canary e são regenerados inteiros a cada run — nenhuma cidade nova
precisa de trabalho manual. **Curado**: a `npc-allowlist.json`, que existe só
para o que o motor não declara.

O motor declara 5 serviços por chamada única e inequívoca
(`data/npclib/npc_system/modules.lua` e `bank_system.lua`):

| serviço | assinatura |
| --- | --- |
| travel | `StdModule.travel` |
| bank | `:parseBank(` |
| bless | `StdModule.bless` |
| promote | `StdModule.promotePlayer` |
| spell | `StdModule.learnSpell` |

Detectar por assinatura e não por nome não é preferência de estilo. **Captain
Tiberius** diz, no diálogo, `"I transport my passengers back to the continent."`
e não tem mecânica nenhuma — zero keywords, zero `teleportTo`. **Captain Kurt**
tem 58 linhas de config e nenhum keyword. Qualquer heurística por nome ou por
texto de diálogo os aceitaria; um grep por `StdModule.travel` não.

O que **não** dá para detectar é a loja que vende por diálogo: o padrão
`removeMoneyBank(...)` + `addItem(...)` não distingue "Blind Orc vende 10 itens,
repetível" de "Oswald cobra 1000g uma vez numa quest". Esses vão à mão.

## Duplicata de Rookgaard

O corte do mapa de Thais pegou a ilha de Rookgaard inteira, então os 24 NPCs de
Rook existem **duas vezes** no catálogo: `ROOK-NPC-obi` e `THAIS-NPC-obi`, mesma
posição de mundo. O `tibia-idle` já descarta a cópia não-ROOK no import
(`findRookDuplicateNpcs`, em `libs/models/content/src/lib/import-source.model.ts`,
casa por slug + posição e devolve `DiscardedDuplicateNpc`). O extractor emite as
24 — **11 delas com loja** — e **2.364 arestas** as carregam, para morrer no
gate. Pará-las na origem é o mesmo corte, no lugar onde o dado nasce.

## Tirar do catálogo

`merge_locations_into_catalog` marca como `stale` e **nunca remove** uma location
que o run deixou de emitir. Os 355 NPCs estão sem `_todo`, logo o merge os trata
como curados e protegidos. **Sem mexer nisso, filtrar no extractor não muda uma
linha do que o jogo carrega.**

NPC é o único tipo de location sem curadoria para proteger: nome vem do Canary,
posição do `-npc.xml`, shop do `.lua`. HUNT, TEMPLE e DEPOT carregam `huntId` e
`displayName` escolhidos à mão e continuam protegidos. Ver a ADR.

## O resultado

| | antes | depois |
| --- | --- | --- |
| NPCs | 355 | 181 |
| locations | 432 | 258 |
| arestas | 16.307 | 5.199 |
| `catalog-source.json` | 38,5 MB | 4,5 MB |

Por cidade (mantidos/total): ROOK 24/24, THAIS 54/120, CARLIN 28/56,
KAZORDOON 37/61, VENORE 38/94.

## Fora de escopo

- **Viagem inter-cidade.** Os 22 NPCs de travel entram como nó parado. Ligar
  cidade a cidade mexe em como o `travelGraph` é particionado (hoje é
  substituído por cidade) e é fatia própria. Eles entram agora para que essa
  fatia não comece tendo que re-adicioná-los.
- **Moeda não-gold.** `npcConfig.currency` (gold token, HTP) é registrado e
  ignorado.
- **O corte de cidade que duplicou Rookgaard dentro de Thais.** A issue 02 para
  de emitir as duplicatas; a máscara de subárea que as trouxe fica como está.
