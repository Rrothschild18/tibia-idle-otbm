# Phaser Integration Guide — Compact map.json Format (v3)

This document explains the **compact map.json** output from `phaserOTBM_converter.py` and how to load/render it in Phaser.

---

## Design Principles

1. **Define once, reference by ID** — All static properties of every appearance live in `objectDefs` (keyed by ID). Tile placements only store `[appearanceId, stackIndex]`.
2. **Derive, don't store** — Sprite paths, world positions, and default-value flags are computed at runtime, not serialized.
3. **Separate metadata** — Raw Tibia appearance metadata lives in `metadata.json` (one file per map), keeping `map.json` focused on rendering.

---

## Output Files

| File | Contents | Typical Size |
|------|----------|-------------|
| `map.json` | Layers, tilesets, objectDefs, animations | ~1 MB |
| `metadata.json` | Raw Tibia metadata keyed by appearance ID | ~65 KB |
| `sprites/` | PNG sprite files organized by appearance ID | varies |

---

## map.json Root Structure

```jsonc
{
  "version": 2,
  "orientation": "orthogonal",
  "renderorder": "right-down",
  "tilewidth": 32,              // TILE_SIZE constant
  "tileheight": 32,
  "width": 60,                  // map width in tiles
  "height": 42,                 // map height in tiles
  "bounds": { "minX": ..., "minY": ..., "maxX": ..., "maxY": ... },
  "assetsRoot": "assets/dragon-darashia-sprites",

  "objectDefs": { ... },        // appearance definitions (see below)
  "layers": [ ... ],            // ground tilelayer + objectgroups
  "tilesets": [ ... ],          // one tileset entry per ground tile ID
  "animations": { ... }         // animated appearance configs
}
```

---

## `objectDefs` — Appearance Definitions

Every unique appearance ID used in the map has **one** entry in `objectDefs`. This is where all static/shared properties live.

```jsonc
{
  "objectDefs": {
    "4427": {
      "type": "random",                         // "static" | "random" | "animated"
      "layerClass": "roof",                      // "border" | "bottom" | "object" | "top" | "roof"
      "spriteIds": ["4427_0", "4427_1", ...],    // sprite identifiers
      "spriteWidth": 64,                         // only present if ≠ 32
      "spriteHeight": 64,                        // only present if ≠ 32
      "random": true,                            // only present if true
      "flags": { "fullbank": true, "unpass": true, ... }  // only true flags
    },
    "1711": {
      "type": "static",
      "layerClass": "border",
      "spriteIds": ["1711"],
      "flags": { "unmove": true, "clip": true }
    }
  }
}
```

### Omitted / Default Fields

| Field | Default when absent |
|-------|-------------------|
| `spriteWidth` | `32` (= `tilewidth`) |
| `spriteHeight` | `32` (= `tileheight`) |
| `hasSprite` | `true` |
| `random` | `false` |
| `animated` | `false` |
| `flags` | `{}` (no flags set) |
| `issues` | `[]` |

---

## Deriving Values at Runtime

### Sprite Asset Paths

Sprite paths are **not stored** in the JSON. Derive them from `assetsRoot` and `spriteIds`:

```typescript
function spritePath(assetsRoot: string, appearanceId: string, spriteId: string): string {
  return `${assetsRoot}/sprites/${appearanceId}/${spriteId}.png`;
}

// Example: assetsRoot = "assets/dragon-darashia-sprites", appearance = "4427", spriteId = "4427_0"
// → "assets/dragon-darashia-sprites/sprites/4427/4427_0.png"
```

### World Position (pixels)

World position is derived from the tile coordinates in the object array:

```typescript
// Each object in an objectgroup is: [tileX, tileY, ...stackEntries]
const tileX = object[0];
const tileY = object[1];

// Bottom-right anchor (use origin(1,1) in Phaser)
const worldX = (tileX + 1) * mapData.tilewidth;
const worldY = (tileY + 1) * mapData.tileheight;
```

### Full Entry Reconstruction

```typescript
function resolveStackEntry(
  mapData: MapData,
  object: any[],
  stackEntry: [number, number],  // [appearanceId, stackIndex]
) {
  const [appearanceId, stackIndex] = stackEntry;
  const def = mapData.objectDefs[String(appearanceId)];
  const tileX = object[0];
  const tileY = object[1];

  return {
    appearanceId,
    stackIndex,
    type: def.type,
    layerClass: def.layerClass,
    spriteIds: def.spriteIds,
    spriteWidth: def.spriteWidth ?? mapData.tilewidth,
    spriteHeight: def.spriteHeight ?? mapData.tileheight,
    worldX: (tileX + 1) * mapData.tilewidth,
    worldY: (tileY + 1) * mapData.tileheight,
    random: def.random ?? false,
    animated: def.animated ?? false,
    hasSprite: def.hasSprite ?? true,
    flags: def.flags ?? {},
  };
}
```

---

## Layer Structure

```
┌─────────────────────────────────────────────────────┐
│  Roof      (objectgroup, depthOffset: 100)          │  unpass+unmove+unsight
│  Top       (objectgroup, depthOffset: 50)           │  top flag
│  Objects   (objectgroup, depthOffset: 10)           │  normal items
│  Bottom    (objectgroup, depthOffset: 5)            │  bottom flag
│  Borders   (objectgroup, depthOffset: 1)            │  clip flag
│  Ground    (tilelayer,   depthOffset: 0)            │  walkable tileids
└─────────────────────────────────────────────────────┘
```

Layers only appear if they have content. Order: Ground → Borders → Bottom → Objects → Top → Roof.

---

## Compact Object Format

### Old (verbose) format — **removed**:
```json
{
  "objects": [
    {
      "tileX": 30, "tileY": 12,
      "stack": [
        { "appearanceId": 1711, "type": "static", "layerClass": "border",
          "spriteIds": ["1711"], "spriteWidth": 32, "spriteHeight": 32,
          "worldX": 992, "worldY": 416, "stackIndex": 0,
          "flags": { "unmove": true, "clip": true } }
      ]
    }
  ]
}
```

### New (compact) format:
```json
{
  "objects": [
    [30, 12, [1711, 0]]
  ]
}
```

Each object is a flat array:
- `[0]` = `tileX`
- `[1]` = `tileY`
- `[2..n]` = stack entries, each `[appearanceId, stackIndex]`

Multiple items on same tile:
```json
[15, 20, [979, 0], [1032, 1], [4427, -1]]
```

---

## Phaser Renderer Implementation

### Loading Object Layers

```typescript
interface MapData {
  tilewidth: number;
  tileheight: number;
  assetsRoot: string;
  objectDefs: Record<string, ObjectDef>;
  layers: Layer[];
  tilesets: Tileset[];
  animations: Record<string, AnimationDef>;
}

interface ObjectDef {
  type: 'static' | 'random' | 'animated';
  layerClass: string;
  spriteIds: string[];
  spriteWidth?: number;
  spriteHeight?: number;
  random?: boolean;
  animated?: boolean;
  hasSprite?: boolean;
  flags?: Record<string, boolean>;
  issues?: string[];
}

for (const layer of mapData.layers) {
  if (layer.type !== 'objectgroup') continue;
  const depthOffset = layer.properties?.depthOffset ?? 0;

  for (const obj of layer.objects) {
    const tileX = obj[0];
    const tileY = obj[1];
    const worldX = (tileX + 1) * mapData.tilewidth;
    const worldY = (tileY + 1) * mapData.tileheight;

    // Stack entries start at index 2
    for (let i = 2; i < obj.length; i++) {
      const [appearanceId, stackIndex] = obj[i];
      const def = mapData.objectDefs[String(appearanceId)];
      if (!def || def.hasSprite === false) continue;

      const textureKey = selectTexture(def, seed, appearanceId);

      const image = scene.add.image(worldX, worldY, textureKey);
      image.setOrigin(1, 1);
      image.setDepth(
        (tileY + 1) * depthFactor + stackIndex * 0.001 + depthOffset
      );
    }
  }
}
```

### Texture Selection

```typescript
function selectTexture(def: ObjectDef, seed: number, appearanceId: number): string {
  if (def.type === 'animated') {
    return `${appearanceId}_anim`; // pre-registered Phaser animation key
  }
  if (def.random && def.spriteIds.length > 1) {
    const index = Math.abs(seed * appearanceId) % def.spriteIds.length;
    return def.spriteIds[index];
  }
  return def.spriteIds[0];
}
```

### Preloading Sprites

```typescript
function preloadSprites(scene: Phaser.Scene, mapData: MapData) {
  for (const [id, def] of Object.entries(mapData.objectDefs)) {
    for (const spriteId of def.spriteIds) {
      const path = `${mapData.assetsRoot}/sprites/${id}/${spriteId}.png`;
      scene.load.image(spriteId, path);
    }
  }
}
```

---

## Depth Offset Values

| Layer | `depthOffset` | Purpose |
|-------|---------------|---------|
| Ground | 0 | Base terrain (tilelayer) |
| Borders | 1 | Terrain transitions (clip flag) |
| Bottom | 5 | Ground decorations |
| Objects | 10 | Furniture, walls, trees |
| Top | 50 | Ceiling items, signs |
| Roof | 100 | Structural blocking (unpass+unmove+unsight) |

---

## `metadata.json` — Separate File

Raw Tibia appearance metadata is stored in a separate `metadata.json` file, **not** in `map.json`. Load it only if you need appearance details (e.g., tooltip info, collision data).

```jsonc
{
  "4427": {
    "metadata": {
      "id": 4427,
      "spriteInfo": { "patternWidth": 4, "patternHeight": 4, ... },
      "flags": { "unpass": true, "unmove": true, ... }
    },
    "spriteInfo": { "patternWidth": 4, ... },
    "flags": { "fullbank": true, "isRoof": true, ... },
    "animation": { ... }   // only for animated appearances
  }
}
```

Access: `const meta = metadataJson[String(appearanceId)]`

---

## Roof Visibility Toggle

```typescript
class TibiaMapRenderer {
  private roofImages: Phaser.GameObjects.Image[] = [];

  loadObjectLayers(mapData: MapData, scene: Phaser.Scene) {
    for (const layer of mapData.layers) {
      if (layer.type !== 'objectgroup') continue;
      const depthOffset = layer.properties?.depthOffset ?? 0;
      const isRoof = layer.properties?.layerClass === 'roof';

      for (const obj of layer.objects) {
        const tileX = obj[0], tileY = obj[1];
        const worldX = (tileX + 1) * mapData.tilewidth;
        const worldY = (tileY + 1) * mapData.tileheight;

        for (let i = 2; i < obj.length; i++) {
          const [id, si] = obj[i];
          const def = mapData.objectDefs[String(id)];
          const img = scene.add.image(worldX, worldY, selectTexture(def, this.seed, id));
          img.setOrigin(1, 1);
          img.setDepth((tileY + 1) * 10 + si * 0.001 + depthOffset);
          if (isRoof) this.roofImages.push(img);
        }
      }
    }
  }

  toggleRoof(visible: boolean) {
    for (const img of this.roofImages) img.setVisible(visible);
  }
}
```

---

## Migration Checklist (v2 → v3)

- [ ] Parse `objectDefs` from map root and build a lookup map
- [ ] Replace verbose stack entry reading with compact `[id, stackIndex]` array parsing
- [ ] Derive `worldX`/`worldY` from `tileX`/`tileY` (no longer in entry)
- [ ] Derive sprite paths from `assetsRoot + "/sprites/" + id + "/" + spriteId + ".png"`
- [ ] Read `spriteWidth`/`spriteHeight` from `objectDefs[id]`, defaulting to `tilewidth`/`tileheight` when absent
- [ ] Read flags from `objectDefs[id].flags` (only true flags stored, absent = false)
- [ ] Load `metadata.json` separately only when raw Tibia metadata is needed
- [ ] Remove any code that reads `spritePaths`, `metadataFound`, or `layerClassification` from entries
- [ ] Object arrays are `[tileX, tileY, ...entries]` not `{tileX, tileY, stack: [...]}` 

---

## Size Comparison

| Format | map.json Lines | map.json Size |
|--------|---------------|--------------|
| v1 (verbose, all fields inline) | ~600,000+ | ~20+ MB |
| v2 (no paths, true-only flags) | ~330,000 | ~8.7 MB |
| v3 (objectDefs + compact arrays) | **~81,000** | **~1.1 MB** |

Reduction: **~87% fewer lines** vs v1.
