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
  "width": 60,                  // map width in tiles — union across ALL floors
  "height": 42,                 // map height in tiles — union across ALL floors
  "bounds": { "minX": ..., "minY": ..., "maxX": ..., "maxY": ... },
  "defaultZ": 7,                 // floor to render by default (7 if present, else lowest z)
  "assetsRoot": "assets/dragon-darashia-sprites",

  "objectDefs": { ... },        // appearance definitions (see below) — global, shared by every floor
  "floors": {                    // one entry per floor (z-level) present in the map
    "7": { "z": 7, "layers": [ ... ] },  // ground tilelayer + objectgroups, same shape as before
    "8": { "z": 8, "layers": [ ... ] }
  },
  "tilesets": [ ... ],          // one tileset entry per ground tile ID — global, shared by every floor
  "animations": { ... }         // animated appearance configs — global, shared by every floor
}
```

### Floors

Maps can have more than one real floor (z-level) — e.g. a dungeon directly beneath the surface.
`layers` used to live at the map root; it now lives per floor under `floors["<z>"].layers`, same
shape as before. `width`/`height`/`bounds` stay a **union across all floors**, so `(tileX,
tileY)` means the same physical column on every floor — this is what lets a floor-transition
tile "line up" between floors without needing explicit destination metadata. See
[ADR 0002](../docs/adr/0002-map-json-floors-e-defaultz.md) for the full rationale, including why
`"version"` didn't change and how floor-transition tiles (stairs/holes) are flagged via the
derived `objectDefs[id].flags.isFloorTransition` boolean.

Single-floor maps just produce `floors: {"7": {...}}` — no special-casing needed on the consumer
side.

---

## `objectDefs` — Appearance Definitions

Every unique appearance ID used in the map has **one** entry in `objectDefs`. This is where all static/shared properties live.

```jsonc
{
  "objectDefs": {
    "4427": {
      "type": "random",                         // "static" | "random" | "animated"
      "layerClass": "roof",                      // "border" | "bottom" | "object" | "top" | "roof"
      "sheet": "roof-64",                        // key into root `sheets`
      "gids": [0, 1],                            // cell indices within that sheet, one per frame
      "spriteWidth": 64,                         // only present if ≠ 32
      "spriteHeight": 64,                        // only present if ≠ 32
      "random": true,                            // only present if true
      "flags": { "fullbank": true, "unpass": true, ... }  // only true flags
    },
    "1711": {
      "type": "static",
      "layerClass": "border",
      "sheet": "border-32",
      "gids": [4],
      "flags": { "unmove": true, "clip": true }
    }
  }
}
```

Since map.json v4 (`docs/adr/0003-map-json-v4-grid-sheets.md`), sprite frames are `sheet`+`gids`
instead of a `spriteIds` path list — see "Root `sheets` Field" below. An entry with neither
`sheet` nor `gids` was only ever seen as a ground `tileid`, never placed as an object; nothing
looks it up dynamically. (Static scenery baking, a separate offline-compositing mechanism, was
removed — see `docs/adr/0004-remover-bake-usar-so-sheets.md` — so there's no `bakedOnly` field or
`bakedgroup` layer type anymore either.)

### Root `sheets` Field

```jsonc
{
  "sheets": {
    "roof-64": { "image": "assets/dragon-darashia-sprites/sheets/roof-64.png", "cellWidth": 64, "cellHeight": 64, "columns": 12 },
    "border-32": { "image": "assets/dragon-darashia-sprites/sheets/border-32.png", "cellWidth": 32, "cellHeight": 32, "columns": 16 }
  }
}
```

One entry per `(layerClass, sizeBucket)` combination that had at least one placed appearance.
`ground`/`tilesets` are unaffected — the tilelayer still resolves through `tilesets`, one PNG per
unique ground appearance, exactly as before.

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

### Sprite Frame Resolution

A sprite frame is a cell inside a shared grid sheet — resolve its pixel rect with pure arithmetic,
no per-sprite path or atlas JSON needed:

```typescript
interface SheetDef {
  image: string;
  cellWidth: number;
  cellHeight: number;
  columns: number;
}

function gidToRect(gid: number, sheet: SheetDef) {
  const col = gid % sheet.columns;
  const row = Math.floor(gid / sheet.columns);
  return { x: col * sheet.cellWidth, y: row * sheet.cellHeight, width: sheet.cellWidth, height: sheet.cellHeight };
}

// Example: def.sheet = "roof-64", def.gids = [0, 1], sheets["roof-64"].columns = 12
// gid 1 -> col 1, row 0 -> pixel (64, 0)
```

Loaded into Phaser via `scene.load.spritesheet(sheetKey, sheets[sheetKey].image, { frameWidth: cellWidth, frameHeight: cellHeight })`,
`gid` is directly usable as the Phaser frame index — no separate rect math needed at draw time.

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
    sheet: def.sheet,
    gids: def.gids,
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
interface SheetDef {
  image: string;
  cellWidth: number;
  cellHeight: number;
  columns: number;
}

interface MapData {
  tilewidth: number;
  tileheight: number;
  assetsRoot: string;
  defaultZ: number;
  objectDefs: Record<string, ObjectDef>;
  sheets: Record<string, SheetDef>;
  floors: Record<string, { z: number; layers: Layer[] }>;
  tilesets: Tileset[];
  animations: Record<string, AnimationDef>;
}

function getFloorLayers(mapData: MapData, z: number): Layer[] {
  return mapData.floors[String(z)]?.layers ?? [];
}

interface ObjectDef {
  type: 'static' | 'random' | 'animated';
  layerClass: string;
  sheet?: string;   // absent for ground-only entries (never placed as an object)
  gids?: number[];
  spriteWidth?: number;
  spriteHeight?: number;
  random?: boolean;
  animated?: boolean;
  hasSprite?: boolean;
  flags?: Record<string, boolean>;
  issues?: string[];
}

const activeZ = mapData.defaultZ; // whichever floor is currently active
for (const layer of getFloorLayers(mapData, activeZ)) {
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
      if (!def || def.hasSprite === false || !def.sheet) continue;

      const gid = selectGid(def, seed, appearanceId);

      const image = scene.add.image(worldX, worldY, def.sheet, gid);
      image.setOrigin(1, 1);
      image.setDepth(
        (tileY + 1) * depthFactor + stackIndex * 0.001 + depthOffset
      );
    }
  }
}
```

### Gid Selection

```typescript
function selectGid(def: ObjectDef, seed: number, appearanceId: number): number {
  const gids = def.gids ?? [];
  if (def.type === 'animated') {
    return gids[0]; // animation itself plays through scene.anims (see below), this is the idle frame
  }
  if (def.random && gids.length > 1) {
    const index = Math.abs(seed * appearanceId) % gids.length;
    return gids[index];
  }
  return gids[0];
}
```

Animated appearances additionally need one `scene.anims.create()` registered per appearance, with
`frames: def.gids.map(gid => ({ key: def.sheet, frame: gid }))` — same shape as the outfit atlas
animation setup in `PHASER_MONSTERS.md`, just sourced from `gids` instead of frame-key strings.

### Preloading Sheets

```typescript
function preloadSheets(scene: Phaser.Scene, mapData: MapData) {
  for (const [sheetKey, sheet] of Object.entries(mapData.sheets)) {
    scene.load.spritesheet(sheetKey, sheet.image, {
      frameWidth: sheet.cellWidth,
      frameHeight: sheet.cellHeight,
    });
  }
}
```

One request per sheet (typically a handful per map — one per `(layerClass, sizeBucket)`
combination actually used) instead of one request per unique appearance.

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

  loadObjectLayers(mapData: MapData, scene: Phaser.Scene, z: number) {
    for (const layer of getFloorLayers(mapData, z)) {
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
- [ ] Read `spriteWidth`/`spriteHeight` from `objectDefs[id]`, defaulting to `tilewidth`/`tileheight` when absent
- [ ] Read flags from `objectDefs[id].flags` (only true flags stored, absent = false)
- [ ] Load `metadata.json` separately only when raw Tibia metadata is needed
- [ ] Remove any code that reads `spritePaths`, `metadataFound`, or `layerClassification` from entries
- [ ] Object arrays are `[tileX, tileY, ...entries]` not `{tileX, tileY, stack: [...]}` 

## Migration Checklist (v3 → v4, sheets)

Note: this doc's own v1→v2→v3 numbering is informal and historically hasn't tracked the real
`map.json` `"version"` field (see `docs/adr/0002-map-json-floors-e-defaultz.md`) — this section
happens to also be the change that bumps the real `version` field to `4`, see
`docs/adr/0003-map-json-v4-grid-sheets.md`.

- [ ] Parse the new root `sheets` field; `scene.load.spritesheet()` once per sheet instead of
      `scene.load.image()` once per appearance/frame
- [ ] Replace all `objectDefs[id].spriteIds` reads with `objectDefs[id].sheet` + `.gids`
- [ ] Resolve a frame as `scene.add.image(worldX, worldY, def.sheet, gid)` (texture key + frame
      index), not a bare texture key
- [ ] Animated appearances: build `scene.anims.create()` frames as `{ key: def.sheet, frame: gid }`
      per gid, not `{ key: spriteId }`
- [ ] `ground`/`tilesets` loading is unaffected — no change needed there
- [ ] An `objectDefs` entry with no `sheet`/`gids` was ground-only (never placed as an object) —
      skip it, there's nothing to render dynamically
- [ ] If your existing loader still reads `bakedgroup` layers or `objectDefs[id].bakedOnly`,
      remove that code — static scenery baking was removed (`docs/adr/0004-remover-bake-usar-so-sheets.md`);
      every dynamic appearance now goes through `sheet`+`gids` uniformly

---

## Size Comparison

| Format | map.json Lines | map.json Size |
|--------|---------------|--------------|
| v1 (verbose, all fields inline) | ~600,000+ | ~20+ MB |
| v2 (no paths, true-only flags) | ~330,000 | ~8.7 MB |
| v3 (objectDefs + compact arrays) | ~81,000 | ~1.1 MB |
| v4 (sheets — `objectDefs[id].spriteIds` → `.sheet`+`.gids`) | **~81,000** | **~1.1 MB** |

Reduction: **~87% fewer lines** vs v1. v4 doesn't change `map.json`'s own size meaningfully — the
win is in asset *requests*: a map's unique-appearance count no longer equals its sprite request
count, since many appearances now share one sheet request.
