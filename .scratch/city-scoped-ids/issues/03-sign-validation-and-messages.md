# 03 — Validação estrita de placas + mensagens de erro/warning específicas por motivo

**What to build:** Duas correções em `travel_graph.py`/`build_travel_fragment.py`, motivadas por dois
bugs reais encontrados testando a feature de travel time:

1. `_SIGN_ID_RE` (hoje `\d+`, aceita qualquer quantidade de dígitos) passa a exigir exatamente 4
   dígitos no `SEQ` — é o que deixou `ROOK-HUNT-00015` (5 dígitos, erro de digitação) passar como
   "formato válido" mesmo não batendo com nenhuma hunt real.
2. O loop de warnings em `build_travel_fragment.py` (`build_region_fragment`) imprime a mesma
   mensagem genérica `"placa fora do formato CIDADE-TIPO-INCREMENTAL"` pra **qualquer** entrada em
   `sign_issues`, mesmo quando o motivo real é outro (ex: id duplicado — placa `ROOK-HUNT-0006`
   colocada duas vezes, mesmo uid, texto idêntico e perfeitamente bem formado). Cada `issue["reason"]`
   ganha sua própria mensagem, citando o motivo real.

**Blocked by:** None — pode começar em paralelo com os outros tickets, mexe só em
`travel_graph.py`/`build_travel_fragment.py`.

- [ ] `_SIGN_ID_RE` rejeita `SEQ` com quantidade de dígitos diferente de 4 (ex: `ROOK-HUNT-00015` e
      `ROOK-HUNT-1` viram `invalid-sign-format`, não um id "válido" órfão)
- [ ] Mensagem de warning pra `invalid-sign-format` e `duplicate-sign-id` são visivelmente
      diferentes, cada uma citando o motivo real (não mais um texto genérico compartilhado)
- [ ] Coberto por teste com fixture pequena reproduzindo os dois casos reais encontrados (sign com 5
      dígitos; duas signs com uid/texto idênticos) — cada um cai no branch de mensagem certo
- [ ] Regressão: os 12 ids de sign já válidos hoje (`ROOK-HUNT-0001`..`0012`, `ROOK-HUNT-0009` etc,
      todos com 4 dígitos) continuam validando normalmente
