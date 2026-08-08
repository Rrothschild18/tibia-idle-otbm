# Pipeline de mapas

Guia rápido + FAQ para gerar mapas Phaser a partir de arquivos `.otbm`.
Para detalhes internos do formato de saída, veja [`MAP_JSON_V6.md`](MAP_JSON_V6.md) (formato novo,
a pilha por tile) e — para o v5, que o jogo ainda consome — [`CONVERTER_DOCS.md`](CONVERTER_DOCS.md)
e [`PHASER_INTEGRATION.md`](PHASER_INTEGRATION.md).

## TL;DR

```
node extractor/scripts/build_map.js <nome-da-pasta>  # gera só esse mapa (ex: ROOK-HUNT-0010_bears-rookguard)
node extractor/scripts/build_map.js --all            # gera todos os mapas de hunt de todas as cidades
npm run build-map -- --all                           # atalho para o comando acima
npm run build-items                                  # bake global de sprites de item (ver abaixo)
python extractor/scripts/build_hunt_fragment.py ROOK-HUNT-0010_bears-rookguard --map-id ROOK-HUNT-0010
                                                      # gera db-fragment.json (hunts/monsters/loot) —
                                                      # nunca escreve em db.json, ver seção 6 abaixo
python extractor/scripts/sync_items_to_tibia_idle.py # publica atlases de item no repo tibia-idle
node extractor/scripts/build_map.js ROOK             # gera o mapa cidade-inteira (fonte: full-maps/ROOK/)
python extractor/scripts/build_travel_fragment.py ROOK
                                                      # gera db-fragment.json (locations/travelGraph) —
                                                      # nunca escreve em db.json, ver "Travel graph" abaixo
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
- Vira, sem tradução nenhuma, o `mapId` do hunt e o `Location.id` do travel-graph no `db.json` do
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
7. Gere o fragmento de dados de jogo do mapa (hunts/monsters/loot) para colar manualmente
   no `db.json` do repositório `tibia-idle`:
   ```
   python extractor/scripts/build_hunt_fragment.py ROOK-HUNT-0019_orc-fortress --map-id ROOK-HUNT-0019
   ```
   Saída: `extractor/ready-maps/ROOK/ROOK-HUNT-0019_orc-fortress/db-fragment.json`. Por padrão
   **este script nunca escreve em `db.json`** — `monsters` e `loot` no fragmento já saem prontos
   (derivados mecanicamente do `respawn.json`), `hunts` sai como rascunho com um campo `_todo`
   listando o que precisa de revisão humana (nome/label, arte de portrait, `startPosition`). Revise
   e copie à mão.

   `--map-id` é **obrigatório** — não é mais opcional nem auto-atribuído. O script extrai o id
   embutido no nome da pasta (tudo antes do primeiro `_`) e **compara** com o valor passado em
   `--map-id`; uma divergência é erro, citando os dois valores (ex: `--map-id ROOK-HUNT-0013 não
   bate com o id da pasta (ROOK-HUNT-0014)`) — pense nisso como uma dupla confirmação deliberada,
   não uma formalidade.

   Se preferir pular a cópia manual, use `--write-db` (opcional, aditivo — precisa ser pedido
   explicitamente, `--all` sozinho continua sem tocar em `db.json`):
   ```
   python extractor/scripts/build_hunt_fragment.py --all --write-db
   ```
   `monsters`/`loot` são sempre mesclados por `mapId` (upsert — igual ao antigo
   `sync-loot-from-extractor.py`, sempre correto porque é 100% mecânico). `hunts` só é
   **adicionado** se o `mapId` ainda não existir em `db.json` — um hunt já curado nunca é
   sobrescrito, e o rascunho novo entra com o campo `_todo` junto, direto no `db.json`, como
   lembrete. Um `mapId` que **já existe** em `db.json` é erro sem `--edit` ("ID do mapa já existe —
   use --edit se a intenção é atualizar") — nada é escrito; passe `--edit` quando a intenção
   realmente for atualizar um mapa já registrado. Com `--all`, `--map-id` não é aceito (cada mapa
   já tem o seu, embutido na própria pasta). Por padrão aponta pro checkout irmão
   `../tibia-idle/tibia-idle`, ajustável via `--tibia-idle-dir`.
8. Se o mapa novo introduziu sprites de item novos (passo 6 gerou atlases novos), publique-os
   no repositório `tibia-idle`:
   ```
   python extractor/scripts/sync_items_to_tibia_idle.py
   ```
   Copia (comparando conteúdo, não sobrescreve à toa) `extractor/atlases/items-static/`,
   `extractor/atlases/items-animated/` e `extractor/atlases/items-index.json` para
   `apps/tibia-idle-front/public/assets/` no repositório `tibia-idle`, assumido como
   `../tibia-idle/tibia-idle` (ajustável via `--tibia-idle-dir`).

## Travel graph (mapa cidade inteira)

Diferente dos mapas de hunt (pequenos, exportados um a um em `extractor/maps/<CIDADE>/<pasta>/`), o
grafo de viagem (`locations`/`travelGraph` no `db.json` do `tibia-idle`) é derivado do **mapa da
cidade inteira**, que vive em `extractor/full-maps/<CIDADE>/` (fonte **e** saída ficam na mesma
pasta — diferente do par `maps/` → `ready-maps/` dos hunts). Hoje só existe `ROOK` (Rookgaard). Ver
`.scratch/travel-graph-and-locations/spec.md` para o design completo.

1. Gere o `map.json` da cidade inteira (mesmo runner dos hunts, só que o nome passado resolve pra
   `full-maps/` em vez de `maps/`):
   ```
   node extractor/scripts/build_map.js ROOK
   ```
   Saída (versionada no Git, ao contrário do `ready-maps/` dos hunts): `extractor/full-maps/ROOK/map.json`.
2. Gere o fragmento `{locations, travelGraph}` — um único argumento, o código da cidade (não mais
   `region` + `--city-prefix` separados: a cidade já é a chave de tudo, do path ao prefixo de id):
   ```
   python extractor/scripts/build_travel_fragment.py ROOK
   ```
   Requer o passo 1 já feito (lê `extractor/raw-maps/ROOK.raw.json` +
   `extractor/full-maps/ROOK/map.json`) e um checkout local do Canary — por padrão
   `C:\canary-3.2.1` (ajustável via `--canary-dir`), usado só pra casar cada NPC com seu `.lua` de
   shop em `data-otservbr-global/npc/`. Saída: `extractor/full-maps/ROOK/db-fragment.json`, pra
   revisar e colar à mão — por padrão **este script nunca escreve em `db.json`**, mesmo padrão do
   `build_hunt_fragment.py`.
3. Se preferir pular a cópia manual, use `--write-db` (mescla `locations`/`travelGraph` direto no
   `db.json` do `tibia-idle`):
   ```
   python extractor/scripts/build_travel_fragment.py ROOK --write-db
   ```
   Campos mecânicos (posição, `shop`, `tileCount`) sempre são atualizados por id/par; o
   `displayName` de uma location já curada (sem `_todo`) nunca é sobrescrito. Por padrão aponta pro
   checkout irmão `../tibia-idle/tibia-idle`, ajustável via `--tibia-idle-dir`.

**Pontos de interesse (POIs) são marcados no `.otbm` com uma sign** (item 2016, `uid` 10001+, texto
no formato `CIDADE-TIPO-NNNN`, com `NNNN` sendo **exatamente 4 dígitos** — ex: `ROOK-HUNT-0001`) —
tipos `HUNT`/`TEMPLE`/`DEPOT`/`QUEST`. Uma quantidade de dígitos diferente de 4 (`ROOK-HUNT-1`,
`ROOK-HUNT-00015`) é rejeitada como `invalid-sign-format`, não aceita como um id "válido" só que
órfão — foi assim que um typo de 5 dígitos (`ROOK-HUNT-00015`) escapou validação antes desta regra.
Cada motivo de warning tem sua própria mensagem (`invalid-sign-format` vs. `duplicate-sign-id`
nunca compartilham texto genérico) — uma sign bem-formada colocada duas vezes por engano
(`ROOK-HUNT-0006`, `uid`/texto idênticos) é reportada como duplicata, não como "formato inválido".

Locations do tipo `NPC` não usam sign — vêm direto de `<CIDADE>-npc.xml`, e seu id segue o mesmo
formato `CIDADE-TIPO-slug` das demais (`ROOK-NPC-obi`). Duas locations só ganham uma aresta em
`travelGraph` se houver caminho andável entre elas no grafo de tiles (BFS por POI, sem penalidade
diagonal, sem custo por tipo de piso) — **um par sem aresta não é erro**, é o grafo genuinamente
desconectado nesse trecho (áreas ainda não conectadas por corredor andável, ou POIs sem sign
colocada). Migrar sinalizações antigas (ids sem o segmento `TIPO`) pro formato novo é tarefa manual
de edição de mapa, o extractor não faz isso sozinho.

## Estrutura de pastas

```
extractor/
  scripts/            ← pipeline ativo (o único lugar que você deveria editar/rodar)
    dump_otbm.js       etapa 1: .otbm → .raw.json (via vendor/otbm2json.js)
    build_phaser_map.py etapa 2: .raw.json → map.json (v5 e v6) + sprites/ + respawn.json
    build_map.js       runner: 1 mapa ou --all, chama as duas etapas
    extract_sprites.py  etapa 0 (avulsa): .aec → extractor/sprites/ (biblioteca compartilhada)
    tile_stack.py       lógica pura: flags do appearances → draw slot + stack order de uma tile (v6)
    map_v6.py           lógica pura: dump OTBM → documento map.json v6 (ver MAP_JSON_V6.md)
    sheet_packer.py     lógica pura: aparências → grade de folhas de sprite + gids
    item_classifier.py  overrides manuais de classificação de layer (só v5 — o v6 não consulta lista de id)
    map_v6_migration_report.py  CLI (avulso): confere v6 contra v5, contagem por tile + antes/depois
    ground_equivalent_report.py CLI (avulso): mede o `ground_equivalent` do RME contra os mapas
    bake_outfit_atlas.py  bake global (avulso): sprites/outfits/ → atlases/outfits/<id>.{png,json}
    bake_item_atlas.py      lib compartilhada: classificação de equipamento/consumível + resolução de frame,
                             usada pelos dois bakes de sheet abaixo (bake_item()/main() próprios não são
                             mais chamados pelo pipeline — ver bake_item_sheets_animated.py)
    bake_item_sheets.py    bake global (avulso): itens estáticos → atlases/items-static/*.{png,json}
    bake_item_sheets_animated.py bake global (avulso): itens animados → atlases/items-animated/*.{png,json}
    build_item_index.py    bake global (avulso): junta os dois bakes de sheet acima → atlases/items-index.json
    build_items.js         runner: chama os três bakes de item acima em sequência (npm run build-items)
    hunt_fragment.py        lógica pura: respawn.json → fragmento {monsters, loot, hunts}
    build_hunt_fragment.py  CLI (avulso): gera ready-maps/<CIDADE>/<pasta>/db-fragment.json — nunca escreve em db.json
    sync_items_to_tibia_idle.py  CLI (avulso): publica atlases de item no repositório tibia-idle
    travel_graph.py         lógica pura: mapa cidade-inteira → grafo de tiles, BFS por POI, fragmento {locations, travelGraph}
    build_travel_fragment.py CLI (avulso): gera full-maps/<CIDADE>/db-fragment.json — nunca escreve em db.json
    map_dirs.py             lógica pura: descoberta de pastas em dois níveis (maps/<CIDADE>/<pasta>), usada por build_phaser_map.py e build_hunt_fragment.py
    city_ids.py             lógica pura: deriva `city`/`status` do id de um hunt/location (nunca digitados à mão)
  vendor/
    otbm2json.js       lib de leitura/escrita de OTBM (vendorizada, não é do npm)
    rme-materials/     arquivos de autoria do Remere's Map Editor, cópia inalterada (ver o NOTICE.md
                         de lá). Evidência da medição do `ground_equivalent` — nenhum script de
                         build lê essa pasta
  maps/<CIDADE>/<ID>_nome/  SOURCE — .otbm + xmls de cada mapa de hunt (versionado); <CIDADE> nunca é
                             adivinhada, é sempre a pasta-pai (ver "Convenção de pastas" acima)
  full-maps/<CIDADE>/  SOURCE **e** saída do mapa cidade-inteira (.otbm e map.json versionados —
                         diferente do ready-maps/ dos hunts; db-fragment.json continua gitignored,
                         igual ao dos hunts — feed do travel-graph, não da rotação de hunts). Pasta =
                         só o código da cidade, conteúdo renomeado pra bater (ROOK.otbm, ...)
  raw-maps/<pasta>.raw.json   saída da etapa 1, hunts e cidade-inteira (gitignored, regenerável)
  ready-maps/<CIDADE>/<pasta>/  saída da etapa 2 pros mapas de hunt, espelha maps/ 1:1 (gitignored, regenerável)
  ready-maps-v6/<CIDADE>/<pasta>/  a mesma saída no formato v6, raiz separada pro ready-maps/ ficar
                         intocado até o jogo migrar (gitignored). Só mapas de hunt — o mapa
                         cidade-inteira não é renderizado, ver ADR 0006
  sprites/              biblioteca de sprites extraída dos .aec (gitignored, binário grande)
  atlases/              saída dos bakes globais (outfits/items-static/items-animated + items-index.json), gitignored, regenerável
  otservbr-monster.xml  lookup nome→looktype de monstro, compartilhado entre mapas
  *.aec                 assets binários do cliente Tibia (gitignored)
  _legacy/              scripts antigos/exploratórios, não fazem parte do pipeline
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
Uma biblioteca compartilhada de imagens (items, missiles, outfits) extraída
uma única vez dos arquivos `.aec` do cliente Tibia. É a mesma pasta para
todos os mapas — não é regenerada por mapa. Fica fora do git (binário
grande, veja `.gitignore`).

**Preciso rodar `extract_sprites.py` toda vez que adiciono um mapa?**
Não, a menos que o mapa novo introduza um monstro (outfit) que ainda não
existe em `extractor/sprites/outfits/`. Nesse caso rode:
```
python extractor/scripts/extract_sprites.py
```
É idempotente — PNGs/JSONs já existentes não são regravados.

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

**Por que `build_hunt_fragment.py` não escreve direto no `db.json` do
`tibia-idle`?**
De propósito — `hunts` (nome, portrait, `startPosition`) exige curadoria
humana que não dá pra derivar do mapa (ver `hunt_fragment.py`), e mesmo os
campos 100% mecânicos (`monsters`, `loot`) não devem ser mesclados sem
revisão. O script gera `ready-maps/<CIDADE>/<pasta>/db-fragment.json` e para
por aí; colar no `db.json` é sempre uma ação manual.

**Onde ficavam antes os scripts `sync-item-sprites-from-extractor.py` e
`sync-loot-from-extractor.py`?**
Em `tibia-idle/apps/tibia-idle-mock-api/scripts/`. Foram removidos de lá —
sincronizar dados do extractor é responsabilidade deste pipeline, não do app
consumidor. `sync-item-sprites-from-extractor.py` virou
`extractor/scripts/sync_items_to_tibia_idle.py` (mesmo comportamento, mesma
direção de cópia, só que rodado a partir daqui). `sync-loot-from-extractor.py`
foi substituído por `build_hunt_fragment.py`, que não escreve mais em
`db.json` — ver acima.

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
  `extractor/*.aec`.
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
