Status: ready-for-agent

# 12 — `tibia-idle`: consertar o `spriteUrl` quebrado do modal de spawn

**What to build:** Em `libs/phaser-game/src/lib/scenes/main.ts:1147`, `spriteUrl` é montado como
`` `/${def.assetsPath}/${idleFrameKey(def.idle['south'])}.png` `` — a convenção v5
(`assets/<map>-sprites/monsters/<id>`). Nenhum bundle v6 emite `assetsPath`: os `monsterDefs` do
`respawn.json` são baseados em atlas (`name/outfitId/atlas/loot/idle/moving`, ex.
`assets/outfits/21.png`). Resultado: a linha produz **`/undefined/21_0.png`** em runtime, e ela é o
único produtor de `spriteUrl` não-nulo, consumido por
`libs/front-end/shell/src/lib/monster-spawn-modal/monster-spawn-modal.html:38-41`.

Não é código morto: é um monstro sem retrato na tela do jogador. As declarações de tipo órfãs ficam
no mesmo passo (`libs/front-end/hunts/data-access/src/lib/monsters/monster.ts:12`,
`libs/phaser-game/src/lib/scenes/preload.ts:15`).

**Blocked by:** nada (repo diferente, ciclo de commit próprio).

- [ ] O modal de spawn mostra o sprite do monstro, vindo do atlas de outfit
- [ ] `assetsPath` removido dos tipos onde só existia pra alimentar essa linha
- [ ] Nenhuma URL `/undefined/` é construída em runtime
- [ ] **Fora deste ticket**, vira issue separada no `tibia-idle`: o `public/assets/map.json` v5 órfão
      e as chaves mortas (`assetsRoot` sem `-v6` em 17 entradas, 3 `portrait` apontando pra pastas
      inexistentes) do `catalog-source.json` — inertes (o zod do `import-source.model.ts:18-41` as
      descarta) e o catálogo se autocorrige no primeiro re-export depois do ticket 07
