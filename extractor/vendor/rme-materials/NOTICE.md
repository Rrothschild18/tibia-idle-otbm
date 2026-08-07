# Arquivos de autoria do Remere's Map Editor (vendorizados)

Cópias **inalteradas** de dois arquivos de dados do Remere's Map Editor, trazidas para medir o
mecanismo de `ground_equivalent` (ver `.scratch/modelo-render-rme/issues/02-materials-ground-equivalent.md`).

## Origem

| Arquivo | Caminho no upstream | sha256 |
|---|---|---|
| `grounds.xml` | `data/materials/brushs/grounds.xml` | `2b19b90d04377e8df5851efca166619590dd85fdd00f1fc22805a38cc21551f4` |
| `borders.xml` | `data/materials/borders/borders.xml` | `14db288385219c64bf4e14652663fe592b120257ad776ed082cd2d17f41660e3` |
| `LICENSE.rtf` | `LICENSE.rtf` | `fb3a1e8407f1457ce20c167b939731b4e035c9911f23f27fc0cab4116b0f5036` |

- **Upstream:** <https://github.com/opentibiabr/remeres-map-editor>, branch `main`
- **Baixado em:** 2026-08-07
- **Último commit que tocou `grounds.xml` no upstream:** `adef6c47c198c672b1cc04e05b561e465aa008e8` (2021-06-24)

## Licença

O Remere's Map Editor é distribuído sob uma EULA de freeware (não é GPL/MIT) — o texto integral está
em `LICENSE.rtf`, incluído aqui porque a própria cláusula 2 exige que ele acompanhe qualquer cópia.

Os termos relevantes para esta vendorização:

- **Cláusula 1 (Freeware):** uso sem custo.
- **Cláusula 2 (Distribution):** permite fazer e distribuir cópias exatas, **em forma não
  modificada**, por meio eletrônico, sem cobrar nada por elas, desde que uma cópia da EULA acompanhe
  a cópia distribuída.
- **Cláusula 3.1:** proíbe engenharia reversa / descompilação **do programa** — não se aplica a ler
  arquivos de dados XML que o próprio editor publica em texto puro.

Por isso os dois XMLs entram aqui **byte a byte como estão no upstream**: qualquer edição sairia da
"unmodified form" que a cláusula 2 autoriza. Se algum dia for preciso derivar dados deles, o
resultado vai num arquivo separado, gerado, fora desta pasta — nunca por edição no lugar.

## Por que só estes dois arquivos

`ground_equivalent` — o único mecanismo do editor que este esforço precisava medir — só aparece em
`grounds.xml` (3 ocorrências, nos brushes `sand` e `sandstone`). `borders.xml` vem junto porque é
onde moram os conjuntos de borda referenciados por `<border align="..." id="N"/>`, necessários para
ler `grounds.xml` inteiro sem referência pendurada.

O resto da máquina de autoria do editor (doodads, walls, tilesets, paletas) está explicitamente fora
de escopo — ver `.scratch/modelo-render-rme/spec.md`.
