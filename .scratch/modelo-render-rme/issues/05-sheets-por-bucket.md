# 05 — Sheets agrupadas por tamanho de sprite

**What to build:** As folhas de sprite passam a ser agrupadas apenas por footprint do sprite, e não
mais por papel de renderização somado ao footprint. Como o papel de renderização deixa de existir no
ticket 04, a chave de agrupamento precisa mudar de qualquer forma.

O efeito medido nos mapas atuais é cair de nove a doze folhas por mapa para duas, com a maior
resultante bem abaixo do limite de textura garantido por qualquer GPU. Isso reduz requisições de
rede no carregamento e mantém o lote de desenho longo mesmo com a ordem de desenho intercalando
sprites de origens diferentes dentro de uma mesma linha.

O contrato de posicionamento dentro da folha não muda: célula quadrada, preenchimento em linha da
esquerda para a direita, sprite alinhado ao canto superior-esquerdo da célula.

**Blocked by:** 04

**Status:** resolved

- [x] Uma folha é identificada apenas pelo tamanho de célula
- [x] Nenhum mapa existente gera folha cuja maior dimensão ultrapasse o limite seguro de textura
- [x] O mapeamento de índice para posição na folha continua sendo aritmética pura, sem arquivo de
      atlas
- [x] Os testes existentes de empacotamento continuam passando, adaptados à chave nova
- [x] O número de folhas por mapa está registrado antes e depois, para os 20 mapas

## Answer

`SheetPacker.add_appearance(..., layer_class=None)` passa a chavear a folha só pelo bucket de
tamanho (`sheet-32`, `sheet-64`). A chave antiga `(layerClass, tamanho)` continua para o v5 — mexer
nela renumeraria os `tilesets` que o jogo lê hoje.

**Folhas por mapa: 4-12 → 2, nos 20 mapas. Total 172 → 40.** O `map.json` cai de 9461 KB para
6153 KB. Números por mapa em [`reports/07-reexportacao-v6.md`](../reports/07-reexportacao-v6.md).

**A grade do v6 também mudou.** Com 16 colunas de 32px, uma folha que só cresce para baixo estourava
o limite seguro de textura em 4 dos 20 mapas (até 2688px de altura). O v6 preenche primeiro a largura
segura — 64/32/16 colunas para 32/64/128px — o que deixa cada folha quadrada-ish e trava a
capacidade em 2048×2048. Depois disso: **nenhuma folha acima de 2048px em nenhum mapa**.

O contrato de posicionamento não mudou: célula quadrada, preenchimento em linha da esquerda para a
direita, sprite no canto superior-esquerdo, índice → posição por aritmética pura.
