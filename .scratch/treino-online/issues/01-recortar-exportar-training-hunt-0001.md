Type: task
Status: ready-for-human

# Recortar e exportar o mapa TRAINING-HUNT-0001 no RME

Primeira hunt de treino da feature "treino online" (ver `spec.md`). Precisa de edição
manual no RME — não é tarefa pra agente AFK.

## O que fazer

1. Escolher/recortar no RME um spot pequeno com um monstro de dano desprezível (ex:
   slime), do jeito que jogadores antigos de Tibia treinavam.
2. Colocar o item **2016** com texto `TRAINING-HUNT-0001` no spot (mecanismo
   tradicional de criação de hunt — não o 2017, que é só pra dedução no mapa-mundo).
3. Exportar do RME: `.otbm` + `-house/-monster/-npc/-zones.xml`, sem renomear.
4. Criar a pasta `extractor/maps/<CIDADE>/TRAINING-HUNT-0001_<nome-descritivo>/` e
   colocar os arquivos ali.
5. Rodar `node extractor/scripts/build_map.js TRAINING-HUNT-0001_<nome-descritivo>` e
   confirmar que o resultado sai limpo em `ready-maps/`.

## Critério de pronto

- `ready-maps/` tem o `TRAINING-HUNT-0001` buildado sem erro.
