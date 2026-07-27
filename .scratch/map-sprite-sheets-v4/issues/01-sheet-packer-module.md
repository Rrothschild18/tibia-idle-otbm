# 01 — Módulo puro de empacotamento em sheets

**What to build:** Portar a lógica validada no protótipo (`prototype/sheet-packer-v4`, commit
`49b3e09`) pra um módulo real dentro de `extractor/scripts/` (`sheet_packer.py`): bucket por
tamanho (32/64/128, arredondando pra cima), chave de sheet `{layerClass}-{bucket}`, atribuição de
gid sequencial (múltiplos frames = gids consecutivos), cálculo de dimensões de sheet
(`columns`/`rows`/`pixelWidth`/`pixelHeight`), e resolução `gid -> (row, col, x, y)`. Módulo puro,
sem I/O — só monta o plano de empacotamento (quem vai pra qual sheet, em qual gid); a geração real
do PNG do sheet e a integração com `build_phaser_map.py` ficam pro ticket 02.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [x] `bucket_for(width, height)` — mesma lógica do protótipo (`max(w,h)`, primeiro bucket de
      `[32, 64, 128]` que comporta, clamp em 128 se maior).
- [x] Classe/módulo `SheetPacker` com `add_appearance(appearance_id, layer_class, width, height,
      frame_count)` retornando `(sheet_key, gids)`, e um jeito de listar o estado final: sheets
      (`cellSize`/`columns`/`count`) e, por aparência, `sheet`+`gids`.
- [x] `sheet_dims(sheet_key)` — `columns`, `rows` (ceil da contagem de células / columns),
      `pixelWidth`, `pixelHeight`.
- [x] `gid_to_rect(sheet_key, gid)` — `{x, y, w, h}` em pixels, usando a mesma aritmética
      `col = gid % columns`, `row = gid // columns` já validada.
- [x] Testes (`extractor/tests/test_sheet_packer.py`), cobrindo os 4 casos já verificados
      manualmente no protótipo, agora como testes automatizados de verdade:
  - 96×96 vai pro bucket 128, não 64.
  - Aparência com `frame_count=6` recebe 6 gids consecutivos no mesmo sheet.
  - Adicionar aparências além do limite de `columns` quebra pra próxima linha corretamente
    (`gid_to_rect` continua correto atravessando a quebra; `sheet_dims` reporta `rows` certo).
  - Duas `layerClass` diferentes com o mesmo tamanho (`object` vs `bottom`, ambos 32×32) caem em
    sheets distintos (`object-32` ≠ `bottom-32`).
  - Determinismo: adicionar as mesmas aparências, na mesma ordem, duas vezes (duas instâncias de
    `SheetPacker`) produz exatamente os mesmos gids.

## Comments

**2026-07-27** — Implementado em `extractor/scripts/sheet_packer.py` via TDD (8 testes em
`extractor/tests/test_sheet_packer.py`), portando a lógica exata já validada no protótipo
descartável (`prototype/sheet-packer-v4`, commit `49b3e09`). Único acréscimo sobre o protótipo:
`columns_for_bucket(bucket)` exposto publicamente, pra os testes conseguirem calcular "quantos
itens preenchem uma linha" sem hardcodar o valor de `COLUMNS_BY_BUCKET`.
