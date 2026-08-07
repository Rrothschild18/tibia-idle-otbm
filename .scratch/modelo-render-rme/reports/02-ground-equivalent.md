# 02 — Divergência de ground sintetizado por borda

Gerado por `extractor/scripts/ground_equivalent_report.py` a partir de
`extractor/vendor/rme-materials/grounds.xml` e de todos os
`extractor/raw-maps/*.raw.json`. Para regerar:

```
python extractor/scripts/ground_equivalent_report.py \
  --out .scratch/modelo-render-rme/reports/02-ground-equivalent.md
```

## O mecanismo

No `grounds.xml` do editor, `ground_equivalent` aparece em **3 elementos `<border>`**, nos
brushes `sand` e `sandstone`, cobrindo **24 ids de borda**.

## Medição estrita — os `<borderitem>` do `<border ground_equivalent>`

| mapa | tiles com borda declarante | coincide com o OTBM | diverge |
|---|---:|---:|---:|
| `ROOK` | 31 | 31 | 0 |
| `rook-full` | 31 | 31 | 0 |
| **total** | **62** | **62** | **0** |

Sem nenhuma tile tocada: 40 mapas.

**Divergência: 0.**

Das 62 tiles tocadas, **62 têm a borda no
próprio slot de chão do OTBM (`tileid`) e 0 a têm como item empilhado**.

Isso não é acidente do conjunto de mapas: **24 dos 24 ids** carregam a
flag `bank` no `appearances.dat` — ou seja, o editor não coloca um chão *por baixo* da borda,
a borda **é** o chão. `ground_equivalent` é uma busca inversa de autoria ("a que brush este
chão pertence, para eu recalcular as bordas ao redor"), não uma regra de empilhamento.

## Medição ampla (controle) — mais os alvos de `<specific>`/`<replace_item>`

Os blocos `<specific>` dentro dos mesmos `<border>` trocam uma borda por outra, somando
**8 ids** que nunca aparecem como `<borderitem>`. Assumir que essa troca herda o
`ground_equivalent` do `<border>` que a hospeda produziria:

| mapa | tiles com borda declarante | coincide com o OTBM | diverge |
|---|---:|---:|---:|
| `ROOK-HUNT-0001_rats-sewers-2-rookguard` | 28 | 0 | 28 |
| `ROOK-HUNT-0002_rats-sewers` | 7 | 0 | 7 |
| `ROOK-HUNT-0003_troll-rookguard` | 45 | 0 | 45 |
| `ROOK-HUNT-0004_skeletons-rookguard` | 9 | 0 | 9 |
| `ROOK-HUNT-0010_bears-rookguard` | 24 | 0 | 24 |
| `ROOK-HUNT-0013_rats-rookguard` | 7 | 0 | 7 |
| `ROOK-HUNT-0015_trolls-tower-rookguard` | 17 | 0 | 17 |
| `ROOK-HUNT-0016_wolfs-east-rookguard` | 17 | 0 | 17 |
| `ROOK-HUNT-0017_wolfs-south-rookguard` | 66 | 0 | 66 |
| `ROOK-HUNT-0018_bugs-rookguard` | 17 | 0 | 17 |
| `ROOK` | 734 | 31 | 703 |
| `bears-rookguard` | 24 | 0 | 24 |
| `bugs-rookguard` | 17 | 0 | 17 |
| `rats-rookguard` | 7 | 0 | 7 |
| `rats-sewers-2-rookguard` | 28 | 0 | 28 |
| `rats-sewers` | 7 | 0 | 7 |
| `rook-full` | 734 | 31 | 703 |
| `skeletons-rookguard` | 9 | 0 | 9 |
| `troll-rookguard` | 45 | 0 | 45 |
| `trolls-tower-rookguard` | 17 | 0 | 17 |
| `wolfs-east-rookguard` | 17 | 0 | 17 |
| `wolfs-south-rookguard` | 66 | 0 | 66 |
| **total** | **1942** | **62** | **1880** |

Sem nenhuma tile tocada: 20 mapas.

**1880 divergências — todas artefato da assunção.**
Nenhum dos 8 ids de troca carrega a flag `bank`: são itens `clip`
(borda de fundo) que legitimamente ficam **sobre** um chão gravado. Herdar o
`ground_equivalent` para eles inventaria um chão que o editor nunca coloca.

## Recomendação

**Ignorar o mecanismo.** A divergência real é **zero**: onde o editor considera a borda um
chão, o OTBM já grava exatamente essa borda no slot de chão da tile. Não há nada a sintetizar,
e o ticket 03 pode montar a pilha só com as flags do `appearances.dat` — `bank` para o draw
slot, `clip`/`bottom`/`top` para o `top order` — sem consultar arquivo de autoria nenhum.

Os arquivos vendorizados ficam no repo como evidência desta medição, não como entrada do
pipeline: nenhum script de build lê `extractor/vendor/rme-materials/`.
