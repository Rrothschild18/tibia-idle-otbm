# 01 — Script de bake de atlas por outfit

**What to build:** Um novo script Python (`extractor/scripts/bake_outfit_atlas.py`), separado de
`extract_sprites.py`/`build_phaser_map.py`, que lê os PNGs por frame já extraídos de cada outfit em
`sprites/outfits/<id>/` (ou `sprites/outfits/<id>.png` para outfits de sprite única) junto com o
`<id>.json` que os acompanha, e empacota os frames de cada outfit em um único atlas: uma imagem
`<id>.png` (grade de 1 linha, frames na mesma ordem já presente no `spriteId`/`frameGroups` do
JSON, com 1px de padding transparente entre células) e um `<id>.json` no formato "JSON Hash" de
atlas de textura do Phaser (`frames: {<chave>: {frame: {x,y,w,h}}}`, `meta: {image, size}}`),
escritos em um diretório de saída global (não por mapa) — `extractor/atlases/outfits/`.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [x] Função pura `pack_outfit_frames(frames)` — recebe uma lista ordenada de `(chave, caminho_png)`,
      retorna `(Image, frame_map)` onde `frame_map` é o dict `frames` do JSON do atlas. Layout: 1
      linha, células de `max(largura/altura reais dos frames) + 2px`, 1px de padding em cada lado.
- [x] Função `build_atlas_json(image_name, canvas_size, frame_map)` — monta o dict completo do
      atlas (`frames` + `meta.image` + `meta.size`).
- [x] Função que lista todos os IDs de outfit disponíveis em `sprites/outfits/` (tanto os que têm
      subpasta `<id>/` quanto os de sprite única `<id>.png`+`<id>.json` no nível raiz), ordenados.
- [x] Função que, dado um outfit ID, carrega seu JSON e devolve a lista ordenada de
      `(chave, caminho_png)` a partir de `frameGroups[].spriteId` (ou `spriteId` quando não há
      múltiplos frame groups) — a ordem já vem correta do `extract_sprites.py`, não precisa
      recalcular direção/índice aqui.
- [x] Função `bake_outfit(outfit_id)` que liga as três funções acima e escreve
      `extractor/atlases/outfits/<id>.png` + `<id>.json`; outfit sem JSON encontrado retorna `None`
      sem lançar exceção (mesmo padrão tolerante de `_load_outfit_json` em `build_phaser_map.py`).
- [x] `main()`/CLI que roda `bake_outfit` para todos os IDs listados, imprime quantos atlases
      foram gerados (mesmo estilo de log de `extract_sprites.py`).
- [x] `.gitignore`: adicionar `extractor/atlases/` (saída gerada, binária, mesmo tratamento de
      `extractor/**/sprites/` e `extractor/ready-maps/**`).
- [x] Testes em `extractor/tests/` (estilo `test_render_baked_row.py`: fixtures PNG via PIL em
      `tmp_path`, chamando as funções puras diretamente):
  - `pack_outfit_frames` com frames de mesmo tamanho — posições/chaves/tamanho do canvas corretos.
  - `pack_outfit_frames` com uma lista vazia e com um único frame (casos de borda).
  - `bake_outfit` ponta a ponta contra uma fixture de outfit (JSON + PNGs em `tmp_path`,
    `OUTFITS_SPRITES_DIR`/`OUTFITS_ATLAS_DIR` via monkeypatch) — confirma que os dois arquivos são
    escritos e que suas chaves batem com as `spriteId` da fixture.
  - Determinismo: rodar `bake_outfit` duas vezes sobre a mesma fixture produz PNG e JSON de saída
    byte a byte idênticos.
  - Outfit de sprite única (sem `frameGroups`, só `spriteId: [id]` no JSON raiz) também é
    empacotado corretamente (atlas de 1 frame).
- [x] Rodar o script contra os dados reais já extraídos em `extractor/sprites/outfits/` e conferir
      visualmente (abrindo 2-3 atlases gerados) que o frame de índice 0 de um outfit conhecido
      (ex.: outfit 21) corresponde à direção sul, conforme `OUTFIT_SPRITES_DOCUMENTATION.md`.

## Comments

**2026-07-26** — Implementado em `extractor/scripts/bake_outfit_atlas.py` via TDD (11 testes em
`extractor/tests/test_bake_outfit_atlas.py`). Layout escolhido: 1 linha, células de
`max(largura/altura reais dos frames) + 2px` (1px de padding em cada lado), célula dimensionada
pelo maior frame do outfit em vez de assumir 32×32 fixo — outfit 21 (rato), por exemplo, tem
sprites reais de 64×64, não 32×32.

Achado real durante a checagem contra os 827 outfits já extraídos: outfits cujos frame groups têm
exatamente 1 sprite cada (ex.: outfit 1015, com 1 sprite idle + 1 sprite moving, sem ciclo de
caminhada) caem no branch "SPRITE ÚNICA" de `extract_sprites.py`, que escreve o PNG na pasta
raiz `sprites/outfits/` em vez de `sprites/outfits/<id>/`, mesmo com o JSON daquele outfit vivendo
na subpasta. `_resolve_frame_path()` tenta a subpasta primeiro e cai para a raiz, cobrindo esse
caso (teste de regressão incluído). Rodado contra os 827 outfits reais: 827 atlases gerados, 0
ignorados; inspeção visual do atlas do outfit 21 confirma a ordem sul→leste→norte→oeste e o ciclo
de caminhada batendo com `OUTFIT_SPRITES_DOCUMENTATION.md`.
