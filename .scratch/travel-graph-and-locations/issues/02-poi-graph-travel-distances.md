# 02 — Extração de POIs por placa + grafo de walkability + BFS → travelGraph

**What to build:** A partir do dump bruto do OTBM e do `map.json` da cidade inteira (produzido no ticket 01), extrair os POIs marcados por placa (tipos `HUNT`, `TEMPLE`, `DEPOT`, `QUEST`, convenção de id `CIDADE-TIPO-INCREMENTAL`), construir o grafo de tiles caminháveis (nós = tiles sem `unpass`, arestas ortogonais/diagonais custo 1 no mesmo floor, mais arestas de `isFloorTransition` ligando o mesmo `(x,y)` em `z-1` e `z+1`), e rodar uma BFS por POI (early exit ao alcançar todos os outros POIs da região) para gerar as distâncias em tiles entre cada par alcançável. Resultado: entradas de `locations` para esses 4 tipos + a coleção `travelGraph` com `{from, to, tileCount}`.

**Blocked by:** 01 — precisa do `map.json` da cidade inteira já processado e livre das placas.

- [ ] Placas com uid fora da faixa reservada (10001+) são ignoradas
- [ ] Texto de placa fora do formato `CIDADE-TIPO-INCREMENTAL` é rejeitado/reportado, não silenciosamente aceito
- [ ] O grafo exclui tiles com `unpass` e inclui vizinhos diagonais com o mesmo custo dos ortogonais
- [ ] Tiles com `isFloorTransition` geram aresta para o mesmo `(x,y)` em ambos `z-1` e `z+1` quando caminháveis
- [ ] BFS a partir de cada POI para com early exit assim que todos os outros POIs da região são alcançados
- [ ] Par de POIs inalcançável entre si simplesmente não gera aresta (sem erro)
- [ ] Rodando a CLI contra Rookgaard (após migrar as 12 placas de hunt para a nova convenção), o `travelGraph` mostra `tileCount` plausível entre pares de hunts, temple e depot
- [ ] Lógica de parsing/grafo/BFS coberta por testes com fixtures pequenas em memória (sem tocar arquivo real de OTBM/map.json)
