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

- [ ] `extractor/vendor/canary/items.xml` versionado
- [ ] Extratos dos `.lua` (ofertas de shop de NPC, o que `monster_loot.py` consome) versionados como
      JSON
- [ ] `vendor/canary/MANIFEST.json` grava o commit sha do Canary, a data e o comando que gerou
- [ ] `update-canary-data` regenera tudo isso a partir de `--canary-dir`/`CANARY_DIR`
- [ ] `build_travel_fragment.py` e `build_monster_loot_index.py` leem do vendor por padrão; o
      checkout do Canary vira opcional, necessário só pra atualizar
- [ ] Fragmento do ROOK gerado a partir do vendor é **idêntico ao golden do 01**
