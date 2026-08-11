Status: ready-for-agent

# Outfit de personagem — extração e sheets

## Problem Statement

Nenhum dos 22 outfits de jogador do Tibia foi extraído. A tela de customização de personagem no
`tibia-idle` está pronta há tempo — grade, busca, radio de sexo, as 133 casas da paleta, quatro
abas de cor — e desenha `unknownoutfit.png` em todas as casas, porque `atlasOf()` devolve `null`
pra todo mundo.

O motivo é `extract_sprites.py:104`, `outfit_has_addons_or_mounts`: ela descarta qualquer
appearance com `pattern_height > 1`, `pattern_depth > 1` ou `layers > 1`. Os 22 outfits caem nos
três critérios de uma vez. O docstring da função descreve o corte como "sprite count inflado por
addons/montarias", e é essa leitura — *quantidade* de sprites como critério — que escondeu o
problema: ninguém precisou saber **qual eixo** excluía o quê.

Junto disso, `OUTFIT_SPRITES_DOCUMENTATION.md` descrevia a ordem dos frames errada (direções
`sul, leste, norte, oeste`; caminhada agrupada em 8 por direção). Os dois consumidores reais no
`tibia-idle` — `animated-outfit-atlas.ts` e `monster-sprite.ts` — sempre leram o formato certo
(`% 4`, ordem `north, east, south, west`), então o que estava quebrado era só o documento. Ele já
foi corrigido; esta spec depende da versão corrigida.

## Solution

Estender a extração aos 22 ids conhecidos e produzir **um sheet por outfit** com os eixos que o
cliente precisa: direção, addon e camada. Montaria fica fora.

Um outfit de jogador tem 432 sprites = `4 direções × 3 addons × 2 montaria × 2 layers × 9 fases`,
de 64×64. Cortando o eixo de montaria sobram **216 frames**, numa grade de 24 colunas com 1px de
padding: 1561×586px, ~92 KB por outfit, **2,28 MB** nos 22.

## Decisions

- **O critério de extração deixa de ser "quantidade de sprites".** A exclusão passa a nomear o
  eixo que a motiva. Outfits de criatura seguem entrando como hoje; os 22 ids de jogador entram
  por serem conhecidos, não por passarem num limiar.
- **Montaria (`z = 1`) fica fora.** Aqueles frames são o personagem *sentado em pose de montaria*,
  e o bicho embaixo é uma appearance separada — renderizá-los sem sistema de montaria dá alguém
  flutuando sentado. O JSON declara `mounts: 1` pra que ligar o eixo depois seja re-bake, não
  mudança de contrato.
- **Addon (`y`) entra inteiro**, os três valores. Não são variantes: `y=1` e `y=2` contêm só as
  peças do addon, transparentes no resto (o frame `y=1` do 128 tem 95 pixels opacos contra 539 do
  `y=0`). Quem empilha é o cliente; o sheet só precisa carregá-los.
- **Base e máscara no mesmo arquivo.** Separá-los economiza 6% (2,28 → 2,14 MB) ao custo de dobrar
  as requisições e criar o estado "outfit meio carregado".
- **Chave de frame explícita**: `<outfitId>_<layer>_a<addon>_<direção>_<fase>`, ex.
  `128_mask_a0_north_2`. Não o `<id>_<n>` numérico dos atlases de criatura — pelo motivo exato da
  correção acima: `128_17` fica calado quando alguém soma o índice errado.
- **Os ids são os 22 clássicos**: 128–134 e 136–142 (Citizen, Hunter, Mage, Knight, Nobleman,
  Summoner, Warrior), 143–146 e 147–150 (Barbarian, Druid, Wizard, Oriental). O id 135 não existe.
  O `.aec` não tem nomes — o campo `name` está vazio nos 1.330 outfits —, então o mapa id→nome vive
  só no `BASE_OUTFITS` do `tibia-idle`.

## Testing Decisions

- Mesmo estilo de `tests/test_render_baked_row.py`: função pura que recebe frames + chaves e
  devolve `(imagem, mapeamento)`, testada contra fixtures PIL em `tmp_path` — dimensões, chaves,
  posições. Não bytes de pixel.
- **A lei de índice merece teste próprio e direto**, dado que é o que estava errado: uma função
  `frame_index(fase, z, y, x, layer)` testada contra os casos que dá pra conferir à mão — o total
  de 432, o `idx(0,0,0,2,0) = 4` do sul, e a máscara sempre em índice ímpar.
- Determinismo byte a byte entre duas execuções, como o `outfit-sprite-atlas` já exige.
- Conferência visual contra dado real antes de confiar: o frame `south` de pelo menos um dos 22
  precisa ser olhado por um humano. Já foi feito uma vez durante o desenho (128, 136 e 131
  conferidos e aprovados) e vale repetir sobre a saída do baker.

## Out of Scope

- Eixo de montaria, e qualquer sistema de montaria.
- Outfits de store e de quest (151+).
- Qualquer código do cliente — vive em `.scratch/outfit-de-personagem/` do repo `tibia-idle`.
- Posse de outfit por conta (premium, quest). Não existe conceito de premium em lugar nenhum.
