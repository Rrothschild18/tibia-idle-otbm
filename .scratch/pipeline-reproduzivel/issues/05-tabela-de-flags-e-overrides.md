Status: ready-for-agent

# 05 — Tabela de flags versionada + `flag-overrides.json`

**What to build:** O travel-graph nunca leu "um mapa": de `full-maps/<CIDADE>/map.json` ele usa
**só** `objectDefs[<id>].flags` (`build_travel_fragment.py:161` → `travel_graph.py:263`, `_flags()`),
nunca `floors`, `sheets`, `tilesets` ou `animations`. Os tiles vêm do dump cru
(`raw-maps/<CIDADE>.raw.json`).

Extrair essa tabela pra um artefato próprio, **versionado** — `extractor/appearance-flags/<CIDADE>.json`,
~2158 entradas — gerado sem construir documento de mapa nenhum. Ao lado dele,
`appearance-flags/<CIDADE>.overrides.json`: pequeno, versionado, **sempre vence no merge**, pros
casos em que a derivação automática erra. A tabela permanece 100% mecânica; a curadoria vive num
diff separado e cada linha dela documenta um caso de erro da derivação.

Verificar durante a implementação se montar a tabela precisa dos sprites — `analyze_item` lê PNG pra
`spriteWidth`/`spriteHeight`, que o grafo **não** usa. Se não precisar, a geração do grafo passa a
rodar sem a biblioteca de sprites, o que é o ponto inteiro de versionar isso.

**Blocked by:** 01 (golden), 04 (as flags de floorchange saem do `items.xml` vendorizado).

- [ ] `appearance-flags/<CIDADE>.json` gerado sem construir `map.json`, versionado no git
- [ ] `appearance-flags/<CIDADE>.overrides.json` sempre vence; regenerar a tabela nunca apaga
      override
- [ ] `travel_graph.py`/`build_travel_fragment.py` leem a tabela nova, não mais `map.json`
- [ ] **Fragmento do ROOK idêntico ao golden do 01** — byte a byte, `db-fragment.json` e
      `travel-graph-rejections.txt`
- [ ] Documentado se a geração precisa ou não de `sprites/` (e portanto do cliente)
- [ ] Coberto por teste: override vence o valor derivado; tabela sem override é puro derivado
