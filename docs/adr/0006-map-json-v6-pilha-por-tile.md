# `map.json` v6: a pilha por tile substitui os papéis de renderização

O modelo de render do pipeline (`layerClass` + tabela de `depthOffset`) foi substituído pelo modelo
que o Remere's Map Editor usa. O objetivo era **corrigir bugs de visualização**, não performance —
ver `.scratch/modelo-render-rme/spec.md`.

## O que estava errado

O modelo v5 nasceu de exploração empírica de metadata de sprite. Detecção de parede era uma
combinação de 5 flags observada no conjunto de Rookgaard; `roof` e `border` eram listas de id
escritas à mão em `item_classifier.py`; cada `depthOffset` foi calibrado contra o anterior até a
tela ficar aceitável. Dois sintomas concretos:

- **Bordas renderizavam acima de tudo.** `Borders` tinha `depthOffset: 1` mas era um objectgroup
  separado desenhado depois da tilelayer `Ground`, então uma borda cobria o que deveria cobri-la.
  No editor, borda é item de fundo (`clip`, `top order` 1) — quase no piso da pilha. Estava
  invertido.
- **A camada `Roof` não tinha um único telhado.** Em todo mapa ela era composta de duas aparências
  com a flag `bank` — ou seja, **chão** — desviadas para fora da tilelayer só porque o sprite é
  64×64 e um tilelayer de 32×32 não comporta (`_is_roof_tile`).

## Decisão

Três eixos que o `layerClass` colapsava num só passam a ser independentes:

| Eixo | Determinado por | Responde |
|---|---|---|
| `draw slot` | flag `bank` | é ground ou item? |
| passagem | flag `unpass` | dá para andar? |
| footprint | tamanho do sprite | qual bucket de folha? |

A `paint order` é andar → anti-diagonal (`tileX + tileY`) → `stack order`. Dentro da tile: ground
primeiro, depois itens de fundo por `top order` crescente (`clip`=1, `bottom`=2, `top`=3), depois os
demais em ordem de inserção. Criaturas sempre por último. **A profundidade de um sprite é
consequência dessa ordem** — deixa de existir constante de profundidade por categoria.

> Esta ADR dizia "andar → linha → `stack order`". Estava errado, e o erro é do lado da leitura, não
> deste formato: varrer por linha põe a parede de oeste por cima da tile a leste dela. Ver
> `MAP_JSON_V6.md` ("Reconstruir a ordem de desenho") e a emenda da ADR 0012 do `tibia-idle`.
> Nenhum mapa precisou ser reexportado.

A regra vive em `extractor/scripts/tile_stack.py`, puro e sem I/O. Nenhuma lista de id é consultada:
`item_classifier.py` continua no repo só porque o caminho v5 ainda o chama, e morre junto com ele.

## Formato

`map.json` v6 sai em árvore própria (`extractor/ready-maps-v6/<CIDADE>/<pasta>/`), documentado em
[`extractor/MAP_JSON_V6.md`](../../extractor/MAP_JSON_V6.md). A unidade é a tile com sua pilha
ordenada; não existe `layerClass`, `depthOffset`, camada `Roof`, tilelayer `Ground` nem `tilesets`.

**Só mapas de hunt.** O `map.json` da cidade inteira (`full-maps/<CIDADE>/`) não ganha v6: ele nunca
é renderizado — existe para o `build_travel_fragment.py` ler o `objectDefs` — e empacotar as ~2000
aparências de uma cidade em folhas por footprint pediria textura de 512×7936, muito além do que
qualquer GPU garante.

## Folhas por footprint, não por papel

Como o papel de renderização deixou de existir, a chave de agrupamento das folhas passou a ser só o
bucket de tamanho: `sheet-32`, `sheet-64`. Nos 20 mapas isso derruba **172 folhas no total para
40** — de 4-12 por mapa para exatamente 2 — e o `map.json` de **9461 KB para 6153 KB**.

A grade do v6 também é mais larga que a do v5 (64/32/16 colunas em vez de 16/12/8): uma grade que só
cresce para baixo estourava o limite seguro de textura em 4 dos 20 mapas (até 2688px de altura).
Preenchendo primeiro a largura segura, cada folha fica quadrada-ish e sua capacidade fica travada em
2048×2048. Os números do v5 ficaram intocados — mexer neles renumeraria os `tilesets` que o jogo lê
hoje.

## `shift` e `elevation` passam a sair

As duas propriedades de posicionamento que o extractor já lia do cliente e não entregava a ninguém
agora saem por aparência, e só quando diferentes de zero (42 aparências com `shift`, 129 com
`elevation` no conjunto atual). São elas que fazem uma pilha parecer pilha e que põem objeto pequeno
no lugar certo dentro do quadrado.

O `metadata.json` continua sendo gerado no v5: tem consumidor declarado fora deste repositório.

## Migração

O diretório que o jogo consome hoje fica **byte a byte intacto**. O v5 e o v6 são gerados na mesma
passada de `build_map.js` (o v6 depois, reaproveitando o `ITEM_CACHE` já quente), em raízes
separadas e com `assetsRoot` distintos (`assets/<mapa>-sprites` vs `assets/<mapa>-sprites-v6`), para
que os dois possam coexistir no front durante a migração. A troca de caminho é o último ticket, no
repositório do jogo.

**Conferência:** `extractor/scripts/map_v6_migration_report.py` compara o **conjunto de aparências
por tile** entre os dois formatos — não a contagem, para que uma aparência trocada por outra não
passe. O que muda de propósito não conta: a ordem dentro da pilha, e o slot em que uma aparência cai
(uma com `bank` que o v5 empurrava pra um objectgroup vira o chão da tile). Nos 20 mapas: **0 tiles
divergentes**. Relatório em `.scratch/modelo-render-rme/reports/07-reexportacao-v6.md`.

## Sobre o `ground_equivalent` do editor

O editor tem um mecanismo de autoria em que certas bordas declaram um chão equivalente. Foi medido
contra todos os mapas antes de qualquer código de render existir: **divergência zero** — os 24 ids
envolvidos carregam `bank` (são chão) e já estão no slot de chão do OTBM. O mecanismo ficou fora de
escopo. Ver `.scratch/modelo-render-rme/reports/02-ground-equivalent.md`.
