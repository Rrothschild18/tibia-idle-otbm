# Pipeline de mapas

Guia rápido + FAQ para gerar mapas Phaser a partir de arquivos `.otbm`.
Para detalhes internos do formato de saída (`map.json`, flags, layers), veja
[`CONVERTER_DOCS.md`](CONVERTER_DOCS.md) e [`PHASER_INTEGRATION.md`](PHASER_INTEGRATION.md).

## TL;DR

```
node extractor/scripts/build_map.js <nome-do-mapa>   # gera só esse mapa
node extractor/scripts/build_map.js --all            # gera todos os mapas encontrados
npm run build-map -- --all                           # atalho para o comando acima
npm run build-items                                  # bake global de sprites de item (ver abaixo)
python extractor/scripts/build_hunt_fragment.py <nome-do-mapa> --map-id ROOK-00NN
                                                      # gera db-fragment.json (hunts/monsters/loot) —
                                                      # nunca escreve em db.json, ver seção 6 abaixo
python extractor/scripts/sync_items_to_tibia_idle.py # publica atlases de item no repo tibia-idle
```

## Como adicionar um mapa novo

1. Crie uma pasta em `extractor/maps/<nome>/` — `<nome>` é o identificador que
   você vai usar em todos os comandos daqui pra frente.
2. Coloque dentro dela os arquivos exportados pelo editor de mapas, sem
   renomear nada:
   ```
   extractor/maps/<nome>/
     <nome>.otbm
     <nome>-house.xml
     <nome>-monster.xml
     <nome>-npc.xml
     <nome>-zones.xml
   ```
   O `.otbm` **precisa** ter o mesmo nome da pasta, e os XMLs seguem o padrão
   `<nome>-house.xml` etc. — é exatamente o nome que o editor de mapas já usa
   ao exportar, então normalmente basta arrastar os arquivos exportados pra
   dentro da pasta.
3. Rode:
   ```
   node extractor/scripts/build_map.js <nome>
   ```
4. O resultado sai em `extractor/ready-maps/<nome>/`:
   ```
   map.json            ← tilemap Phaser
   metadata.json        ← metadados por appearanceId
   sprites/             ← PNGs copiados, organizados por appearanceId
   monsters/respawn.json (se houver spawns em monster.xml)
   ```

### Exemplo: `orc-fortress.otbm`

```
extractor/maps/orc-fortress/
  orc-fortress.otbm
  orc-fortress-house.xml
  orc-fortress-monster.xml
  orc-fortress-npc.xml
  orc-fortress-zones.xml
```

```
node extractor/scripts/build_map.js orc-fortress
```

Saída: `extractor/ready-maps/orc-fortress/`.

5. Se o mapa novo introduz itens (loot, equipamento em NPC, etc.) que ainda não foram baked, rode
   também:
   ```
   npm run build-items
   ```
   Isso gera/atualiza, de forma **global** (não por mapa — o mesmo conjunto de assets serve todos
   os mapas): `extractor/atlases/items/` (atlas por item animado), `extractor/atlases/items-static/`
   (sheets estáticas compartilhadas) e `extractor/atlases/items-index.json` (índice `itemId →
   localização do sprite`, consumido pelo repositório `tibia-idle`). Não é chamado automaticamente
   por `build_map.js` — mesmo padrão já usado pelo atlas de outfit (`bake_outfit_atlas.py`, também
   um passo manual separado) — porque é global e caro (~2min no dado real), então rodar em toda
   invocação de `build_map.js` penalizaria até rebuilds repetidos do mesmo mapa durante iteração.
   Rode sempre que adicionar/mudar itens, não a cada build de mapa. Ver
   `.scratch/item-sprite-sheets/spec.md` para o contrato completo.
6. Gere o fragmento de dados de jogo do mapa (hunts/monsters/loot) para colar manualmente
   no `db.json` do repositório `tibia-idle`:
   ```
   python extractor/scripts/build_hunt_fragment.py <nome> --map-id ROOK-00NN
   ```
   Saída: `extractor/ready-maps/<nome>/db-fragment.json`. Por padrão **este script nunca
   escreve em `db.json`** — `monsters` e `loot` no fragmento já saem prontos (derivados
   mecanicamente do `respawn.json`), `hunts` sai como rascunho com um campo `_todo` listando
   o que precisa de revisão humana (nome/label, arte de portrait, `startPosition`). Revise e
   copie à mão. `--map-id` é opcional; sem ele o fragmento usa um id placeholder e sinaliza em
   `_todo` que você precisa rodar de novo com o id real antes de copiar.

   Se preferir pular a cópia manual, use `--write-db` (opcional, aditivo — precisa ser pedido
   explicitamente, `--all` sozinho continua sem tocar em `db.json`):
   ```
   python extractor/scripts/build_hunt_fragment.py --all --write-db
   ```
   `monsters`/`loot` são sempre mesclados por `mapId` (upsert — igual ao antigo
   `sync-loot-from-extractor.py`, sempre correto porque é 100% mecânico). `hunts` só é
   **adicionado** se o `mapId` ainda não existir em `db.json` — um hunt já curado nunca é
   sobrescrito, e o rascunho novo entra com o campo `_todo` junto, direto no `db.json`, como
   lembrete. Sem `--map-id` (obrigatório omitir com `--all`), o id de cada mapa novo é
   atribuído automaticamente (prefixo `ROOK` para mapas `*-rookguard`, senão o primeiro
   segmento do nome em maiúsculas — vale conferir se fez sentido) continuando a sequência já
   usada em `db.json`. Por padrão aponta pro checkout irmão `../tibia-idle/tibia-idle`,
   ajustável via `--tibia-idle-dir`.
7. Se o mapa novo introduziu sprites de item novos (passo 5 gerou atlases novos), publique-os
   no repositório `tibia-idle`:
   ```
   python extractor/scripts/sync_items_to_tibia_idle.py
   ```
   Copia (comparando conteúdo, não sobrescreve à toa) `extractor/atlases/items/`,
   `extractor/atlases/items-static/` e `extractor/atlases/items-index.json` para
   `apps/tibia-idle-front/public/assets/` no repositório `tibia-idle`, assumido como
   `../tibia-idle/tibia-idle` (ajustável via `--tibia-idle-dir`).

## Estrutura de pastas

```
extractor/
  scripts/            ← pipeline ativo (o único lugar que você deveria editar/rodar)
    dump_otbm.js       etapa 1: .otbm → .raw.json (via vendor/otbm2json.js)
    build_phaser_map.py etapa 2: .raw.json → map.json + sprites/ + respawn.json
    build_map.js       runner: 1 mapa ou --all, chama as duas etapas
    extract_sprites.py  etapa 0 (avulsa): .aec → extractor/sprites/ (biblioteca compartilhada)
    item_classifier.py  overrides manuais de classificação de layer
    bake_outfit_atlas.py  bake global (avulso): sprites/outfits/ → atlases/outfits/<id>.{png,json}
    bake_item_atlas.py     bake global (avulso): item animado → atlases/items/<id>.{png,json}
    bake_item_sheets.py    bake global (avulso): itens estáticos → atlases/items-static/*.{png,json}
    build_item_index.py    bake global (avulso): junta os dois bakes acima → atlases/items-index.json
    build_items.js         runner: chama os três bakes de item acima em sequência (npm run build-items)
    hunt_fragment.py        lógica pura: respawn.json → fragmento {monsters, loot, hunts}
    build_hunt_fragment.py  CLI (avulso): gera ready-maps/<nome>/db-fragment.json — nunca escreve em db.json
    sync_items_to_tibia_idle.py  CLI (avulso): publica atlases de item no repositório tibia-idle
  vendor/
    otbm2json.js       lib de leitura/escrita de OTBM (vendorizada, não é do npm)
  maps/<nome>/          SOURCE — .otbm + xmls de cada mapa (versionado)
  raw-maps/<nome>.raw.json   saída da etapa 1 (gitignored, regenerável)
  ready-maps/<nome>/         saída da etapa 2 (gitignored, regenerável)
  sprites/              biblioteca de sprites extraída dos .aec (gitignored, binário grande)
  atlases/              saída dos bakes globais (outfits/items/items-static + items-index.json), gitignored, regenerável
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
Ele varre `extractor/maps/*/` procurando uma subpasta que contenha um arquivo
`<nome-da-pasta>.otbm`. Pastas sem esse arquivo (como `training-spots/`, que
está vazia) são ignoradas.

**Erro `OTBM não encontrado: .../maps/<nome>/<nome>.otbm`**
O nome da pasta e o nome do arquivo `.otbm` dentro dela precisam ser
idênticos. Confira também maiúsculas/minúsculas e hífens.

**`build_phaser_map.py falhou (exit 1)` ao rodar `--all` para vários mapas**
O runner continua para o próximo mapa mesmo se um falhar, e no fim lista quais
falharam. Rode aquele mapa sozinho (`node build_map.js <nome>`) pra ver o erro
completo.

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
revisão. O script gera `ready-maps/<nome>/db-fragment.json` e para por aí;
colar no `db.json` é sempre uma ação manual.

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
python extractor/scripts/item_classifier.py --dump-unknown extractor/ready-maps/<nome>/map.json
```

### Git — o que versionar

- **Versionado:** `extractor/maps/` (fonte dos mapas), `extractor/scripts/`,
  `extractor/vendor/`, `extractor/otservbr-monster.xml`, os `.md` de
  documentação.
- **Gitignored (regenerável, não commitar):** `extractor/raw-maps/`,
  `extractor/ready-maps/`, `extractor/sprites/`, `extractor/*.aec`.
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
