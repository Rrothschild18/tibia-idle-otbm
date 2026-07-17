# Wall Depth & Orientation System

## Problema

Num mapa isométrico estilo Tibia, as paredes precisam de profundidades diferentes
dependendo da orientação:

- **Paredes verticais** (borda oeste da sala) precisam renderizar **POR CIMA** do
  jogador quando ele está ao lado — a perspectiva isométrica faz com que a parede
  à esquerda esteja "mais perto da câmera".
- **Paredes horizontais** (borda norte da sala) ficam **ATRÁS** do jogador —
  o sorting natural por Y já resolve esse caso.

```
VISTA ISOMÉTRICA (câmera olhando de cima-esquerda para baixo-direita)

     x=25  26  27  28  29  30  31
y=35: [NW] [──] [──] [──] [──] [──] [NE]   ← WallsSouth (horizontal, topo)
y=36: [│ ]  .    .    .    .    .   [│ ]   ← WallsEast (vertical, lados)
y=37: [│ ]  .   [P]   .    .    .   [│ ]   ← jogador [P] ao lado da parede
y=38: [SW] [──] [──] [──] [──] [──] [SE]   ← WallsSouth (horizontal, base)
```

## Solução: 2 Layers Separados

O converter agora gera **dois layers** de parede em vez de um:

| Layer | depthOffset | Orientação | Renderiza | hookDirection |
|-------|-------------|------------|-----------|---------------|
| **WallsSouth** | 3 | Horizontal + cantos | ATRÁS do jogador | `HOOK_TYPE_SOUTH` ou sem hook |
| **WallsEast** | 12 | Vertical | POR CIMA do jogador | `HOOK_TYPE_EAST` |

### Comparação com outras layers

```
Ground          depthOffset = 0    (tilelayer)
Borders         depthOffset = 1    (clip/transições)
WallsSouth      depthOffset = 3    (paredes horizontais — atrás do player)
Bottom          depthOffset = 5    (decorações de chão)
Objects         depthOffset = 10   (móveis, árvores, etc.)
WallsEast       depthOffset = 12   (paredes verticais — na frente do player)
Top             depthOffset = 50   (bandeiras, sinais)
Roof            depthOffset = 100  (telhados, bloqueio de visão)
```

## Como funciona a classificação

### Detecção automática (flags do metadata)

Um item é automaticamente detectado como parede quando possui **TODAS** as flags:
- `bottom: true`
- `unpass: true`
- `unmove: true`
- `unsight: true`
- `automap: present`
- NÃO tem `top: true`
- NÃO é roof (sprite > 1x1 com bank)

### Orientação via `hookDirection`

O campo `hook.direction` no JSON do sprite indica para que lado a parede "olha":

| hookDirection | wallOrientation | Layer | Significado |
|---------------|-----------------|-------|-------------|
| `HOOK_TYPE_EAST` | `east` | WallsEast | Parede vertical (borda oeste da sala) |
| `HOOK_TYPE_SOUTH` | `south` | WallsSouth | Parede horizontal (borda norte da sala) |
| ausente | `corner` | WallsSouth | Canto, pilar, peça de junção |

### Exemplo: IDs 1294-1304

| ID | hookDirection | Orientação | pattern | Função |
|----|---------------|------------|---------|--------|
| 1294 | HOOK_TYPE_EAST | east | 1×2 | Parede vertical (borda oeste) |
| 1295 | HOOK_TYPE_SOUTH | south | 2×1 | Parede horizontal (borda norte) |
| 1296 | — | corner | 1×1 | Canto noroeste |
| 1297 | — | corner | 2×1 | Pilar sudeste |
| 1298 | — | corner | 1×1 | Canto sudoeste |
| 1299 | — | corner | 1×2 | Pilar nordeste |
| 1300 | HOOK_TYPE_EAST | east | 1×1 | Parede vertical variante |
| 1301 | — | corner | 1×2 | Porta/janela em parede vertical |
| 1302 | HOOK_TYPE_SOUTH | south | 1×1 | Parede horizontal variante |
| 1303 | — | corner | 2×1 | Parede larga sem hook |
| 1304 | — | corner | 1×1 | Peça avulsa |

## Output no map.json

### objectDefs

Cada item de parede no `objectDefs` agora inclui:

```json
{
  "1294": {
    "type": "static",
    "layerClass": "walls_east",
    "wallOrientation": "east",
    "spriteIds": ["1294_0", "1294_1"],
    "flags": {
      "unmove": true,
      "unpass": true,
      "unsight": true,
      "automap": true,
      "bottom": true,
      "hookDirection": "HOOK_TYPE_EAST"
    }
  },
  "1295": {
    "type": "static",
    "layerClass": "walls_south",
    "wallOrientation": "south",
    "spriteIds": ["1295_0", "1295_1"],
    "flags": { "..." }
  },
  "1296": {
    "type": "static",
    "layerClass": "walls_south",
    "wallOrientation": "corner",
    "spriteIds": ["1296"],
    "flags": { "..." }
  }
}
```

### Layers

```json
{
  "name": "WallsSouth",
  "type": "objectgroup",
  "properties": {
    "depthOffset": 3,
    "layerClass": "walls_south"
  }
},
{
  "name": "WallsEast",
  "type": "objectgroup",
  "properties": {
    "depthOffset": 12,
    "layerClass": "walls_east"
  }
}
```

## Classificação manual (item_classifier.py)

### Três opções para paredes

1. **`WALL_IDS`** — classificação genérica "walls" → o converter resolve automaticamente
   em `walls_east` ou `walls_south` baseado no `hookDirection` do metadata.

2. **`WALL_EAST_IDS`** — força a parede para o layer WallsEast (depth alto), ignorando
   o hookDirection. Use quando o metadata está errado ou ausente.

3. **`WALL_SOUTH_IDS`** — força para WallsSouth (depth baixo).

### Exemplo

```python
# item_classifier.py

# Genérico (resolve via hook):
WALL_IDS = {1294, 1295, 1296, 1297, 1298}

# Forçar orientação:
WALL_EAST_IDS = {9999}   # este ID será sempre WallsEast
WALL_SOUTH_IDS = {8888}  # este ID será sempre WallsSouth
```

## Uso no Phaser

```javascript
// Ao criar sprites, usar o depthOffset do layer:
const depthOffset = layer.properties.depthOffset;

// Depth de cada sprite:
// depth = (tileY + 1) * DEPTH_FACTOR + depthOffset
//
// DEPTH_FACTOR deve ser grande o suficiente para separar Y-levels.
// Recomendado: DEPTH_FACTOR = 32 (tamanho do tile)
//
// Exemplo para tileY=5:
//   WallsSouth: depth = (5+1)*32 + 3  = 195  (atrás do player)
//   Player:     depth = (5+1)*32 + 10 = 202
//   WallsEast:  depth = (5+1)*32 + 12 = 204  (na frente do player)

function createSprite(tileX, tileY, layer) {
    const sprite = scene.add.sprite(
        (tileX + 1) * 32,
        (tileY + 1) * 32
    );
    sprite.setDepth(
        (tileY + 1) * 32 + layer.properties.depthOffset
    );
    return sprite;
}
```

## Resumo

| Pergunta | Resposta |
|----------|---------|
| Como saber se parede é esquerda/direita? | `hookDirection` no metadata do item |
| Onde fica essa info no map.json? | `objectDefs[id].wallOrientation` |
| Quantos layers de parede existem? | 2: WallsSouth (depth 3) e WallsEast (depth 12) |
| Posso forçar orientação manual? | Sim: `WALL_EAST_IDS` e `WALL_SOUTH_IDS` no item_classifier.py |
| E se o item não tem hookDirection? | Classificado como `corner` → vai para WallsSouth |
