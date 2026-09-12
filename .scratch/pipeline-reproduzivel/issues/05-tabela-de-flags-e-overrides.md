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

- [x] `appearance-flags/<CIDADE>.json` gerado sem construir `map.json`, versionado no git
- [x] `appearance-flags/<CIDADE>.overrides.json` sempre vence; regenerar a tabela nunca apaga
      override
- [x] `travel_graph.py`/`build_travel_fragment.py` leem a tabela nova, não mais `map.json`
- [x] **Fragmento do ROOK idêntico ao golden do 01** — byte a byte, `db-fragment.json` e
      `travel-graph-rejections.txt`
- [x] Documentado se a geração precisa ou não de `sprites/` (e portanto do cliente)
- [x] Coberto por teste: override vence o valor derivado; tabela sem override é puro derivado

## Comments

`extractor/appearance-flags/ROOK.json` — 2093 entradas, 161 KB, no lugar de 20,3 MB de `map.json`
+ 1,8 MB de `metadata.json`. `appearance_flags.py` faz o merge, `build_appearance_flags.py` gera.

**O fragmento do ROOK continua byte a byte idêntico ao golden do 01** — com a tabela, sem
`map.json`, e sem checkout do Canary.

### A pergunta que o ticket mandava responder: sim, precisa de sprites — mas só pra *gerar*

O ticket pedia pra verificar se montar a tabela precisa da biblioteca de sprites. Precisa, e não
pelo motivo que o ticket suspeitava:

- **Não** é o PNG. `analyze_item` lê a imagem só pra `spriteWidth`/`spriteHeight`, que o grafo de
  fato não usa.
- **É o `.json` por appearance.** As flags vêm de `load_item_json(appearance_id)` →
  `resolve_item_json_path` → `extractor/sprites/{items,missiles}/<id>.json`
  (`build_phaser_map.py:202-207`, `:320`). Sem a biblioteca de sprites não há de onde derivar.

Por isso a tabela é **versionada**: gerar exige os metadados, usar não exige nada. É exatamente o
payoff que o spec previu — o travel-graph continua rodando num clone sem `.aec` nenhum, que é o
único produto fim-a-fim que essa máquina consegue montar hoje.

`build_appearance_flags.py` falha alto quando `extractor/sprites/` não existe, dizendo que a
tabela versionada continua válida e que regenerar é que depende do ticket 08.

### A tabela desta rodada veio dos `objectDefs`, não dos sprites

Esta máquina não tem `extractor/sprites/`, então a tabela foi extraída numa migração única dos
`objectDefs` do `map.json` v5 — que **são** exatamente a mesma derivação que
`build_appearance_flags.py` refaz. O golden prova que são: 2093 das 2158 entradas têm alguma flag
verdadeira, e o fragmento resultante é idêntico.

Quando os sprites chegarem (08/13), rodar o gerador tem que reproduzir este arquivo. Se não
reproduzir, é bug do gerador — e o golden pega.

### Guardadas todas as flags, não só as duas que o grafo lê

O grafo lê **duas**: `unpass` e `isFloorTransition` (`travel_graph.py:274-275`, `:284-285`). Só
elas dariam 961 entradas e 34 KB, contra 2093 e 161 KB de tudo.

Escolhi guardar todas as flags verdadeiras — mesma convenção do `objectDefs` que a tabela
substitui. 161 KB contra os 20,3 MB que saíram não é custo, e evita ter que adivinhar qual flag o
grafo vai precisar na próxima. A tabela segue 100% mecânica de qualquer jeito.

### Semântica do override, e por que substitui em vez de mesclar

8 testes em `extractor/tests/test_appearance_flags.py`. O que eles fixam:

- override **substitui a entrada inteira** daquele id, não mescla chave a chave — ele é a resposta
  final. Mesclar deixaria a derivação reintroduzir pela porta dos fundos justamente o valor que a
  curadoria existe pra corrigir
- override pode **adicionar** um id que a derivação nunca viu
- regenerar a tabela **não toca** no arquivo de overrides (a regra do `CONTEXT.md:44-50`)
- tabela ausente falha alto citando o gerador, em vez de produzir um grafo silenciosamente vazio

Ainda não existe `ROOK.overrides.json`: nenhum caso de erro de derivação conhecido. O arquivo é
criado quando o primeiro aparecer — e cada linha dele documenta o caso.

### Mudança de forma

`extract_tile_flags` passou a receber `{id: {flag: valor}}` em vez de `{id: {"flags": {...}}}` — o
envelope existia só porque a fonte era o `objectDefs`. Assinatura e docstring atualizadas em
`travel_graph.py`, mais o helper de teste.
