Status: ready-for-agent

# 11 — Limpeza de docs: apagar o que mente, migrar o porquê

**What to build:** O `.scratch/` acumulou spec concluído que hoje descreve o passado como se fosse o
presente. Critério: **concluído é deletado**, com uma catraca — se o spec carrega o único registro
de um *porquê* que não está em ADR nenhuma, esse porquê vira ADR **antes** da deleção.

Deletar: `city-scoped-ids`, `item-sprite-sheets`, `map-sprite-sheets-v4`, `monstro-respawn-e-corpse`,
`multi-floor-support`, `outfit-de-personagem`, `outfit-sprite-atlas`, `static-scenery-baking`.

Reescrever: `travel-graph-and-locations` — é a maior concentração do modelo morto (`spec.md:90`
afirma que "the real backend is `json-server` over the sibling repo's `db.json`", `:123` repete como
"the actual mechanism"). Sobrevive a descrição do seam (`spec.md:89`), em termos de
`--export`/`content_export.py`.

Manter: `item-sprites-para-o-market` (único trabalho de fato aberto no repo) e `modelo-render-rme`
(os dois arquivos de `reports/` são citados por `docs/adr/0006-map-json-v6-pilha-por-tile.md:89` —
deletar quebraria link de ADR viva).

Dois casos que mentem ativamente e por isso são prioridade: `map-sprite-sheets-v4/spec.md:1,106`
apresenta o v4 como formato-alvo e `tilesets` como v3; `monstro-respawn-e-corpse/spec.md:1` diz "não
implementada" sobre o que o commit `09964cf` entregou.

**Blocked by:** 06, 07 (o README e o `CONTEXT.md` só podem descrever o estado final depois que ele
existir).

- [x] Os 8 diretórios deletados; nenhum porquê perdido sem ADR correspondente
- [x] `travel-graph-and-locations` reescrito sem `db.json`/`json-server`/`--write-db`
- [x] `grep -ri "db.json\|json-server\|write-db" .scratch docs extractor/*.md` só retorna menções
      históricas explicitamente marcadas como tal
- [x] `extractor/README.md:4` não diz mais que o v5 é "o que o jogo ainda consome"
- [x] `CONTEXT.md` ganha os termos novos (tabela de flags, override, publish) com seus `_Avoid_`

## Comments

8 diretórios deletados (~2200 linhas). Sobraram quatro em `.scratch/`:
`item-sprites-para-o-market` e `modelo-render-rme` (os dois que o ticket mandava manter),
`travel-graph-and-locations` (reescrito) e `pipeline-reproduzivel` (este trabalho).

### A catraca segurou dois porquês

Antes de apagar, varri os 8 specs atrás de razão que não estivesse em ADR nenhuma. A maioria já
estava coberta:

| Porquê | Onde já estava |
|---|---|
| espaço de coordenadas compartilhado entre andares | ADR 0002 |
| grade fixa em vez de bin-packing | ADR 0003 |
| bake removido em favor de folhas | ADR 0004 |
| cidade é a pasta-pai física, nunca adivinhada | `CONTEXT.md`, termo **City** |

Dois **não** estavam, e viraram ADR:

- **`docs/adr/0007-atlas-por-outfit.md`** — por que a unidade de bake é o outfit e não o mapa nem
  um atlas global. O mesmo rato aparece em várias hunts: um bake por mapa faria o cliente baixar os
  mesmos 36 frames uma vez por mapa; um atlas global com 1049 outfits passa de qualquer limite de
  GPU. Junto vai o que o formato preserva: chave de frame inalterada, ordem determinística,
  espaçamento contra sangramento de textura.
- **`docs/adr/0008-corpse-e-respawn-saem-do-canary.md`** — por que a cadeia de corpo é lida do
  Canary em vez de inventada (varia demais por monstro: 1 estágio num rato, 5+ num humano), por que
  virou chave do `monster-loot.json` em vez de arquivo novo, e por que o escopo de efeito parou no
  id 11.

### `travel-graph-and-locations` reescrito

Era a maior concentração do modelo morto. O `spec.md:90` afirmava que "the real backend is
`json-server` over the sibling repo's `db.json`" e o `:123` repetia como "the actual mechanism".
Reescrito em termos de fragmento-e-`--export`, com um cabeçalho `Status: histórico` dizendo o que
mudou e por quê. O ticket `04-merge-fragment-into-db.md` foi deletado inteiro — era `--write-db` da
primeira linha à última.

O que **sobreviveu** é o que o ticket mandava preservar: a descrição do seam (módulo puro + CLI
fina), que continua sendo o desenho real do código.

### O grep

```
grep -ri "db.json\|json-server\|write-db" .scratch docs extractor/*.md CONTEXT.md
```

Devolve três arquivos, todos com menção **explicitamente marcada como histórica**: os dois
`_Avoid_` do `CONTEXT.md`, o "Existia:" e o FAQ "Cadê o `db.json`?" do README, e o cabeçalho novo do
spec reescrito.

### Extra: os dois docs do v5

`extractor/README.md:4` dizia que o v5 era "o que o jogo ainda consome" — falso desde antes desta
sessão, e agora o formato nem existe. Reescrito.

`CONVERTER_DOCS.md` e `PHASER_INTEGRATION.md` descrevem o v5 inteiro. **Não deletei**: as ADRs 0002
e 0004 apontam para eles, e quebrar link de ADR viva é o erro que o próprio ticket manda evitar no
caso do `modelo-render-rme`. Ganharam um cabeçalho de duas linhas dizendo que são históricos e
apontando para o `MAP_JSON_V6.md`.
