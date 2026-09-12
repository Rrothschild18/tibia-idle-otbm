# Pipeline de mapas

Guia rápido + FAQ para gerar mapas Phaser a partir de arquivos `.otbm`.
Para detalhes internos do formato de saída, veja [`MAP_JSON_V6.md`](MAP_JSON_V6.md) (formato novo,
a pilha por tile) e — para o v5, que o jogo ainda consome — [`CONVERTER_DOCS.md`](CONVERTER_DOCS.md)
e [`PHASER_INTEGRATION.md`](PHASER_INTEGRATION.md).

## Setup

Tudo o que o pipeline precisa em Python está declarado em `pyproject.toml` (Pillow e protobuf de
runtime, pytest de dev) e travado em `uv.lock`. Num clone limpo:

```
uv sync
```

É o único passo. `build_map.js` resolve o interpretador sozinho — usa `$PYTHON` se definido, senão
o `.venv/` do repo, senão cai em `uv run python`; ele nunca mais spawna um `python` cru do PATH.

Para rodar um script Python direto, use a env:

```
uv run python extractor/scripts/build_travel_fragment.py ROOK
uv run pytest extractor/tests
```

Os caminhos para os repos irmãos vêm de variáveis de ambiente (ver
[Caminhos dos repos irmãos](#caminhos-dos-repos-irmãos)):

```
TIBIA_IDLE_DIR     checkout do tibia-idle   (default: ../tibia-idle)
CANARY_DIR         checkout do canary       (default: ../canary)
TIBIA_CLIENT_DIR   cliente Tibia extraído   (default: ../tibia-client)
```

### Máquina nova, do zero

```
uv sync                                                  # deps Python
uv run python extractor/scripts/fetch_assets.py          # cliente Tibia (403 MB)
node extractor/scripts/dump_otbm.js ROOK                 # dump cru do mapa
uv run python extractor/scripts/build_travel_fragment.py ROOK
```

O terceiro e o quarto passo **não precisam do segundo**: o grafo de viagem roda com a tabela de
flags e o vendor do Canary, ambos versionados. O `fetch-assets` é necessário para sprites, sheets e
atlases.

## Caminhos dos repos irmãos

Um script lê de fora deste repo no fluxo normal: o checkout do **tibia-idle** (destino do
`--export` e dos syncs de atlas). O do **canary** virou opcional — ver
[Vendor do Canary](#vendor-do-canary). Os dois caminhos saem de um lugar só —
`extractor/scripts/paths.py` — com esta precedência:

| Precedência | tibia-idle | canary |
|---|---|---|
| 1. flag | `--tibia-idle-dir` | `--canary-dir` |
| 2. env var | `TIBIA_IDLE_DIR` | `CANARY_DIR` |
| 3. irmão no workspace | `../tibia-idle` | `../canary` |

Se o layout for o irmão padrão, nenhum dos dois precisa ser passado:

```
uv run python extractor/scripts/build_travel_fragment.py ROOK
```

Diretório ausente para com uma mensagem que diz o caminho tentado, a env var e a flag — nunca um
traceback vindo de dentro do pipeline:

```
error: esperava um checkout do canary em /nao/existe; passe --canary-dir ou defina CANARY_DIR
```

## Vendor do Canary

Gerar o grafo de viagem exigia um clone inteiro do Canary — `data/items/items.xml` (3,5 MB), 1035
`.lua` de NPC (9 MB) e 1656 `.lua` de monstro (7,5 MB). O que o pipeline de fato lê está
versionado em `extractor/vendor/canary/`:

| Arquivo | O que é | Por que nesse formato |
|---|---|---|
| `items.xml` | cópia crua de `data/items/items.xml` | é um arquivo só, e é fonte de duas coisas (floorchange pro grafo, nome↔id e decay pro loot) — cru continua auditável |
| `npc-lua-facts.json` | tabelas `shop` e `outfit` dos 1035 `.lua` de NPC | ninguém revisa 1035 arquivos num diff |
| `MANIFEST.json` | commit do Canary, data e comando que gerou | sem isso o vendor não tem procedência e ninguém sabe quando envelheceu |

Com isso, **um clone sem Canary nenhum gera o fragmento do ROOK**:

```
uv run python extractor/scripts/build_travel_fragment.py ROOK
```

Para atualizar o vendor depois de um bump do Canary:

```
uv run python extractor/scripts/update_canary_data.py            # usa CANARY_DIR ou ../canary
```

`--canary-dir` nos scripts que consomem o vendor **relê do checkout** em vez do vendor, que é como
se confere se o vendor envelheceu — a saída tem que ser idêntica.

Duas coisas continuam exigindo o checkout, de propósito:

- **`build_monster_loot_index.py`** — é o gerador do `monster-loot.json`, que já é o extrato
  versionado dos `.lua` de monstro. Ele lê o `items.xml` do mesmo checkout dos `.lua`, e não do
  vendor: resolver id de item por uma versão do Canary e tabela de loot por outra produziria um
  índice silenciosamente inconsistente.
- **`update_canary_data.py`** — por definição.

## Tabela de flags por appearance

`extractor/appearance-flags/<CIDADE>.json` — o que o travel-graph realmente consome. Dois arquivos,
e a separação é a regra mecânico-vs-curado do `CONTEXT.md`:

| Arquivo | Natureza | Regenerar |
|---|---|---|
| `<CIDADE>.json` | **100% mecânico**, derivado dos metadados de appearance | sobrescreve sem dó |
| `<CIDADE>.overrides.json` | **curado**, pequeno, sempre vence no merge | nunca é tocado |

Um override **substitui a entrada inteira** daquele id, não mescla chave a chave: ele é a resposta
final. Mesclar deixaria a derivação reintroduzir pela porta dos fundos justamente o valor que a
curadoria existe pra corrigir. Cada linha do arquivo de overrides documenta um caso em que a
derivação erra.

Regenerar a tabela:

```
node extractor/scripts/dump_otbm.js ROOK
uv run python extractor/scripts/build_appearance_flags.py ROOK
```

**Regenerar exige `extractor/sprites/`** — os `.json` por appearance, de onde as flags saem. Os PNGs
não: `spriteWidth`/`spriteHeight` vêm da imagem e o grafo não usa nenhum dos dois. **Usar** a tabela
não exige nada: ela é versionada exatamente pra que um clone sem biblioteca de sprites continue
gerando o grafo, que é o produto fim-a-fim que essa máquina consegue montar.

## Cliente Tibia (fonte dos sprites)

Todo sprite sai da pasta `assets/` de um cliente Tibia — `catalog-content.json`, as folhas
`sprites-<sha>.bmp.lzma` e o `appearances-<sha>.dat`. Não é preciso Assets Editor, e não é preciso
bucket privado: a release é pública e imutável.

A versão está fixada em `extractor/assets-manifest.json`, **e em nenhum outro lugar**. Trocar de
cliente é editar aquele arquivo.

```
uv run python extractor/scripts/fetch_assets.py           # baixa, confere, extrai
uv run python extractor/scripts/fetch_assets.py --force   # rebaixa mesmo se já válido
```

| | |
|---|---|
| Release | [`dudantas/tibia-client` @ `15.25.0a00a0`](https://github.com/dudantas/tibia-client/releases/tag/15.25.0a00a0) |
| Zip | 403,5 MB, sha256 `da42a4ff…` |
| Extraído | 131 MB em `packages/Tibia/assets/` |
| Catálogo | 4933 entradas (4927 folhas de sprite + appearances + estáticos) |

**Checksum divergente é erro, não aviso.** O modo de falha é silencioso: um cliente mais novo
desloca ids de aparência, e o sintoma aparece seis estágios adiante como sprite trocado — nunca
como erro. Três coisas são conferidas: o sha256 do zip, o `assets.json.sha256` (o mecanismo de
integridade do próprio cliente, que pega extração truncada depois do zip apagado) e a contagem de
entradas do catálogo.

O `package.json` irmão de `assets/` também é extraído e conferido. Extrair só `assets/` é o erro
fácil: o RME recusa a pasta com *"The file package.json is not present"*, numa caixa de diálogo
cujo título fala do `catalog-content.json`.

## TL;DR

```
node extractor/scripts/build_map.js <nome-da-pasta>  # gera só esse mapa (ex: ROOK-HUNT-0010_bears-rookguard)
node extractor/scripts/build_map.js --all            # gera todos os mapas de hunt de todas as cidades
npm run build-map -- --all                           # atalho para o comando acima
npm run build-items                                  # bake global de sprites de item (ver abaixo)
python extractor/scripts/build_hunt_fragment.py ROOK-HUNT-0010_bears-rookguard --map-id ROOK-HUNT-0010
                                                      # gera db-fragment.json (hunts/monsters/loot) —
                                                      # nunca escreve no back-end, ver seção 7 abaixo
python extractor/scripts/sync_items_to_tibia_idle.py # publica atlases de item no repo tibia-idle
node extractor/scripts/build_map.js ROOK             # gera o mapa cidade-inteira (fonte: full-maps/ROOK/)
python extractor/scripts/build_travel_fragment.py ROOK
                                                      # gera db-fragment.json (locations/travelGraph) +
                                                      # travel-graph-rejections.txt (nó sem entrada no
                                                      # grafo) — nunca escreve no back-end, ver
                                                      # "Travel graph" abaixo
```

## Convenção de pastas (cidade + id)

Todo mapa — de hunt ou de cidade inteira — mora sob uma **pasta de cidade**: a cidade nunca é
adivinhada do nome do mapa (não existe mais um `_id_prefix_for_map` tentando reconhecer
`"-rookguard"` ou o primeiro pedaço do nome) — ela é sempre, e só, a pasta-pai física onde o mapa
está. Isso vale nos três lugares:

- `extractor/maps/<CIDADE>/<CIDADE-TIPO-SEQ>_nome-descritivo/` — fonte dos mapas de hunt.
- `extractor/ready-maps/<CIDADE>/<mesmo-nome>/` — espelha `maps/` 1:1 (mesmo path relativo, raiz
  diferente, gitignored/regenerável).
- `extractor/full-maps/<CIDADE>/` — o mapa da cidade inteira, um por cidade. Aqui a pasta **é** só o
  código da cidade (sem sufixo, ex: `ROOK/`, não `rook-full/`), e o conteúdo é renomeado pra
  combinar: `ROOK.otbm`, `ROOK-house.xml`, `ROOK-monster.xml`, `ROOK-npc.xml`, `ROOK-zones.xml`,
  saída `map.json` na mesma pasta.

O nome de uma pasta de hunt **é** o id do mapa, mais um sufixo legível pra humano:
`<CIDADE-TIPO-SEQ>_nome-descritivo`. Esse id:

- **Nunca é gerado pelo pipeline** — é escolhido à mão, digitado na sign do editor de mapas que
  marca a entrada daquele hunt no mapa da cidade inteira, e copiado (literalmente copiar-colar,
  não "traduzido") pro nome da pasta. `build_map.js`/`build_hunt_fragment.py` só leem e validam
  esse id, nunca inventam um novo.
- **Repete a cidade de propósito** (`ROOK/ROOK-HUNT-0002_.../`) — é redundante à vista, mas é
  exatamente essa redundância que permite colar o texto da sign direto no nome da pasta sem montar
  nada de cabeça (cidade + tipo + número).
- Vira, sem tradução nenhuma, o `mapId` do hunt e o `Location.id` do travel-graph no catálogo do
  `tibia-idle` — os dois eram strings diferentes reconciliadas por `resolveHuntLocationId`; agora são
  a mesma string, ponto.

**Exemplo — cidade real (Rookgaard):**

```
extractor/maps/ROOK/ROOK-HUNT-0002_bears-rookguard/
  bears-rookguard.otbm
  bears-rookguard-house.xml
  bears-rookguard-monster.xml
  bears-rookguard-npc.xml
  bears-rookguard-zones.xml

extractor/full-maps/ROOK/
  ROOK.otbm
  ROOK-house.xml
  ROOK-monster.xml
  ROOK-npc.xml
  ROOK-zones.xml
```

> **Renomeou um mapa de cidade? Reabra e re-salve o `.otbm` antes de qualquer coisa.** O cabeçalho
> do OTBM guarda os nomes dos xmls irmãos, e renomear os arquivos no disco não o atualiza: o editor
> abre o mapa, procura os nomes velhos, não acha, carrega zero NPC/spawn — e no save grava os xmls
> novos **vazios**. Foi exatamente assim que `ROOK-npc.xml` e `ROOK-monster.xml` foram zerados
> depois do renomeio `rook-full-*` → `ROOK-*` (recuperados do Git em seguida).

Note que o **nome da pasta** carrega o id (`ROOK-HUNT-0002_...`), mas os arquivos `.otbm`/`.xml` de
dentro continuam com o nome descritivo que o editor de mapas já exportou (`bears-rookguard.otbm`,
não `ROOK-HUNT-0002_bears-rookguard.otbm`) — o pipeline encontra o `.otbm`/`.xml` de dentro por
sufixo (`*.otbm`, `*-monster.xml`, ...), não por nome exato, então não é preciso renomear nada ao
mover um mapa pra sua pasta de cidade. Isso é diferente de `full-maps/<CIDADE>/`, onde o conteúdo
**é** renomeado pra bater com o código da cidade (só existe um mapa cidade-inteira por cidade, então
não há ambiguidade a resolver).

**Exemplo — cidade fictícia de mapas de teste/descartáveis (`TEST`):**

```
extractor/maps/TEST/TEST-HUNT-0001_dragon-darashia/
  dragon-darashia.otbm
  dragon-darashia-house.xml
  dragon-darashia-monster.xml
  dragon-darashia-npc.xml
  dragon-darashia-zones.xml
```

`TEST` é uma cidade como qualquer outra pro pipeline — mesmo mecanismo de pasta, nenhum sistema de
tag separado. `hunts`/`locations` sob `city: "TEST"` (campo derivado do id, nunca digitado à mão —
ver abaixo) ganham `status: "test"`, e o `tibia-idle` filtra a lista de hunts visível por
`city !== 'TEST'` por padrão — é assim que os mapas de teste (Dragon Darashia, Grim Reaper, Larva
Ankrah, Sea Serpent) somem da UI sem precisar de um campo `hidden` à parte.

`city`/`status` nunca são digitados à mão em nenhum hunt/location — o extractor deriva os dois do
próprio id em toda geração de fragmento (`city_ids.py`): `city` é o primeiro segmento
(`"ROOK-HUNT-0002"` → `"ROOK"`), `status: "test"` só aparece quando `city === "TEST"` (ausente, não
`null`/`false`, nos demais casos). Não há como os dois campos ficarem dessincronizados do id — eles
não existem em lugar nenhum além de serem recalculados a partir dele.

Locations de NPC seguem o mesmo formato `CIDADE-TIPO-slug` de todo outro tipo de POI: `ROOK-NPC-obi`
(cidade/tipo maiúsculos, slug minúsculo — antes era `rook-npc-obi`, tudo minúsculo, sem separar
cidade/tipo).

## Como adicionar um mapa novo

1. Decida o id do hunt à mão — é o texto que você vai colocar na sign do editor de mapas marcando
   a entrada desse hunt no mapa da cidade inteira, no formato `CIDADE-HUNT-SEQ` (ex:
   `ROOK-HUNT-0019`, sempre 4 dígitos). Se a cidade ainda não existir em `extractor/maps/`, crie a
   pasta (`extractor/maps/<CIDADE>/`) — é só isso, nenhum código muda.
2. Crie a pasta do mapa **dentro** da pasta da cidade, nomeada `<ID>_nome-descritivo`:
   ```
   extractor/maps/<CIDADE>/<ID>_nome-descritivo/
   ```
3. Coloque dentro dela os arquivos exportados pelo editor de mapas, sem renomear nada — o nome
   descritivo que o editor já usa ao exportar, não o id da pasta:
   ```
   extractor/maps/<CIDADE>/<ID>_nome-descritivo/
     nome-descritivo.otbm
     nome-descritivo-house.xml
     nome-descritivo-monster.xml
     nome-descritivo-npc.xml
     nome-descritivo-zones.xml
   ```
   O pipeline encontra o `.otbm`/XMLs de dentro por sufixo (`*.otbm`, `*-monster.xml`, ...), então
   não é preciso que o nome do arquivo bata com o nome da pasta — só a pasta carrega o id.
4. Rode, passando o **nome da pasta** (`<ID>_nome-descritivo`, não só o nome descritivo):
   ```
   node extractor/scripts/build_map.js <ID>_nome-descritivo
   ```
5. O resultado sai em `extractor/ready-maps/<CIDADE>/<ID>_nome-descritivo/` (mesmo path relativo de
   `maps/`, raiz diferente):
   ```
   map.json            ← tilemap Phaser (v5)
   metadata.json        ← metadados por appearanceId
   sprites/             ← PNGs copiados, organizados por appearanceId
   sheets/              ← folhas de sprite por (layerClass, tamanho)
   monsters/respawn.json (se houver spawns em monster.xml)
   ```
   E, na mesma passada, a árvore do formato novo em
   `extractor/ready-maps-v6/<CIDADE>/<ID>_nome-descritivo/`:
   ```
   map.json            ← tilemap v6: tile com pilha ordenada (ver MAP_JSON_V6.md)
   sheets/              ← folhas de sprite só por tamanho (2 por mapa)
   monsters/respawn.json (cópia, pra árvore ser autossuficiente)
   ```
   Os dois convivem de propósito: `ready-maps/` é o que o jogo consome hoje e fica intocado até o
   Phaser migrar — ver [ADR 0006](../docs/adr/0006-map-json-v6-pilha-por-tile.md).

### Exemplo: `orc-fortress.otbm`, hunt novo de Rookgaard

```
extractor/maps/ROOK/ROOK-HUNT-0019_orc-fortress/
  orc-fortress.otbm
  orc-fortress-house.xml
  orc-fortress-monster.xml
  orc-fortress-npc.xml
  orc-fortress-zones.xml
```

```
node extractor/scripts/build_map.js ROOK-HUNT-0019_orc-fortress
```

Saída: `extractor/ready-maps/ROOK/ROOK-HUNT-0019_orc-fortress/`.

6. Se o mapa novo introduz itens (loot, equipamento em NPC, etc.) que ainda não foram baked, rode
   também:
   ```
   npm run build-items
   ```
   Isso gera/atualiza, de forma **global** (não por mapa — o mesmo conjunto de assets serve todos
   os mapas): `extractor/atlases/items-static/` (sheets compartilhadas, itens sem animação) e
   `extractor/atlases/items-animated/` (sheets compartilhadas, itens animados — mesmo modelo,
   frames de animação em vez de ícones fixos) e `extractor/atlases/items-index.json` (índice
   `itemId → localização do sprite`, consumido pelo repositório `tibia-idle`). Não é chamado automaticamente
   por `build_map.js` — mesmo padrão já usado pelo atlas de outfit (`bake_outfit_atlas.py`, também
   um passo manual separado) — porque é global e caro (~2min no dado real), então rodar em toda
   invocação de `build_map.js` penalizaria até rebuilds repetidos do mesmo mapa durante iteração.
   Rode sempre que adicionar/mudar itens, não a cada build de mapa. Ver
   `.scratch/item-sprite-sheets/spec.md` para o contrato completo.
7. Gere o fragmento de dados de jogo do mapa (hunts/monsters/loot) para revisar antes de mandar
   pro back-end (ver "Export pro back-end" abaixo pra onde cada coleção vai parar):
   ```
   python extractor/scripts/build_hunt_fragment.py ROOK-HUNT-0019_orc-fortress --map-id ROOK-HUNT-0019
   ```
   Saída: `extractor/ready-maps/ROOK/ROOK-HUNT-0019_orc-fortress/db-fragment.json`. Por padrão
   **este script nunca escreve fora de `extractor/`** — `monsters` e `loot` no fragmento já saem
   prontos (derivados mecanicamente do `respawn.json`), `hunts` sai como rascunho com um campo
   `_todo` listando o que precisa de revisão humana (nome/label, arte de portrait,
   `startPosition`). Revise e copie à mão.

   `--map-id` é **obrigatório** — não é mais opcional nem auto-atribuído. O script extrai o id
   embutido no nome da pasta (tudo antes do primeiro `_`) e **compara** com o valor passado em
   `--map-id`; uma divergência é erro, citando os dois valores (ex: `--map-id ROOK-HUNT-0013 não
   bate com o id da pasta (ROOK-HUNT-0014)`) — pense nisso como uma dupla confirmação deliberada,
   não uma formalidade.

   Se preferir pular a cópia manual, use `--export` (opcional, precisa ser pedido explicitamente —
   `--all` sozinho continua sem tocar no back-end):
   ```
   python extractor/scripts/build_hunt_fragment.py --all --export
   ```
   `loot` e o respawn são sempre reescritos (100% mecânicos). `hunts` só é **adicionado** ao
   `catalog-source.json` se o `mapId` ainda não existir — um hunt já curado nunca é sobrescrito, e
   o rascunho novo entra com o campo `_todo` junto, como lembrete. Um `mapId` que **já está
   registrado** é erro sem `--edit` ("ID do mapa já existe — use --edit se a intenção é atualizar")
   — nada é escrito; passe `--edit` quando a intenção realmente for atualizar um mapa já
   registrado. Com `--all`, `--map-id` não é aceito (cada mapa já tem o seu, embutido na própria
   pasta). Por padrão aponta pro checkout irmão `../tibia-idle`, ajustável via
   `--tibia-idle-dir` ou `TIBIA_IDLE_DIR`.
8. Se o mapa novo introduziu sprites de item novos (passo 6 gerou atlases novos), publique-os
   no repositório `tibia-idle`:
   ```
   python extractor/scripts/sync_items_to_tibia_idle.py
   ```
   Copia (comparando conteúdo, não sobrescreve à toa) `extractor/atlases/items-static/`,
   `extractor/atlases/items-animated/` e `extractor/atlases/items-index.json` para
   `apps/tibia-idle-front/public/assets/` no repositório `tibia-idle`, assumido como
   `../tibia-idle` (ajustável via `--tibia-idle-dir` ou `TIBIA_IDLE_DIR`).

## Travel graph (mapa cidade inteira)

Diferente dos mapas de hunt (pequenos, exportados um a um em `extractor/maps/<CIDADE>/<pasta>/`), o
grafo de viagem (`locations`/`travelGraph` no catálogo do `tibia-idle`) é derivado do **mapa da
cidade inteira**, que vive em `extractor/full-maps/<CIDADE>/` (fonte **e** saída ficam na mesma
pasta — diferente do par `maps/` → `ready-maps/` dos hunts). Hoje só existe `ROOK` (Rookgaard). Ver
`.scratch/travel-graph-and-locations/spec.md` para o design completo.

O mapa da cidade **não produz um `map.json`**. O grafo nunca leu um mapa: de `objectDefs` ele usava
só as `flags` por appearance, e nada mais — nem `floors`, nem `sheets`, nem `tilesets`, nem
`animations`. Essa tabela agora é um artefato próprio e versionado,
`extractor/appearance-flags/<CIDADE>.json` (~2100 entradas, 161 KB), no lugar dos 20,3 MB de
`map.json` + 1,8 MB de `metadata.json` que eram gerados e descartados.

1. Faça o dump cru do `.otbm` (é dele que saem os tiles):
   ```
   node extractor/scripts/dump_otbm.js ROOK
   ```
2. Gere o fragmento `{locations, travelGraph}` — um único argumento, o código da cidade (não mais
   `region` + `--city-prefix` separados: a cidade já é a chave de tudo, do path ao prefixo de id):
   ```
   uv run python extractor/scripts/build_travel_fragment.py ROOK
   ```
   Lê `extractor/raw-maps/ROOK.raw.json` + `extractor/appearance-flags/ROOK.json` + o
   [vendor do Canary](#vendor-do-canary) — **nenhum checkout do Canary é necessário**. Saída:
   `extractor/full-maps/ROOK/db-fragment.json`, pra revisar e colar à mão — por padrão **este script nunca escreve fora de `extractor/`**, mesmo
   padrão do `build_hunt_fragment.py`. Sai junto o `travel-graph-rejections.txt` (passo 4).
3. Se preferir pular a cópia manual, use `--export` (escreve `locations`/`travelGraph` no
   `catalog-source.json` do `tibia-idle` — ver "Export pro back-end" abaixo):
   ```
   python extractor/scripts/build_travel_fragment.py ROOK --export
   ```
   `locations` é upsert por id: campos mecânicos (posição, `shop`) sempre atualizados, e o
   `displayName` de uma location já curada (sem `_todo`) nunca sobrescrito — uma location da cidade
   que sumiu do fragmento é **reportada, nunca apagada** (pode carregar curadoria). Já o
   `travelGraph` é **substituído**, não mesclado: o fragmento é o conjunto completo de arestas da
   cidade, então aresta que não está nele deixa de existir no catálogo. Foi o upsert-só-adiciona
   que deixou 23 arestas que nenhum BFS produziu sobreviverem no catálogo versionado, uma delas
   citando `ROOK-HUNT-00015`. Arestas entre outras cidades não são tocadas. Por padrão aponta pro
   checkout irmão `../tibia-idle`, ajustável via `--tibia-idle-dir` ou `TIBIA_IDLE_DIR`.
4. Confira `extractor/full-maps/<CIDADE>/travel-graph-rejections.txt` — todo nó **sem entrada no
   grafo fica fora do fragmento** e vai pra esse arquivo, com o que existe dele e o que fazer:

   | Caso | O que o relatório carrega | O que fazer |
   |---|---|---|
   | `poi-without-edge` | id + `x/y/z` | a placa existe mas o tile dela não alcança ninguém — abrir a coordenada no editor e mover pra um tile andável |
   | `edge-without-poi` | id + as arestas que o citam (sem coordenada) | id escrito errado na fonte — corrigir o texto da placa |
   | `hunt-without-poi` | id + nome da pasta (sem coordenada) | o mapa da hunt existe em `maps/`, mas ninguém marcou a entrada — colocar a placa no OTBM |

   A ordem é determinística (caso, depois id), pra dar diff limpo entre execuções.

**Pontos de interesse (POIs) são marcados no `.otbm` com uma sign** (item 2016, `uid` 10001+, texto
no formato `CIDADE-TIPO-NNNN`, com `NNNN` sendo **exatamente 4 dígitos** — ex: `ROOK-HUNT-0001`) —
tipos `HUNT`/`TEMPLE`/`DEPOT`/`QUEST`. Uma quantidade de dígitos diferente de 4 (`ROOK-HUNT-1`,
`ROOK-HUNT-00015`) é rejeitada como `invalid-sign-format`, não aceita como um id "válido" só que
órfão — foi assim que um typo de 5 dígitos (`ROOK-HUNT-00015`) escapou validação antes desta regra.
Cada motivo de warning tem sua própria mensagem (`invalid-sign-format` vs. `duplicate-sign-id`
nunca compartilham texto genérico) — uma sign bem-formada colocada duas vezes por engano
(`ROOK-HUNT-0006`, `uid`/texto idênticos) é reportada como duplicata, não como "formato inválido".

Locations do tipo `NPC` não usam sign — vêm direto de `<CIDADE>-npc.xml`, e seu id segue o mesmo
formato `CIDADE-TIPO-slug` das demais (`ROOK-NPC-obi`). **NPC é nó do grafo como qualquer outro**, e
sua distância sai do mesmo BFS por tiles andáveis, nunca de euclidiana: a partir da onda 2.5 só se
compra estando no NPC, então ele é destino de viagem (o `CONTEXT.md` do `tibia-idle` registra a
reversão da decisão anterior). Dois NPCs colados viram dois destinos a `tileCount` 0 — é a verdade
do mapa, não ruído.

NPC tem **alcance** (`--npc-reach`, default 3): o jogador conta como tendo chegado ao NPC parando
no tile andável mais próximo dentro desse raio. Sem isso, quase todo balconista de Rook é destino
inalcançável — eles ficam atrás de um balcão `unpass`, num bolsão de dois tiles onde ninguém entra.
Cada tile de aproximação custa a própria distância até o NPC (não 0), então um NPC em rua aberta
entra pelo próprio tile de graça e **suas distâncias não encolhem**. O alcance vale **só pra NPC**:
placa ilhada é bug de mapa e continua indo pro relatório de rejeição, não é acobertada.

**O alcance é a única parte que não é caminho andado**, e vale saber: a distância do NPC até o tile
de aproximação é medida em linha reta (Chebyshev), **ignorando parede** — é literalmente atravessar
o balcão. Todo o resto do trajeto é BFS por tiles andáveis. Ou seja, o alcance é um atalho por
geometria maciça, limitado ao raio: com o default 3, no máximo 3 tiles de um lado e 3 do outro. É o
preço de conseguir expressar "estou no balconista" num grafo que só conhece tile andável.

Por isso o default é 3, e não mais: é onde Rookgaard para de mudar. 2 e 3 dão o mesmo resultado
(todo balconista entra, plenamente ligado ao resto da cidade), e 4+ só acrescenta um NPC —
atravessando ~5 tiles de parede maciça pra deixá-lo com uma única aresta artificial, e escondendo do
relatório um NPC que está genuinamente mal colocado. Alcance largo o bastante pra inventar caminho é
pior que um nó que o relatório manda você ir consertar.

Duas locations só ganham uma aresta em `travelGraph` se houver caminho andável entre elas no grafo
de tiles (BFS por location, sem penalidade diagonal, sem custo por tipo de piso) — **um par sem
aresta não é erro**, é o grafo genuinamente desconectado nesse trecho. As arestas são canônicas
(`from` < `to`, um par sem repetir, nunca auto-aresta) e a lista sai ordenada, então rodar de novo
contra um mapa inalterado dá um fragmento byte a byte idêntico. Migrar sinalizações antigas (ids sem
o segmento `TIPO`) pro formato novo é tarefa manual de edição de mapa, o extractor não faz isso
sozinho.

## Export pro back-end

Este pipeline **não tem mais um destino só**. Existia: `apps/tibia-idle-mock-api/db.json`, servido
por `json-server`, com todas as coleções juntas. Esse app foi apagado (fatia 1.8) e o que ele
carregava foi separado **por como o back-end lê cada coisa**. Nada mais escreve num `db.json` — o
flag antigo `--write-db` virou `--export`. O contrato está codificado em
`extractor/scripts/content_export.py`, que é onde os paths e as regras de merge moram.

| Destino | O que vai | Como o back-end usa |
|---|---|---|
| `apps/tibia-idle-api/content/catalog-source.json` | `hunts`, `locations`, `travelGraph` | Vira **linha no Postgres**: `import-content` valida com Zod e grava. Ninguém lê esse arquivo em runtime |
| `apps/tibia-idle-api/content/hunts/loot.json` | `{mapId, drops}` por hunt | Lido **do disco em runtime**, inteiro por hunt |
| `apps/tibia-idle-api/content/hunts/respawn/<HUNT-ID>.json` | `{mapBoundsRef, monsterDefs, spawns}` | Idem — repassado direto pro Phaser |
| `apps/tibia-idle-api/content/hunts/hunts.json` | `{id, mapId, mapUrl, startPosition}` | Manifesto que o simulador lê. **Derivado** do `hunts` do catálogo, nunca mesclado à parte |
| `apps/tibia-idle-front/public/assets/` | atlases de item e sheets de outfit | `sync_items_to_tibia_idle.py`, ver passo 8 |

A linha entre as duas primeiras é a da ADR-0015: virou coluna o que a tela **filtra e ordena**
(cidade, status, POI de entrada); ficou em arquivo o que se carrega inteiro e não responde a
`WHERE` (respawn, loot). O `catalog-source.json` é versionado ao lado da API — é o que faz
`nx run db:reset` ser **um** comando em vez de "ache o despejo do extractor primeiro".

Os dois comandos que exportam:

```
python extractor/scripts/build_hunt_fragment.py --all --export
python extractor/scripts/build_travel_fragment.py ROOK --export
```

Depois, no `tibia-idle`, pro catálogo virar linha:

```
nx run db:reset
```

**Semântica do merge**, e ela não é a mesma pras três coleções do catálogo, de propósito:

- `hunts` — **append-only**. Só entra se o `mapId` for novo; um hunt já existente nunca é tocado.
  Nome, label, portrait, seed e `startPosition` são curados à mão, e não há merge por campo aqui:
  a entrada inteira fica como está. Reexportar por cima devolveria o título gerado e o seed
  placeholder.
- `locations` — **upsert por id**, merge por campo: posição e `shop` sempre atualizados,
  `displayName`/`huntId` preservados depois que uma edição humana tirou o `_todo`. Location da
  cidade que sumiu do fragmento é **reportada, nunca apagada** — pode carregar curadoria.
- `travelGraph` — **substituído** por cidade. Sem curadoria nenhuma numa aresta, e o fragmento é o
  conjunto completo, então aresta que não está nele deixa de existir.
- `loot` e `respawn` — sempre reescritos. 100% mecânicos, derivados do `respawn.json`.

A coleção `monsters` do fragmento **não tem mais destino**. O payload dela ainda importa (é de onde
sai o arquivo de respawn), mas o embrulho que ela adicionava — `id`/`mapId`/`assetsRoot` — não é
lido por ninguém desde que o back-end passou a ler `respawn/<HUNT-ID>.json` direto.

### Três armadilhas do `--all --export`

O `--all` varre `ready-maps/` — **saída gerada e gitignored** —, não a árvore de fontes. Isso faz
ele achar coisa que não devia virar conteúdo. As três já custaram caro, e as três estão cobertas:

1. **Pasta de rascunho** (`DEBUG-MAP`, `Nova pasta`, `TEST-WASPS-DEBUG`) não tem id no nome, então o
   "map id" vira o nome da pasta. O export **pula** qualquer id fora de `CIDADE-TIPO-NNNN` — sem
   isso, um `nx run db:reset` importaria uma hunt chamada "Nova pasta".
2. **Mapa com a fonte apagada.** `ready-maps/` é gitignored, então apagar um mapa de `maps/` deixa o
   build dele pra trás e o `--all` continua achando. Foi assim que o `ROOK-HUNT-0013`, removido em
   f67a94c, voltou como hunt viva no catálogo. O export **pula** o que não tem mais fonte.
3. **Build desatualizado.** Pela mesma razão, `ready-maps/` pode ser mais velho que `maps/` — e aí o
   export publica conteúdo **mais velho** por cima do que já está no back-end, sem erro nenhum. O
   que torna isso traiçoeiro é que uma edição legítima (podar spawns inalcançáveis, por exemplo)
   também faz o export encolher coisa: olhando só o diff, não dá pra distinguir "podei de
   propósito" de "exportei de um build velho". Aqui é só **aviso** (mtime não sobrevive a um clone
   novo, e travar num checkout recém-clonado seria pior).

> **Regra prática:** `node build_map.js --all` **antes** de `build_hunt_fragment.py --all --export`.
> Exportar de um build velho não falha — degrada em silêncio, e o diff parece uma poda intencional.

## Estrutura de pastas

```
extractor/
  scripts/            ← pipeline ativo (o único lugar que você deveria editar/rodar)
    dump_otbm.js       etapa 1: .otbm → .raw.json (via vendor/otbm2json.js)
    build_phaser_map.py etapa 2: .raw.json → map.json (v5 e v6) + sprites/ + respawn.json
    build_map.js       runner: 1 mapa ou --all, chama as duas etapas
    extract_sprites.py  etapa 0 (avulsa): assets/ do cliente → extractor/sprites/ (biblioteca
                             compartilhada); `--group <nome>` extrai só um grupo
                             (items/effects/missiles/outfits)
    client_sprites.py   lógica pura: sprite id → PNG, sobre as folhas LZMA do cliente
    fetch_assets.py     baixa e verifica o cliente fixado em assets-manifest.json
    tile_stack.py       lógica pura: flags do appearances → draw slot + stack order de uma tile (v6)
    map_v6.py           lógica pura: dump OTBM → documento map.json v6 (ver MAP_JSON_V6.md)
    sheet_packer.py     lógica pura: aparências → grade de folhas de sprite + gids
    item_classifier.py  overrides manuais de classificação de layer (só v5 — o v6 não consulta lista de id)
    map_v6_migration_report.py  CLI (avulso): confere v6 contra v5, contagem por tile + antes/depois
    ground_equivalent_report.py CLI (avulso): mede o `ground_equivalent` do RME contra os mapas
    bake_outfit_atlas.py  bake global (avulso): sprites/outfits/ → atlases/outfits/<id>.{png,json}
    bake_effect_atlas.py  bake global (avulso): sprites/effects/ → atlases/effects/effects.{png,json};
                             só os ids de ATLAS_EFFECT_IDS (hoje o efeito 11, teleport) — ver SPRITE_METADATA.md
    bake_item_atlas.py      lib compartilhada: classificação de equipamento/consumível + resolução de frame,
                             usada pelos dois bakes de sheet abaixo (bake_item()/main() próprios não são
                             mais chamados pelo pipeline — ver bake_item_sheets_animated.py)
    bake_item_sheets.py    bake global (avulso): itens estáticos → atlases/items-static/*.{png,json}
    bake_item_sheets_animated.py bake global (avulso): itens animados → atlases/items-animated/*.{png,json}
    build_item_index.py    bake global (avulso): junta os dois bakes de sheet acima → atlases/items-index.json
    build_items.js         runner: chama os três bakes de item acima em sequência (npm run build-items)
    hunt_fragment.py        lógica pura: respawn.json → fragmento {monsters, loot, hunts}
    build_hunt_fragment.py  CLI (avulso): gera ready-maps/<CIDADE>/<pasta>/db-fragment.json; só escreve no back-end com --export
    sync_items_to_tibia_idle.py  CLI (avulso): publica atlases de item no repositório tibia-idle
    travel_graph.py         lógica pura: mapa cidade-inteira → grafo de tiles, distância por location, rejeição, fragmento {locations, travelGraph}
    build_travel_fragment.py CLI (avulso): gera full-maps/<CIDADE>/db-fragment.json + travel-graph-rejections.txt; só escreve no back-end com --export
    content_export.py       lógica pura: pra onde cada coleção vai no back-end e como cada uma mescla (ver "Export pro back-end")
    map_dirs.py             lógica pura: descoberta de pastas em dois níveis (maps/<CIDADE>/<pasta>), usada por build_phaser_map.py, build_hunt_fragment.py e build_travel_fragment.py
    city_ids.py             lógica pura: deriva `city`/`status` do id de um hunt/location (nunca digitados à mão)
  vendor/
    otbm2json.js       lib de leitura/escrita de OTBM (vendorizada, não é do npm)
    rme-materials/     arquivos de autoria do Remere's Map Editor, cópia inalterada (ver o NOTICE.md
                         de lá). Evidência da medição do `ground_equivalent` — nenhum script de
                         build lê essa pasta
  maps/<CIDADE>/<ID>_nome/  SOURCE — .otbm + xmls de cada mapa de hunt (versionado); <CIDADE> nunca é
                             adivinhada, é sempre a pasta-pai (ver "Convenção de pastas" acima)
  full-maps/<CIDADE>/  SOURCE **e** saída do mapa cidade-inteira (.otbm, map.json e
                         travel-graph-rejections.txt versionados — diferente do ready-maps/ dos
                         hunts; db-fragment.json continua gitignored, igual ao dos hunts — feed do
                         travel-graph, não da rotação de hunts). O relatório de rejeição é
                         versionado justamente pro diff entre execuções ter uma baseline. Pasta =
                         só o código da cidade, conteúdo renomeado pra bater (ROOK.otbm, ...)
  raw-maps/<pasta>.raw.json   saída da etapa 1, hunts e cidade-inteira (gitignored, regenerável)
  ready-maps/<CIDADE>/<pasta>/  saída da etapa 2 pros mapas de hunt, espelha maps/ 1:1 (gitignored, regenerável)
  ready-maps-v6/<CIDADE>/<pasta>/  a mesma saída no formato v6, raiz separada pro ready-maps/ ficar
                         intocado até o jogo migrar (gitignored). Só mapas de hunt — o mapa
                         cidade-inteira não é renderizado, ver ADR 0006
  sprites/              biblioteca de sprites extraída do cliente Tibia (gitignored, binário grande)
  atlases/              saída dos bakes globais (outfits/items-static/items-animated/effects + items-index.json), gitignored, regenerável
  otservbr-monster.xml  lookup nome→looktype de monstro, compartilhado entre mapas
  assets-manifest.json  versão do cliente Tibia + checksums (versionado)
  vendor/canary/        fatias do Canary que o pipeline lê (versionado)
  appearance-flags/     tabela de flags por appearance, por cidade (versionado)
  _legacy/              scripts antigos/exploratórios, não fazem parte do pipeline —
                         inclui read_aec.py, do insumo .aec aposentado
```

---

## FAQ

### Geração de mapas

**Preciso rodar `dump_otbm.js` e `build_phaser_map.py` na mão?**
Não. `build_map.js` chama as duas etapas em sequência para cada mapa. Só rode
os scripts individuais se estiver depurando uma etapa específica.

**Como o `--all` descobre quais mapas existem?**
Ele varre `extractor/maps/<CIDADE>/*/` (dois níveis — toda cidade
automaticamente, sem hardcode) procurando uma subpasta que contenha algum
arquivo `*.otbm`. Pastas sem esse arquivo (como `training-spots/`, que está
vazia) são ignoradas.

**Erro `Mapa "<nome>" não encontrado em nenhuma cidade sob .../maps nem em .../full-maps`**
O nome passado precisa ser o nome exato de uma pasta de mapa
(`maps/<CIDADE>/<nome>/`) ou de uma cidade inteira (`full-maps/<CIDADE>/`).
O erro lista as cidades disponíveis pra ajudar a comparar — confira também
maiúsculas/minúsculas e hífens/underscore.

**O `.otbm`/XMLs de dentro da pasta precisam ter o mesmo nome da pasta?**
Não — só a pasta carrega o id (`<ID>_nome-descritivo`). O `.otbm`/XMLs de
dentro são encontrados por sufixo (`*.otbm`, `*-monster.xml`, ...), então o
nome que o editor de mapas já usa ao exportar (`bears-rookguard.otbm`, por
exemplo) funciona direto, sem renomear nada. Isso não vale para
`full-maps/<CIDADE>/`, onde o conteúdo É renomeado pra bater com o código da
cidade — ver "Convenção de pastas" acima.

**`build_phaser_map.py falhou (exit 1)` ao rodar `--all` para vários mapas**
O runner continua para o próximo mapa mesmo se um falhar, e no fim lista quais
falharam. Rode aquele mapa sozinho (`node build_map.js <nome-da-pasta>`) pra
ver o erro completo.

**"python" não é reconhecido pelo sistema**
`build_map.js` chama o comando `python` diretamente. Se no seu ambiente o
interpretador se chama `python3` ou `py`, troque a string em
`extractor/scripts/build_map.js` (variável usada no `spawnSync`) ou crie um
alias/symlink chamado `python` no PATH.

### Sprites e appearances

**O que é `extractor/sprites/`?**
Uma biblioteca compartilhada de imagens (items, missiles, outfits, effects) extraída
uma única vez da pasta `assets/` do cliente Tibia (ver
[Cliente Tibia](#cliente-tibia-fonte-dos-sprites)). É a mesma pasta para
todos os mapas — não é regenerada por mapa. Fica fora do git (binário
grande, veja `.gitignore`).

Até o ticket 08 a fonte eram quatro containers `.aec`, export do Assets Editor. Foram aposentados:
os dois editores que existem hoje são Windows-only, e o que ainda tem manutenção
(`beats-dh/Beats-Assets-Editor`) passou a gravar os bytes de sprite num arquivo **companheiro**
`.aec.sprites` — um export novo produziria containers vazios, provavelmente sem erro.

**Preciso rodar `extract_sprites.py` toda vez que adiciono um mapa?**
Não, a menos que o mapa novo introduza um monstro (outfit) que ainda não
existe em `extractor/sprites/outfits/`. Nesse caso rode:
```
uv run python extractor/scripts/fetch_assets.py      # se ainda não tem o cliente
uv run python extractor/scripts/extract_sprites.py   # outfits + effects
uv run python extractor/scripts/extract_sprites.py --group items --group missiles
```
É idempotente — PNGs/JSONs já existentes não são regravados. Sem `--group`, roda só `outfits` e
`effects` (`ENABLED_GROUPS`); `items` é o grupo caro, 42107 appearances.

A fonte é a pasta `assets/` do cliente fixado em `assets-manifest.json` — ver
[Cliente Tibia](#cliente-tibia-fonte-dos-sprites). Os pixels são recortados das folhas do cliente
pelo `sprite_info.sprite_id` que o `appearances.dat` oficial já declara; não existe mais insumo
`.aec`.

**`[WARN] appearance X: missing_sprite:<id>`**
O item existe no mapa mas o PNG do sprite não foi encontrado em
`sprites/items/`, `sprites/missiles/` ou `sprites/`. O mapa ainda é gerado,
só fica sem essa imagem.

**Outfit de monstro não aparece / veio incompleto**
`extract_sprites.py` ignora outfits cujo `patternHeight`, `patternDepth` ou
`layers` seja maior que 1 em algum frame group (`outfit_has_addons_or_mounts`)
— sinal de addon/montaria/camada extra, pulados de propósito. Outfits de
monstro com animação contínua no IDLE (ex: Wasp, Ghost, Fire Elemental —
mais de 36 sprites só por causa das fases de animação, não de addons) **são**
extraídos normalmente. Veja `PHASER_MONSTERS.md` para como o `idle` desses
outfits é representado no `respawn.json`.

### Monstros

**`[INFO] Nenhum spawn de monstros encontrado.`**
Normal quando `monster.xml` não tem nenhuma tag `<monster centerx=...>` no
nível esperado (áreas de spawn). Não é erro — o mapa é gerado sem
`monsters/respawn.json`.

**`[WARN] Outfit ID não encontrado para monstro: '<nome>'`**
O nome do monstro no `monster.xml` não bate com nenhum `name=` em
`extractor/otservbr-monster.xml` (comparação é case-insensitive). Adicione o
monstro nesse arquivo ou corrija o nome no spawn. O monstro ainda entra no
`respawn.json`, mas com `outfitId: 0` (sem sprite).

**Onde fica o lookup de monstros?**
`extractor/otservbr-monster.xml` — é compartilhado entre todos os mapas, não
duplicado por mapa.

### Publicando dados no repositório `tibia-idle`

**Por que `build_hunt_fragment.py` não escreve no back-end por padrão?**
De propósito — `hunts` (nome, portrait, `startPosition`) exige curadoria
humana que não dá pra derivar do mapa (ver `hunt_fragment.py`). O script gera
`ready-maps/<CIDADE>/<pasta>/db-fragment.json` e para por aí; escrever no
back-end é sempre um pedido explícito, via `--export`.

**Cadê o `db.json`? O `--write-db` sumiu.**
O `apps/tibia-idle-mock-api` foi apagado (fatia 1.8) e as coleções dele foram
separadas por como o back-end lê cada uma. `--write-db` virou `--export`, que
escreve em mais de um destino — ver "Export pro back-end" acima pra tabela
completa.

**Onde ficavam antes os scripts `sync-item-sprites-from-extractor.py` e
`sync-loot-from-extractor.py`?**
Em `tibia-idle/apps/tibia-idle-mock-api/scripts/`. Foram removidos de lá —
sincronizar dados do extractor é responsabilidade deste pipeline, não do app
consumidor. `sync-item-sprites-from-extractor.py` virou
`extractor/scripts/sync_items_to_tibia_idle.py` (mesmo comportamento, mesma
direção de cópia, só que rodado a partir daqui). `sync-loot-from-extractor.py`
foi substituído por `build_hunt_fragment.py` — ver acima.

### Classificação de layers (paredes, roof, borders...)

**Um item está aparecendo na camada errada (ex: parede virou "object")**
Edite `extractor/scripts/item_classifier.py` e adicione o `appearanceId` na
categoria certa — essa classificação manual tem prioridade sobre a detecção
automática por flags.

**Como ver quais IDs ainda dependem só da detecção automática?**
```
python extractor/scripts/item_classifier.py --dump-unknown extractor/ready-maps/<CIDADE>/<pasta>/map.json
```

### Git — o que versionar

- **Versionado:** `extractor/maps/` (fonte dos mapas), `extractor/scripts/`,
  `extractor/vendor/`, `extractor/otservbr-monster.xml`, os `.md` de
  documentação.
- **Gitignored (regenerável, não commitar):** `extractor/raw-maps/`,
  `extractor/ready-maps/`, `extractor/ready-maps-v6/`, `extractor/sprites/`,
  `extractor/*.aec` (insumo aposentado), `extractor/full-maps/*/map.json`.
- Se `git status` mostrar algo dentro dessas pastas ignoradas, normalmente é
  sinal de que o `.gitignore` está desatualizado, não que precisa commitar.

### Assets no jogo (Phaser)

**Por que `assetsRoot` no `map.json` ainda tem o sufixo `-sprites`
(ex: `assets/orc-fortress-sprites`) se a pasta local agora é
`ready-maps/orc-fortress/` sem sufixo?**
De propósito. `assetsRoot` é o path que o *jogo* usa em runtime para montar
as URLs dos PNGs (`${assetsRoot}/sprites/<id>/<spriteId>.png`) — é
independente de onde este repositório guarda a saída localmente. Mantivemos
o sufixo pra não quebrar quem já lê esse campo do lado do jogo.

### Legado

**O que tem em `extractor/_legacy/`?**
Scripts de exploração pontual e um parser OTBM manual antigo, mantidos só
como referência histórica — não fazem parte do pipeline e os paths internos
deles estão desatualizados. Veja `_legacy/README.md`.
