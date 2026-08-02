# Spec: Sprites de Item (Atlas Animado + Sheets Estáticas)

Status: ready-for-agent

## Problem Statement

O jogo precisa exibir ícones de item (equipamento e consumível — espadas, armaduras, poções,
runas, etc.) em inventário, loot de monstro (já existe `monster-loot.json`, referenciando itens só
por `itemId` numérico, sem nenhuma informação de sprite) e, futuramente, market. Hoje **não existe
nenhum asset de sprite de item consumível pelo cliente** — os PNGs brutos extraídos em
`extractor/sprites/items/` são um-arquivo-por-frame (até 12+ frames por item animado) e cobrem
**todos** os ~38.6k appearance IDs de item do jogo, incluindo cenário de mapa que não interessa
aqui (paredes, chão, bordas — já tratados por um pipeline totalmente separado, ver
`SPRITE_METADATA.md` e o spec `map-sprite-sheets-v4`).

Baixar um PNG por frame por item, para os milhares de itens de equipamento/consumível do jogo,
reproduziria exatamente o mesmo problema de "muitas requisições pequenas" que já motivou o atlas de
outfit (ver `.scratch/outfit-sprite-atlas/spec.md`) e as sheets de mapa (ver
`.scratch/map-sprite-sheets-v4/spec.md`) — na escala de itens, pior ainda: 5.891 itens candidatos
identificados na extração atual.

## Solution

Dois mecanismos de empacotamento, escolhidos por tipo de item, ambos já implementados e rodados
contra os dados reais neste repositório (extractor):

1. **Itens animados** (808 no dado real) → um atlas Phaser "JSON Hash" por item (mesmo contrato já
   validado no atlas de outfit), em `extractor/atlases/items/<id>.png` + `<id>.json`.
2. **Itens estáticos** (5.083 no dado real, sem animação) → consolidados em **4 sheets em grid**
   compartilhadas, em `extractor/atlases/items-static/items-static-{0,1,2,3}.png` + `.json`.

Ambos os mecanismos só cobrem itens que passam por uma classificação de
equipamento/consumível (ver seção 3) — cenário de mapa nunca entra aqui.

**Isto é só o lado da extração/empacotamento.** O consumo real (Phaser `load.atlas`/
`load.spritesheet`, renderização de inventário/loot/market) vive no repositório separado
`tibia-idle`, que não está acessível nesta sessão — este spec documenta o contrato que aquele
repositório precisa implementar.

## Contrato de Dados

### 1. Classificação — quais itens têm sprite gerado

Implementada em `extractor/scripts/bake_item_atlas.py` (`is_equipment_candidate`). Um item entra se
qualquer uma das três condições bater (checadas nesta ordem de prioridade, mas o resultado é um OR,
não hierárquico):

| Critério | Sinal (`flags`) | Itens no dado real |
|---|---|---|
| `is_market_item` | `flags.market` presente | 4.564 |
| `is_wearable_without_market` | `flags.clothes` presente **e** sem `flags.market` (equipáveis de quest/evento, geralmente com `expire`/`wearout`) | 479 |
| `is_portable_consumable_without_market` | `flags.usable` **e** `flags.take`, sem `flags.market` **e** sem nenhuma flag de cenário (`corpse`, `container`, `unpass`, `bottom`, `top`, `automap`, `hang`, `lying_object`) | 848 |

Total: **5.891 itens**. As flags de cenário no terceiro critério existem porque `usable+take`
sozinho pega ~7.476 itens no dado bruto, dominado por falsos positivos (corpos de monstro,
containers do mundo, alavancas/portas marcadas `take`) — excluir quem carrega qualquer flag de
cenário é o que separa os ~848 consumíveis reais do resto.

Itens que não batem em nenhum critério (cenário de mapa: paredes, chão, bordas, decoração fixa) não
têm asset nenhum gerado por este pipeline.

### 2. Atlas por item (animados)

- Local: `extractor/atlases/items/<itemId>.png` + `extractor/atlases/items/<itemId>.json`
- Um arquivo por item animado (808 arquivos de imagem).
- Formato JSON ("JSON Hash" do Phaser, consumível direto via `scene.load.atlas(itemId, pngPath, jsonPath)`):
  ```json
  {
    "frames": {
      "3555_0":  { "frame": { "x": 1,   "y": 1, "w": 32, "h": 32 } },
      "3555_1":  { "frame": { "x": 35,  "y": 1, "w": 32, "h": 32 } }
    },
    "meta": { "image": "3555.png", "size": { "w": 408, "h": 34 } }
  }
  ```
- Chave de frame = exatamente a string `spriteId` já usada nos dados extraídos brutos
  (`extractor/sprites/items/<id>/<id>_<n>.png`) — mesma convenção usada no atlas de outfit.
- 1px de padding transparente entre frames (evita bleeding ao escalar/filtrar a textura).
- Duração de cada frame vem de `spriteInfo.animation.spritePhase[i].durationMin` (em ms) no JSON
  bruto de `extractor/sprites/items/<id>/<id>.json` — **não replicada no atlas gerado**, o cliente
  precisa ler essa informação do JSON bruto de metadados, não do atlas. `loopType` também vem de
  lá (`ANIMATION_LOOP_TYPE_INFINITE`/`_PINGPONG`/`_COUNTED`).

### 3. Sheets estáticas (compartilhadas)

- Local: `extractor/atlases/items-static/items-static-{0,1,2,3}.png` + `.json` (4 arquivos de cada).
- Mesmo formato "JSON Hash" da seção anterior, mas cada JSON descreve **centenas de itens
  diferentes** compartilhando uma única imagem:
  ```json
  {
    "frames": {
      "49094":   { "frame": { "x": 640, "y": 96, "w": 32, "h": 32 } },
      "130_0":   { "frame": { "x": 672, "y": 96, "w": 32, "h": 32 } }
    },
    "meta": { "image": "items-static-0.png", "size": { "w": 1024, "h": 1632 } }
  }
  ```
- Chave de frame: `<itemId>` para item de célula única, `<itemId>_<n>` para item multi-célula
  (mesma convenção de chave usada em todo o resto do pipeline).
- Dimensões reais geradas: ~1024×1632px por sheet, ~1-1.3MB cada, **sem padding entre células**
  (mesma decisão já tomada nas sheets de mapa — os ícones já carregam margem transparente própria
  dentro da célula 32×32).
- Split determinístico em 4 arquivos por contagem de célula acumulada (itens ordenados por ID);
  nenhum item multi-célula é cortado entre dois arquivos.
- Todas as dimensões ficam bem abaixo de 2048×2048 — o mínimo garantido em qualquer dispositivo
  WebGL — então nenhum device deveria ter problema pra alocar a textura.

### 4. Casos multi-célula (edge case de item, não de mapa)

~240 itens estáticos e ~21 animados usam mais de uma célula por causa de `patternWidth`/
`patternHeight` > 1 (ex.: item 9058, produto de criatura, 4×2 células × 13 frames = 104 sprites).
Verificado empiricamente contra o dado real (comparação de hash de PNG) que essas células vêm em
blocos contíguos por frame de animação na ordem original de `spriteId` — o pipeline **empacota
essa ordem verbatim, sem interpretar o que cada célula extra significa** (tier de contagem
empilhada, variante de direção de gancho, etc. — mesma filosofia "preserva tudo, cliente decide"
já usada pro atlas de outfit). Isso importa **só** pras categorias
DECORATION/OTHERS/CREATURE_PRODUCTS/CONTAINERS — toda categoria de equipamento de fato
(SWORDS/POTIONS/ARMORS/AXES/etc.) é 100% célula única (32×32) no dado real.

Se o cliente algum dia precisar renderizar a célula "certa" de um item multi-célula (não só a
primeira), o significado de cada eixo ainda não está documentado e precisa de investigação
própria — fora do escopo deste spec.

## Gap conhecido — falta um índice `itemId → localização do sprite`

**Nenhum arquivo hoje mapeia `itemId → {atlas individual ou sheet estática + frame}`.** Um item
animado está em `atlases/items/<id>.json`; um item estático está em **uma das 4** sheets, e não há
como saber qual sem abrir os 4 JSONs e procurar a chave. `monster-loot.json` já referencia itens
só por `itemId` numérico — para renderizar o ícone de um loot, o cliente precisa resolver essa
localização primeiro.

Antes de implementar o consumo no client, alguém precisa gerar (no extractor, junto do resto deste
pipeline) um índice único e pequeno, por exemplo:

```json
{
  "3555":  { "kind": "atlas",       "file": "items/3555.json" },
  "49094": { "kind": "static-sheet", "file": "items-static/items-static-2.json", "key": "49094" }
}
```

Isso não foi implementado ainda — é o próximo passo natural antes (ou junto) da implementação no
`tibia-idle`, e fica registrado aqui como decisão em aberto, não como parte já pronta do contrato.

**Atualização:** desenhado em `issues/01-item-sprite-index.md`. `issues/02-wire-item-baking-into-pipeline.md`
cobre o passo seguinte (bake de item deixar de ser um passo manual lembrado à parte). O consumo no
`tibia-idle` (refatorar `ItemSprite`, gerar uma diretiva de renderização por item, sincronizar
`items-broad.generated.ts`) está desenhado em `.scratch/item-render-pipeline/spec.md` naquele
repositório.

## Testing Decisions

- Já implementado e testado no lado da extração: `extractor/tests/test_bake_item_atlas.py` (28
  casos — empacotamento, os três critérios de classificação isolados e combinados, item
  single-frame, item animado, item multi-célula) e `extractor/tests/test_bake_item_sheets.py` (11
  casos — balanceamento entre shards, item multi-célula nunca cortado entre shards, wrap de linha,
  determinismo, exclusão correta de animados/cenário).
- Do lado do cliente (`tibia-idle`, fora desta sessão): mesmo padrão já usado pro atlas de outfit —
  carregar pelo menos um atlas de item animado e uma sheet estática reais gerados aqui e confirmar
  visualmente que os frames batem com o ícone esperado antes de confiar no pipeline.

## Out of Scope

- O índice `itemId → localização` descrito acima (gap conhecido, não implementado).
- Qualquer mudança de código no cliente Phaser/TypeScript (`load.atlas`/`load.spritesheet`,
  renderização de inventário/loot/market) — vive no repositório `tibia-idle`.
- Interpretar o significado de células extras em itens multi-célula (stack-count, direção de
  gancho) além de preservá-las endereçáveis.
- Estender a classificação de equipamento/consumível além dos três critérios já implementados
  (ex.: heurísticas adicionais para pegar itens ainda perdidos na classificação atual).
- Categorias de item com 0-1 ocorrência no dado real (`ITEM_CATEGORY_PREMIUM_SCROLLS`,
  `ITEM_CATEGORY_TIBIA_COINS`) não receberam tratamento especial — passam pelas mesmas regras dos
  demais.

## Further Notes

- Prior art direto, mesmo padrão de contrato ("JSON Hash" do Phaser, chave de frame = spriteId
  original, 1px de padding em atlas individual): `.scratch/outfit-sprite-atlas/spec.md` e o código
  em `extractor/scripts/bake_outfit_atlas.py`.
- Prior art direto pro modelo de sheet em grid (colunas fixas, sem bin-packing, split por conta de
  limite de tamanho de textura): `.scratch/map-sprite-sheets-v4/spec.md` e
  `extractor/scripts/sheet_packer.py` — a sheet estática de item **não reusa** a classe
  `SheetPacker` de lá porque aquele empacotador bucketiza por tamanho de sprite (necessário pra
  cenário de mapa, que mistura 32/64/128px); todo ícone de item de equipamento é uniformemente
  32×32, então a única variável livre aqui é em qual dos 4 arquivos cada item cai, não o bucket de
  tamanho.
- Números completos de classificação por categoria (quantos itens estáticos por
  `ITEM_CATEGORY_*`, incluindo os dois buckets sem market) estão só no histórico da sessão que
  gerou este spec — não persistidos em nenhum arquivo do repositório. Se precisar reproduzir,
  `extractor/scripts/bake_item_atlas.py` e `bake_item_sheets.py` são determinísticos e podem ser
  rodados de novo a qualquer momento contra `extractor/sprites/items/`.
