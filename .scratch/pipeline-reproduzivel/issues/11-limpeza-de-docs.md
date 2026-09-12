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

- [ ] Os 8 diretórios deletados; nenhum porquê perdido sem ADR correspondente
- [ ] `travel-graph-and-locations` reescrito sem `db.json`/`json-server`/`--write-db`
- [ ] `grep -ri "db.json\|json-server\|write-db" .scratch docs extractor/*.md` só retorna menções
      históricas explicitamente marcadas como tal
- [ ] `extractor/README.md:4` não diz mais que o v5 é "o que o jogo ainda consome"
- [ ] `CONTEXT.md` ganha os termos novos (tabela de flags, override, publish) com seus `_Avoid_`
