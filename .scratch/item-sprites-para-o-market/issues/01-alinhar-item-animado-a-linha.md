Status: ready-for-agent

# 01 — Cada item animado começa numa linha

**What to build:** Os sheets de `extractor/atlases/items-animated/` param de
encaixar um item no espaço que sobrou da linha anterior. Cada sequência de frames
começa em `x = 0`.

É o que torna possível animar item em CSS no `tibia-idle` — `steps()` interpola
linearmente, então ele só descreve os frames de um item se eles estiverem numa
linha só, com passo constante. Hoje isso vale pra 636 dos 798 animados.

## Onde mexer, e o cuidado

O empacotamento é de `plan_static_sheets`, em
`extractor/scripts/bake_item_sheets.py`. Um contador `idx` corre por todas as
células do shard e a posição sai dele:

```python
col = idx % columns
row = idx // columns
```

Alinhar é arredondar `idx` pra cima até o próximo múltiplo de `columns` **no
começo de cada item**, em vez de no começo de cada célula.

**O cuidado:** `bake_item_sheets_animated.py` chama essa mesma função
(`bis.plan_static_sheets`), e o baker de estáticos também. Alinhar in loco
mudaria `items-static/` junto, que é 5.129 itens que não animam e não precisam
disso — crescimento de arquivo por nada. O alinhamento entra como **parâmetro**,
e só o baker de animados o liga.

O docstring da função descreve o empacotamento em duas frases ("assign each cell
a sequential grid position"; "an item's cells always stay together in the same
shard"). Ele passa a ter uma terceira coisa a dizer, e ela é a razão de a função
existir do jeito novo — não deixe implícito.

## Os 19 que não cabem

Item de até 32 frames passa a ocupar exatamente uma linha. **19 itens têm mais**
— o maior tem 125 frames —, e esses continuam transbordando por mais linhas.
Alargar o sheet até caber o maior (125 × 32 = 4.000px) custaria uma textura de
~25 milhões de pixels, quase toda transparente, contra ~1 milhão hoje: PNG
comprime o vazio, memória de textura decodificada não.

Deixe-os transbordando e **liste-os** na saída do comando, com id e contagem de
frames. Quem decide o que fazer com eles é a ticket 02 do `tibia-idle`, e ela
decide melhor com a lista na mão do que com uma estimativa.

## O número que a ticket tem que trazer

Alinhar desperdiça as células que sobram no fim da linha de cada item. Com 798
itens, a maioria com 3 a 8 frames, a **altura** total sobe bastante. Em **bytes**
deve subir bem menos, porque o desperdício é transparente contíguo — mas isso é
hipótese, não medição. Meça antes e depois: dimensão e KB de cada um dos 8 sheets.

Se os bytes subirem muito mais do que a intuição acima diz, isso é achado da
ticket e vale reportar antes de seguir — pode ser que valha empacotar por
contagem de frames (um sheet por número de frames, sem desperdício nenhum) em
vez de alinhar.

**Blocked by:** nada.

- [ ] Todo item animado do `items-index.json` ou tem `y` único e passo constante
      em `x`, ou tem mais de 32 frames — teste sobre o artefato assado, não sobre
      fixture
- [ ] `items-static/` sai byte a byte igual ao de antes: o alinhamento é
      parâmetro, e o baker de estáticos não o liga
- [ ] `items-index.json` é reassado no mesmo comando e aponta pras posições novas
- [ ] Duas execuções seguidas produzem os mesmos bytes, como no
      `bake_player_outfit_sheet.py`
- [ ] A saída do comando lista os 19 itens de mais de 32 frames, com id e
      contagem
- [ ] Dimensão e KB dos 8 sheets, antes e depois, no corpo do commit
