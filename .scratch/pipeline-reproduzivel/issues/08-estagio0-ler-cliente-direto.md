Status: ready-for-agent

# 08 — Estágio 0 lê o `assets/` do cliente direto; o `.aec` é aposentado

**What to build:** Hoje `extract_sprites.py:17-21` espera quatro containers `.aec` em `extractor/`
(~270 MB, gitignorados, inexistentes em qualquer clone) e os lê com um protobuf **não-padrão**:
`Appearances.proto:67` declara `repeated bytes sprite_data = 7`, campo que o `appearances.proto`
oficial do Canary não tem. É por isso que o `appearances.dat` do checkout do Canary nunca serviu de
substituto.

Esse insumo é insustentável: `.aec` é export de uma ferramenta GUI de terceiros, e **o formato já
mudou** — o editor atual em manutenção (`beats-dh/Beats-Assets-Editor`, Rust+Tauri, Tibia 15.x)
escreve o container AEC com os bytes de sprite num **arquivo companheiro** (`export_appearance_to_aec`
→ "+ `.aec.sprites` companion"), não embutidos. Reexportar hoje produziria `.aec` com o campo 7
vazio: zero sprite extraído, provavelmente sem erro. O outro editor (`Arch-Mina/Assets-Editor`,
C#/.NET) nem menciona `.aec` — exporta `spr/dat`. Os dois são Windows-only, o que é incompatível com
o alvo de "clonar no VPS e rodar um comando".

**Trocar só o leitor, mantendo o contrato de saída idêntico.** O estágio 0 continua produzindo
`extractor/sprites/<grupo>/<id>.png` + os JSONs que já produz — nada rio abaixo muda
(`build_phaser_map.ITEMS_SOURCES:69-87`, os quatro `bake_*`, `ground_equivalent_report.py:37`).
Muda a entrada: a pasta `assets/` do cliente, com `catalog-content.json` (quais sheets existem e que
faixa de sprite id cada uma cobre), as sheets comprimidas em LZMA, e `appearances-*.dat` no
**protobuf oficial**.

## Formato confirmado contra o cliente real (15.25.0a00a0)

Tudo abaixo foi verificado num cliente baixado, não inferido:

- `catalog-content.json` tem **4933 entradas**: 4927 do tipo `sprite`, 1 `appearances`, e
  `staticdata`/`staticmapdata`/`fullmap`/`map`/`proficiencies`. Cada entrada `sprite` é
  `{"file": "sprites-<sha256>.bmp.lzma", "spritetype": 0|1|2|3, "firstspriteid": N,
  "lastspriteid": M, "area": 0}` — a faixa de ids por folha vem pronta, não precisa ser calculada.
  Maior `lastspriteid`: 289767. Distribuição: `spritetype` 3 em 4488 folhas, 0 em 327, 1 em 57,
  2 em 55.
- **O `lzma` da stdlib lê as folhas**, com um ajuste de header — não precisa de dependência nova:
  os 32 primeiros bytes são cabeçalho proprietário (24 zeros + 8 bytes de marca), os props do LZMA1
  começam no offset 32 (`5d 00 00 ...`), e o campo de tamanho de 8 bytes vem zerado e precisa virar
  `0xFF * 8` (tamanho desconhecido). Daí `LZMADecompressor(format=FORMAT_ALONE)` devolve um **BMP**.
- Folha de `spritetype` 0 decodifica pra **384×384, 32bpp** (589.946 bytes) = 12×12 sprites de
  32×32, batendo exatamente com a faixa `0-143` (144 sprites) que o catálogo declara.
- **O `appearances.dat` do cliente é byte-a-byte o mesmo do checkout do Canary**: sha256
  `aa44a154f30c7ed59acc25f246286396e4043851ef0b54ef3cf3951e46d1ce50`, 4.862.287 bytes, idêntico a
  `canary/data/items/appearances.dat`. Ou seja, **a metade de metadados do estágio 0 já está no
  Canary** — só as 4927 folhas de sprite exigem o download do cliente.

**Blocked by:** 02 (`Pillow`/`protobuf` pela env do `uv`), 13 (é preciso ter o `assets/` de um
cliente em mãos pra escrever contra arquivo real).

- [ ] `extract_sprites.py` lê `assets/` do cliente: `catalog-content.json` + sheets LZMA +
      `appearances-*.dat` oficial
- [ ] `Appearances.proto` passa a ser o schema oficial; o campo não-padrão `sprite_data = 7` some
- [ ] A saída em `extractor/sprites/` é **equivalente à de hoje** — mesmos nomes, mesmos grupos
      (`items`, `effects`, `missiles`, `outfits`); nenhum consumidor rio abaixo muda
- [ ] Continua idempotente (PNG/JSON existente não é regravado), como o README já promete
- [ ] Caminho do cliente vem do `paths.py` (`TIBIA_CLIENT_DIR` / `--client-dir`), com erro alto
      citando o que falta
- [ ] `extractor/_legacy/read_aec.py` e as menções a `.aec` no README/`.gitignore` removidas ou
      marcadas como histórico
- [ ] Coberto por teste com uma sheet pequena de fixture: faixa de ids do catálogo → PNGs corretos
- [ ] O manifesto confere que o `appearances.dat` do cliente e o do Canary têm o mesmo sha256 —
      divergência significa que servidor e cliente discordam sobre metadado de item, e isso tem que
      ser erro explícito, não surpresa seis estágios adiante
