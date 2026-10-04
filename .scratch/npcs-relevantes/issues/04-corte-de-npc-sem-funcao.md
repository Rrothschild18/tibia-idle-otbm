Status: resolved

# 04 — Corte de NPC sem função

**What to build:** O fragmento passa a emitir só NPC que faz alguma coisa. Sai um
`npc-skipped.txt` por cidade dizendo quem foi cortado e por quê.

## A regra

Entra o NPC que satisfaz **qualquer uma**:

1. **É de ROOK.** Rookgaard é a área inicial e precisa de volume. Todos os 25
   ficam, com ou sem função. A isenção é pelo campo `city` da location, então
   `ROOK-NPC-cipfried` fica e a cópia de Thais cai (a 02 já a tinha cortado).
2. **Tem `shop`.** Tamanho do inventário não entra na conta: um shop de 1 item
   (Albinius, Elane, Gnomette, Xelvar…) é mecanicamente o mesmo nó que o de 129.
   Filtrar por tamanho seria enfiar julgamento de relevância dentro da regra
   mecânica, que é exatamente o que esta ticket existe para não fazer.
3. **Tem `services`** em `travel`, `bank`, `bless` ou `promote` (da 01).
4. **Está na `npc-allowlist.json`.**

## Fora, por decisão

- **`spell`** (`StdModule.learnSpell`, 11 NPCs). Ensina magia por ouro, mas não
  é loop de idle. Nove deles *só* fazem isso e caem; Padreia e Muriel ficam por
  outro motivo.
- **Cura grátis** (15). Teto de 40 HP e dinheiro nenhum troca de mão. A exceção
  real é Cipfried (cura até 185), e ele é de ROOK — já entra pela regra 1.
- **Addon de quest** (9) e **gate de teleporte de boss** (2). One-shot e
  endgame; nenhum dos dois existe no jogo hoje.

## A allowlist

`extractor/npc-allowlist.json`, mapa de **id de location** para **motivo em
texto livre**. Id completo, não nome nem slug: `Junkar` aparece em três lugares
com `.lua` diferentes e `Ferryman Kamil` em dois, e nome obrigaria a decidir
pelos três de uma vez. Id também faz um typo falhar alto, porque id que não
existe em cidade nenhuma é erro.

Motivo é texto livre, não enum. Ele é o que responde "por que o Dukosch está
aqui?" seis meses depois, e enum obrigaria a inventar a taxonomia antes de
conhecer os casos.

**Não existe denylist.** Loja é lei: se vende, fica. Abrir exceção do outro lado
convida a lista a ser preenchida por gosto, e aí voltam as 184 linhas de
julgamento humano — só invertidas.

Os casos que vão na allowlist são os que o motor **não** declara, cada um
verificado no `.lua` (linhas em `spec.md` e na ticket 06):

- **Travel artesanal** — `player:teleportTo` próprio, sem `StdModule.travel`:
  Palomino (coche Thais→Venore, 125g, repetível), Appaloosa (o inverso),
  Eustacio (barco pra Rascacoon), Riddler (charada que teleporta).
- **Passe de vagonete** — 250g por 7 dias, habilita os vagonetes de minério
  dentro de Kazordoon: Dukosch, Lukosch, Pukosch. (Lokur, Brodrosch e Gewen
  vendem o mesmo passe e já entram por `bank`/`travel`.)
- **Pré-requisito de bênção** — Kawill: sem ele, `StdModule.bless` com
  `bless == 3` recusa (`modules.lua:174`). Pydar fica inalcançável sem Kawill
  antes, e os dois são de Kazordoon.
- **Loja por diálogo** — vende item por ouro sem tabela `shop`: Bozo, Dermot,
  Chester Kahs, Emael, Padreia, Robson, Gnominus, Zebron (cassino), Ruprecht
  (loja sazonal por present bag), Oldrak.
- **Cosmético pago** — Walter Jaeger (loja inteira de outfit/addon/mount por
  Hunting Task Points).
- **XP/rank repetível** — Storkus (token por XP), Rottin Wood, Commander Stone.
- **Paliativo da 06** — Black Bert (129 itens) e Yana (14): o parser lê a tabela
  deles errado e registra `shop: []`. Entram à mão até a 06; **deixe o motivo
  dizer que é paliativo e citar a 06**, senão alguém vai remover a linha depois
  do conserto sem saber que ela existia por isso.

## O relatório

`extractor/full-maps/<CIDADE>/npc-skipped.txt`: um NPC por linha, com nome e
motivo do corte (`sem shop e sem serviço` / `duplicata de ROOK-NPC-x` /
`serviço só de magia`). **Não** reaproveite o `travel-graph-rejections.txt`: ele
significa "bug de mapa, conserta e some", e enfiar 184 descartes intencionais
nele destruiria o valor dele como sinal.

Termo novo no `CONTEXT.md` e seção no `extractor/README.md`.

**Blocked by:** 01.

- [x] Todos os 25 NPCs de ROOK continuam no fragmento de ROOK
- [x] NPC com shop de 1 item continua entrando
- [x] NPC cujo único serviço é `spell` é cortado
- [x] NPC em `npc-allowlist.json` entra mesmo sem shop e sem serviço
- [~] Id na allowlist que não existe em nenhuma cidade faz o run falhar, não
      passar em silêncio — **metade no run, metade na suíte.** Slug errado
      (`THAIS-NPC-bozzo`) aborta o run da cidade dona. Prefixo de cidade errado
      (`THASI-NPC-bozo`) não tem cidade dona, então nenhum run isolado o
      reprova: derivar a lista de cidades de `full-maps/` trocaria a falha
      silenciosa por um falso positivo (checkout sem a pasta de uma cidade
      abortaria com a allowlist correta). Vive em
      `test_every_allowlist_id_names_a_city_that_exists`
- [x] `npc-skipped.txt` existe por cidade, com nome e motivo de cada corte
- [x] As contagens por cidade saem como a `spec.md` diz
- [x] `travel-graph-rejections.txt` não ganhou nenhuma linha de corte intencional
