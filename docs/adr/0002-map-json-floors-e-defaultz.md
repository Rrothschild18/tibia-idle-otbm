# `map.json` ganha `floors`/`defaultZ` em vez de um `layers` achatado

`build_phaser_map.py` indexava tiles/itens só por `(x, y)`, ignorando `feature.z` do dump do
OTBM. Mapas com mais de um floor real (ex. `skeletons-rookguard`: z=7 chão, z=8 masmorra embaixo
com 100% de overlap de `(x,y)` com o z=7, z=9 pequena área acima) tinham seus floors colididos
num único `layers` achatado — tile de chão de um floor sobrescrevia o outro, e itens de floors
diferentes ficavam empilhados na mesma posição.

**Decisão:** o `map.json` passa a ter `"floors": {"<z>": {"z": <z>, "layers": [...]}, ...}` no
lugar do `"layers": [...]` do topo, mais um `"defaultZ"` (o floor que deve renderizar por
padrão — `7` se existir, senão o menor z presente). Cada floor tem seu próprio conjunto
independente das mesmas 8 layers de sempre (Ground/Borders/Bottom/WallsSouth/WallsEast/Objects/
Top/Roof). `objectDefs`/`tilesets`/`animations`/`bounds`/`width`/`height` continuam globais —
já eram floor-agnósticos (chaveados por appearanceId, não por posição), então não duplicam.

**Bounds continuam união entre todos os floors do mapa** (não uma bounding box por floor). Isso
garante que `(tileX, tileY)` significa a mesma coluna física em qualquer floor — replica o
comportamento real do Tibia, onde trocar de floor preserva x,y e só muda z. Sem isso, o
front-end precisaria de metadata explícita de "destino" em cada escada/buraco pra saber pra onde
o jogador vai; com bounds unificadas, ele só precisa checar se o floor de destino tem conteúdo
na mesma coluna.

**O campo `"version"` do map.json não muda.** A mudança é estrutural/aditiva, não um bump de
schema formal — e isso é deliberado: `extractor/PHASER_INTEGRATION.md` já se refere a esse
formato como "v3" no título (compact `objectDefs` + arrays), enquanto o campo `version` real do
JSON sempre foi `2`. Bumpar `version` pra 3 agora colidiria com esse "v3" que já significa outra
coisa. Quem for versionar o schema de verdade no futuro deve escolher um nome que não seja "v3".

**Detecção de tile de transição (escada/buraco):** Tibia não tem uma flag genérica de OTBM pra
isso. `extractor/SPRITE_METADATA.md` documentava a heurística observada nos appearance IDs 421 e
12202 como `bank + usable + forceuse + unmove + automap`. Ao validar essa heurística contra os
itens realmente usados nos 8 mapas existentes, ela **não pegava a escada real de
`skeletons-rookguard`** (appearance ID 1948, o único tile daquele mapa com essa assinatura de uso
— presente uma única vez, exatamente onde se espera a descida pra masmorra do z=8): 1948 tem
`usable + forceuse + unmove + automap`, mas não tem `bank`. Checando todo item colocado nos 8
mapas, o conjunto `usable + forceuse + unmove + automap` (sem exigir `bank`) combina com
exatamente 4 appearance IDs — 386, 421, 1948, 12202 — e nenhum outro item do corpus atual
compartilha essa assinatura sem ser uma dessas 4 escadas/buracos conhecidas. Por isso a
heurística final **não exige `bank`**: `usable + forceuse + unmove + automap` sozinha já é
suficiente e não introduz falso positivo nos dados atuais. `analyze_item()`
(`build_phaser_map.py`) passa a preservar `usable`/`forceuse` (antes descartados) e deriva
`isFloorTransition` a partir dessa combinação, do mesmo jeito que `isRoof` já é derivado de outra
combinação de flags — não é uma flag bruta do OTBM, é calculada. **Limitação conhecida:** essa
heurística não indica a *direção* nem o *destino* da transição (só que aquele tile é um). A
resolução de "pra qual floor essa escada leva" fica a cargo do front-end (ver tickets do repo
`tibia-idle`), usando a regra "desce se o floor de baixo tiver conteúdo na mesma coluna, senão
sobe" — suficiente pro caso comum (entrada de masmorra), mas não modela escadas que sobem
deliberadamente nem exceções pontuais (ex. o tile solto em z=3 do `troll-rookguard`). Também
vale notar que essa é uma heurística sobre os 8 mapas hoje existentes — um mapa novo pode conter
um item de transição com uma assinatura de flags diferente que essa heurística não capture;
isso exigiria revisitar a heurística (ou um override manual, no estilo do `item_classifier.py`),
não é uma garantia geral do formato OTBM.

**Mapas single-floor não regridem:** viram só `floors: {"7": {...}}`, sem nenhum tile marcado
`isFloorTransition` — o front-end não precisa de nenhum caso especial pra esse formato.
