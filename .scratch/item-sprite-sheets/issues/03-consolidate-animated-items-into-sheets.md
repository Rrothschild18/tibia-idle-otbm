# 03 — Consolidar itens animados em sheets (mesmo modelo dos itens estáticos)

**What to build:** `bake_item_atlas.py` gerava um atlas individual por item animado (809 no dado
real: `extractor/atlases/items/<id>.png` + `<id>.json`) — o mesmo problema de "muitas requisições
pequenas" que motivou `bake_item_sheets.py` a consolidar os itens estáticos em sheets
compartilhadas, só que menor em contagem (809 vs 5083) e pior por arquivo (cada item carrega seu
próprio par PNG+JSON mesmo sendo, quase sempre, um ícone 32×32 igual aos estáticos — só com mais
frames). O pedido: juntar os animados em sheets também, pro consumidor carregar sheets + JSON de
metadado do mesmo jeito para os dois tipos de item.

**Blocked by:** nenhum (`bake_item_sheets.py`, `bake_item_atlas.py` e `build_item_index.py` — issue
01 — já estavam implementados e rodados).

**Status:** ready-for-agent

- [x] Novo módulo `extractor/scripts/bake_item_sheets_animated.py`, espelhando
      `bake_item_sheets.py`: lista candidatos de equipamento/consumível **com** animação
      (`bia.is_equipment_candidate` + `not bis._is_static`), empacota com
      `bis.plan_static_sheets` (já genérica — opera em pares `(item_id, spriteKeys)` sem saber nada
      sobre animação) e escreve `extractor/atlases/items-animated/items-animated-{i}.png` + `.json`.
      Sem padding entre frames, mesma decisão já tomada para as sheets estáticas (ícones já carregam
      margem transparente própria).
  - Config real: `COLUMNS=32`, `NUM_SHEETS=8` — dado real tem 809 itens animados / 7686 células
    (frames de animação, incluindo os ~21 itens multi-célula). Com 8 shards, cada sheet fica
    ~1024×992px (pior caso teórico ~1024×1088px), bem abaixo do limite seguro de textura
    WebGL (2048×2048).
- [x] `build_item_index.py` atualizado: `kind` de item animado passa de `"atlas"` (apontando pro
      atlas individual) para `"animated-sheet"` (apontando pra
      `items-animated/items-animated-{shard}.json`) — mesmo padrão já usado por `"static-sheet"`.
      `_compute_static_shard_of` virou `_compute_shard_of` (genérica, reusada pros dois tipos).
- [x] `build_items.js`: `bake_item_atlas.py` saiu da lista de `STEPS` (não é mais rodado como bake
      standalone); `bake_item_sheets_animated.py` entrou no lugar. `bake_item_atlas.py` continua
      existindo como biblioteca compartilhada (classificação + resolução de frame) importada pelos
      dois bakes de sheet — só `bake_item()`/`main()` (o bake individual em si) não fazem mais parte
      do pipeline.
- [x] `sync_items_to_tibia_idle.py` atualizado: sincroniza `items-animated/` em vez de `items/`.
- [x] Testes novos em `extractor/tests/test_bake_item_sheets_animated.py` (mesmo estilo de
      `test_bake_item_sheets.py`: listagem exclui estático/cenário, bake fim-a-fim, item multi-frame
      nunca cortado entre shards, item multi-célula, determinismo). Testes existentes em
      `test_build_item_index.py` atualizados para o novo contrato (`kind: "animated-sheet"`,
      `animated_shard_of` como parâmetro extra de `build_item_index()`).
- [x] Rodado contra o dado real: `bake_item_sheets_animated.py` (8 sheets, todas sob o limite seguro
      de textura) e `build_item_index.py` (5927 entradas no índice, sem chave de frame órfã — mesmo
      teste de dado real de `test_build_item_index.py` cobre isso).
- [x] Docs atualizados: `extractor/README.md` (TL;DR do passo 6/8, estrutura de pastas),
      docstrings de `bake_item_sheets.py`/`bake_item_atlas.py`/`sync_items_to_tibia_idle.py`.

## Comments

Implementado nesta sessão. `extractor/atlases/items/` (saída antiga do bake individual) ficou
órfã — nada mais aponta pra ela — e foi removida do disco (gitignored/regenerável, sem perda:
`python bake_item_atlas.py` reconstrói se algum dia precisar de novo, ainda que não faça mais parte
do fluxo automático).
