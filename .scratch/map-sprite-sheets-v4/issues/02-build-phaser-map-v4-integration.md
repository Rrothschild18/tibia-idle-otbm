# 02 — `build_phaser_map.py` gera sheets em vez de PNGs soltos

**What to build:** Integrar o `SheetPacker` (ticket 01) em `build_phaser_map.py`: durante a
segunda passada (quando `_build_object_defs()` monta os defs finais), cada aparência com sprite
disponível é adicionada ao packer (`layer_class` já conhecido pela classificação existente,
`width`/`height` de `analysis["sprites"][0]`, `frame_count = len(analysis["sprites"])`). Ao final,
pra cada sheet do packer, renderizar o PNG real (`PIL.Image`, colando cada sprite na célula do seu
gid) e escrever em `{OUTPUT_DIR}/sheets/{sheetKey}.png`. `objectDefs` passa a ter `sheet`+`gids`
em vez de `spriteIds`; a raiz do `map.json` ganha o campo `sheets`; `"version"` sobe pra `4`.

**Blocked by:** 01

**Status:** ready-for-agent

- [~] ~~`ensure_sprite_assets()` deixa de copiar PNG por aparência para `sprites/<id>/<spriteId>.png`~~
      — não implementado assim; ver `## Comments` para o motivo e o trade-off aceito.
- [x] Nova função `_render_sheet(sheet_key, entries) -> Image` — cola cada sprite na célula do seu
      gid (`gid_to_rect`), canvas dimensionado por `sheet_dims`, mesmo padrão de composição
      (`PIL.Image.alpha_composite` ou `paste`) já usado em `_render_baked_row`.
- [x] `_build_object_defs()`: troca `entry["spriteIds"] = [...]` por `entry["sheet"] = sheet_key` +
      `entry["gids"] = gids` (usando o resultado do `SheetPacker`, mantendo a mesma ordem que
      `spriteIds` tinha — animações continuam funcionando só trocando path por gid).
- [x] `map.json` raiz ganha `"sheets": {sheetKey: {"image": ..., "cellWidth", "cellHeight",
      "columns"}}`; `"version"` muda de `1` (ou o valor atual) para `4`.
- [x] `tilesets` (ground) **não muda** — continua no formato v3, fora do escopo deste ticket.
- [x] Testes em `extractor/tests/` (estilo `test_build_phaser_map_baking.py`): `build_phaser_map()`
      com fixtures pequenas confirma que `objectDefs` tem `sheet`/`gids` (não `spriteIds`) e que
      `sheets` na raiz existe com as chaves esperadas.
- [x] `node build_map.js --all` rodado nos 8 mapas reais; inspeção visual de pelo menos 2 sheets
      gerados (abrir o PNG) confirmando que os sprites aparecem intactos nas células esperadas e
      batem com o `gid` registrado no `objectDef` correspondente.

## Comments

**2026-07-27** — Implementado em `extractor/scripts/build_phaser_map.py` via TDD (4 testes novos
em `extractor/tests/test_build_phaser_map_sheets.py`, mais correção de 1 teste pré-existente em
`test_build_phaser_map_baking.py` que ainda assertava `spriteIds`). Rodado `node build_map.js
--all` nos 8 mapas reais: todos com `version: 4` e `sheets` na raiz; inspeção visual do sheet
`object-32` de `rats-rookguard` confirma sprites reais (não corrompidos) nas células esperadas;
`border-32` do mesmo mapa tem várias células em branco, mas isso bateu com IDs que já tinham
`issues: ["missing_sprite:...", "metadata_missing"]` mesmo antes deste trabalho — dado de origem
faltando, não bug do packer. Nenhum `map.json` gerado ainda contém `spriteIds`.

**Desvio real encontrado**: `ensure_sprite_assets()` continua sendo chamada (sem alteração) para
todo appearance ID em `all_tile_ids` dentro do loop de `tilesets` — esse loop nunca foi tocado
porque é a mesma infraestrutura que copia os PNGs individuais das aparências usadas como `tileid`
de chão (`ground`/`tilesets`, explicitamente fora de escopo deste spec). Só que `all_tile_ids` é a
união de tileids **e** IDs de item/objeto — então uma aparência dinâmica que também foi empacotada
num sheet (ex.: 5557 em `rats-rookguard`) ainda ganha uma cópia solta redundante em
`sprites/5557/5557_*.png`, além de aparecer dentro do PNG do sheet. Verificado diretamente no
output real. Isso é desperdício de espaço em disco no output do build, mas não afeta o problema
que este spec resolve (número de requests do cliente) — o cliente só vai carregar o que
`PHASER_INTEGRATION.md` (ticket 03) documentar, e isso não inclui mais os paths soltos de
`objectDefs` dinâmicos. Separar "IDs só de ground" de "IDs de objeto" dentro de `all_tile_ids` para
eliminar essa cópia redundante ficou de fora deste ticket — exigiria tocar o loop de `tilesets`,
que o spec pede explicitamente pra não mudar. Registrado aqui como limitação conhecida, não como
bug.
