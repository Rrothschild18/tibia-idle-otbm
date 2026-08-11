# Sprites de Outfit

Como as sprites de outfit saem do `outfits.aec`, e o contrato dos sheets que o
`tibia-idle` consome.

> **Correção (2026-08-11).** A versão anterior deste documento afirmava que as direções eram
> `sul, leste, norte, oeste` e que a animação de caminhada vinha **agrupada** em 8 frames
> consecutivos por direção (`4 + direção*8 + frame`). **As duas afirmações estavam erradas**, e
> ninguém percebeu porque uma chave numérica crua (`128_17`) não denuncia um índice mal somado.
> Os dois consumidores reais sempre leram o formato correto — `animated-outfit-atlas.ts` e
> `monster-sprite.ts`, ambos no repo `tibia-idle` — então o que estava quebrado era só este
> arquivo. A fórmula abaixo é a mesma lei do ADR-0014 do `tibia-idle`, com um eixo a mais.

## A lei de índice

Uma appearance guarda suas sprites numa lista plana. A posição de cada uma é dada por:

```
index = ((((fase * numZ + z) * numY + y) * numX + x) * layers) + layer
```

O eixo que varia mais rápido é `layer`; o mais lento é `fase`. Ou seja: **os frames vêm
intercalados por direção, não agrupados** — todas as direções da fase 0, depois todas as da
fase 1, e assim por diante. É por isso que `frameIndex % 4` funciona para uma criatura simples,
e é a mesma regra que o ADR-0014 já estabeleceu para itens (`fase * patternCount + variante`);
outfits só acrescentam o eixo `layer`, que itens não têm.

| eixo | nome no protobuf | o que significa num outfit |
|---|---|---|
| `x` | `pattern_width` | direção — sempre 4 numa criatura |
| `y` | `pattern_height` | addon — 1 (criatura) ou 3 (outfit de jogador) |
| `z` | `pattern_depth` | montaria — 1 (criatura) ou 2 (outfit de jogador) |
| `layer` | `layers` | 1 (criatura) ou 2 (outfit de jogador: base + máscara) |
| `fase` | — | 1 no frame group `idle`, 8 no `moving` |

## Direções

```
x = 0 → norte      x = 1 → leste      x = 2 → sul      x = 3 → oeste
```

Verificado renderizando `x=0` de três criaturas já em uso no jogo — rato (21), lobo (3) e
dragão (39): as três aparecem **de costas**. Nos outfits de jogador o rosto confirma o resto:
`x=0` sem rosto, `x=1` e `x=3` de perfil, `x=2` com o rosto inteiro.

Frame group `idle` tem uma fase só; `moving` tem 8. Um outfit de criatura simples portanto tem
`4 + 32 = 36` sprites — o número que o formato antigo deste documento descrevia, pela razão
errada.

## Outfits de jogador

Os 22 outfits clássicos (128–134, 136–150 — o id 135 não existe) têm todos exatamente a mesma
forma:

```
432 sprites = 4 direções × 3 addons × 2 montaria × 2 layers × 9 fases
              idle: 48 · moving: 384 · sprites de 64×64
```

### As duas layers

`layer = 0` é o desenho em tons de cinza. `layer = 1` é uma **máscara** de quatro cores puras,
que diz a que região cada pixel pertence:

| cor da máscara | região |
|---|---|
| `#FFFF00` amarelo | cabeça |
| `#FF0000` vermelho | corpo |
| `#00FF00` verde | pernas |
| `#0000FF` azul | pés |

A cor final é **multiplicação em runtime** do pixel base pela cor escolhida daquela região. Não
existe sprite por cor: seriam 133⁴ ≈ 312 milhões de combinações por outfit. Ver ADR-0019 do
`tibia-idle` para onde essa multiplicação acontece e por quê.

### Addon é camada aditiva, não variante

`y = 1` e `y = 2` contêm **apenas as peças do addon**, transparentes no resto — o frame `y=1`
do outfit 128 tem 95 pixels opacos contra 539 do `y=0`. Renderizar "addon 1" é desenhar `y=0`
e **depois** `y=1` por cima. Os quatro resultados visuais (nenhum, 1, 2, 1+2) saem de três
frames empilhados.

### Montaria fica fora

O eixo `z=1` é o personagem **sentado, em pose de montaria**; o bicho embaixo é uma appearance
separada. Sem sistema de montaria esses frames renderizam alguém flutuando sentado, então o
bake os descarta e declara `mounts: 1` no JSON — ligar montaria depois é re-bake, não mudança
de contrato.

### O `.aec` não tem nomes

O campo `name` está vazio nos 1.330 outfits. A extração é por id, e o mapa id→nome vive só em
`BASE_OUTFITS` (`libs/models/character` no `tibia-idle`).

## Contrato do sheet

Um sheet por outfit, células de 64×64 com 1px de padding, grade de 24 colunas — 216 frames
(`4 direções × 3 addons × 2 layers × 9 fases`), 1561×586px, ~92 KB por outfit.

Base e máscara moram no **mesmo** arquivo. Separá-los em dois economiza 6% (2,28 → 2,14 MB nos
22 outfits) ao custo de dobrar as requisições e inventar o estado "outfit meio carregado".

### Chave de frame

```
<outfitId>_<layer>_a<addon>_<direção>_<fase>      ex.: 128_mask_a0_north_2
```

`layer` é `base` ou `mask`; `direção` é `north|east|south|west`. A chave é explícita, e não o
`<id>_<n>` numérico usado nos atlases de criatura, exatamente pelo motivo da nota de correção
no topo: `128_17` fica calado quando alguém soma o índice errado, e `128_mask_a0_north_2` não.

O JSON declara os eixos, para que o consumidor não precise deduzi-los da contagem de frames:

```json
{
  "frames": { "128_base_a0_north_0": { "frame": { "x": 1, "y": 1, "w": 64, "h": 64 } } },
  "axes": { "directions": 4, "phases": 9, "layers": 2, "addons": 3, "mounts": 1 },
  "meta": { "image": "128.png", "size": { "w": 1561, "h": 586 } }
}
```
