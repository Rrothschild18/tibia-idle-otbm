# Hunt de treino (TRAINING-HUNT-0001)

Lado extractor da feature "treino online" do `tibia-idle` — treino num spot fixo, com o
personagem parado, contra monstro de dano desprezível (tipo slime do Tibia antigo). A
spec completa do lado jogo (Hunt com flag de ficar parado, passo novo de Routine,
catch-up, janela "now skilling") está sendo desenhada numa sessão de `/grilling` no
repo `tibia-idle`, ainda sem documento final.

## O que sai daqui

Um `.otbm` recortado à mão, pequeno, com um monstro (ou poucos) de dano baixíssimo,
pelo mecanismo **tradicional** de criação de hunt — o mesmo que ROOK usa:

- Item **2016**, texto livre `TRAINING-HUNT-0001`, dentro do próprio `.otbm` já
  recortado só daquele spot.
- **Não** o item 2017 — esse é o mecanismo de dedução por placa no mapa-mundo
  completo (CARLIN/THAIS/VENORE/KAZORDOON), não se aplica aqui.

Processo documentado em `extractor/README.md`, seção "Como adicionar um mapa novo".

## Critério de pronto

- Pasta `extractor/maps/<CIDADE>/TRAINING-HUNT-0001_<nome-descritivo>/` criada, com os
  arquivos exportados do RME (`.otbm` + `-house/-monster/-npc/-zones.xml`) sem
  renomear.
- `node extractor/scripts/build_map.js TRAINING-HUNT-0001_<nome-descritivo>` roda
  limpo.
- Resultado aparece em `ready-maps/`.

Hunts de treino seguintes (outros monstros/níveis de tolerância) repetem este processo
com `TRAINING-HUNT-0002`, `0003`, etc. — o jogador escolhe qual hunt de treino usar
pelo monstro que aguenta.
