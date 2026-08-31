# 01 — Extrair o sprite do efeito de teleport e gerar atlas de effects

**What to build:** Habilitar a extração da categoria `effect` do protobuf de
aparências (`APPEARANCE_EFFECT = 3`), rodar pra obter o sprite id 11
(`CONST_ME_TELEPORT`, 11 frames de 70ms, sem loop, luz própria), e gerar um
atlas de effects consumível pelo jogo, no mesmo padrão de `items-static`/
`items-animated`.

**Blocked by:** Nenhum — pode começar imediatamente

**Status:** ready-for-agent

- [ ] `"effects"` adicionado a `ENABLED_GROUPS` em `extract_sprites.py:25`
      (ou um jeito de rodar só esse grupo sem desligar `outfits`)
- [ ] Rodar a extração e confirmar que o sprite id 11 (`CONST_ME_TELEPORT`) sai
      como PNGs individuais (11 frames), com o `spriteInfo`/`animation`
      correto (`durationMin`/`durationMax` 70, `loopType` contado, não
      repetido)
- [ ] `bake_effect_atlas.py` novo (cópia simplificada de `bake_item_atlas.py`,
      sem `is_equipment_candidate` — não se aplica a effects) que empacota os
      sprites de effect extraídos num atlas único
- [ ] Atlas gerado e localizável do mesmo jeito que `items-static`/
      `items-animated` hoje (mesma convenção de nome/pasta de saída)
- [ ] Documentar em `extractor/SPRITE_METADATA.md` (ou `PHASER_MONSTERS.md`,
      o que fizer mais sentido) que a categoria `effect` agora é extraída, e
      que o escopo por ora é só o efeito de teleport
- [ ] Nenhuma regressão na extração de `outfits`/`items` já existente
