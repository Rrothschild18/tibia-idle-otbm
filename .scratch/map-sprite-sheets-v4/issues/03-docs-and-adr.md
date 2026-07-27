# 03 — Documentação e ADR do v4

**What to build:** Atualizar a documentação do conversor com o novo formato de `objectDefs`
(`sheet`+`gids`) e o campo raiz `sheets`, e registrar a decisão de grid fixo (em vez de packer tipo
TexturePacker) numa nova ADR, seguindo o estilo das ADRs 0001/0002 já existentes.

**Blocked by:** 02

**Status:** ready-for-agent

- [x] `docs/adr/0003-map-json-v4-grid-sheets.md` — decisão de grid fixo com colunas constantes por
      bucket de tamanho (32/64/128) em vez de bin-packing otimizado; por que o bump de `version`
      pra `4` (breaking change explícito, ao contrário da decisão aditiva da ADR 0002); referência
      ao protótipo (`prototype/sheet-packer-v4`) como evidência de validação.
- [x] `extractor/CONVERTER_DOCS.md`: seção "Output Format" atualizada — `objectDefs` mostra
      `sheet`+`gids` em vez de `spriteIds`; novo campo raiz `sheets`; nota de que `tilesets`
      (ground) não mudou.
- [x] `extractor/PHASER_INTEGRATION.md`: exemplo de carregamento trocado de `scene.load.image()`
      por aparência para `scene.load.spritesheet(sheetKey, sheets[sheetKey].image, {frameWidth,
      frameHeight})` por sheet; resolução de frame de uma aparência vira
      `scene.make.image({key: def.sheet, frame: def.gids[i], ...})`.

## Comments

**2026-07-27** — `docs/adr/0003-map-json-v4-grid-sheets.md` escrita, documentando grid fixo vs
bin-packing, colunas fixas por bucket, escopo (só `objectDefs`, não `ground`/`tilesets`), o bump
de `version` pra `4` (ao contrário da ADR 0002), a limitação conhecida da cópia solta redundante
(ver ticket 02), e a referência ao protótipo validado.

`extractor/CONVERTER_DOCS.md`: corrigido também o exemplo de "Objectgroup layers", que já estava
desatualizado (mostrava um formato verboso com `stack`/`spritePaths` que não existe mais desde a
mudança pra `objectDefs` + arrays compactos) — trocado por um exemplo real extraído de
`rats-rookguard` (`[42, 3, [5557, 0]]` + `objectDefs["5557"]`), já no formato v4 (`sheet`/`gids`).
Adicionado `sheet`/`gids` na seção de baking (entrada `bakedOnly` também não tem mais `spriteIds`
pra remover). Root object example atualizado pra `version: 4` + `floors`/`sheets`.

`extractor/PHASER_INTEGRATION.md`: atualizado `objectDefs` example, resolução de sprite (função
`gidToRect` em vez de `spritePath`), `ObjectDef`/`MapData`/`SheetDef` interfaces, o loop de
carregamento de objectgroup (`scene.add.image(worldX, worldY, def.sheet, gid)` em vez de resolver
uma texture key por path), seleção de gid (`selectGid`, substituindo `selectTexture`), preload
(`preloadSheets`, um `scene.load.spritesheet()` por sheet em vez de um `scene.load.image()` por
frame de cada aparência), e uma nova seção "Migration Checklist (v3 → v4, sheets)" com uma nota
explícita sobre a numeração informal deste doc (v1/v2/v3) não ter historicamente acompanhado o
campo `version` real do JSON (mesmo ponto já registrado na ADR 0002) — dessa vez elas coincidem
por acaso, não por design.
