Status: ready-for-agent

# 10 — `pipeline`: um comando, incremental por hash, com check por estágio

**What to build:** Hoje são ~8 invocações manuais numa ordem que não está escrita como sequência
(`extract_sprites` → `dump_otbm` → `build_map --all` → bakes → `build_item_index` → fragmentos →
publish); `build_map.js --all` cobre só o estágio 2. O objetivo é o clone numa máquina nova:
`uv sync` → `fetch-assets` → `pipeline --all`.

Incremental: cada estágio pula quando nada mudou, `--force` refaz de verdade. **Staleness é hash de
conteúdo** gravado num `.stamp` por estágio — mtime mente exatamente quando dói (`git checkout`
reescreve mtime, cópia preserva) e o modo de falha é servir saída velha em silêncio, o pior que um
pipeline tem. Exceção única: a pasta `assets/` do cliente, onde hashear centenas de MB por invocação não se paga
e o manifesto do 13 já decide.

Cada estágio começa verificando o que precisa (`assets/` do cliente, `sprites/`, deps, checkouts/vendor) e diz o
que falta antes de gastar tempo; os scripts individuais continuam falhando bem por conta própria,
pra quem entra pelo meio.

**Blocked by:** 02, 03, 09, 13.

- [x] `pipeline --all` roda a sequência inteira do zero numa máquina limpa
- [x] Cada estágio declara explicitamente suas entradas; `.stamp` guarda o hash delas
- [x] `--force` refaz mesmo com stamp válido
- [x] Incremental nunca serve saída velha: coberto por teste que muda uma entrada sem tocar mtime e
      confirma que o estágio reexecuta
- [x] Check por estágio lista o que falta, com o comando pra obter cada coisa
- [x] README traz a sequência completa e o que cada estágio consome/produz

## Comments

`extractor/scripts/pipeline.py`, nove estágios. A máquina nova virou três comandos:

```
uv sync
uv run python extractor/scripts/fetch_assets.py
uv run python extractor/scripts/pipeline.py --all
```

Rodado inteiro nesta máquina, exit 0: 204 mil PNGs extraídos, 12 folhas de item, 1049 atlases de
outfit, **21 mapas construídos**, atlases de efeito/corpo/poça, tabela de flags e o fragmento do
travel-graph.

Segunda rodada: **8 dos 9 estágios pulados**. O nono reexecutou porque eu tinha mexido na entrada
dele — que é o comportamento correto.

### Staleness por hash, com duas exceções declaradas

`.stamps/<estágio>.stamp` guarda o hash das entradas declaradas. O teste que importa muda o
conteúdo de um arquivo e **restaura o mtime** com `os.utime`, confirmando que o estágio reexecuta;
o inverso também é testado (mtime diferente, bytes iguais, não reexecuta), porque `git checkout`
faz exatamente isso e um rebuild espúrio a cada checkout tornaria o incremental inútil.

1. A pasta `assets/` do cliente não entra no hash — centenas de MB por invocação não pagam, e o
   `assets-manifest.json` já decide essa versão por checksum. É o manifesto que entra.
2. Para `sprites/` (204 mil PNGs) e `atlases/`, o hash é do **inventário** (caminho + tamanho), não
   dos bytes. Ler tudo custaria mais que refazer o estágio. Um PNG editado à mão sem mudar de
   tamanho escaparia; para isso existe `--force`.

Um estágio que falha **não grava stamp** — coberto por teste, porque um estágio quebrado que fosse
pulado na rodada seguinte seria pior que não ter incremental nenhum.

### O `--check` e o bug que ele não teria pego

```
9/9 estágios prontos para rodar
```

Cada estágio declara o que precisa e **o comando que resolve**; dois testes fixam que toda
dependência nomeia um comando e que todo estágio declara entradas.

---

## O golden pegou um bug real, e ele era grave

Rodar o pipeline inteiro regenerou a tabela de flags **a partir dos sprites** pela primeira vez —
até aqui ela tinha sido semeada dos `objectDefs` do `map.json` v5. O fragmento do travel-graph
**deixou de bater com o golden do ticket 01**: a location `ROOK-HUNT-0001` e a aresta que chegava
nela sumiram.

Causa: `build_appearance_flags.py` dumpava as flags **cruas** do `appearances.dat`. Comparando as
duas tabelas:

```
isFloorTransition     4  ->  0
isRoof                8  ->  0
hookDirection        71  ->  0   (virou `hook`, o nome cru)
unpass              957  ->  957
```

`unpass` batia porque é crua. `isFloorTransition` e `isRoof` **não existem no protobuf** — são
heurísticas derivadas em `analyze_item`. Sem elas o BFS perdeu as escadas, a entrada da hunt ficou
inalcançável e a location foi rejeitada. **Sem erro nenhum**: o pipeline terminou com exit 0.

Conserto: `extractor/scripts/appearance_derivation.py`, uma definição só, usada pelos dois lados —
`analyze_item` (que monta o mapa) e `build_appearance_flags` (que monta a tabela). Duas cópias
concordariam hoje e divergiriam depois, em silêncio, que é exatamente o que aconteceu.

Depois do conserto: `isFloorTransition` de volta em 4, `isRoof` em 8, e o fragmento **byte a byte
idêntico ao golden**. O `map.json` do hunt também continua idêntico ao golden v6 — a refatoração do
`analyze_item` não mudou saída.

10 testes novos em `test_appearance_derivation.py`, incluindo um que afirma que a tabela versionada
do ROOK carrega suas quatro transições de andar. Zero ali significa grafo sem escadas.

**460 testes passando.**
