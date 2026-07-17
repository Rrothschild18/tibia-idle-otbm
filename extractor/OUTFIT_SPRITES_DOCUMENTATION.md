# Documentação de Sprites de Outfits

Este documento descreve como as sprites de outfits extraídas do arquivo `.aec` estão organizadas e ordenadas para uso em animações no Phaser.js ou outros game engines.

## Estrutura de Pastas

```
sprites/outfits/
├── 2/
│   ├── 2_0.png    # IDLE - Sul (parado olhando para baixo)
│   ├── 2_1.png    # IDLE - Leste (parado olhando para direita) 
│   ├── 2_2.png    # IDLE - Norte (parado olhando para cima)
│   ├── 2_3.png    # IDLE - Oeste (parado olhando para esquerda)
│   ├── 2_4.png    # MOVING - Sul frame 0
│   ├── 2_5.png    # MOVING - Sul frame 1
│   ├── ...
│   ├── 2_35.png   # MOVING - Oeste frame 7 (último frame)
│   └── 2.json     # Metadados com frameGroups
├── 3/
│   ├── 3_0.png
│   ├── ...
```

## Organização das Sprites

### Frame Groups

Cada outfit possui 2 **frame groups**:

1. **IDLE** (`frameGroup: "idle"`) - Sprites estáticas
2. **MOVING** (`frameGroup: "moving"`) - Sprites de caminhada

### Ordem das Direções

As sprites seguem a ordem padrão do Tibia:

| Índice | Direção | Descrição |
|--------|---------|-----------|
| 0 | **Sul** | Personagem olhando para baixo ↓ |
| 1 | **Leste** | Personagem olhando para direita → |
| 2 | **Norte** | Personagem olhando para cima ↑ |
| 3 | **Oeste** | Personagem olhando para esquerda ← |

## Sprites IDLE (4 sprites)

As primeiras 4 sprites são sempre IDLE:

```
outfit_ID_0 = Sul (parado)
outfit_ID_1 = Leste (parado) 
outfit_ID_2 = Norte (parado)
outfit_ID_3 = Oeste (parado)
```

## Sprites MOVING (32 sprites)

As próximas 32 sprites são animação de caminhada, organizadas como:
- **8 frames por direção**
- **4 direções** (Sul, Leste, Norte, Oeste)

### Cálculo do Índice

```javascript
// Fórmula para calcular índice da sprite MOVING:
const movingStartIndex = 4; // Após as 4 sprites IDLE
const frameIndex = movingStartIndex + (direction * 8) + frameNumber;

// Exemplos:
// Sul frame 0:   4 + (0 * 8) + 0 = 4  → outfit_ID_4
// Sul frame 7:   4 + (0 * 8) + 7 = 11 → outfit_ID_11
// Leste frame 0: 4 + (1 * 8) + 0 = 12 → outfit_ID_12
// Leste frame 7: 4 + (1 * 8) + 7 = 19 → outfit_ID_19
// Norte frame 0: 4 + (2 * 8) + 0 = 20 → outfit_ID_20
// Norte frame 7: 4 + (2 * 8) + 7 = 27 → outfit_ID_27
// Oeste frame 0: 4 + (3 * 8) + 0 = 28 → outfit_ID_28
// Oeste frame 7: 4 + (3 * 8) + 7 = 35 → outfit_ID_35
```

### Mapeamento Completo

| Direção | Frames | Índices das Sprites |
|---------|---------|-------------------|
| **Sul** | 0-7 | `outfit_ID_4` até `outfit_ID_11` |
| **Leste** | 0-7 | `outfit_ID_12` até `outfit_ID_19` |
| **Norte** | 0-7 | `outfit_ID_20` até `outfit_ID_27` |
| **Oeste** | 0-7 | `outfit_ID_28` até `outfit_ID_35` |

## Arquivo JSON de Metadados

Cada outfit possui um arquivo `{ID}.json` com a seguinte estrutura:

```json
{
  "id": 2,
  "frameGroups": [
    {
      "spriteId": ["2_0", "2_1", "2_2", "2_3"],
      "frameGroup": "idle",
      "spriteInfo": {
        "patternWidth": 4,
        "patternHeight": 1,
        "patternDepth": 1,
        "layers": 1,
        "patternFrames": 0
      }
    },
    {
      "spriteId": ["2_4", "2_5", "2_6", ..., "2_35"], 
      "frameGroup": "moving",
      "spriteInfo": {
        "patternWidth": 4,
        "patternHeight": 1,
        "patternDepth": 1,
        "layers": 1,
        "patternFrames": 0,
        "animation": {
          "synchronized": false,
          "loopType": "ANIMATION_LOOP_TYPE_INFINITE",
          "spritePhase": [
            {"durationMin": 300, "durationMax": 300},
            {"durationMin": 300, "durationMax": 300},
            ...
          ]
        }
      }
    }
  ]
}
```

## Exemplo de Uso no Phaser.js

```javascript
// Carregar sprites de um outfit
const outfitId = 2;
const outfitPath = `sprites/outfits/${outfitId}/`;

// Sprites IDLE (1 por direção)
const idleSprites = {
    south: `${outfitPath}${outfitId}_0.png`,
    east:  `${outfitPath}${outfitId}_1.png`, 
    north: `${outfitPath}${outfitId}_2.png`,
    west:  `${outfitPath}${outfitId}_3.png`
};

// Sprites MOVING (8 frames por direção)
const movingSprites = {
    south: Array.from({length: 8}, (_, i) => `${outfitPath}${outfitId}_${4 + i}.png`),
    east:  Array.from({length: 8}, (_, i) => `${outfitPath}${outfitId}_${12 + i}.png`),
    north: Array.from({length: 8}, (_, i) => `${outfitPath}${outfitId}_${20 + i}.png`),
    west:  Array.from({length: 8}, (_, i) => `${outfitPath}${outfitId}_${28 + i}.png`)
};

// Criar animações no Phaser
this.anims.create({
    key: 'walk-south',
    frames: movingSprites.south.map(sprite => ({ key: sprite })),
    frameRate: 10,
    repeat: -1
});

this.anims.create({
    key: 'idle-south', 
    frames: [{ key: idleSprites.south }],
    frameRate: 1
});
```

## Direções no Sistema de Coordenadas

```
    Norte (2)
       ↑
Oeste (3) ← → Leste (1)  
       ↓
     Sul (0)
```

## Validação

- **Total de sprites por outfit padrão**: 36 (4 IDLE + 32 MOVING)
- **Duração típica dos frames**: 300ms 
- **Formato das sprites**: PNG 32x32 pixels
- **Loop das animações**: Infinito (`ANIMATION_LOOP_TYPE_INFINITE`)

## Notas Importantes

1. **Outfits com mais de 36 sprites** podem conter addons, layers ou montarias
2. **Pattern dimensions** informam se o outfit ocupa mais de 1 tile (ex: montarias grandes)
3. **Frames sempre começam do 0** na contagem interna
4. **Sprites são extraídas sequencialmente** do arquivo `.aec` conforme aparecem nos `frame_group`

Esta organização garante compatibilidade com sistemas de animação 2D e facilita a criação de múltiplas direções de movimento em jogos estilo RPG.