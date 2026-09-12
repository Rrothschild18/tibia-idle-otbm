# Um atlas por outfit, global — não por mapa, não um atlas único

A unidade de bake de sprite de criatura é **o outfit**: `atlases/outfits/<id>.png` +
`<id>.json`, gerados uma vez, num lugar compartilhado, independente de quais mapas
referenciam aquele outfit.

Registrado aqui porque o porquê vivia só em `.scratch/outfit-sprite-atlas/spec.md`, deletado na
limpeza do ticket 11.

## As duas alternativas recusadas

**Um atlas por mapa** desperdiça banda e cache: o mesmo rato aparece em várias hunt spots, e um
bake por mapa faria o cliente baixar os mesmos 36 frames uma vez por mapa. Com a unidade sendo o
outfit, ele baixa uma vez e o cache serve todas.

**Um atlas global com todos os outfits** vai para o outro extremo: 1049 outfits numa textura só
passa de qualquer limite de GPU, e obrigaria a carregar tudo para desenhar um monstro.

## O que o formato preserva

- **Phaser JSON Hash** (`frames` indexado por nome + `meta`), para o cliente chamar
  `scene.load.atlas(outfitId, png, json)` direto, sem passo de tradução.
- **A chave de frame não muda**: `<outfitId>_<frameIndex>`, a mesma string que o arquivo solto
  usava. Só o mecanismo de carregamento mudou (um atlas em vez de N imagens), não o contrato — a
  lógica de montar chave por direção/índice continuou valendo sem alteração.
- **Ordem determinística**: idle sul/leste/norte/oeste nos índices 0-3, depois 8 frames de
  caminhada por direção na mesma ordem de direção. Rodar duas vezes sobre a mesma entrada produz
  saída byte a byte idêntica.
- **Espaçamento transparente entre células**, para o filtro de textura do cliente não sangrar o
  frame vizinho quando escala.

Frames de outfit têm tamanho fixo, então o empacotamento é grade uniforme — não é preciso
bin-packing. O JSON existe mesmo assim porque um outfit pode ter frames de tamanhos diferentes
entre grupos; nas folhas de mapa (ADR 0003) todo frame tem o mesmo tamanho e por isso elas
dispensam JSON.

## Consequência

`publish.py` trata `atlases/outfits/` como destino global do front, não como parte de um bundle de
mapa — e falha alto quando um `respawn.json` referencia um atlas que nunca foi bakeado.
