Status: ready-for-agent

# 09 — `publish`: o único comando que escreve no `tibia-idle`

**What to build:** Hoje **nenhum script** leva um bundle pro repo irmão — a cópia é manual. A prova:
os bundles publicados têm `map.json` + `sheets/`, mas não o `monsters/respawn.json` que
`write_map_v6` também escreve (`build_phaser_map.py:1395-1398`) — cópia seletiva de humano, não sync.
`content_export.py` não faz I/O nenhum (só monta a string do `mapUrl`), e `--export` escreve quatro
JSONs e nenhum binário. O `README.md:337` nem lista o bundle na tabela de destinos.

E a cobertura de atlas está invertida: `sync_items_to_tibia_idle.py` cobre `items-static/`,
`items-animated/`, `items-index.json` e `player-outfits/`; **não cobre** `outfits/`, `effects/`,
`corpses/`, `pools/`. Mas no front existem `effects/`, `corpses/` e `pools/` (foram na mão) e
**não** existem `items-animated/`, `player-outfits/` e `outfits/` — enquanto `respawn.json` aponta
os monstros justamente pra `assets/outfits/...`.

Um `publish` só, cobrindo bundle + todos os atlases + os quatro JSONs do catálogo. Ele passa a ser o
**único ponto de escrita** no repo irmão — invariante mais forte que a de hoje, não mais fraca: o
`CONTEXT.md:24-31` separa fragmento (local, gitignorado, pra revisão) de export (explícito, escreve
no irmão), e essa separação continua intacta.

**Blocked by:** 03 (paths), 07 (uma árvore só pra publicar).

- [x] `publish` copia o bundle do mapa (`map.json` + `sheets/`) pro
      `apps/tibia-idle-front/public/assets/<MAP>-sprites-v<N>/`
- [x] Copia os oito destinos de atlas, incluindo `outfits/`, `effects/`, `corpses/`, `pools/`
- [x] Escreve os quatro JSONs de catálogo/conteúdo que o `--export` já escrevia
- [x] **Falha alto** quando um atlas referenciado não foi bakeado, listando o que falta e o comando
      que gera — o caso do `assets/outfits/` de hoje deve virar erro, não silêncio
- [x] `--prune` remove do destino o que o catálogo não referencia, **listando antes**; sem a flag,
      nunca remove
- [x] Cópia comparada por conteúdo (não sobrescreve bytes iguais), como `sync_items` já faz
- [x] `sync_items_to_tibia_idle.py` deixa de existir como comando separado

## Comments

`extractor/scripts/publish.py`. `sync_items_to_tibia_idle.py` foi removido.

### A prova de que o problema era real

Rodado contra um front de mentira com o layout do de verdade:

```
[OK] ROOK-HUNT-0001_rats-sewers-2-rookguard: 4 copiados -> .../ROOK-HUNT-0001_..._-sprites-v6
[OK] atlases/corpses/: 2   [OK] atlases/effects/: 2    [OK] atlases/pools/: 2
[OK] atlases/items-animated/: 16   [OK] atlases/items-static/: 8   [OK] atlases/outfits/: 2098
[OK] atlases/items-index.json: copiado
```

Os 4 arquivos do bundle incluem **`monsters/respawn.json`** — exatamente o que a cópia manual sempre
deixava para trás, e a evidência que abriu o ticket. `sync_tree` é recursivo; uma cópia plana
reproduziria o bug.

Segunda rodada: 7 destinos com 0 copiados. Comparação por conteúdo funciona.

### Falha alto quando o atlas não existe

Testado escondendo `atlases/outfits/` e rodando de novo:

```
[ERRO] atlas referenciado pelo bundle que nunca foi bakeado:
  - atlases/outfits/  ->  uv run python extractor/scripts/bake_outfit_atlas.py
  (exit 1)
```

O que ele exige não é uma lista fixa: `referenced_atlases()` **lê o `respawn.json`** e coleta os
`atlas.image`/`atlas.json` que começam com `assets/`. Assumir a lista deixaria o erro aparecer como
imagem quebrada na tela em vez de aqui.

### Duas decisões que valem registro

**O nome da pasta de destino sai do `assetsRoot` do próprio `map.json`**, não é remontado. Remontar
criaria uma segunda fonte de verdade para o mesmo nome, e divergir significa 404 no bundle inteiro.

**`--prune` só toca pasta com `-sprites-v` no nome.** O `assets/` do front tem atlas, fontes e
imagens soltas; um prune que varresse tudo que "não está no catálogo" apagaria metade. E sem a flag
ele nunca remove nada — com ela, lista antes.

### Oito destinos, incluindo os quatro que faltavam

`items-static`, `items-animated`, `outfits`, `player-outfits`, `effects`, `corpses`, `pools` +
`items-index.json`. Um teste fixa que os quatro esquecidos (`outfits`, `effects`, `corpses`,
`pools`) estão cobertos, e outro que todo alvo nomeia um comando de bake — sem isso o erro viraria
"(bake desconhecido)", que é a mensagem que não ajuda ninguém.

`player-outfits` ainda não foi bakeado nesta máquina; o publish reporta `[--] não bakeado` com o
comando, em vez de falhar — ele não é referenciado por nenhum `respawn.json`.

14 testes em `extractor/tests/test_publish.py`. 437 na suíte.

### O que eu não fiz, de propósito

**Não rodei o publish contra o `tibia-idle` de verdade.** Ele escreveria ~61 MB de atlas no
`public/assets/` de um checkout que está no meio de uma migração Bun/Nx, numa branch com trabalho
não publicado. Verifiquei o comportamento inteiro contra um destino temporário com o mesmo layout.
Para publicar de verdade:

```
uv run python extractor/scripts/publish.py --all --dry-run   # confere o que vai
uv run python extractor/scripts/publish.py --all
```
