# `map.json` v6 — formato

A unidade do formato é a **tile com sua pilha ordenada**. Não existe papel de renderização, constante
de profundidade, camada de telhado, tilelayer de chão nem `tilesets`. Para o porquê, ver
[ADR 0006](../docs/adr/0006-map-json-v6-pilha-por-tile.md); para o vocabulário (`draw slot`,
`stack order`, `top order`, `paint order`, `elevation`, `shift`), ver [`CONTEXT.md`](../CONTEXT.md).

Gerado por `node extractor/scripts/build_map.js <pasta>` em
`extractor/ready-maps-v6/<CIDADE>/<pasta>/`, junto com `sheets/*.png` e `monsters/respawn.json`. O
`extractor/ready-maps/` (v5) continua sendo gerado na mesma passada e é o que o jogo consome até
migrar.

## Topo do arquivo

```jsonc
{
  "version": 6,
  "tilewidth": 32,
  "tileheight": 32,
  "width": 62,               // em tiles, união de todos os floors
  "height": 31,
  "bounds": { "minX": 32100, "minY": 31900, "maxX": 32161, "maxY": 31930 },
  "defaultZ": 7,             // 7 se existir, senão o menor z do mapa
  "assetsRoot": "assets/ROOK-HUNT-0013_rats-rookguard-sprites-v6",
  "appearances": { /* ... */ },
  "sheets": { /* ... */ },
  "floors": { /* ... */ }
}
```

`bounds` é coordenada de mundo; `width`/`height` e todo `tileX`/`tileY` são relativos a
`minX`/`minY`. Os bounds são a **união de todos os floors**, então `(tileX, tileY)` significa a mesma
coluna física em qualquer floor do mapa (ver [ADR 0002](../docs/adr/0002-map-json-floors-e-defaultz.md)).

## `floors` — a pilha

```jsonc
"floors": {
  "7": {
    "z": 7,
    "tiles": [
      [0, 0, 101],                  // só chão
      [1, 0, 351, 4411, 1947],      // chão + borda + item
      [2, 0, 0, 2913]               // sem chão, só item
    ]
  }
}
```

Cada tile é um array plano:

```
[ tileX, tileY, ground, ...stack ]
```

- **`ground`** — o id da aparência no slot de chão, ou `0` quando a tile não tem chão. Ids de
  aparência começam bem acima de zero, então `0` não é ambíguo. (No conjunto atual, 10.880 tiles
  são assim: têm item e não têm chão.)
- **`...stack`** — os ids das demais aparências, **já na ordem de desenho**. Nada precisa ser
  reordenado na leitura.

`tiles` vem ordenado por linha e depois por coluna, e uma tile sem nenhuma aparência é omitida.

### Reconstruir a ordem de desenho

É uma varredura, sem tabela de consulta:

```
para cada floor em ordem crescente de z:
  para cada tile em floors[z].tiles:        # já vem em ordem de linha
    desenhe ground (se != 0)
    para cada id em stack:                  # já vem em stack order
      desenhe id
    desenhe as criaturas da tile            # sempre depois de todo item
```

A profundidade de um sprite é a posição dele nessa varredura. Não existe `depthOffset` a somar.

### Deslocamento e elevação

Ao desenhar a pilha de uma tile, o `y` acumula:

```
elevacao_acumulada = 0
para cada id em [ground, ...stack]:
  ap = appearances[id]
  desenhe em (tileX*32 + shift.x, tileY*32 + shift.y - elevacao_acumulada)
  elevacao_acumulada += ap.elevation ?? 0
```

`shift` desloca só o próprio sprite e não acumula; `elevation` desloca os itens desenhados **depois**
e acumula. Ambos são omitidos quando zero — trate a ausência como `{x: 0, y: 0}` e `0`. Vale clampar
a elevação acumulada: sem teto, uma pilha alta empurra o sprite para fora da própria tile (o editor
não clampa porque é editor, não cliente).

## `appearances` — uma entrada por id usado

```jsonc
"appearances": {
  "101":  { "type": "static", "sheet": "sheet-32", "gids": [0],
            "flags": { "bank": true, "unpass": true, "unmove": true, "unsight": true, "fullbank": true } },
  "103":  { "type": "random", "sheet": "sheet-32", "gids": [1, 2, 3, 4],
            "random": true, "flags": { "bank": true, "unmove": true, "automap": true } },
  "1947": { "type": "static", "sheet": "sheet-64", "gids": [28],
            "spriteWidth": 64, "spriteHeight": 64, "elevation": 8,
            "flags": { "bottom": true, "unmove": true, "automap": true } },
  "2110": { "type": "static", "sheet": "sheet-32", "gids": [57],
            "shift": { "x": 8, "y": 8 }, "flags": { "unmove": true } }
}
```

| campo | quando aparece | significado |
|---|---|---|
| `type` | sempre | `static`, `animated`, `random` ou `unknown` |
| `sheet` / `gids` | sempre | a folha e a célula de cada frame (ver abaixo) |
| `spriteWidth` / `spriteHeight` | quando ≠ 32 | tamanho do sprite em pixels |
| `shift` | quando ≠ 0 em algum eixo | `{x, y}`, deslocamento do próprio sprite |
| `elevation` | quando ≠ 0 | pixels que este item soma aos desenhados depois dele |
| `random` | quando `true` | os `gids` são variantes; escolha uma, não anime |
| `animated` + `animation` | quando `true` | os `gids` são frames em sequência |
| `hasSprite` | quando `false` | nenhum frame foi encontrado na extração |
| `flags` | quando há alguma | flags verdadeiras do `appearances.dat` |
| `issues` | quando há alguma | problemas encontrados na extração |

Só entram ids que alguma tile de fato usa. Marcadores do travel-graph (uid ≥ 10001) nunca entram.

**As flags são informativas.** A ordem de desenho já está resolvida na pilha; `bank`/`clip`/
`bottom`/`top` só aparecem porque a lógica de jogo as usa para outras perguntas (`unpass` para
passagem, por exemplo). O render não precisa consultá-las.

Duas flags **derivadas** do v5 não vêm: `isRoof` (da heurística de telhado de 5 flags) e
`hookDirection` (da de orientação de parede). As duas respondiam "onde isso desenha?", que agora é a
pilha quem responde. `isFloorTransition` continua vindo — também é derivada, mas responde uma
pergunta de lógica de jogo (pisar aqui muda de floor? — [ADR 0002](../docs/adr/0002-map-json-floors-e-defaultz.md)).

## `sheets` — folhas por footprint

```jsonc
"sheets": {
  "sheet-32": { "image": "assets/<mapa>-sprites-v6/sheets/sheet-32.png",
                "cellWidth": 32, "cellHeight": 32, "columns": 64 },
  "sheet-64": { "image": "assets/<mapa>-sprites-v6/sheets/sheet-64.png",
                "cellWidth": 64, "cellHeight": 64, "columns": 32 }
}
```

Uma folha é identificada **só pelo tamanho de célula** — ground e item dividem a mesma folha, porque
não há mais papel de renderização para separá-los. Na prática cada mapa emite 2.

Posição de um `gid` dentro da folha é aritmética pura, sem arquivo de atlas:

```
col = gid % columns
row = floor(gid / columns)
x   = col * cellWidth
y   = row * cellHeight
```

O sprite fica alinhado ao **canto superior-esquerdo** da célula; uma célula é sempre quadrada e uma
célula vazia é transparente. No Phaser, `scene.load.spritesheet(key, image, { frameWidth: cellWidth,
frameHeight: cellHeight })` dá exatamente essa numeração.

Nenhum mapa produz folha acima de 2048px em qualquer dimensão — o limite que toda GPU garante. A
grade preenche a largura segura primeiro, o que trava a capacidade de cada folha em 2048×2048.

## `monsters/respawn.json`

Cópia idêntica à do v5, no mesmo lugar relativo, para a árvore v6 ser autossuficiente. Formato
inalterado — ver [`PHASER_MONSTERS.md`](PHASER_MONSTERS.md).

## O que sumiu do v5

| v5 | v6 |
|---|---|
| `layerClass` por aparência | nada — o slot vem da flag `bank` na leitura, e a ordem já está na pilha |
| `depthOffset` por layer | nada — profundidade é a posição na varredura |
| 7 objectgroups (`Borders`, `Bottom`, `WallsSouth`, `WallsEast`, `Objects`, `Top`, `Roof`) | a pilha da tile |
| tilelayer `Ground` + `tilesets` + `firstgid` | o slot de chão da tile, na mesma folha dos itens |
| `wallOrientation` | nada — orientação de parede não afetava desenho |
| `objectDefs` | `appearances` |
| `animations` no topo | `animation` dentro da entrada da aparência |
| `metadata.json` ao lado | continua saindo no v5 (tem consumidor fora deste repo) |
