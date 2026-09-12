# Legado

Scripts de exploração pontual e um parser OTBM manual antigo, mantidos aqui só
como referência histórica. **Não fazem parte do pipeline ativo** (veja
`extractor/scripts/`) e os paths internos deles não foram atualizados — não
vão rodar sem ajuste manual.

- `analyze_maps.py`, `analyze_sprites.py`, `analyze_sprites2.py`,
  `analyze_sprites3.py`, `read_aec.py` — scripts de debug/exploração usados
  para investigar a estrutura dos `.raw.json` e dos JSONs de sprites durante
  o desenvolvimento do conversor. O `read_aec.py` lia os containers `.aec` do
  Assets Editor, **insumo aposentado**: o estágio 0 passou a ler a pasta
  `assets/` do cliente Tibia direto (ver `extractor/scripts/client_sprites.py`).
- `map_otbm.py`, `map_otbm2.py` — parser OTBM binário manual, escrito antes de
  adotar `otbm2json.js` (agora em `extractor/vendor/`). Superado pelo pipeline
  atual (`dump_otbm.js` + `build_phaser_map.py`).
