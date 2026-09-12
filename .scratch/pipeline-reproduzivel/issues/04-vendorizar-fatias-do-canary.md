Status: ready-for-agent

# 04 — Vendorizar as fatias do Canary, com o commit de origem gravado

**What to build:** Hoje o pipeline exige um clone inteiro do Canary pra ler `data/items/items.xml`
(3,6 MB), 1035 `.lua` de NPC e 1656 `.lua` de monstro. Vendorizar o que é de fato lido, no padrão
que o próprio repo já pratica com `monster-loot.json` (3,4 MB, derivado do Canary e congelado aqui
justamente pra ninguém precisar clonar o Canary).

Misto, de propósito: **`items.xml` cru** (é um arquivo só, e é fonte de duas coisas — floorchange/
stairs pro grafo e nome↔id pro loot; cru continua auditável) + **extratos dos `.lua`** (ninguém vai
ler 2691 arquivos num diff). Junto vai um `update-canary-data` que regenera os extratos a partir de
um checkout, e um manifesto registrando **de qual commit do Canary** aquilo saiu.

**Blocked by:** 01 (o golden tem que estar congelado antes de mexer nas entradas do grafo), 03 (o
`update-canary-data` usa o `paths.py`).

- [x] `extractor/vendor/canary/items.xml` versionado
- [x] Extratos dos `.lua` (ofertas de shop de NPC, o que `monster_loot.py` consome) versionados como
      JSON
- [x] `vendor/canary/MANIFEST.json` grava o commit sha do Canary, a data e o comando que gerou
- [x] `update-canary-data` regenera tudo isso a partir de `--canary-dir`/`CANARY_DIR`
- [x] `build_travel_fragment.py` lê do vendor por padrão; o checkout do Canary vira opcional,
      necessário só pra atualizar. **`build_monster_loot_index.py` não** — ver comentário abaixo
- [x] Fragmento do ROOK gerado a partir do vendor é **idêntico ao golden do 01**

## Comments

`extractor/vendor/canary/` com três arquivos (4,5 MB no total, contra ~20 MB de checkout):

| Arquivo | Tamanho | Conteúdo |
|---|---|---|
| `items.xml` | 3,5 MB | cópia crua |
| `npc-lua-facts.json` | 1015 KB | 1035 NPCs (303 com shop, 1001 com outfit) |
| `MANIFEST.json` | 504 B | canary `06c73ccb99…` (v3.6.0-93), data, comando |

`extractor/scripts/update_canary_data.py` regenera os três a partir de `--canary-dir`/`CANARY_DIR`.

**O critério que importa passou:** o fragmento do ROOK gerado a partir do vendor é byte a byte
idêntico ao golden do 01, e a saída com `--canary-dir` apontando pro checkout real concorda com
ele. `build_travel_fragment.py ROOK` agora roda **sem Canary nenhum**.

### O que quase passou despercebido

A primeira versão do vendor gerou um `db-fragment.json` com o mesmo conteúdo e **ordem de chaves
diferente** — `lookAddons` antes de `lookType`, `buy` antes de `itemName`. Causa: `sort_keys=True`
no dump do extrato, que ordena também os dicionários internos (linhas de shop, campos do outfit).
As chaves de topo já saíam ordenadas do `sorted(glob)`, então o `sort_keys` não estava ganhando
nada e estava custando a identidade byte a byte. Removido.

Sem o golden do 01 isso teria passado como "funciona igual" — o conteúdo *era* igual.

### Uma alínea ficou deliberadamente diferente do que o ticket pedia

O ticket pedia que **`build_monster_loot_index.py` também lesse do vendor**. Ele continua lendo do
checkout, e a razão é que fazer o contrário criaria um bug silencioso:

- Os 1656 `.lua` de monstro **não** são vendorizados — o extrato deles já existe e já é versionado,
  é o próprio `extractor/monster-loot.json` que esse script gera. Vendorizar de novo seria guardar
  a mesma informação duas vezes.
- Logo o script precisa do checkout de qualquer forma. Se ele lesse `items.xml` do vendor e os
  `.lua` do checkout, resolveria **id de item por uma versão do Canary e tabela de loot por
  outra**. O sintoma seria um id errado no índice, sem erro nenhum.

Ele é o "necessário só pra atualizar" do próprio ticket, junto com `update_canary_data.py`. A
intenção do spec — um clone limpo consegue rodar o pipeline — está satisfeita: `monster-loot.json`
já está versionado.

Documentado na docstring do script e na seção "Vendor do Canary" do README.

### Testes

`extractor/tests/test_vendor_canary.py`, 7 testes. O que eles protegem de verdade é a distinção
que o vendor poderia ter apagado: um NPC cujo `.lua` **não existe** (o CLI avisa) versus um cujo
`.lua` existe **sem tabela de shop** (silencioso). Por isso o extrato guarda os 1035 arquivos,
inclusive os 31 sem nenhuma das duas tabelas — omitir os vazios colapsaria os dois casos e geraria
warning falso.

395 testes passando. As duas falhas restantes seguem pré-existentes (dependem de
`extractor/sprites/`).
