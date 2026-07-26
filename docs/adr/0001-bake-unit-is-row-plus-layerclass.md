# Unidade de bake de cenário estático é (linha, layerClass), não (linha)

Cada `layerClass` (`walls_south`, `bottom`, `object`, `walls_east`, `top`) tem um `depthOffset`
próprio que existe especificamente para intercalar corretamente com a profundidade do jogador
na mesma linha (`tileY`) — ex.: `walls_south` (depth 3) renderiza atrás do jogador e `walls_east`
(depth 12) na frente, no mesmo `tileY`, porque a profundidade do jogador fica entre os dois (ver
`WALL_DEPTH.md`). Bakear todos os itens elegíveis de uma linha em uma única imagem com uma única
depth destruiria essa intercalação — repetindo o mesmo tipo de bug já corrigido e depois revertido
em 2026-07-17 (memória `roof_wall_depth_fix`), quando um hack similar (promover walls para a layer
`border` com depth absoluta) foi tentado e explicitamente revertido a pedido do usuário.

**Decisão:** cada unidade de bake offline é `(tileY, layerClass)` — uma imagem composta e uma depth
por combinação, preservando o `depthOffset` nativo de cada `layerClass`. `border` e `roof` ficam
fora do escopo de bake: ambos já têm comportamento de profundidade/visibilidade especial (depth
absoluta para `border`, toggle de visibilidade para `roof`) e são conjuntos pequenos, então o custo
de mantê-los dinâmicos é baixo.

**Consequência:** o layer `bakedgroup` do `map.json` tem uma entrada por `(tileY, layerClass)` em
vez de uma por `tileY` — mais arquivos PNG do que a proposta original de "um PNG por linha", mas
cada um preserva exatamente o comportamento de depth que o sistema dinâmico já garante hoje.
