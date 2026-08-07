# 02 — Medir divergência de ground sintetizado por borda

**What to build:** Uma resposta em número para a pergunta "precisamos dos dados de autoria do editor
de mapas para montar a pilha de tile igual a ele?". O editor tem um mecanismo em que certas bordas
sintetizam um chão embaixo de si e se inserem no fundo da pilha; esse dado não vem das flags do
appearances, vem dos arquivos de autoria dele. Este ticket traz esses arquivos para o repositório e
mede em quantas tiles dos mapas existentes o chão sintetizado difere do que já está gravado no OTBM.

Se a divergência for zero, o mecanismo é descartado do escopo e os tickets seguintes ignoram o
assunto. Se não for, este ticket documenta o tamanho do problema para que o 03 decida o que fazer.

**Blocked by:** None — can start immediately.

**Status:** resolved

- [x] Os arquivos de autoria do editor estão versionados no repositório, com a licença de origem
      verificada e registrada
- [x] Existe um relatório com a contagem, por mapa, de tiles em que uma borda declara chão
      sintetizado
- [x] Para cada uma dessas tiles, o relatório diz se o chão sintetizado coincide ou não com o chão
      já gravado no OTBM
- [x] O relatório termina com uma recomendação explícita: ignorar o mecanismo, ou tratá-lo no 03

## Answer

**Divergência: zero. O mecanismo sai do escopo.**

Relatório completo em [`reports/02-ground-equivalent.md`](../reports/02-ground-equivalent.md),
regerável por `python extractor/scripts/ground_equivalent_report.py --out <caminho>`.

- **Arquivos vendorizados:** `extractor/vendor/rme-materials/` — `grounds.xml` e `borders.xml`
  byte a byte como no upstream (`opentibiabr/remeres-map-editor@main`), mais o `LICENSE.rtf` e um
  `NOTICE.md` com origem, sha256 e a leitura da licença. O RME **não** é GPL/MIT: é uma EULA de
  freeware cuja cláusula 2 autoriza redistribuir cópias **não modificadas** desde que a própria EULA
  as acompanhe — daí os arquivos entrarem intocados (o `&` cru de `grounds.xml` é corrigido só em
  memória, na leitura).
- **A medida:** `ground_equivalent` aparece em 3 elementos `<border>` (brushes `sand` e `sandstone`),
  cobrindo 24 ids. Nos 42 dumps de `raw-maps/`, esses ids tocam **62 tiles, todas no mapa da cidade
  inteira** (`ROOK`/`rook-full` — os 20 mapas de hunt não têm nenhuma). Em **todas as 62** a borda
  está no próprio slot de chão do OTBM (`tileid`), nunca empilhada como item. Nada é sintetizado,
  nada diverge.
- **Por que não é sorte do conjunto de mapas:** os 24 ids carregam a flag `bank` — são chão. O
  `ground_equivalent` é busca inversa de autoria ("a que brush pertence este chão, para eu
  recalcular as bordas ao redor"), não regra de empilhamento.
- **Controle:** assumir que os 8 ids de troca dos blocos `<specific>` herdam o `ground_equivalent`
  do `<border>` que os hospeda produziria 1880 "divergências" — artefato puro: nenhum desses 8
  carrega `bank` (são `clip`), então ficam legitimamente **sobre** um chão gravado.

**Consequência para o 03:** monta a pilha só com as flags do `appearances.dat` (`bank` → draw slot,
`clip`/`bottom`/`top` → `top order`). Nenhum script de build lê `extractor/vendor/rme-materials/`;
os arquivos ficam como evidência desta medição.
