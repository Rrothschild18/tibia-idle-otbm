# Pipeline de mapas

Guia rápido + FAQ para gerar mapas Phaser a partir de arquivos `.otbm`.
Para detalhes internos do formato de saída (`map.json`, flags, layers), veja
[`CONVERTER_DOCS.md`](CONVERTER_DOCS.md) e [`PHASER_INTEGRATION.md`](PHASER_INTEGRATION.md).

## TL;DR

```
node extractor/scripts/build_map.js <nome-do-mapa>   # gera só esse mapa
node extractor/scripts/build_map.js --all            # gera todos os mapas encontrados
npm run build-map -- --all                           # atalho para o comando acima
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

## Estrutura de pastas

```
extractor/
  scripts/            ← pipeline ativo (o único lugar que você deveria editar/rodar)
    dump_otbm.js       etapa 1: .otbm → .raw.json (via vendor/otbm2json.js)
    build_phaser_map.py etapa 2: .raw.json → map.json + sprites/ + respawn.json
    build_map.js       runner: 1 mapa ou --all, chama as duas etapas
    extract_sprites.py  etapa 0 (avulsa): .aec → extractor/sprites/ (biblioteca compartilhada)
    item_classifier.py  overrides manuais de classificação de layer
  vendor/
    otbm2json.js       lib de leitura/escrita de OTBM (vendorizada, não é do npm)
  maps/<nome>/          SOURCE — .otbm + xmls de cada mapa (versionado)
  raw-maps/<nome>.raw.json   saída da etapa 1 (gitignored, regenerável)
  ready-maps/<nome>/         saída da etapa 2 (gitignored, regenerável)
  sprites/              biblioteca de sprites extraída dos .aec (gitignored, binário grande)
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
