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

- [x] `extract_sprites.py` lê `assets/` do cliente: `catalog-content.json` + sheets LZMA +
      `appearances-*.dat` oficial
- [x] `Appearances.proto` passa a ser o schema oficial; o campo não-padrão `sprite_data = 7` some
- [x] A saída em `extractor/sprites/` é **equivalente à de hoje** — mesmos nomes, mesmos grupos
      (`items`, `effects`, `missiles`, `outfits`); nenhum consumidor rio abaixo muda
- [x] Continua idempotente (PNG/JSON existente não é regravado), como o README já promete
- [x] Caminho do cliente vem do `paths.py` (`TIBIA_CLIENT_DIR` / `--client-dir`), com erro alto
      citando o que falta
- [x] `extractor/_legacy/read_aec.py` e as menções a `.aec` no README/`.gitignore` removidas ou
      marcadas como histórico
- [x] Coberto por teste com uma sheet pequena de fixture: faixa de ids do catálogo → PNGs corretos
- [x] O manifesto confere que o `appearances.dat` do cliente e o do Canary têm o mesmo sha256 —
      divergência significa que servidor e cliente discordam sobre metadado de item, e isso tem que
      ser erro explícito, não surpresa seis estágios adiante

## Comments

**O `.aec` está aposentado. 204.003 PNGs saíram do cliente, sem Assets Editor.**

```
[OK] cliente 15.25.0a00a0: 4927 folhas, maior sprite id 289767
[OK] outfits:  94916 PNGs   (242 outfits de jogador, 152 appearances puladas por eixo)
[OK] items:   105321 PNGs
[OK] effects:   3160 PNGs
[OK] missiles:   558 PNGs
```

Zero `missing_sprite` em qualquer grupo. 1,0 GB em `extractor/sprites/`.

### A troca foi pequena porque o script já lia o campo certo

`extract_sprites.py` sempre percorreu `sprite_info.sprite_id` **em paralelo** a `sprite_data`, com
um `sprite_data_offset` andando em lockstep. Ou seja, a informação necessária já estava no protobuf
oficial — o `.aec` só acrescentava os pixels.

Então a mudança foi trocar três acessos a `appearance.sprite_data[offset]` por
`write_sprite(sprite_ids[i], path)`. A lei de índice do outfit de jogador, os eixos, os nomes de
arquivo e os JSONs de saída ficaram intactos. Nenhum consumidor rio abaixo mudou.

`client_sprites.py` é o novo módulo: catálogo → busca binária por faixa de id → folha decodificada
(cache LRU de 8) → recorte pelo `spritetype`. A decodificação LZMA usa só a stdlib, com o ajuste de
header que o ticket documentava.

### Verificação visual, não só contagem

Contar PNGs não prova que são os PNGs certos — recortar a célula errada produz arquivos do tamanho
certo. Montei tiras de inspeção:

- **efeito 11 (CONST_ME_TELEPORT)**: os 11 frames formam o redemoinho azul expandindo e se
  dissipando, na ordem temporal correta
- **outfit 21 (rat)**: rato visto das 4 direções, dois frames cada

Os testes de fixture cobrem o mesmo por cor: cada célula da folha sintética tem cor própria, então
o teste afirma **qual** célula foi recortada, não só que algo foi.

### Duas coisas quebraram no caminho, ambas reais

1. **`FieldDescriptor.label` não existe mais no protobuf 7.** O `proto_to_dict` usava
   `field.label == LABEL_REPEATED`. Agora usa `is_repeated` com fallback pro `label` antigo, então
   funciona nas duas majors.
2. **Regerar o schema moveu o piso do runtime.** Tirar o campo 7 exigiu rodar o `protoc` (36.1), e
   o `Appearances_pb2.py` novo chama `ValidateProtobufRuntimeVersion(PUBLIC, 7, 36, 1)` no import.
   `pyproject.toml` subiu de `protobuf>=6.33.5` para `>=7.36.1`, com um comentário ligando os dois —
   regerar o schema move esse piso de novo.

O campo 7 virou `reserved 7` no `.proto`, não sumiu: reservar impede que alguém o reutilize com
outro significado. Confirmado que o `.dat` oficial continua parseando (42107/1443/242/62) e que
`sprite_data` não está mais no descritor.

### A conferência cliente-vs-Canary

`fetch_assets.check_canary_agreement()` compara o `appearances.dat` do cliente com o
`canary/data/items/appearances.dat`. Nesta máquina:

```
[OK] cliente e Canary concordam sobre appearances.dat (aa44a154f30c7ed5…)
```

Divergência é erro. Canary ausente é `INFO`, não falha — o checkout virou opcional no ticket 04.

### Efeito colateral: a suíte destravou

Os três arquivos de teste que nem coletavam (importam `build_phaser_map`, que fazia `raise` no
import sem `extractor/sprites/`) agora rodam, e `test_ground_equivalent_report` voltou a passar.
**444 testes passando**, contra 403 antes e 379 no início da sessão.

Sobrou 1 falha, e ela mudou de natureza: `test_build_item_index` não diz mais "índice vazio", diz
que falta `atlases/items-static/items-static-0.json` — ou seja, os sprites existem e o que falta é
o bake, que é o passo seguinte do pipeline.

### Ajuste nos testes existentes

`test_extract_sprites.py` modelava `sprite_data` direto. Agora injeta uma fonte falsa
(`FakeSprites`, id → PNG 1×1 que codifica o id) por fixture `autouse`, e os `FakeSpriteInfo` usam
ids **contíguos e únicos entre frame groups**, como no cliente real — antes os dois grupos usavam
`range(n)` e colidiam, o que só não importava porque nada indexava por id.

Um teste teve a asserção reescrita: `test_..._skips_an_outfit_of_unexpected_size` afirmava
`"esperado 432"`, mas 432 é **derivado** (`phases = len(sprite_id) // per_phase`), então encurtar a
fixture muda o esperado junto. Passou a afirmar o comportamento — pula, não escreve nada, diz por
quê — em vez da constante.
