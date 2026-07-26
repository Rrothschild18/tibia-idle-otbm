# 01 — `map.json` floor-aware

**What to build:** O extractor passa a preservar todos os floors (z-levels) de um mapa OTBM em
vez de misturá-los. Rodar o pipeline em `skeletons-rookguard` produz um `map.json` com os 3
floors (z=7/8/9) separados corretamente, cada um com seu próprio conjunto de layers
(Ground/Borders/Bottom/WallsSouth/WallsEast/Objects/Top/Roof), compartilhando o mesmo espaço de
coordenadas (`bounds`/`width`/`height` como união de todos os floors, para que `(tileX,tileY)`
signifique a mesma coluna física em qualquer floor).

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] `build_phaser_map()` (`extractor/scripts/build_phaser_map.py`) lê `feature.get("z", 7)` e
      indexa `ground_tiles`/`raw_item_stacks` por `(x, y, z)` em vez de `(x, y)`
- [ ] Os 7 dicts de classificação de layer (`border_objects`, `bottom_objects`, ...
      `walls_east_objects`) passam a existir por floor
- [ ] O array de Ground é construído uma vez por floor, usando as bounds da união (mesmas
      dimensões `width*height` em todo floor, só que esparso fora da pegada daquele floor)
- [ ] `objectDefs`/`tilesets`/`animations` continuam globais (compartilhados entre floors, como
      já são hoje) — não duplicar por floor
- [ ] O JSON de saída substitui o `"layers": [...]` do topo por `"floors": {"<z>": {"z": <z>,
      "layers": [...]}, ...}` e adiciona `"defaultZ"` (`7` se existir, senão o menor z presente)
- [ ] `"version"` do `map.json` **não muda** (a mudança é estrutural/aditiva, não um bump de
      schema — ver decisão registrada no spec.md)
- [ ] Novo `docs/adr/0002-map-json-floors-e-defaultz.md` documentando as decisões de design
      (união de bounds, por que não houve bump de version)
- [ ] `extractor/PHASER_INTEGRATION.md` atualizado com o novo schema (`floors`/`defaultZ`)
- [ ] `node extractor/scripts/build_map.js --all` rodado, regerando os 8 mapas em
      `extractor/ready-maps/*/map.json`
- [ ] Verificação: `floors["7"]`/`floors["8"]`/`floors["9"]` de `skeletons-rookguard` reproduzem
      exatamente 1848/1812/50 **posições de tile distintas (Ground + todas as objectgroups
      somadas)**, cada floor isolado (sem contaminação cruzada — hoje eles colidem num único
      array); `rats-sewers` reproduz 2120/372 do mesmo jeito. (Não confundir com contagem só do
      tilelayer Ground: tiles de bloqueio grandes são redirecionados pro Roof por
      `_is_roof_tile()` — comportamento preexistente, não relacionado a floors — então Ground
      sozinho sempre fica abaixo do total bruto de tiles daquele floor.)
- [ ] Verificação: os 5 mapas single-floor (`dragon-darashia`, `grim-reaper`, `larva-ankrah`,
      `rats-rookguard`, `sea-serpent`) produzem `floors == {"7": {...}}` (uma única chave) e
      `defaultZ == 7`

## Comments
