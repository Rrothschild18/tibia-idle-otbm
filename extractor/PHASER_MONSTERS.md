# Phaser Monsters Integration — respawn.json & Outfits

Documento complementar ao "Phaser Integration Guide" para carregar monstros, animações e respawns gerados pelo `phaserOTBM_converter.py`.

---
## Arquivos gerados

| File | Conteúdo |
|------|----------|
| `map.json` | Map layers, tilesets, objectDefs (sem monstros) |
| `monsters/respawn.json` | Definições de monstros (animações, referência de atlas) + lista de spawns |
| `atlases/outfits/<outfitId>.png` + `.json` | Atlas global do outfit (gerado uma vez por `bake_outfit_atlas.py`, compartilhado por todos os mapas — ver `.scratch/outfit-sprite-atlas/`) |
| `sprites/outfits/<outfitId>/<outfitId>.json` | Metadados originais do outfit (usado na geração do respawn.json e do atlas) |

Carregue **map.json** primeiro (para obter `bounds`), depois `monsters/respawn.json`. Cada mapa
não copia mais sprites de outfit para dentro do seu próprio diretório de saída — o atlas de cada
outfit é gerado uma única vez, globalmente, e reaproveitado (e cacheado pelo navegador) por
qualquer mapa que o referencie.

---
## Estrutura de `respawn.json`

```jsonc
{
  "mapBoundsRef": { "minX": ..., "minY": ..., "maxX": ..., "maxY": ... },
  "monsterDefs": {
    "300": {
      "name": "Grim Reaper",
      "outfitId": 300,
      "atlas": { "image": "assets/outfits/300.png", "json": "assets/outfits/300.json" },
      "idle": {
        "south": "300_0", "east": "300_1", "north": "300_2", "west": "300_3"
      },
      "moving": {
        "south": { "frames": ["300_4".."300_11"], "frameRate": 3.33, "loopType": "infinite" },
        "east":  { "frames": ["300_12".."300_19"], "frameRate": 3.33, "loopType": "infinite" },
        "north": { "frames": ["300_20".."300_27"], "frameRate": 3.33, "loopType": "infinite" },
        "west":  { "frames": ["300_28".."300_35"], "frameRate": 3.33, "loopType": "infinite" }
      }
    }
  },
  "spawns": [
    {
      "name": "Grim Reaper",
      "outfitId": 300,
      "tileX": 8, "tileY": 10,
      "worldX": 998, "worldY": 1020, "worldZ": 7,
      "radius": 1,
      "spawntime": 90
    }
  ]
}
```

### Campos-chave
- `atlas`: caminho do par imagem+JSON do atlas global daquele outfit (`assets/outfits/<outfitId>.{png,json}`).
  Pode ser `null` se `bake_outfit_atlas.py` ainda não rodou para aquele outfit — nesse caso o mapa
  foi gerado mesmo assim (não é um erro fatal), mas o outfit não vai renderizar até o atlas existir.
- `monsterDefs`: uma entrada por `outfitId` com mapeamento de animações/direções.
- `spawns`: posição de cada spawn em coordenadas de tile (`tileX`, `tileY`), coordenadas Tibia (`worldX`, `worldY`) e o floor (`worldZ`).
- `mapBoundsRef`: mesmo bounds do `map.json` (usado para converter coordenadas Tibia → tileX/tileY). Bounds são a união de todos os floors do mapa — ver `map.json`'s `floors`/`defaultZ` (`PHASER_INTEGRATION.md`) — então `tileX`/`tileY` já vêm corretos independente de qual floor o spawn pertence.
- `worldZ`: floor (z-level) onde aquele spawn deve existir. Um mapa com mais de um floor tem spawns com `worldZ` diferentes; o consumidor **deve filtrar `spawns` pelo floor ativo do jogador** antes de instanciar monstros — spawnar um monstro cujo `worldZ` não é o floor atualmente renderizado o coloca fora da vista, sobre um chão que não existe naquele contexto.

---
## Convenções de animação de outfits

Segue o guia de `OUTFIT_SPRITES_DOCUMENTATION.md` (mesmo layout Tibia):
- 4 sprites **idle** (parado): sul, leste, norte, oeste.
- 32 sprites **moving**: 8 frames × 4 direções, ordem sul → leste → norte → oeste.
- Chaves de frame: `<outfitId>_<index>` — mesmas chaves de antes, só que agora resolvidas dentro do
  atlas do outfit (`def.atlas`) em vez de arquivos soltos em `monsters/<outfitId>/`.

---
## Fluxo de carregamento no Phaser (exemplo TypeScript)

```ts
async function loadMonsters(scene: Phaser.Scene, mapData: MapData) {
  const respawn = await scene.load.json('respawn', `${mapData.assetsRoot}/monsters/respawn.json`).start();
  const data = scene.cache.json.get('respawn');

  // Preload one shared atlas per outfit instead of one image per frame.
  // The same outfitId resolves to the same atlas key across every map, so
  // Phaser's texture cache dedupes it automatically if it was already
  // loaded for a previous hunt spot.
  for (const [outfitId, def] of Object.entries<any>(data.monsterDefs)) {
    if (!def.atlas) continue; // atlas not baked yet for this outfit
    if (!scene.textures.exists(outfitId)) {
      scene.load.atlas(outfitId, def.atlas.image, def.atlas.json);
    }
  }
  await scene.load.startAsync();

  // Criar animações Phaser
  for (const [outfitId, def] of Object.entries<any>(data.monsterDefs)) {
    for (const [dir, anim] of Object.entries<any>(def.moving || {})) {
      const key = `${outfitId}-walk-${dir}`;
      scene.anims.create({
        key,
        // frame keys reference regions inside the outfit's atlas texture,
        // not separate textures — same frame-key strings as before, just
        // resolved against `outfitId`'s atlas instead of their own image.
        frames: anim.frames.map((f: string) => ({ key: outfitId, frame: f })),
        frameRate: anim.frameRate ?? 6,
        repeat: anim.loopType === 'infinite' ? -1 : 0,
      });
    }
  }

  return data;
}
```

### Instanciando monstros

```ts
function spawnMonsters(scene: Phaser.Scene, mapData: MapData, respawn: any) {
  const tileSize = mapData.tilewidth;
  for (const spawn of respawn.spawns) {
    const def = respawn.monsterDefs[String(spawn.outfitId)];
    if (!def) continue;

    // Escolhe frame idle sul como frame inicial dentro do atlas do outfit
    const idleSouth = def.idle?.south || Object.values(def.idle || {})[0];
    const x = (spawn.tileX + 1) * tileSize;
    const y = (spawn.tileY + 1) * tileSize;
    const sprite = scene.add.sprite(x, y, String(spawn.outfitId), idleSouth);
    sprite.setOrigin(1, 1);

    // Usa animação de caminhada sul se existir
    const walkKey = `${spawn.outfitId}-walk-south`;
    if (scene.anims.exists(walkKey)) {
      sprite.play(walkKey);
    }
  }
}
```

### Conversão de coordenadas
- `tileX/tileY` já estão ajustados com base em `mapBoundsRef` (x - minX, y - minY). Basta multiplicar por `tilewidth/tileheight`.
- `worldX/worldY` são absolutos em coordenadas Tibia; use apenas se precisar de referência global.

---
## Layers e classificação manual (resumo)

| Layer | depthOffset | Origem |
|-------|-------------|--------|
| Ground  | 0   | tilelayer (tileid) |
| Borders | 1   | **Somente manual** (BORDER_IDS) |
| Bottom  | 5   | flag bottom |
| Walls   | 8   | **Somente manual** (WALL_IDS) |
| Objects | 10  | fallback/objetos |
| Top     | 50  | flag top |
| Roof    | 100 | **Somente manual** (ROOF_IDS) |

Manual overrides vivem em `item_classifier.py`; flags automáticas só atuam em bottom/object/top.

---
## Checklist para usar monstros
- [ ] Garantir que os outfits necessários estão extraídos em `sprites/outfits/<id>/` e que
      `bake_outfit_atlas.py` já gerou `atlases/outfits/<id>.{png,json}` para eles
- [ ] Preload de um `scene.load.atlas(outfitId, ...)` por outfit referenciado (dedupado pelo cache
      de texturas do Phaser entre mapas)
- [ ] Criar animações Phaser usando `moving` de cada direção (frames dentro do atlas do outfit)
- [ ] Usar `tileX/tileY` para posicionar: `(tile + 1) * 32`, origem (1,1)
- [ ] Opcional: usar `radius`/`spawntime` para sua lógica de respawn em runtime
