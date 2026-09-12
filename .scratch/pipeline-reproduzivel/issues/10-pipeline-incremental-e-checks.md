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

- [ ] `pipeline --all` roda a sequência inteira do zero numa máquina limpa
- [ ] Cada estágio declara explicitamente suas entradas; `.stamp` guarda o hash delas
- [ ] `--force` refaz mesmo com stamp válido
- [ ] Incremental nunca serve saída velha: coberto por teste que muda uma entrada sem tocar mtime e
      confirma que o estágio reexecuta
- [ ] Check por estágio lista o que falta, com o comando pra obter cada coisa
- [ ] README traz a sequência completa e o que cada estágio consome/produz
