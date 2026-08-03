# 05 — `build_travel_fragment.py`: parâmetro único de cidade, ids de NPC unificados, campos `city`/`status` derivados

**What to build:** Três ajustes em `travel_graph.py`/`build_travel_fragment.py`:

1. CLI colapsa `region` (posicional) + `--city-prefix` (hoje dois parâmetros pro mesmo conceito) num
   único parâmetro: `build_travel_fragment.py ROOK` — lê de `extractor/full-maps/ROOK/` (ticket 01),
   sem mais region com nome próprio desconectado do código da cidade.
2. `build_npc_locations` gera ids no formato `CIDADE-NPC-slug` (ex: `ROOK-NPC-obi`) em vez do atual
   `rook-npc-obi` (minúsculo, sem separar cidade/tipo) — mesmo padrão `CIDADE-TIPO-slug` que
   HUNT/TEMPLE/DEPOT/QUEST já seguem.
3. Toda `Location` (e o `hunts` correspondente, quando aplicável) ganha `city` (primeiro segmento do
   id, ex: `"ROOK"`) e `status: "test"` (só quando `city === "TEST"`, ausente caso contrário) —
   ambos calculados pelo fragmento, nunca setados à mão.

**Blocked by:** 01 (convenção `full-maps/<CIDADE>` documentada), 03 (validação de sign já robusta
antes de mexer no que consome o resultado dela).

- [ ] `build_travel_fragment.py ROOK` funciona sem `--city-prefix`/sem nome de region separado — lê
      `extractor/full-maps/ROOK/ROOK.otbm`/`ROOK-npc.xml`/etc.
- [ ] Locations de NPC saem como `ROOK-NPC-<slug-do-nome>`, maiúsculo, mesmo padrão dos outros tipos
- [ ] Toda entrada de `locations` tem `city` preenchido corretamente a partir do próprio id
- [ ] `status: "test"` presente e igual a `"test"` só quando `city === "TEST"`; campo ausente
      (não `null`/`false`) nos demais casos
- [ ] Coberto por teste: NPC id gerado corretamente a partir de um nome com espaço/maiúscula
      (slugificação), `city`/`status` corretos pra uma location `ROOK-*` e uma `TEST-*`
