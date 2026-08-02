# 01 — Índice `itemId → localização do sprite`

**What to build:** Um novo módulo `extractor/scripts/build_item_index.py` que junta a saída de
`bake_item_atlas.py` (`extractor/atlases/items/`) e `bake_item_sheets.py`
(`extractor/atlases/items-static/`) num único arquivo pequeno,
`extractor/atlases/items-index.json`, mapeando cada `itemId` candidato (os mesmos 5.891 de
`is_equipment_candidate`) para onde seu sprite mora e como ele deve ser lido. Isso fecha o "Gap
conhecido" já registrado em `.scratch/item-sprite-sheets/spec.md`: hoje não existe nenhum jeito de
saber, sem abrir os 809 atlas individuais ou as 4 sheets estáticas, onde um `itemId` específico
está.

**Blocked by:** nenhum (os dois bakes que ele consome já estão implementados e rodados).

**Status:** ready-for-agent

- [ ] Formato de cada entrada do índice (chave = `itemId` como string, mesma convenção do resto do
      pipeline):
  ```json
  {
    "3555":  { "kind": "atlas", "file": "items/3555.json", "frameKeys": ["3555_0", "3555_1", "..."], "stackable": false, "spriteCount": 1 },
    "49094": { "kind": "static-sheet", "file": "items-static/items-static-2.json", "frameKeys": ["49094"], "stackable": true, "spriteCount": 1 },
    "9058":  { "kind": "static-sheet", "file": "items-static/items-static-1.json", "frameKeys": ["9058_0", "9058_1", "...", "9058_103"], "stackable": true, "spriteCount": 8 }
  }
  ```
  - `kind`: `"atlas"` para os 808 itens animados (cada um com seu próprio arquivo em
    `extractor/atlases/items/`), `"static-sheet"` para os 5.083 estáticos.
  - `file`: caminho relativo a `extractor/atlases/`, resolvendo direto pro par PNG+JSON já
    existente (`.json` trocado pela extensão do JSON de frames; a imagem tem o mesmo nome com
    `.png`).
  - `frameKeys`: a lista completa de chaves de frame do item, na mesma ordem de `spriteId` do
    metadado bruto (`extractor/sprites/items/<id>/<id>.json`) — o cliente precisa dela tanto pra
    animação (ordem de ciclo) quanto pra indexar por stack-tier.
  - `stackable`: `true` se `flags.cumulative` estava presente no metadado bruto do item — sinal
    independente de `spriteCount`, já que um item pode ser `cumulative` com só 1 sprite (sem
    variação visual por quantidade).
  - `spriteCount`: contagem de **células** do item (não frames de animação) —
    `patternWidth × patternHeight × patternDepth` do metadado bruto. Para item animado com célula
    única, é sempre `1` (as N entradas de `frameKeys` são frames de animação, não células). Este é
    o mesmo significado que `ItemData.spriteCount` já tem hoje no repo `tibia-idle`
    (`libs/game-logic/src/lib/entities/item-data.ts`) — ver ticket 01 do
    `.scratch/item-render-pipeline/` naquele repo, que consome exatamente este campo pra
    `getStackTierIndex`.
- [ ] `build_item_index()`: função pura que recebe as duas pastas de atlas já geradas (ou os
      resultados em memória de `bake_item_atlas.py`/`bake_item_sheets.py`) e retorna o dict do
      índice — sem I/O direto, seguindo o padrão já usado em `sheet_packer.py`
      (planejamento puro separado de renderização/escrita).
- [ ] `main()`: roda os dois bakes (ou assume que já rodaram, a definir durante a implementação —
      ver ticket 02 sobre ordenação no pipeline) e escreve `items-index.json`.
- [ ] Testes em `extractor/tests/test_build_item_index.py` (fixtures pequenas, mesmo estilo dos
      testes de `bake_item_atlas.py`/`bake_item_sheets.py`): item animado aparece com
      `kind: "atlas"`, item estático de célula única aparece com `kind: "static-sheet"` apontando
      pra sheet certa, item multi-célula tem `frameKeys` completo e `spriteCount` correto,
      `stackable` reflete `flags.cumulative` independente de `spriteCount`.
- [ ] Rodar contra o dado real e conferir: 5.891 entradas no total, toda chave de `frameKeys`
      resolve pra um frame que de fato existe no atlas/sheet referenciado (nenhuma entrada órfã).
