Status: ready-for-agent

# Sprite de item em escala — o lado do bake

Complementa `.scratch/item-sprites-para-o-market/spec.md` do repo `tibia-idle`.
Leia os dois: eles não se repetem. Lá está o porquê (o Market vai desenhar todos
os itens de uma vez, e `ItemSprite` não aguenta); aqui está a única coisa que o
extractor precisa mudar pra que a solução de lá seja possível.

## Problem Statement

O consumo passa a animar item em CSS, com `@keyframes` + `steps()`. `steps()`
interpola linearmente entre um começo e um fim: ele só consegue descrever os
frames de um item se eles estiverem numa **linha só do sheet, com passo
constante**.

Os sheets de `extractor/atlases/items-animated/` empacotam por área, sem saber
disso. Medido contra o `items-index.json` de hoje:

| | itens |
|---|---|
| animados (não stackable, mais de um frame) | 798 |
| com os frames numa linha só, passo constante | **636** |
| com a sequência quebrando pra linha seguinte | **162** |

Dos 162, apenas **1** começa em `x = 0`. Os outros 161 começam no meio de uma
linha e transbordam pra próxima — não é um caso de borda, é o comportamento
normal de um empacotador que preenche por área.

Os sheets são de 1024px de largura (32 colunas de 32px), em quatro alturas:
928, 992, 1632 e 1664.

## Solution

**Cada item animado começa numa linha nova.** O empacotador para de encaixar um
item no espaço que sobrou da linha anterior e passa a alinhar o começo de cada
sequência a `x = 0`.

Com isso, todo item de até 32 frames ocupa exatamente uma linha, e `steps()` o
descreve. São 779 dos 798. Os 19 restantes — os que têm mais de 32 frames, até um
de 125 — continuam transbordando, e é a ticket 01 que decide o que fazer com
eles.

## Decisions

- **A regra é de alinhamento, não de largura.** Alargar o sheet até caber o maior
  item (125 frames × 32px = 4.000px) resolveria os 19 também, e custaria uma
  textura de 4.000 × ~6.400px por sheet — 25 milhões de pixels, contra ~1 milhão
  de hoje, quase toda transparente. Não vale: PNG comprime bem o vazio, memória
  de textura decodificada não.
- **O custo de área é o que a ticket tem que medir.** Alinhar desperdiça as
  células que sobram no fim da linha de cada item; com 798 itens e a maioria
  tendo 3 a 8 frames, a altura total sobe bastante. Em bytes deve subir bem menos
  — o desperdício é transparente contíguo, que é o melhor caso do PNG —, mas *bem
  menos* é uma hipótese, e a ticket mede antes e depois.
- **O bake continua determinístico.** Duas execuções seguidas produzem os mesmos
  bytes, como já vale pro `bake_player_outfit_sheet.py`. Alinhamento não pode
  introduzir dependência de ordem de `os.listdir`.
- **`items-index.json` é reassado junto**, no mesmo comando. Índice e sheet que
  discordam são a doença que a ticket 01 do `tibia-idle` está consertando; não
  vale a pena criar uma segunda cepa.

## Testing Decisions

- A propriedade a testar é a que o CSS precisa, e ela se afirma direto sobre a
  saída: para todo item animado do índice, ou os frames dele têm o mesmo `y` e
  passo constante em `x`, ou ele tem mais de 32 frames. Um teste, sobre o
  artefato de verdade.
- Determinismo tem teste próprio, no formato do que já existe pro baker de
  outfit: assar duas vezes e comparar bytes.

## Out of Scope

- Os 19 itens de mais de 32 frames. Eles são exceção conhecida e nomeada; o que
  fazer com eles é decisão da ticket 01, com o número de área na mão.
- `items-static/`. Item estático não anima, então nada de `steps()` se aplica —
  e reempacotar 5.129 itens que já funcionam pra alinhar o que não anima seria
  crescimento de arquivo por nada.
- Os atlas de criatura (`extractor/atlases/outfits/`) e os sheets de outfit de
  jogador. Outra discussão, outro consumidor.
