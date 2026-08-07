# Modelo de render espelhado no RME

Substituir o modelo de renderização de mapa inventado pelo pipeline (`layerClass` + tabela de
`depthOffset`) pelo modelo que o Remere's Map Editor usa para desenhar mapas de Tibia, mantendo
intactas as partes do pipeline que foram genuinamente pensadas para o Phaser (extração de sprites,
empacotamento em sheets, loot, hunts).

O objetivo é **corrigir bugs de visualização**, não ganhar performance. Performance deve ficar
neutra e é condição de aceite, não meta.

## Por que

O modelo atual nasceu de exploração empírica de metadata de sprites: a detecção de parede é uma
combinação de flags observada no conjunto de Rookgaard, e as categorias `roof` e `border` são listas
de id escritas à mão. Cada `depthOffset` foi calibrado contra o anterior até a tela ficar aceitável.

O RME resolve o mesmo problema com duas categorias e uma ordem, ambas derivadas direto das flags do
`appearances.dat` — sem heurística e sem tabela de constantes.

Dois sintomas concretos do modelo atual:

- Bordas renderizam acima de tudo, inclusive do que deveria cobri-las. No RME border é item de
  fundo, quase no piso da pilha. Está invertido.
- A camada chamada "Roof" não contém um único telhado. Em todos os mapas ela é composta de duas
  aparências com a flag `bank` — ou seja, **chão** — desviadas para fora do tilelayer só porque o
  sprite é 64×64 e um tilelayer de 32×32 não comporta.

## O modelo

Três eixos que o `layerClass` colapsava num só, e que passam a ser independentes:

| Eixo | Determinado por | Responde |
|---|---|---|
| `draw slot` | flag `bank` | é ground ou item? |
| passagem | flag `unpass` | dá para andar? |
| footprint | tamanho do sprite | tilelayer, blitter ou sprite? |

A ordem de desenho (`paint order`) é: andar → linha → `stack order`. Dentro da tile: ground
primeiro, depois itens de fundo por `top order` crescente (`clip`=1, `bottom`=2, `top`=3), depois os
demais em ordem de inserção. Criaturas sempre por último.

A profundidade de um sprite passa a ser consequência dessa ordem. Deixa de existir constante de
profundidade atribuída por categoria.

Ver `CONTEXT.md` para os termos.

## Espelho híbrido: onde seguimos o RME e onde desviamos

O RME é um editor, não o cliente. Segue-se o RME por padrão; cada desvio é decisão nossa e está
registrado aqui com o motivo.

| Ponto | RME | Decisão | Motivo |
|---|---|---|---|
| Ordem de iteração | por coluna | **por linha** | O RME percorre coluna por artefato da estrutura de dados dele. Por linha é o que dá a pista de profundidade correta, e é o que já fazemos |
| Clamp de elevação | nenhum | **clampar, ajustável** | Sem teto, uma pilha alta desloca o sprite para fora da própria tile. O RME nunca encontra o caso porque é editor |
| Seleção de variante por andar | ignora | **ignorar, atrás de switch** | Critério de aceite é o mapa ficar igual ao que se vê no RME. Afeta ~6.300 posicionamentos; se algum sair errado, o switch liga |
| Telhado dinâmico | não existe | **não implementar** | Nenhum mapa tem telhado real. O que chamávamos de telhado é chão |
| Classificação de parede/borda | vem de XML de autoria | **não usar** | Não afeta o desenho. A única exceção é `ground_equivalent`, medida no ticket 02 |

## Fora de escopo

Toda a máquina de autoria do RME: brushes, autoborder, doodads, tilesets, paletas, seleção,
live-client, minimap do editor.

## Estratégia de migração

O schema novo é escrito em diretório separado, e o diretório atual permanece intacto até o jogo
migrar. O jogo continua rodando durante toda a mudança; a troca de caminho é o último ticket.

## Tickets

Numeração global, dividida entre dois repositórios:

- **`tibia-idle-otbm`** (pipeline): 02 a 07, em `.scratch/modelo-render-rme/issues/`
- **`tibia-idle`** (Phaser): 01, e 08 a 12, no `.scratch/modelo-render-rme/issues/` daquele repo

O 01 é o baseline e não tem bloqueio — precisa rodar antes de qualquer código de render existir.
