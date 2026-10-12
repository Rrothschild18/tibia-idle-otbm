# extractor/archive

Recortes **assados** que não têm fonte em `extractor/maps/`.

Para eles, "regenerável" é mentira: recriar qualquer um custa um recorte novo a
partir do dump de 638 MB da cidade, com a curadoria da época — que mudou. Eles
nasceram de rodadas antigas do `build_curated_hunts.py`, foram assados pelo
`build_map.js`, e sobreviveram só porque `ready-maps/` existia nesta máquina.

O que está aqui entra no jogo **por cópia**, sem pipeline:

```
uv run python extractor/scripts/publish.py <CIDADE>/<ID>_<slug>
bunx nx run hunt-add:add -- --from <pasta-publicada-em-public/assets> --name "<nome de jogador>"
```

Duas coisas não entram, por regra:

- **recorte de Rookgaard sob id de cidade do continente.** Rookgaard é região
  própria e separada de Thais. Os cinco que existiam assim
  (`al-dee-rat-cave`, `troll-cave-rookgaard`, `rookgaard-bear-cave`,
  `spider-cave-rookgaard-premium`, `orc-fortress-rookgaard`, todos sob id de
  THAIS) ficaram fora; eles já existem corretamente sob `ROOK-*`.
- **pastas `*_window`.** Nada no jogo lê a saída do `build_hunt_window.py`.
