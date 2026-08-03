# 02 — `build_map.js`: descoberta em dois níveis (cidade/pasta) + `full-maps/<CIDADE>`

**What to build:** `build_map.js` passa a escanear `extractor/maps/<CIDADE>/<pasta>/` (dois níveis)
em vez do atual `extractor/maps/<pasta>/` (flat). `discoverMapNames()`/`mapExists()` percorrem toda
cidade automaticamente — adicionar uma cidade nova é só criar a pasta, sem tocar em código. O
tratamento especial hoje existente pra `full-maps/<nome>/` (usado só pelo mapa cidade-inteira) passa
a ser `full-maps/<CIDADE>/` (ticket 01) — output do `map.json`/`metadata.json` continua indo pro
próprio `full-maps/<CIDADE>/` (versionado), não pro `ready-maps/` (gitignored).

**Blocked by:** 01 (convenção documentada).

- [ ] `node build_map.js --all` encontra e builda mapas de todas as cidades sob `extractor/maps/`,
      sem hardcode de nome de cidade
- [ ] `node build_map.js <nome-da-pasta-do-mapa>` continua funcionando pra um mapa específico,
      resolvendo automaticamente em qual cidade ele está (sem precisar passar a cidade como
      argumento separado)
- [ ] `node build_map.js ROOK` builda o mapa cidade-inteira de Rookgaard
      (`extractor/full-maps/ROOK/ROOK.otbm`), saída em `extractor/full-maps/ROOK/`
- [ ] Erro claro e específico quando o nome passado não existe em nenhuma cidade (nem em `maps/`,
      nem em `full-maps/`) — lista as cidades disponíveis pra ajudar a debugar
- [ ] Regressão: builds de mapas de hunt individuais continuam produzindo o mesmo `map.json`/
      `sprites/`/`respawn.json` de antes, só que no path novo (`ready-maps/<CIDADE>/<pasta>/`)
