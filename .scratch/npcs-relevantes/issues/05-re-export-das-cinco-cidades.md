Status: ready-for-agent

# 05 — Re-export das cinco cidades

**What to build:** O `catalog-source.json` do `tibia-idle` encolhe de **38,5 MB**
para o tamanho que a `spec.md` prevê, com o conteúdo validando e o banco
subindo. É aqui que o trabalho das três anteriores chega ao jogo.

## Por que é ticket própria

As 02, 03 e 04 mexem no extractor e se verificam sozinhas, olhando fragmento.
Esta é a única que escreve no outro repositório, e por isso é a única que pode
falhar por motivo de lá: `import-content` valida com Zod, `nx run db:reset`
recria as tabelas, e 174 locations somem de uma coleção que outras coisas
referenciam. Separar deixa esse risco num lugar onde ele se vê.

## O cuidado

`merge_travel_graph_into_catalog` substitui as arestas da cidade inteira, então o
grafo não precisa de atenção. As **locations** precisam: a 03 tornou NPC
deletável, e esta ticket é o primeiro run em que isso remove 174 linhas de uma
vez. Confira que nada fora de NPC saiu.

Rode as cinco cidades, não uma — um catálogo meio migrado tem NPC de Thais já
cortado e NPC de Venore não, e a diferença não aparece em nenhum erro.

**Blocked by:** 02, 03, 04.

- [ ] As cinco cidades re-exportadas no mesmo lote
- [ ] `import-content` valida o catálogo novo sem erro de Zod
- [ ] `nx run db:reset` passa
- [ ] Nenhuma location de HUNT, TEMPLE ou DEPOT mudou nem desapareceu
- [ ] Nenhuma aresta sobrou citando location que não existe mais
- [ ] Tamanho do arquivo, contagem de locations e de arestas — antes e depois —
      no corpo do commit
