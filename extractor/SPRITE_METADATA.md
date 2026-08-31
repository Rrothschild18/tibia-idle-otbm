# Sprite Metadata — Análise Completa de Flags e Padrões

Documentação gerada a partir da análise exaustiva de todos os arquivos JSON de metadados em `sprites/items/`, dos mapas `dragon-darashia` e `larva-ankrah`, e do protobuf `Appearances.proto`.

---

## 1. Estrutura de um Arquivo de Metadados (JSON)

Cada item possui um JSON em `sprites/items/{id}/{id}.json` ou `sprites/items/{id}.json`:

```json
{
  "id": 4427,
  "frame_group": [
    {
      "fixed_frame_group": "FRAME_GROUP_IDLE",
      "sprite_info": {
        "sprite_id": ["4427_0", "4427_1", "4427_2", ...],
        "patternWidth": 4,
        "patternHeight": 4,
        "patternDepth": 1,
        "layers": 1,
        "patternFrames": 0,
        "animation": null
      }
    }
  ],
  "flags": {
    "bank": { "waypoints": 0 },
    "unpass": true,
    "unmove": true,
    "unsight": true,
    "automap": { "color": 114 },
    "fullbank": true
  }
}
```

### Campos do `sprite_info`

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `sprite_id` | `string[]` | Lista de IDs dos PNGs. Quantidade = `patternWidth × patternHeight × patternDepth × layers × max(patternFrames, 1)` |
| `patternWidth` | `int` | Quantas tiles o sprite ocupa na horizontal |
| `patternHeight` | `int` | Quantas tiles o sprite ocupa na vertical |
| `patternDepth` | `int` | Variantes direcionais (1 = sem variação, 2+ = norte/sul/hook) |
| `layers` | `int` | Camadas visuais compostas (geralmente 1) |
| `patternFrames` | `int` | Frames de animação (0 = estático) |
| `animation` | `object\|null` | Configuração de animação (ver seção 6) |

### Cálculo de Sprites Totais

```
total_sprites = patternWidth × patternHeight × patternDepth × layers × max(patternFrames, 1)
```

---

## 2. Catálogo Completo de Flags

### 2.1 Flags de Terreno / Chão

| Flag | Tipo | Descrição | Impacto na Renderização |
|------|------|-----------|------------------------|
| `bank` | `{ waypoints: int }` | Superfície caminhável. `waypoints` = velocidade do chão (0 = bloqueado, 100–160 = normal) | Identifica tiles de chão na tilelayer |
| `fullbank` | `bool` | Cobre visualmente todo o tile (sem transparência) | Tiles com `bank+fullbank` são ground puro |

**Exemplos:**
- `bank: { waypoints: 100 }` — chão normal (grama, pedra)
- `bank: { waypoints: 0 }` — chão bloqueado (parede sólida, vazio, lava)
- `bank: { waypoints: 150 }` — chão de caverna
- `bank: { waypoints: 160 }` — areia

### 2.2 Flags de Bloqueio

| Flag | Tipo | Descrição | Impacto na Renderização |
|------|------|-----------|------------------------|
| `unpass` | `bool` | Bloqueia passagem (pathfinding) | Item não pode ser atravessado |
| `unmove` | `bool` | Não pode ser movido por jogadores | Quase todos os itens de mapa possuem |
| `unsight` | `bool` | Bloqueia visão (line of sight) | Oculta tiles atrás/abaixo |

**Padrão crucial:** `unpass + unmove + unsight` juntos = **parede/teto estrutural** → layer "roof"

### 2.3 Flags de Camada Visual

| Flag | Tipo | Descrição | Layer de Destino |
|------|------|-----------|-----------------|
| `clip` | `bool` | Sprite estende além dos limites do tile (bordas de transição) | → "border" (depthOffset: 1) |
| `bottom` | `bool` | Renderizado acima do chão, abaixo de criaturas | → "bottom" (depthOffset: 5) |
| `top` | `bool` | Renderizado acima de tudo (teto, sinais) | → "top" (depthOffset: 50) |

### 2.4 Flags de Aparência / Visual

| Flag | Tipo | Descrição | Exemplo |
|------|------|-----------|---------|
| `automap` | `{ color: int }` | Cor no minimapa | `{ color: 114 }` = montanha cinza |
| `height` | `{ elevation: int }` | Elevação visual do sprite (pixels acima do tile) | `{ elevation: 24 }` em degraus |
| `light` | `{ brightness: int, color: int }` | Emite luz dinâmica | `{ brightness: 4, color: 138 }` em lava |
| `shift` | `{ x: int, y: int }` | Offset de renderização em pixels | Ajuste fino de posição |
| `translucent` | `bool` | Sprite semitransparente | Bordas d'água |
| `hang` | `bool` | Item pendurado em parede | Tochas, quadros |
| `hook` | `{ direction: enum }` | Ponto de gancho na parede (EAST/SOUTH) | Paredes com espaço para pendurar |
| `avoid` | `bool` | NPC evita pisar neste tile | Poças, bordas |
| `ignore_look` | `bool` | Não exibe tooltip ao passar mouse | Decorações invisíveis de borda |
| `dont_hide` | `bool` | Não fica invisível quando sob teto | Itens sempre visíveis |
| `no_movement_animation` | `bool` | Sem animação de movimento | Itens estáticos |

### 2.5 Flags de Interação

| Flag | Tipo | Descrição | Exemplo |
|------|------|-----------|---------|
| `usable` | `bool` | Pode ser usado (clicável) | Alavancas, portas |
| `multiuse` | `bool` | Pode usar com outro objeto | Cordas, pás |
| `forceuse` | `bool` | Uso forçado ao clicar | Escadas automáticas |
| `rotate` | `bool` | Pode ser rotacionado | Móveis |
| `take` | `bool` | Pode ser pego pelo jogador | Itens de inventário |
| `wrap` | `bool` | Pode ser embalado | Decorações de casa |
| `container` | `bool` | Pode conter outros itens | Baús, mochilas |
| `default_action` | `{ action: enum }` | Ação padrão ao clicar | `NONE`, `AUTOWALK_HIGHLIGHT` |
| `lenshelp` | `{ id: int }` | ID de ajuda contextual | Sinais com texto |

### 2.6 Flags de Item / Comércio

| Flag | Tipo | Descrição |
|------|------|-----------|
| `cumulative` | `bool` | Item empilhável (moedas, flechas) |
| `ammo` | `bool` | Item de munição |
| `clothes` | `{ slot: int }` | Equipamento vestível (slot = posição no corpo) |
| `market` | `{ category, trade_as, show_as }` | Comercializável no mercado |
| `npcsaledata` | `[{ name, location, sale_price, buy_price }]` | Dados de venda em NPCs |
| `cyclopediaitem` | `{ cyclopedia_type }` | Entrada na enciclopédia |
| `upgradeclassification` | `{ upgrade_classification }` | Tier de upgrade |

### 2.7 Flags de Estado

| Flag | Tipo | Descrição |
|------|------|-----------|
| `liquidpool` | `bool` | Poça de líquido no chão |
| `liquidcontainer` | `bool` | Container de líquido (garrafas) |
| `corpse` | `bool` | Corpo de criatura morta |
| `lying_object` | `bool` | Objeto caído no chão |
| `expire` | `bool` | Desaparece após tempo |
| `expirestop` | `bool` | Para de expirar |
| `changedtoexpire` | `{ former_object_typeid }` | ID do objeto original antes de expirar |
| `wearout` | `bool` | Desgasta com uso |
| `write_once` | `{ max_text_length_once }` | Pode ser escrito uma vez |
| `reportable` | `bool` | Pode ser reportado |
| `show_off_socket` | `bool` | Socket de exibição |

---

## 3. Combinações de Pattern (dimensões de sprites)

### Padrões Encontrados nos Mapas Analisados

| Pattern (WxHxD) | Sprites | Tamanho Visual | Ocorrências | Exemplo IDs | Uso Típico |
|-----------------|---------|----------------|-------------|-------------|------------|
| **1×1×1** | 1 | 32×32 (1 tile) | ~120 itens | 979, 1006, 7062 | Itens simples, bordas, decorações |
| **2×1×1** | 2 | 64×32 (2 tiles horiz.) | ~20 itens | 968, 1091, 1704 | Paredes largas, cercas, bordas |
| **1×2×1** | 2 | 32×64 (2 tiles vert.) | ~15 itens | 969, 1092, 1705 | Pilares, paredes verticais |
| **2×2×1** | 4 | 64×64 (2×2 tiles) | ~10 itens | 1703, 6475, 9813 | Árvores, rochas, objetos grandes |
| **3×1×1** | 3 | 96×32 | Raro | — | Objetos muito largos |
| **1×3×1** | 3 | 32×96 | Raro | — | Objetos muito altos |
| **3×3×1** | 9 | 96×96 (3×3 tiles) | ~2 itens | 9824 | Decorações de chão grandes |
| **4×3×1** | 12 | 128×96 | ~2 itens | 2888, 2891 | Poças de líquido |
| **4×4×1** | 16 | 128×128 (4×4 tiles) | ~6 itens | 231, 1128, 4427, 9246, 11942 | Terreno (grounds multi-tile) |
| **1×2×2** | 4 | 32×64 com 2 variantes | ~2 itens | 4747 | Paredes direcionais (N/S) |
| **2×1×2** | 4 | 64×32 com 2 variantes | ~2 itens | 4748 | Paredes direcionais (L/O) |
| **1×3×3** | 9 | 32×96 com 3 variantes | ~1 item | 1026 | Parede com 3 faces |
| **3×1×3** | 9 | 96×32 com 3 variantes | ~1 item | 1027 | Parede com 3 faces |
| **1×1×2** | 2 | 32×32 com 2 variantes | Raro | — | Item com variante direcional |

### Nota sobre `patternDepth > 1`

Quando `patternDepth > 1`, o item possui variantes para diferentes paredes/direções. Geralmente usado com flag `hook` (itens penduráveis). O renderer deve selecionar a sprite correta baseado na orientação da parede adjacente.

---

## 4. Padrões de Classificação Descobertos

### 4.1 Ground (tilelayer)

**Regra:** `tileid` do OTBM vai para a tilelayer Ground, **exceto** tiles grandes bloqueantes
(`unpass + unmove + unsight` com sprite > 1×1) que são reclassificados como Roof.

**Padrão de flags típico:**
```
bank + fullbank + unmove + automap
```

**Variantes que ficam no Ground:**
| Combinação de Flags | Significado | Exemplos |
|---------------------|------------|----------|
| `bank{100-160} + fullbank + unmove + automap` | Chão caminhável normal | 7062–7066, 9700–9705 |
| `bank{0} + fullbank + unpass + unmove + unsight` | Vazio 1×1 (fica no ground) | 101 |
| `bank + fullbank + usable + forceuse + unmove + automap` | Chão interativo (escada, buraco) | 421, 12202 |
| `bank + fullbank + unmove + avoid + translucent + automap` | Borda d'água (semi-transparente) | 7734, 12203 |

**Variantes reclassificadas como Roof (objectgroup):**
| Combinação de Flags | Significado | Exemplos |
|---------------------|------------|----------|
| `bank{0} + unpass + unmove + unsight + automap` (4×4) | Parede de montanha/caverna | 4427, 9246, 1128 |

Estes tiles são grandes (128×128px) e quando renderizados numa tilelayer 32×32
causam artefatos visuais. Ao serem movidos para o Roof objectgroup, renderizam
no tamanho nativo e cobrem corretamente os sprites de borda/clip abaixo.

### 4.2 Border / Clip (objectgroup, depth +1)

**Regra:** `clip = true`

**Padrão de flags típico:**
```
clip + unmove
```

**Variantes:**
| Combinação | Significado | Exemplos |
|------------|------------|----------|
| `clip + unmove` | Borda simples de terreno | 979–991, 1095–1098, 4419–4426 |
| `clip + unmove + ignore_look` | Borda invisível ao tooltip | 1708–1711, 6480–6483 |
| `clip + unmove + height` | Borda com elevação (degrau) | 4746 |
| `clip + unmove + automap` | Borda com cor no minimapa | 4746 |

**Tamanhos encontrados para clips:**
- 1×1 (32×32) — bordas de canto
- 2×1 (64×32) — bordas horizontais
- 1×2 (32×64) — bordas verticais
- 2×2 (64×64) — cantos grandes de transição

### 4.3 Bottom (objectgroup, depth +5)

**Regra:** `bottom = true` (e `clip` é `false`)

**Padrão de flags típico:**
```
bottom + unpass + unmove + automap
```

**Variantes:**
| Combinação | Significado | Exemplos |
|------------|------------|----------|
| `bottom + unpass + unmove + automap` | Parede baixa, cerca | 968, 969, 1006, 1090 |
| `bottom + unpass + unmove + unsight + automap` | Parede sólida que bloqueia visão | 1026, 1027, 1032–1034, 4429–4432, 7541 |
| `bottom + unmove + avoid + height + automap` | Degrau/elevação com aviso | 7542, 7544, 7546 |
| `bottom + unmove + height + automap` | Degrau/elevação normal | 7543, 7545, 7547 |
| `bottom + liquidpool + unmove` | Poça de líquido | 2888, 2891 |
| `bottom + unmove + automap` | Decoração grande de chão | 9824 |

### 4.4 Roof (objectgroup, depth +100)

**Regra:** `unpass + unmove + unsight` (os três juntos, sem `bottom`, sem `clip`, sem `top`)

**Inclui também tileids reclassificados:** Tiles que o OTBM marca como `tileid` mas que possuem
`unpass + unmove + unsight` e sprite > 1×1 (ex: 4427, 1128, 9246) são automaticamente
movidos do ground tilelayer para este objectgroup.

**Padrão de flags típico:**
```
unpass + unmove + unsight + automap [+ bank]
```

Nota: Muitos itens de "roof" na verdade têm flag `bottom` também (ex: 1026, 4429). Nesse caso, o `bottom` tem prioridade na árvore de decisão e eles vão para a camada "bottom", não "roof". A camada roof recebe apenas itens que NÃO têm `bottom`, `clip`, nem `top`.

**Tileids reclassificados como roof:**
| Combinação | Significado | Exemplos |
|------------|------------|----------|
| `bank{0} + unpass + unmove + unsight + automap` (4×4) | Parede de montanha/caverna | 4427, 9246, 1128 |

**Itens que caem no roof (sem bottom/clip/top):**
| Combinação | Significado | Exemplos |
|------------|------------|----------|
| `unpass + unmove` | Bloqueio simples sem visão bloqueada | 24875, 18609–18614 |
| `unmove + ignore_look` | Decoração bloqueadora invisível | 9820–9823 |

### 4.5 Object (objectgroup, depth +10)

**Regra:** Não possui `clip`, `bottom`, `top`, nem a combinação completa `unpass+unmove+unsight`.

**Padrão de flags típico:**
```
unmove [+ qualquer outra flag que não seja clip/bottom/top]
```

**Variantes:**
| Combinação | Significado | Exemplos |
|------------|------------|----------|
| `unmove` | Decoração imóvel simples | 1049, 1051 |
| `usable + unpass + unmove` | Objeto interativo bloqueante | 24875 |
| `take + usable + multiuse + clothes + market` | Equipamento (item de inventário) | 3294 |
| `unmove + ignore_look` | Objeto invisível ao tooltip | 9820–9823 |

### 4.6 Top (objectgroup, depth +50)

**Regra:** `top = true`

**Padrão de flags típico:**
```
top + unmove [+ light]
```

**Exemplos gerais (não encontrados nos mapas analisados):**
| Combinação | Significado | Exemplos Globais |
|------------|------------|------------------|
| `top + unmove + light` | Teto com iluminação | 1012 |
| `top + usable + unmove + lenshelp` | Sinal/placa overhead | 5083 |

---

## 5. Itens Completos por Mapa

### 5.1 Dragon-Darashia — Tile IDs (9 únicos)

| ID | Pattern | Flags | Descrição |
|----|---------|-------|-----------|
| **231** | 4×4×1 | `bank{160}`, `unmove`, `automap{207}`, `fullbank` | Chão de areia/pedra |
| **1128** | 4×4×1 | `bank{0}`, `unpass`, `unmove`, `unsight`, `automap{86}` | Parede de caverna |
| **4427** | 4×4×1 | `bank{0}`, `unpass`, `unmove`, `unsight`, `automap{114}`, `fullbank` | Parede de montanha |
| **7062** | 1×1×1 | `bank{150}`, `unmove`, `automap{129}`, `fullbank` | Chão de caverna (variante 1) |
| **7063** | 1×1×1 | `bank{150}`, `unmove`, `automap{129}`, `fullbank` | Chão de caverna (variante 2) |
| **7064** | 1×1×1 | `bank{150}`, `unmove`, `automap{129}`, `fullbank` | Chão de caverna (variante 3) |
| **7065** | 1×1×1 | `bank{150}`, `unmove`, `automap{129}`, `fullbank` | Chão de caverna (variante 4) |
| **7066** | 1×1×1 | `bank{150}`, `unmove`, `automap{129}`, `fullbank` | Chão de caverna (variante 5) |
| **7734** | 1×1×1 | `bank{150}`, `unmove`, `avoid`, `translucent`, `automap{210}`, `default_action{AUTOWALK_HIGHLIGHT}` | Borda d'água subterrânea |

### 5.2 Dragon-Darashia — Item IDs (95 únicos)

#### Clips (bordas de terreno) — 53 itens
| ID(s) | Pattern | Flags Extras | Descrição |
|-------|---------|-------------|-----------|
| 979, 980, 981, 983–991 | 1×1×1 | — | Bordas de caverna (cantos) |
| 1091, 1093 | 2×1×1 | — | Bordas horizontais de caverna |
| 1092, 1094 | 1×2×1 | — | Bordas verticais de caverna |
| 1095–1098 | 1×1×1 | — | Cantos de borda de caverna |
| 1703 | 2×2×1 | — | Transição grande de terreno |
| 1704, 1706 | 2×1×1 | — | Transição horizontal |
| 1705, 1707 | 1×2×1 | — | Transição vertical |
| 1708–1711 | 1×1×1 | `ignore_look` | Borda invisível ao tooltip |
| 1712–1715 | 1×1×1 | — | Cantos de transição |
| 1729, 1731 | 2×1×1 | — | Borda de montanha horizontal |
| 1730, 1732 | 1×2×1 | — | Borda de montanha vertical |
| 1733 | 1×1×1 | — | Canto de montanha |
| 2727, 2731 | 1×1×1 | — | Pequenas bordas |
| 3993, 4412, 4422–4426 | 1×1×1 | — | Bordas de areia/rocha |
| 6475 | 2×2×1 | — | Transição grande |
| 6476, 6477 | 2×1×1 | — | Transição horizontal |
| 6478, 6479 | 1×2×1 | — | Transição vertical |
| 6480–6483 | 1×1×1 | `ignore_look` | Borda invisível |
| 6484–6487 | 1×1×1 | — | Cantos |
| 24881, 24885, 24886 | 1×1×1 | — | Bordas especiais |
| 24882 | 2×1×1 | — | Borda horizontal especial |

#### Bottom (decorações de chão) — 33 itens
| ID(s) | Pattern | Flags Extras | Descrição |
|-------|---------|-------------|-----------|
| 968 | 2×1×1 | `unpass`, `automap` | Parede baixa horizontal |
| 969 | 1×2×1 | `unpass`, `automap` | Parede baixa vertical |
| 1006 | 1×1×1 | `unpass`, `automap` | Bloco de parede pequeno |
| 1026 | 1×3×3 | `unpass`, `unsight`, `automap` | Parede direcional (3 faces, 3 alturas) |
| 1027 | 3×1×3 | `unpass`, `unsight`, `automap` | Parede direcional (3 larguras, 3 faces) |
| 1032–1034 | 1×1×1 | `unpass`, `unsight`, `automap` | Cantos de parede |
| 1090 | 1×1×1 | `unpass`, `automap` | Decoração bloqueante |
| 3642–3644, 3648, 3650, 3697 | 1×1×1 | `unpass`, `automap` | Pedras/blocos no chão |
| 4429–4432 | 1×1×1 | `unpass`, `unsight`, `automap` | Blocos de parede |
| 4747 | 1×2×2 | `unpass`, `unsight`, `automap` | Parede N/S com 2 direções |
| 4748 | 2×1×2 | `unpass`, `unsight`, `automap` | Parede L/O com 2 direções |
| 7541 | 1×1×1 | `unpass`, `unsight`, `automap` | Pilar/bloco |
| 7542, 7544, 7546 | 1×1×1 | `avoid`, `height`, `automap`, `default_action` | Degrau com aviso |
| 7543, 7545, 7547 | 1×1×1 | `height`, `automap`, `default_action` | Degrau normal |
| 7586 | 2×1×1 | `unpass`, `automap` | Parede horizontal |
| 7587 | 1×2×1 | `unpass`, `automap` | Parede vertical |

#### Objects (itens normais) — 8 itens
| ID(s) | Pattern | Flags | Descrição |
|-------|---------|-------|-----------|
| 1049 | 1×2×1 | `unmove` | Decoração vertical |
| 1051 | 2×1×1 | `unmove` | Decoração horizontal |
| 3294 | 1×1×1 | `usable`, `multiuse`, `take`, `clothes`, `market`, `npcsaledata`, `cyclopediaitem`, `upgradeclassification` | Espada (item de equipamento) |
| 24875 | 1×1×1 | `usable`, `unpass`, `unmove` | Objeto interativo bloqueante |

### 5.3 Larva-Ankrah — Tile IDs (17 únicos)

| ID | Pattern | Flags | Descrição |
|----|---------|-------|-----------|
| **101** | 1×1×1 | `bank{0}`, `unpass`, `unmove`, `unsight`, `fullbank` | Vazio preto (void tile) |
| **231** | 4×4×1 | `bank{160}`, `unmove`, `automap{207}`, `fullbank` | Chão de areia |
| **421** | 1×1×1 | `bank{100}`, `usable`, `forceuse`, `unmove`, `automap{210}`, `fullbank`, `default_action{NONE}` | Escada/buraco |
| **4427** | 4×4×1 | `bank{0}`, `unpass`, `unmove`, `unsight`, `automap{114}`, `fullbank` | Parede de montanha |
| **9246** | 4×4×1 | `bank{0}`, `unpass`, `unmove`, `unsight`, `automap{114}` | Variante de montanha |
| **9700–9703** | 1×1×1 | `bank{110}`, `unmove`, `automap{207}`, `fullbank` | Areia (variantes) |
| **9704–9707** | 1×1×1 | `bank{110}`, `unmove`, `automap{121}`, `fullbank` | Areia escura (variantes) |
| **11942** | 4×4×1 | `bank{120}`, `unmove`, `automap{121}`, `fullbank` | Terreno multi-tile |
| **12202** | 1×1×1 | `bank{100}`, `usable`, `forceuse`, `unmove`, `automap{210}`, `fullbank`, `default_action{NONE}` | Escada/buraco |
| **12203** | 1×1×1 | `bank{130}`, `unmove`, `avoid`, `translucent`, `automap{210}`, `fullbank`, `default_action{AUTOWALK_HIGHLIGHT}` | Borda d'água |
| **19272** | 1×1×1 | `bank{110}`, `unmove`, `automap{121}`, `fullbank` | Areia (variante) |

### 5.4 Larva-Ankrah — Item IDs (90 únicos)

#### Clips (bordas) — ~40 itens
| ID(s) | Pattern | Flags Extras | Descrição |
|-------|---------|-------------|-----------|
| 1704, 1706 | 2×1×1 | — | Transição horizontal |
| 1708, 1709 | 1×1×1 | `ignore_look` | Borda invisível |
| 4415, 4417 | 2×1×1 | — | Borda de areia horizontal |
| 4416, 4418 | 1×2×1 | — | Borda de areia vertical |
| 4419–4426 | 1×1×1 | — | Cantos de areia |
| 6475 | 2×2×1 | — | Transição grande |
| 6476–6479 | 2×1 / 1×2 | — | Transições |
| 6480–6483 | 1×1×1 | `ignore_look` | Bordas invisíveis |
| 6484–6487 | 1×1×1 | — | Cantos |
| 8881, 8885 | 1×1×1 | — | Bordas especiais de deserto |
| 9708–9719 | 1×1×1 | — | Bordas de terreno de deserto/caverna |

#### Bottom (decorações) — ~30 itens
| ID(s) | Pattern | Flags Extras | Descrição |
|-------|---------|-------------|-----------|
| 968, 969 | 2×1 / 1×2 | `unpass`, `automap` | Paredes baixas |
| 1026 | 1×3×3 | `unpass`, `unsight`, `automap` | Parede direcional |
| 1027 | 3×1×3 | `unpass`, `unsight`, `automap` | Parede direcional |
| 1032–1034 | 1×1×1 | `unpass`, `unsight`, `automap` | Cantos de parede |
| 2888, 2891 | 4×3×1 | `liquidpool` | Poças de líquido |
| 4429–4432 | 1×1×1 | `unpass`, `unsight`, `automap` | Blocos de parede |
| 4747 | 1×2×2 | `unpass`, `unsight`, `automap` | Parede N/S |
| 4748 | 2×1×2 | `unpass`, `unsight`, `automap` | Parede L/O |
| 7541 | 1×1×1 | `unpass`, `unsight`, `automap` | Pilar |
| 7586, 7587 | 2×1 / 1×2 | `unpass`, `automap` | Paredes |
| 9813, 9814, 9817 | 2×2×1 | `unpass`, `automap` | Blocos grandes |
| 9824 | 3×3×1 | `automap` | Decoração grande |
| 19000–19029 (15 IDs) | 1×1×1 | `unpass`, `unsight`, `automap` | Paredes de colmeia |

#### Objects — ~14 itens
| ID(s) | Pattern | Flags | Descrição |
|-------|---------|-------|-----------|
| 9820–9823 | 2×2×1 | `unmove`, `ignore_look` | Decorações invisíveis grandes |
| 24875 | 1×1×1 | `usable`, `unpass`, `unmove` | Objeto bloqueante |

#### Animados — 6 itens (EXCLUSIVOS deste mapa)
| ID | Pattern | Sprites | Duração | Flags | Descrição |
|----|---------|---------|---------|-------|-----------|
| **18609** | 1×1×1 | 6 frames | 100ms/frame | `unpass`, `unmove` | Efeito animado de larva |
| **18610** | 1×1×1 | 8 frames | 100ms/frame | `unpass`, `unmove` | Efeito animado de larva |
| **18611** | 1×1×1 | 6 frames | 100ms/frame | `unpass`, `unmove` | Efeito animado de larva |
| **18612** | 1×1×1 | 6 frames | 100ms/frame | `unpass`, `unmove` | Efeito animado de larva |
| **18613** | 1×1×1 | 8 frames | 100ms/frame | `unpass`, `unmove` | Efeito animado de larva |
| **18614** | 1×1×1 | 6 frames | 100ms/frame | `unpass`, `unmove` | Efeito animado de larva |

---

## 6. Estrutura de Animação

Quando um item é animado, o `sprite_info` contém:

```json
{
  "animation": {
    "default_start_phase": 0,
    "random_start_phase": false,
    "loop_count": 0,
    "loop_type": "LOOP_INFINITE",
    "phases": [
      { "duration_min": 100, "duration_max": 100 },
      { "duration_min": 100, "duration_max": 100 },
      { "duration_min": 100, "duration_max": 100 }
    ]
  },
  "sprite_id": ["18609_0", "18609_1", "18609_2", "18609_3", "18609_4", "18609_5"],
  "patternWidth": 1,
  "patternHeight": 1,
  "patternDepth": 1,
  "layers": 1,
  "patternFrames": 6
}
```

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `default_start_phase` | `int` | Frame inicial (0-based) |
| `random_start_phase` | `bool` | Se o frame inicial é aleatório |
| `loop_count` | `int` | Quantidade de loops (0 = infinito) |
| `loop_type` | `enum` | `LOOP_INFINITE`, `LOOP_COUNTED`, `LOOP_PINGPONG` |
| `phases[]` | `array` | Duração de cada frame em ms (min/max para variação) |

**Cálculo de frame rate:**
```
frame_duration = phases[0].duration_min  // geralmente min == max
frame_rate = 1000 / frame_duration       // ex: 100ms → 10 fps
```

---

## 7. Cores do Automap (Minimapa)

| Color ID | Cor Visual | Usado Em |
|----------|-----------|----------|
| 86 | Marrom escuro | Paredes de caverna (1128) |
| 114 | Cinza médio | Parede de montanha (4427, 9246) |
| 121 | Marrom | Areia escura (9704–9707, 11942) |
| 129 | Cinza escuro | Chão de caverna (7062–7066) |
| 140 | Laranja | Lava (4700) |
| 186 | Vermelho | Paredes com hook (5003) |
| 207 | Amarelo claro | Areia (231, 9700–9703) |
| 210 | Verde claro | Grama/chão genérico (421, 7734, 12202, 12203) |
| 215 | Azul claro | Objetos luminosos (47367) |

---

## 8. Velocidades de Ground (waypoints)

| Waypoints | Tipo de Terreno | Exemplos |
|-----------|----------------|----------|
| 0 | Bloqueado (não caminhável) | Paredes, lava, void |
| 100 | Chão normal (pedra, madeira) | 421, 475, 12202 |
| 110 | Areia | 9700–9707, 19272 |
| 120 | Terreno médio | 11942 |
| 130 | Terreno semi-rápido | 12203 |
| 150 | Caverna | 7062–7066, 7734 |
| 160 | Areia/estrada | 231 |

---

## 9. Estatísticas Gerais

| Métrica | Valor |
|---------|-------|
| Total de IDs únicos (ambos mapas) | 174 |
| Tile IDs únicos | 22 (9 dragon + 17 larva, 4 compartilhados) |
| Item IDs únicos | ~152 |
| Itens com animação | 6 (18609–18614, apenas larva-ankrah) |
| Sprites sem metadados (missing) | 0 |
| Pattern mais comum | 1×1×1 (~70% dos itens) |
| Flag mais comum | `unmove` (presente em ~98% dos itens de mapa) |
| Itens de clip (border) | ~53 (dragon) + ~40 (larva) |
| Itens de bottom | ~33 (dragon) + ~30 (larva) |
| Itens de object | ~8 (dragon) + ~14 (larva) |
| Itens de roof | 0 nestes mapas (classificação atual) |
| Itens de top | 0 nestes mapas |

---

## 10. Árvore de Decisão Final — `classify_layer()`

```
ITEM recebido do OTBM
    │
    ├─ É tileid (campo "tileid" do tile)?
    │   └─ SIM → ground (tilelayer) ── SEMPRE, independente das flags
    │
    └─ É item (campo "items[].id" do tile)?
        │
        ├─ flags.top = true?
        │   └─ SIM → "top" (depthOffset: 50)
        │
        ├─ flags.clip = true?
        │   └─ SIM → "border" (depthOffset: 1)
        │
        ├─ flags.unpass + unmove + unsight = true?
        │   └─ SIM → "roof" (depthOffset: 100)
        │
        ├─ flags.bottom = true?
        │   └─ SIM → "bottom" (depthOffset: 5)
        │
        └─ nenhuma das anteriores
            └─ "object" (depthOffset: 10)
```

**Notas importantes:**
1. A ordem importa: `top` tem prioridade sobre `clip`, que tem prioridade sobre `roof`
2. Um item com `bottom + unpass + unmove + unsight` vai para "bottom" (não "roof") porque `bottom` é checado via a precedência adequada — `bottom` items com essas flags extras são paredes/pilões que renderizam na base
3. Items de ground multi-tile (4×4, pattern 16 sprites) possuem `random: true` pois têm múltiplas sprites → o renderer deve selecionar via hash determinístico
4. `unmove` sozinho NÃO determina camada — quase todo item de mapa é `unmove`

---

## 11. Effects (categoria `effect`)

Além de `object`/`outfit`, o pipeline passou a extrair a categoria **`effect`**
do protobuf (`APPEARANCE_EFFECT = 3`, fonte `extractor/effects.aec`). São os
magic effects do cliente — o que o servidor dispara por `CONST_ME_*`.

**Escopo por ora: só o efeito de teleport.** A extração grava a categoria
inteira em `sprites/effects/` (169 effects, 2240 PNGs), mas o único que vira
atlas é o **id 11 — `CONST_ME_TELEPORT`**, o redemoinho usado quando algo é
teleportado e, no jogo, o efeito de nascimento de monstro. Extração genérica
de todos os magic effects não está no escopo — quando o jogo precisar de
outro, basta somar o id em `ATLAS_EFFECT_IDS` (`bake_effect_atlas.py`) e o
mesmo atlas cresce.

### Como rodar

```
python extractor/scripts/extract_sprites.py --group effects
python extractor/scripts/bake_effect_atlas.py
```

`--group` é opcional e existe justamente pra extrair effects sem reparsear os
130MB de `outfits.aec`; sem a flag, `ENABLED_GROUPS` (`outfits` + `effects`)
roda inteiro. A extração continua idempotente — PNG/JSON já existente não é
regravado.

### Forma de um effect

Todo effect mantém `patternWidth = patternHeight = patternDepth = layers = 1`
— sem direções, addons ou camadas —, então cai no mesmo ramo de "variações /
animação" que um item animado já usa. A lista `spriteId` é, portanto,
exatamente a ordem das fases da animação.

O JSON de `sprites/effects/11/11.json`:

| Campo | Valor |
|-------|-------|
| `spriteId` | `11_0` … `11_10` (11 frames) |
| `spriteInfo.animation.spritePhase[]` | 11 fases, `durationMin`/`durationMax` = 70ms |
| `spriteInfo.animation.loopType` | `ANIMATION_LOOP_TYPE_COUNTED` (toca uma vez, não repete) |
| `frameGroup` | `initial` |
| `flags.light` | `{ brightness: 3, color: 173 }` — o efeito tem luz própria |

Tamanhos de sprite na categoria: 32×32 (902), 64×64 (1147), 32×64 (126) e
64×32 (65). O efeito 11 é 32×32 em todos os frames.

### Atlas

`bake_effect_atlas.py` é a versão simplificada de `bake_item_atlas.py` —
mesmo empacotamento em linha única, mesmo formato `{frames, meta}`, sem o
classificador `is_equipment_candidate` (as flags de mercado/vestível que ele
lê não existem num effect).

| | |
|---|---|
| Saída | `atlases/effects/effects.png` + `atlases/effects/effects.json` |
| Chaves de frame | `11_0` … `11_10`, na ordem da animação |
| Tamanho | 374×34px (11 células de 32×32 + 1px de padding por lado) |

O atlas carrega só a geometria dos frames, igual aos de item/outfit — a
duração e o `loopType` ficam no JSON extraído (`sprites/effects/11/11.json`),
que é a fonte pra quem for tocar a animação.

Um atlas com a categoria inteira não foi feito de propósito: 2240 frames de
até 64×64 dariam ~3100×3100px, acima dos 2048×2048 que os sheets de item/mapa
respeitam como limite seguro de textura.

---

## 12. Corpses (cadáveres de monstro)

Quando um monstro morre o jogo larga o corpo na tile e ele apodrece por uma
cadeia de estágios (`monster-loot.json` → `<Monstro>.corpse`). O
`CorpseSprite` não desenhava nada porque **um item de cadáver não tem sheet
em lugar nenhum do pipeline**:

- **sheets do `map.json`** só carregam as `appearances` que o mapa
  efetivamente põe numa tile, e um corpse nunca está *na* tile do OTBM — ele
  nasce em runtime. Medido: a interseção entre os itemIds de corpse e as
  `appearances` dos 21 `map.json` é **zero**.
- **`items-static` / `items-animated`** são o catálogo de mercado, e
  `is_equipment_candidate` (`bake_item_atlas.py`) rejeita a flag `corpse` de
  propósito.

Daí o atlas próprio, `bake_corpse_atlas.py`.

### Como rodar

```
node extractor/scripts/build_map.js <pasta-do-mapa>     # gera monsters/respawn.json
python extractor/scripts/extract_sprites.py             # gera sprites/items/<id>.png
python extractor/scripts/bake_corpse_atlas.py
```

### Escopo: só os monstros que os mapas construídos spawnam

`monster-loot.json` tem **1391 monstros com cadeia de corpse, 2688 itemIds
distintos** (2667 com PNG extraído — 21 nem existem no `items.xml`). Numa
célula de 66px isso é uma grade de 31 colunas × 87 linhas = **2046×5742px**, e
mesmo um empacotamento perfeito por tamanho precisaria de ~7,35M px² contra os
~4,19M que uma textura 2048×2048 comporta: **o conjunto completo não cabe em
uma textura**.

O critério, então, é o mesmo espírito de `ATLAS_EFFECT_IDS`, mas derivado em
vez de escrito à mão: entram os monstros que aparecem em `monsterDefs` de
`ready-maps*/<CIDADE>/<pasta>/monsters/respawn.json` — os mesmos arquivos que
`build_hunt_fragment.py` lê. Hoje são **16 monstros / 63 itemIds**, e o atlas
cresce sozinho quando um mapa com monstro novo é construído; não há lista para
manter.

De cada monstro entra o itemId do corpo **e o de cada estágio da cadeia** — um
tique de decay que caísse num estágio sem textura apagaria o corpo no meio do
apodrecimento. Estágio sem PNG extraído é pulado com aviso, não quebra o bake.

### Atlas

Diferente de `bake_effect_atlas.py`/`bake_item_atlas.py`, o empacotamento é em
**grade**, não em linha única: 63 frames de até 64×64 numa linha dariam 4158px,
já acima do limite. O modelo é o de `bake_item_sheets.py` (colunas fixas,
row-major, sem bin-packing), só que a célula é dimensionada pelo maior sprite
do conjunto em vez de um 32 fixo — corpses vêm em 32×32 (48), 64×32 (8),
32×64 (3) e 64×64 (4). Ordem de frame, padding e o formato `{frames, meta}`
são os helpers compartilhados de `bake_item_atlas.py`, importados em vez de
copiados, igual os dois bakers de sheet de item já fazem.

| | |
|---|---|
| Saída | `atlases/corpses/corpses.png` + `atlases/corpses/corpses.json` |
| Chaves de frame | o **itemId** em string (`"5964"`, `"3994"`, …) |
| Tamanho | 2046×198px (31 colunas × 3 linhas de células 66×66), ~70KB |

A chave é o itemId, e não o `spriteId` do sprite, porque é o itemId que o
cliente já tem em mãos (`MonsterCorpse.stages[i].itemId`). Um corpse carrega
exatamente um `spriteId` (verificado nos 2667 extraídos), então não há frame
para desambiguar. A cadeia de um monstro fica contígua na grade — a do Rat,
por exemplo, é `5964` → `3994` → `3995` → `3996`.

---

## 13. Pools (poças de fluido)

Combate deixa poça no chão, e a poça apodrece igual um cadáver. Mesmo buraco
da seção 12, um passo adiante: um splash nasce em runtime, nunca está numa
tile do OTBM (nenhuma sheet de `map.json` o carrega) e `is_equipment_candidate`
também o rejeita — item `liquidpool` não tem `market`, `clothes` nem `take`,
só `bottom`/`unmove`. Daí o atlas próprio, `bake_pool_atlas.py`.

### O que o servidor spawna (conferido no Canary 3.2.1)

- **hit**: só em dano **físico**, com `ITEM_SMALLSPLASH = 2889`
  (`Game::combatGetTypeInfo`, `src/game/game.cpp:6957`);
- **morte**: `ITEM_FULLSPLASH = 2886` (`Creature::dropCorpse`,
  `src/creatures/creature.cpp:668`);
- **decay** (`data/items/items.xml`), uma cadeia por origem:

| Origem | Cadeia | Durações |
|---|---|---|
| hit | 2889 → 2890 → 2891 → some | 45s, 45s, 60s |
| morte | 2886 → 2887 → 2888 → some | 45s, 45s, 600s |

Uma poça por tile: uma nova **remove** a antiga
(`src/items/tile.cpp:1063`) — mesma regra que o `CorpseSprite` já aplica.

### Qual fluido: a `race` do monstro

| `race` | Fluido | Variante |
|---|---|---|
| `blood` (885 monstros) | sangue | **2** — RGB(255,13,13) |
| `venom` (250) | slime | **4** — RGB(45,229,39) |
| `ink` (10) | ink | **8** — RGB(39,39,39) |
| `undead` (415), `fire` (73), `energy` (2) | nenhuma poça (só efeito visual) | — |

A aparência de um splash é um grid de pattern **4×3 = 12 células**, uma por
cor de fluido que o cliente conhece. Os três índices acima foram confirmados
por inspeção de pixel; as outras 9 células nunca custam um frame porque
nenhuma raça as pede.

### Como rodar

```
python extractor/scripts/extract_sprites.py             # gera sprites/items/<id>/
python extractor/scripts/bake_pool_atlas.py
```

### Atlas

6 itens × 3 fluidos = **18 frames de 32×32**, então o empacotamento volta a
ser em **linha única** (`bia.pack_item_frames`, 612px) em vez da grade que a
seção 12 precisou para 63 frames de até 64×64. Ordem, padding e o formato
`{frames, meta}` continuam sendo os helpers de `bake_item_atlas.py`,
importados em vez de copiados.

| | |
|---|---|
| Saída | `atlases/pools/pools.png` + `atlases/pools/pools.json` |
| Chaves de frame | `"<itemId>_<variante>"` (`"2889_2"`, `"2886_8"`, …) |
| Tamanho | 612×34px (18 células de 34×34 numa linha), ~4KB |

A chave carrega os dois pedaços porque **nenhum sozinho basta**: o itemId vem
do estágio de decay, a variante vem da raça do monstro que sangrou. Ela
coincide com o nome do PNG extraído — `extract_sprites.py` nomeia cada célula
do pattern como `<itemId>_<índice>` —, então o `spriteId` do JSON do item
serve de validação: variante que a aparência não declara é pulada com aviso,
igual um PNG faltando, sem quebrar o bake.

Os 18 frames, na ordem em que ficam no atlas (fluido a fluido, e dentro dele
as duas cadeias na ordem do decay — a sequência que o cliente percorre):

```
2886_2 2887_2 2888_2 2889_2 2890_2 2891_2   (sangue)
2886_4 2887_4 2888_4 2889_4 2890_4 2891_4   (venom/slime)
2886_8 2887_8 2888_8 2889_8 2890_8 2891_8   (ink)
```
