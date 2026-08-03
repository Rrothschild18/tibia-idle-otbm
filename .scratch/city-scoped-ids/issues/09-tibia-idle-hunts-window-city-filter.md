# 09 — `tibia-idle`: `HuntsWindow` esconde hunts com `city === "TEST"`

**What to build:** Repo `tibia-idle`. `Hunt`/`Location` ganham o campo `city` (derivado, ticket 05).
`HuntsWindow` (e qualquer outro lugar que lista hunts, se houver) filtra a lista exibida por
`hunt.city !== 'TEST'` antes de renderizar — mapas de teste (Larva, Dragon, Grim, Sea) somem da UI
sem precisar de um campo boolean `hidden` separado.

**Blocked by:** 06 (`tibia-idle-otbm`) — precisa do `db.json` já com `city` preenchido em cada hunt.

- [ ] `Hunt` (tipo TS) ganha `city: string` e opcionalmente `status?: 'test'`
- [ ] `HuntsWindow` não lista hunts com `city === 'TEST'` — a lista visível não muda de tamanho pros
      16 hunts reais de Rookgaard, mas os 4 mapas de teste somem
- [ ] Nenhum outro comportamento de `HuntsWindow` muda (seleção, preview de monstro/loot, travel
      time, "Start Hunt") — filtro é aditivo, não reestrutura o resto do componente
- [ ] Coberto por teste (se `HuntsWindow` ganhar cobertura própria futuramente) ou verificado
      manualmente no browser: hunt de `city: "TEST"` não aparece na lista
