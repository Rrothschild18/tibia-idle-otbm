Type: note
Status: ready-for-human

# NPCs da allowlist, de antes de 2026-10-12 esvaziar o npc.xml das 5 cidades

Em 2026-10-12, `extractor/full-maps/<CIDADE>/<CIDADE>-npc.xml` (e `-zones.xml`) saiu
vazio pra Carlin, Kazordoon, Rook, Thais e Venore — intencional (ver conversa),
não bug de export. `npc-allowlist.json` foi esvaziado no mesmo commit porque toda
entrada apontava pra um NPC que não existe mais no mapa.

O motivo de cada um fica registrado aqui pra não se perder, caso algum NPC volte
(hand-curado ou num re-cut futuro) e precise do mesmo resgate (loja por diálogo,
travel artesanal, serviço que o motor do Canary não declara).

## THAIS

- **palomino**: travel artesanal — coche Thais→Venore, 125g, repetível (`palomino.lua:77,83`) + aluguel de montaria 500g/24h
- **bozo**: loja por diálogo — mace of the fury 250g (`bozo.lua:899`)
- **dermot**: loja por diálogo — dungeon key de Fibula 2000g (`dermot.lua:79`)
- **chester-kahs**: loja por diálogo — reposição de scroll 1000g (`chester_kahs.lua:149`)
- **emael**: loja por diálogo — podium of vigour 1.000.000g (`emael.lua:70`)
- **walter-jaeger**: cosmético pago — loja inteira de outfit/addon/mount por Hunting Task Points (`walter_jaeger.lua:319-473`)
- **black-bert**: paliativo da issue 06 — compra 129 raridades/troféus, mas o `.lua` usa `itemname`/`clientid` minúsculo e o parser registra shop vazio
- **yana**: paliativo da issue 06 — vende 14 itens, mas o `.lua` usa `clientId` + `npcConfig.currency` (gold token) e o parser registra shop vazio

## CARLIN

- **padreia**: loja por diálogo — vermin poison 50g (`padreia.lua:88`). O `learnSpell` dela não conta — magia está fora
- **ruprecht**: loja sazonal — 20+ itens comprados com present bag, repetível (`ruprecht.lua:56-76`)

## KAZORDOON

- **riddler**: travel artesanal — charada que teleporta, repetível (`riddler.lua:141,146,152,156`)
- **dukosch**: passe de vagonete — 250g por 7 dias, habilita os vagonetes de minério (`dukosch.lua:70-71`)
- **lukosch**: passe de vagonete — idem (`lukosch.lua:70-71`)
- **pukosch**: passe de vagonete — idem (`pukosch.lua:70-71`)
- **robson**: loja por diálogo — parcel 15g, label 1g (`robson.lua:74,84`)
- **gnominus**: loja por diálogo — mushroom beer 10g (`gnominus.lua:85`)
- **storkus**: XP repetível — troca vampire token por rank + XP em 6 degraus (`storkus.lua:140-185`)
- **commander-stone**: rank repetível — 4 missões Bigfoot a cada 20h (`commander_stone.lua:65,85,89`)

## VENORE

- **kawill**: pré-requisito de bênção — sem ele, `StdModule.bless` com `bless==3` recusa (`modules.lua:174`), e o Pydar de Kazordoon fica inalcançável
- **appaloosa**: travel artesanal — coche Venore→Thais, 125g, repetível (`appaloosa.lua:76,82`) + aluguel de montaria 500g/24h
- **eustacio**: travel artesanal — barco pra Rascacoon, repetível (`eustacio.lua:82-90`)
- **oldrak**: loja por diálogo — hallowed axe 1000g, repetível (`oldrak.lua:139`)
- **zebron**: cassino — aposta 1-99g com payout, repetível (`zebron.lua:74,114`)
- **rottin-wood**: XP repetível — missões com cooldown (`rottin_wood.lua:113,124`)

## Impacto funcional conhecido, se nada voltar

- Sem **kawill**: bless de 3 pontos nunca mais fica disponível em lugar nenhum.
- Sem **palomino**/**appaloosa**: a viagem Thais↔Venore por coche desaparece (resta
  andar, se houver caminho terrestre).
- Sem **eustacio**: Rascacoon fica inalcançável por barco.
- Sem nenhum banqueiro/lojista: toda a economia de compra/venda via NPC sai do jogo
  pras cinco cidades — o que sobra é só o que `routine`/`shop` já tinha fixturado.
