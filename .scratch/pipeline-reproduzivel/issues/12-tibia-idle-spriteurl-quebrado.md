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

- [x] O modal de spawn mostra o sprite do monstro, vindo do atlas de outfit
- [x] `assetsPath` removido dos tipos onde só existia pra alimentar essa linha
- [x] Nenhuma URL `/undefined/` é construída em runtime
- [ ] **Fora deste ticket**, vira issue separada no `tibia-idle`: o `public/assets/map.json` v5 órfão
      e as chaves mortas (`assetsRoot` sem `-v6` em 17 entradas, 3 `portrait` apontando pra pastas
      inexistentes) do `catalog-source.json` — inertes (o zod do `import-source.model.ts:18-41` as
      descarta) e o catálogo se autocorrige no primeiro re-export depois do ticket 07

## Comments

Feito no `tibia-idle`, branch `fix/monster-spawn-sprite-url` (commit `69fdb0a9`), já no remoto.

Branch própria e **worktree separado**: o checkout principal estava na
`chore/bun-e-nx-23` com 3 commits não publicados de migração Bun/Nx e um `nx.json` modificado. Nada
disso foi tocado — a branch saiu de `origin/main` num diretório à parte.

### O conserto

O `respawn.json` v6 real confirma o diagnóstico do ticket:

```json
{ "name": "Spider", "outfitId": 30,
  "atlas": { "image": "assets/outfits/30.png", "json": "assets/outfits/30.json" },
  "idle": { "south": "30_0", ... } }
```

Não há `assetsPath`, e `idle.south` é uma **chave de frame dentro do atlas**, não um arquivo. Então
não existe URL de PNG por frame pra montar — o conserto não é ajustar a string.

O retrato passou a ser recortado do atlas que o `Preloader` já carrega
(`preload.ts:165-169`, chave = `String(outfitId)`), via canvas, para data URL. Duas alternativas
descartadas:

- **apontar o `<img>` para `atlas.image`** — mostraria a folha inteira
- **`background-position` no modal** — exigiria mudar o template, que usa `<img [src]>`, e buscar o
  JSON do atlas só pro retângulo do frame; o Phaser já tem isso em memória

Devolve `null` quando o atlas não carregou ou o frame não existe. `spriteUrl` já era
`string | null` (`game-logic-adapter.ts:76`) e o modal já tinha o `@if`, então o caminho nulo é o
que sempre existiu — só nunca era alcançado, porque a string quebrada nunca era vazia.

### Verificação

| | |
|---|---|
| `tsc` em `phaser-game`, `hunts/data-access`, `autohunt/data-access` | limpo |
| `hunt-simulation.service.spec` (a fixture alterada) | 28/28 |
| suíte de `autohunt/data-access` | 40 falhas — **idênticas ao baseline** |

As 40 falhas foram medidas com e sem as mudanças, dando o mesmo número: são ambientais (o worktree
usa `node_modules` emprestado do checkout principal, que está no meio da migração pro Nx 23). Não
introduzi regressão, e também não posso afirmar que aquela suíte está verde — ela não estava antes.

### O que continua faltando pra ver o retrato na tela

`assets/outfits/` **não existe** em `apps/tibia-idle-front/public/assets/` — conferido. O
`respawn.json` aponta os monstros pra um atlas que nada publica. Com este commit o código busca o
lugar certo; publicar é o ticket 09.

A alínea "fora deste ticket" (o `public/assets/map.json` v5 órfão e as chaves mortas do
`catalog-source.json`) segue fora, como o ticket pedia.
