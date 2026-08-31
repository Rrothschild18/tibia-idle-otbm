Status: **especificada em 2026-08-30**, não implementada. Sai de uma sessão de
`/grilling` disparada pela pergunta "como o respawn de monstros diverge do
Canary, e dá pra adicionar corpse + envelhecimento?". A contraparte de consumo
(client/game-logic) está especificada em paralelo no repo `tibia-idle`, mesmo
slug: `.scratch/monstro-respawn-e-corpse/spec.md`.

# Extração de sprite de efeito e de dado de corpse/decay por monstro

## Problem Statement

O jogo (`tibia-idle`) quer três coisas que o pipeline de extração hoje não
fornece:

1. Um **efeito visual de nascimento** quando um monstro respawna.
2. Um **corpse cosmético** no tile onde o monstro morreu.
3. **Decay em estágios** desse corpse ao longo do tempo (fresco → podre →
   ossos → some), igual ao Tibia real.

Nenhum dos três dados-fonte está no repo hoje:

- **Efeito de nascimento**: o efeito identificado como o correto — `CONST_ME_TELEPORT`
  (id 11 no enum `MagicEffectClasses` do TFS/Canary, confirmado contra a wiki de
  constantes do `forgottenserver` — é o redemoinho usado quando algo é
  teleportado) — tem sua categoria já mapeada no `Appearances.proto`
  (`APPEARANCE_EFFECT = 3`, `Appearances.proto:5-11,342-347`) e o arquivo-fonte
  `extractor/effects.aec` **já existe no repo e já contém PNGs embutidos**
  (confirmado por inspeção binária — headers `PNG` reais dentro do `.aec`). Mas
  `extract_sprites.py:16-25` só roda `ENABLED_GROUPS = ["outfits"]` — nenhum
  sprite de effect foi extraído ainda, e não existe atlas de effects em
  `extractor/atlases/` nem em `extractor/full-maps/ROOK/`.
- **Corpse por monstro**: nenhum XML/JSON do repo associa monstro → item de
  corpse. `otservbr-monster.xml` é só um índice de bestiário (`looktype`/
  `lookitem`, sem corpse). Os `*-monster.xml` de spawn (`extractor/maps/**`,
  `extractor/full-maps/ROOK/ROOK-monster.xml`) são posição/nome/`spawntime`, não
  atributo de criatura. O dado real (`monster.corpse = N`) só existe fora do
  repo, no Lua de cada monstro em `C:\canary-3.2.1\data-otservbr-global\monster\**\*.lua`
  — a mesma fonte que `build_monster_loot_index.py` já lê hoje pra loot.
- **Cadeia de decay**: `decayTo`/`duration` por item também só existe fora do
  repo, em `C:\canary-3.2.1\data\items\items.xml`, como
  `<attribute key="decayTo" value="N"/>` / `<attribute key="duration" value="segundos"/>`
  dentro de cada `<item>`. `monster_loot.py:load_items_index()` já faz
  `ET.parse` desse arquivo hoje, mas só lê `id`/`name`/`fromid`/`toid` do
  elemento raiz — nunca desce aos `<attribute>` filhos.

## Solution

Duas extensões independentes ao pipeline, cada uma reaproveitando código já
existente — nenhuma das duas exige parser novo do zero.

### Sprite do efeito de teleport

Habilitar `"effects"` em `ENABLED_GROUPS` (`extract_sprites.py:25`) e rodar a
extração — o `.aec` já está no disco, a categoria já é reconhecida pelo proto,
e como `CONST_ME_TELEPORT` (`patternWidth=patternHeight=patternDepth=1`, 11
frames sem loop) não tem layers/patterns/direções, cai direto no mesmo ramo de
"sprite única vs. animação" que `extract_group()` já usa pra itens animados
(`extract_sprites.py:319-488`, especificamente o `else` de variações/animação,
linhas 397-445) — sem diferença estrutural relevante.

Depois, um `bake_effect_atlas.py` novo, cópia simplificada de
`bake_item_atlas.py`: sem o classificador `is_equipment_candidate` (não faz
sentido pra effect — não tem `flags.market/clothes/usable` do mesmo jeito que
item), simplesmente empacota tudo que veio de `effect` num atlas único (a
contagem de effects num client Tibia é pequena, não precisa de filtro).

Escopo desta ticket é **só o efeito 11 (teleport)** — não uma extração
genérica de todos os magic effects do jogo. Se o jogo precisar de outro efeito
depois, o mesmo atlas cresce.

### Corpse + cadeia de decay por monstro

Estender `build_monster_loot_index.py`/`monster_loot.py`, no mesmo ponto que já
itera cada `.lua` de monstro e já tem `name_to_id`/`id_to_name` calculados:

1. **Capturar `monster.corpse`**: um regex novo ao lado do que já existe pra
   nome/loot (`_MONSTER_NAME_RE`, `_LOOT_BLOCK_START_RE` em `monster_loot.py:65-66`),
   aplicado ao mesmo `text` já lido em `parse_monster_loot_lua()`
   (`monster_loot.py:102-135`) — mesma leitura de disco, mais uma extração.
2. **Indexar decay de `items.xml`**: estender `load_items_index()`
   (`monster_loot.py:25-58`) — ou uma função irmã que reaproveita o mesmo
   `ET.parse` — pra também ler, por item, `item.findall("attribute")` e montar
   um índice `id → {decayTo, durationSeconds}` a partir dos `key="decayTo"`/
   `key="duration"`.
3. **Resolver a cadeia**: a partir do `corpse` do monstro, caminhar
   `id → decayTo → decayTo → ...` até `decayTo` ausente ou `0`, montando uma
   lista ordenada de estágios `[{itemId, durationSeconds}, ...]`. Loop
   iterativo simples, com guarda de profundidade máxima (proteção contra ciclo
   malformado no dado de origem — não esperado, mas o parser não deve travar
   se acontecer).
4. **Anexar ao `monster-loot.json`**: uma chave nova por monstro,
   `"corpse": {"itemId": N, "stages": [{"itemId": X, "durationSeconds": Y}, ...]}`,
   ao lado de `loot`/`issues` já existentes (`build_monster_loot()`,
   `monster_loot.py:227-239`). Aditivo — não muda o schema de `loot`/`issues`,
   então nenhum consumidor existente quebra.

## Implementation Decisions

Fechadas na sessão de `/grilling`, com a alternativa recusada.

### Puxar do Canary local, não inventar um esquema genérico

A cadeia real varia muito por monstro — um rato tem 1 estágio de 10s, um
humano tem 5+ estágios — então um esquema fixo (N estágios, mesmos tempos pra
todo mundo) seria menos fiel e ainda exigiria inventar/balancear números à mão.
Como o pipeline já sabe ler do Canary local pra loot, estender a mesma fonte é
o caminho de menor esforço **e** o mais autêntico ao mesmo tempo — não houve
trade-off real entre os dois aqui.

### `monster-loot.json` ganha a chave, não um arquivo novo

Recusada a alternativa de um `monster-corpse.json` separado: seria mais um
arquivo pra manter sincronizado com o mesmo lookup por nome de monstro que já
existe, sem ganho. Uma chave nova em cima do que já é consumido junto (loot +
corpse saem da mesma morte) é a mudança de interface mínima.

### Escopo é só o efeito 11

Recusada a extração genérica de todos os magic effects do client agora: o
pedido concreto é só o efeito de nascimento, e generalizar sem um segundo caso
de uso conhecido é trabalho especulativo. `bake_effect_atlas.py` fica simples
o bastante pra crescer depois sem retrabalho.

## Riscos conhecidos, registrados para não virarem surpresa em code review

- **Casing do atributo em `items.xml`: confirmado por leitura direta em
  2026-08-30.** É `decayTo` (camelCase) e `duration`, ambos dentro de
  `<attribute key="..." value="..."/>`. Conferido ao vivo contra
  `C:\canary-3.2.1\data\items\items.xml` — item 5964 "dead rat"
  (`duration=10`, `decayTo=3994`) e item 4022 "dead dog" (`duration=60`,
  `decayTo=0`) batem exatamente com o que está documentado nesta spec. O
  parser de loot lida com uma pegadinha parecida hoje para
  `minCount`/`mincount` (`monster_loot.py:194-195`) — não é o caso aqui, mas
  vale a mesma atenção se outro atributo aparecer com casing inconsistente
  durante a implementação.
- **`C:\canary-3.2.1` é uma instalação local nesta máquina**, fora do repo e
  fora de controle de versão — mesma dependência que `build_monster_loot_index.py`
  já tem hoje (`DEFAULT_CANARY_DIR`, `build_monster_loot_index.py:20`). Não é
  uma dependência nova introduzida por esta spec, mas cresce a superfície que
  depende dela.

## Out of Scope

- **Consumo do efeito/corpse no jogo** (leash de movimento, tocar o efeito ao
  respawnar, `CorpseSprite`, timers de decay em runtime) — é a spec irmã no
  repo `tibia-idle`, mesmo slug.
- **Extração de outros magic effects** além do 11 (teleport).
- **Loot como container físico no corpse** — decisão de produto já fechada
  (corpse é cosmético, loot continua indo direto pro inventário).

## Tickets

Sem bloqueio entre si — podem sair em paralelo.

| # | o quê | bloqueado por |
|---|---|---|
| [01](./issues/01-extrair-sprite-de-effects.md) | Extrair o sprite do efeito de teleport (id 11) e gerar atlas de effects | Nenhum |
| [02](./issues/02-corpse-e-decay-no-monster-loot.md) | `monster.corpse` + cadeia de decay do Canary local, anexados ao `monster-loot.json` | Nenhum |
