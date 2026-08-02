# 02 — Bake de item entra no pipeline de build, não é mais um passo manual lembrado à parte

**What to build:** Hoje `bake_item_atlas.py`, `bake_item_sheets.py` e o `build_item_index.py`
(ticket 01) só rodam quando alguém lembra de rodá-los manualmente — foi assim que os dados atuais
foram gerados nesta sessão. O pedido é que isso pare de depender de lembrança manual: sempre que o
pipeline de build de mapa rodar (`npm run build-map`, hoje só `node extractor/scripts/build_map.js`),
os assets de item também devem ficar em dia.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] Decisão de design a resolver durante a implementação (documentar a escolha feita, não só
      codar): bake de item é **global** (não depende de qual mapa está sendo buildado — mesma
      natureza do atlas de outfit, que já é global e roda separado do build por mapa), enquanto
      `build_map.js` builda **um mapa por vez**. Rodar o bake completo de item (~2min no dado real:
      ~1m30s de `bake_item_atlas.py` + ~25s de `bake_item_sheets.py`) toda vez que
      `build_map.js` builda um único mapa seria desperdício se `build_map.js` for chamado
      repetidamente numa sessão de trabalho. Duas opções razoáveis, escolher uma:
  - (a) `build_map.js` sempre dispara o bake de item também, aceitando o custo fixo (~2min) por
    build de mapa — simples, sem estado extra pra gerenciar.
  - (b) Um novo script `npm run build-items` (script Python já existe, só falta o wrapper np script
    e a orquestração), rodado separado do build de mapa, mas documentado como parte obrigatória do
    fluxo "eu fiz um mapa novo" — não escondido, mas também não pago a cada build de mapa
    individual.
  Registrar a escolha e o motivo num comentário no script escolhido.
- [ ] `package.json` na raiz do `tibia-idle-otbm` ganha o(s) script(s) novo(s) (`build-items` e/ou
      integração dentro de `build-map`), espelhando a entrada já existente `"build-map": "node
      extractor/scripts/build_map.js"`.
- [ ] `README.md`/`CONVERTER_DOCS.md` do extractor documentam o fluxo "mapa novo" atualizado,
      incluindo a etapa de item — hoje esses documentos só cobrem sprites de mapa/outfit.
- [ ] Idempotência: rodar o bake de item duas vezes seguidas sem mudança nos dados de origem não
      deve produzir diffs (já garantido pelos bakes individuais, que são determinísticos — só
      confirmar que a orquestração nova não introduz não-determinismo, ex. ordem de iteração de
      diretório).

## Comments

Este ticket depende de uma decisão de produto/fluxo (ponto (a) vs (b) acima) que não foi resolvida
na sessão que escreveu este ticket — o usuário pediu "sempre que eu fizer um mapa novo quero ter
tudo isso feito", que é compatível com as duas opções. Quem pegar este ticket deve confirmar com o
usuário antes de implementar, ou registrar a escolha feita e o porquê aqui.
