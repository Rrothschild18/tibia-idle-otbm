# 02 — `build_phaser_map.py` referencia o atlas global em vez de copiar sprites por mapa

**What to build:** A geração de `monsters/respawn.json` por mapa (`build_monster_respawn()`) para
de copiar os PNGs soltos de cada outfit para dentro do diretório de saída daquele mapa
(`monsters/<outfitId>/*.png`, via `_copy_outfit_sprites()`) e passa a referenciar o atlas global
compartilhado daquele outfit (gerado pelo ticket 01, em `extractor/atlases/outfits/<id>.{png,json}`)
por ID. Cada `monsterDefs[<id>]` ganha um campo `atlas: {image, json}` apontando para o caminho de
asset compartilhado (`assets/outfits/<id>.png` / `.json`); os campos `assetsPath` (por outfit) e
`assetsRoot` (topo do `respawn.json`) são removidos, já que nada mais é copiado para
`monsters/<outfitId>/`. As chaves de frame dentro de `idle`/`moving` (ex.: `"300_0"`) não mudam —
só o arquivo para o qual elas resolvem no cliente.

**Blocked by:** 01

**Status:** ready-for-agent

- [x] Novas constantes `OUTFITS_ATLAS_DIR` (`extractor/atlases/outfits`, mesma pasta física
      escrita pelo ticket 01) e `OUTFITS_ATLAS_ASSETS_ROOT` (`assets/outfits`) em
      `build_phaser_map.py`, seguindo a mesma convenção de `OUTFITS_SPRITES_DIR`/`ASSETS_ROOT` já
      existentes.
- [x] Nova função `_outfit_atlas_ref(outfit_id)` — retorna `{"image": ..., "json": ...}` se os dois
      arquivos existirem em `OUTFITS_ATLAS_DIR`, senão `None` com um `[WARN]` no mesmo estilo dos
      warnings já existentes de outfit/JSON ausente (não lança exceção — mapas podem ser buildados
      antes do atlas de um outfit específico existir).
- [x] `_copy_outfit_sprites()` removida (não tem mais nenhum call site).
- [x] `build_monster_respawn()`: `monster_defs[outfit_id_str]` ganha `"atlas": _outfit_atlas_ref(outfit_id)`
      no lugar de `"assetsPath"`; o dict `respawn` de topo perde a chave `"assetsRoot"`.
- [x] `MONSTERS_ASSETS_ROOT` removida (não tem mais nenhum uso).
- [x] Testes em `extractor/tests/` (estilo `test_build_phaser_map_baking.py`: monkeypatch de
      globais do módulo + fixtures em `tmp_path`):
  - `build_monster_respawn` com um outfit cujo atlas existe em `OUTFITS_ATLAS_DIR` (monkeypatched
    para uma fixture `tmp_path`) produz `monsterDefs[id]["atlas"] == {"image": ..., "json": ...}`.
  - `build_monster_respawn` com atlas ausente produz `monsterDefs[id]["atlas"] is None` sem lançar
    exceção.
  - Nenhum arquivo é copiado para `MONSTERS_OUTPUT_DIR/<outfitId>/` (a pasta não é mais criada por
    outfit).
  - As chaves de frame em `idle`/`moving` continuam idênticas às do `spriteId` da fixture de
    outfit (não regride o comportamento existente de `_build_outfit_anims`).
- [x] `extractor/PHASER_MONSTERS.md` atualizado: novo formato de `respawn.json` (campo `atlas` em
      vez de `assetsPath`/`assetsRoot`), e o exemplo de carregamento em TypeScript trocado de N
      chamadas `scene.load.image()` por frame para uma chamada
      `scene.load.atlas(String(outfitId), def.atlas.image, def.atlas.json)`, mantendo as mesmas
      chaves de frame nas chamadas de `scene.anims.create()`.
- [x] `extractor/CONVERTER_DOCS.md`: nota sobre o novo diretório global `extractor/atlases/outfits/`
      e o fato de que `monsters/<outfitId>/*.png` não é mais gerado por mapa.
- [x] `node extractor/scripts/build_map.js --all` rodado após rodar `bake_outfit_atlas.py`,
      regerando os `monsters/respawn.json` dos mapas com spawn de monstros (`troll-rookguard`,
      `rats-rookguard`, `skeletons-rookguard`, `rats-sewers`, `grim-reaper`, `dragon-darashia`) —
      confirmar visualmente que nenhum tem mais `monsters/<outfitId>/` nem `assetsPath`, e que
      todos têm `atlas.image`/`atlas.json` apontando para `assets/outfits/<id>.*`.

## Comments

**2026-07-26** — Implementado em `extractor/scripts/build_phaser_map.py` via TDD (3 testes em
`extractor/tests/test_build_monster_respawn_atlas.py`). `_copy_outfit_sprites` removida,
substituída por `_outfit_atlas_ref` (tolerante a atlas ausente, mesmo padrão de warning que já
existia para outfit JSON ausente). `MONSTERS_ASSETS_ROOT` e os campos `assetsRoot`/`assetsPath`
removidos do `respawn.json`.

Rodado `node build_map.js --all` nos 8 mapas reais: todos os `monsters/respawn.json` gerados têm
`atlas.image`/`atlas.json` apontando para `assets/outfits/<id>.*` e nenhum tem mais
`assetsPath`/`assetsRoot`. As pastas `monsters/<outfitId>/` que sobravam de builds anteriores (9
pastas, uma por outfit único entre os 8 mapas) foram removidas manualmente — são saída gerada e
gitignorada, `build_phaser_map.py` não limpa arquivos de execuções antigas, só não cria mais
pastas novas.

Atualizada também a documentação (`PHASER_MONSTERS.md`, `CONVERTER_DOCS.md`): o exemplo de
carregamento em TypeScript trocou N `scene.load.image()` por outfit por um único
`scene.load.atlas(outfitId, ...)`, e a criação de animação/sprite ajustada para referenciar frames
dentro do atlas (`{key: outfitId, frame: f}` em vez de `{key: f}`) — não é só uma troca de
chamada de load, o `AnimationFrameConfig` do Phaser também muda de forma quando os frames deixam
de ser texturas próprias.
