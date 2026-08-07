# 06 — Emitir deslocamento e elevação por aparência

**What to build:** Duas propriedades de posicionamento que já são extraídas do cliente e hoje não
chegam a lugar nenhum passam a sair no formato novo, prontas para o render consumir:

- **deslocamento** — um offset em pixels do próprio sprite, que não acumula
- **elevação** — um offset que um item aplica aos itens desenhados **depois** dele na mesma tile, e
  que portanto acumula ao longo da pilha

São elas que fazem uma pilha de objetos parecer pilha e que colocam objetos pequenos no lugar certo
dentro do quadrado. Hoje o arquivo que as carrega é gerado, copiado para o front e lido por
ninguém — este ticket fecha esse caminho morto.

**Blocked by:** 04

**Status:** resolved

- [x] As duas propriedades saem no formato novo, por aparência, e só quando diferentes de zero
- [x] Uma aparência conhecida por ter cada uma delas é usada como caso de teste
- [x] O arquivo de metadados que hoje é gerado e não lido é removido ou passa a ter consumidor
      declarado

## Answer

`analyze_item` passa a extrair as duas da metadata (`flags.shift` → `{x, y}`, `flags.height.elevation`
→ inteiro) e o v6 as emite por aparência, **só quando diferentes de zero**. No conjunto atual isso é
42 aparências com `shift` e 129 com `elevation` — o filtro não é decorativo: há 2 `shift` e 4
`elevation` gravados como zero na metadata do cliente.

Casos de teste com aparências reais: 10035 (`shift {x: 8, y: 8}`) e 10033 (`elevation: 8`), mais o
caso de um eixo só (`{x: 0, y: 8}` sai inteiro) e o de zero (não sai).

Como o render consome as duas está no pseudocódigo de
[`extractor/MAP_JSON_V6.md`](../../../extractor/MAP_JSON_V6.md) — `shift` desloca só o próprio
sprite, `elevation` acumula ao longo da pilha.

**Sobre o `metadata.json`:** ele **não** é o caminho morto que o ticket supunha — tem consumidor
declarado fora deste repositório, confirmado pelo dono do projeto, e por isso continua sendo gerado
no v5 sem alteração. O v6 não o gera: as propriedades que o render precisa saem no próprio mapa.
