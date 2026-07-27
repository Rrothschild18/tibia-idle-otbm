# Spec: Atlas de Sprites de Outfit (Outfit Sprite Atlas)

Status: ready-for-agent

## Problem Statement

Hoje, para cada outfit (jogador ou monstro), o cliente Phaser baixa um arquivo PNG separado por
frame de animação — até 36 requisições HTTP individuais por outfit (4 frames de `idle` + 32 frames
de `moving`, cobrindo as 4 direções sul/leste/norte/oeste). Isso já é reconhecido no pipeline como
fonte de overhead (o trabalho recente de bake de cenário estático documenta o mesmo tipo de
gargalo para objetos de mapa: muitas requisições/instanciações pequenas competindo pelo frame
budget). Para outfits o problema é ainda mais direto: entrar numa hunt spot com vários tipos de
monstro dispara dezenas de downloads pequenos de uma vez, e — pior — cada mapa que referencia o
mesmo outfit acaba com sua própria cópia dos mesmos arquivos de sprite, porque a etapa atual de
build por mapa copia os PNGs soltos de cada outfit para dentro do diretório de saída daquele mapa
especificamente.

Além disso, embora a convenção de orientação dos frames (ordem das direções, índices de
`idle`/`moving`) já esteja documentada no pipeline, essa informação não é carregada adiante para
nenhum formato de atlas — hoje ela só importa para quem lê os arquivos soltos um a um.

## Solution

Empacotar os frames de cada outfit em um único atlas (uma imagem + um JSON de mapeamento de
frames), gerado uma vez de forma global — não por mapa — e referenciado por ID de outfit a partir
de qualquer hunt spot que o utilize. Isso reduz o carregamento de um outfit a uma única imagem
compartilhada (cacheável entre mapas) em vez de dezenas de arquivos soltos duplicados por mapa,
mantendo cada frame individualmente endereçável (a seleção de direção/fase de animação continua
sendo uma decisão de runtime do Phaser, não algo resolvido em tempo de build).

A extração continua sendo feita pelo script existente que já decodifica `outfits.aec` e escreve um
PNG por frame; um novo script Python, dedicado exclusivamente a empacotamento, consome essa saída
já extraída e produz o atlas por outfit. A etapa de build por mapa passa a referenciar o atlas
global do outfit em vez de copiar os arquivos soltos para dentro da saída do mapa.

## User Stories

1. Como desenvolvedor do cliente de jogo (Phaser), quero que os frames de um outfit venham
   agrupados num único atlas, para carregar a animação de um monstro/jogador com uma única
   requisição de imagem em vez de dezenas.
2. Como desenvolvedor do cliente de jogo, quero que as chaves de frame dentro do atlas mantenham
   exatamente a mesma convenção de nome já usada nos arquivos soltos hoje, para não precisar
   reescrever a lógica que já monta listas de frames por direção/índice só por causa da troca de
   `load.image` para `load.atlas`.
3. Como jogador, quero que uma hunt spot carregue mais rápido, para que entrar numa área com vários
   tipos de monstro diferentes não trave em dezenas de downloads pequenos simultâneos.
4. Como jogador, quero que um outfit de monstro já baixado numa hunt spot seja reaproveitado em
   outra hunt spot que use o mesmo monstro, para não baixar os mesmos sprites de novo.
5. Como mantenedor do pipeline de extração, quero que o bake do atlas rode uma vez de forma global
   (não por mapa), para que o mesmo outfit não seja duplicado no diretório de saída de cada mapa
   que o referencia.
6. Como mantenedor do pipeline de extração, quero um script separado e de responsabilidade única
   para o empacotamento em atlas, para manter a decodificação dos assets brutos do Tibia e o
   empacotamento em atlas como preocupações independentes e testáveis separadamente.
7. Como mantenedor do pipeline de extração, quero que o script de atlas leia os PNGs por frame já
   extraídos (e o JSON por outfit que os acompanha) em vez de reprocessar `outfits.aec`, para não
   duplicar a lógica de decodificação de protobuf em dois scripts.
8. Como mantenedor do pipeline de extração, quero que os frames de cada outfit sejam empacotados
   exatamente na ordem já documentada (idle: sul/leste/norte/oeste nos índices 0-3; moving: 8
   frames de ciclo de caminhada por direção, mesma ordem de direções, índices 4-35), para que o
   layout do atlas seja previsível e coerente com a convenção de índice já usada no resto do
   pipeline.
9. Como mantenedor do pipeline de extração, quero que o bake do atlas seja determinístico
   (mesma entrada → saída byte a byte idêntica), para que regenerar os atlases não produza diffs
   ruidosos sem relação com mudanças reais nos sprites.
10. Como mantenedor do pipeline de extração, quero que o JSON do atlas siga um formato que o
    Phaser consiga consumir diretamente via `scene.load.atlas`, para não precisar de nenhuma etapa
    extra de tradução no cliente.
11. Como revisor visual/QA, quero uma forma de inspecionar um atlas gerado (imagem + mapeamento de
    frames), para confirmar que os frames batem com a direção/índice documentados antes de confiar
    no pipeline novo.
12. Como mantenedor do pipeline de extração, quero que outfits já hoje ignorados na extração (mais
    de 36 sprites, ou seja, com addon/mount) continuem sendo ignorados também no bake de atlas, para
    não transformar uma lacuna de extração já conhecida numa nova categoria de atlas
    corrompido/parcial.
13. Como mantenedor do build por mapa, quero que a saída por mapa referencie o atlas global
    compartilhado de um outfit (pelo ID) em vez de copiar os arquivos de sprite individuais desse
    outfit para dentro do diretório do próprio mapa, para reduzir o tamanho da saída por mapa e
    torná-la independente da quantidade de outfits de monstro distintos que existem no jogo.
14. Como mantenedor do build por mapa, quero que o esquema de definição de monstros/respawn seja
    estendido com uma referência aos arquivos de atlas de cada outfit citado, para que o cliente
    Phaser saiba qual par imagem+JSON de atlas carregar por definição de monstro, sem depender de
    adivinhar uma convenção de caminho.
15. Como desenvolvedor do cliente de jogo, quero que a convenção de chave de frame já usada nos
    nomes de arquivo por frame seja preservada dentro do atlas, para que qualquer lógica existente
    de busca de frame por direção/índice continue funcionando sem alteração.
16. Como mantenedor do pipeline de extração, quero um pequeno espaçamento fixo entre os frames
    empacotados (ou uma decisão explícita de não usar espaçamento), para evitar sangramento de
    textura ("texture bleeding") quando o Phaser escala ou filtra a textura do outfit.
17. Como mantenedor do repositório, quero que o novo contrato de atlas e o esquema atualizado de
    definição de monstros/respawn fiquem documentados junto da documentação já existente de sprites
    de outfit, para que a convenção de direção/ordem de frame e o contrato de atlas vivam numa única
    fonte descobrível, não só no código.
18. Como mantenedor do pipeline de extração, quero um modelo de regeneração que reconstrua todos os
    atlases de outfit numa única passada (seguindo o mesmo estilo de rebuild completo já usado na
    extração de sprites hoje), para que essa nova etapa não introduza comportamento de cache
    parcial/obsoleto na v1.
19. Como desenvolvedor do cliente de jogo (repositório `tibia-idle`), quero um contrato documentado
    para a saída do atlas (convenção de caminho, formato do JSON, formato da chave de frame) mesmo
    que a mudança de carregamento no Phaser em si viva num repositório separado, para que os dois
    repositórios possam evoluir de forma independente sem adivinhar o formato um do outro.

## Implementation Decisions

- **Novo módulo**: um script Python autônomo, executado como uma etapa própria do pipeline, após a
  etapa existente de extração de sprite por frame. Sua única responsabilidade é: para um outfit já
  extraído, ler seus PNGs por frame e o JSON por outfit que os acompanha, e produzir exatamente uma
  imagem de atlas e um JSON de mapeamento de frames para aquele outfit.
- **Escopo/unidade do bake**: um atlas por ID de outfit — não por mapa, e não um único atlas global
  contendo todos os outfits. Gerado uma vez, num local de saída compartilhado/global, independente
  de quais mapa(s) referenciam aquele outfit. Isso espelha o fato de que o mesmo outfit (ex.: um
  "rato") pode aparecer em várias hunt spots e deve ser baixado/cacheado pelo cliente apenas uma
  vez.
- **Determinismo**: os frames são dispostos numa grade fixa, seguindo exatamente a ordem de
  índice já estabelecida pela convenção de frame group/direção/índice do outfit (idle: sul, leste,
  norte, oeste nos índices 0-3; moving: 8 frames de ciclo de caminhada por direção, mesma ordem de
  direção, índices 4-35). Rodar o script duas vezes sobre a mesma entrada deve produzir saída
  idêntica byte a byte.
- **Tamanho de frame / empacotamento**: todos os frames de um outfit têm o tamanho fixo já
  documentado (32×32px), então o empacotamento é uma grade uniforme simples — não é necessário
  nenhum algoritmo de bin-packing. Um pequeno espaçamento transparente fixo é inserido entre as
  células para evitar sangramento de textura quando o cliente escala/filtra a textura do atlas.
- **Convenção de chave de frame**: cada frame empacotado mantém exatamente a mesma string de chave
  já usada hoje no nome do arquivo solto (ex.: `<outfitId>_<frameIndex>`), para que qualquer lógica
  já existente de montagem de chave de frame por direção/índice continue funcionando sem alteração
  — só o mecanismo de carregamento muda (um atlas vs. muitas imagens), não o contrato de chave.
- **Formato do JSON do atlas**: um formato de atlas de textura compatível com Phaser (formato
  "JSON Hash": um mapa `frames` indexado pelo nome do frame, cada um com o retângulo de pixels
  `frame`; um bloco `meta` com o nome e tamanho da imagem de origem), para que o cliente possa
  chamar `scene.load.atlas(outfitId, pngPath, jsonPath)` diretamente, sem etapa de tradução. Forma
  ilustrativa (não o conteúdo literal do arquivo):
  ```json
  {
    "frames": {
      "21_0": { "frame": { "x": 0, "y": 0, "w": 32, "h": 32 } },
      "21_1": { "frame": { "x": 34, "y": 0, "w": 32, "h": 32 } }
    },
    "meta": { "image": "21.png", "size": { "w": 1224, "h": 34 } }
  }
  ```
- **Comportamento de skip**: outfits já excluídos da extração por frame (mais que o layout base de
  36 sprites documentado, ou seja, com addon/mount) permanecem excluídos do bake de atlas também —
  a etapa de atlas só enxerga os outfits que a etapa de extração existente já produziu.
- **Integração com o build por mapa**: a etapa de build por mapa que hoje copia os PNGs por frame
  de cada outfit referenciado para dentro do diretório de saída daquele mapa passa a parar de copiar
  arquivos de sprite para outfits, e em vez disso emite uma referência ao atlas global compartilhado
  do outfit (pelo ID) dentro das definições de monstro/respawn que o mapa já gera. As chaves de
  frame dentro dessas definições não mudam; só o(s) arquivo(s) para o(s) qual(is) elas apontam muda,
  de muitos arquivos por frame para um par de atlas compartilhado.
- **Documentação**: a documentação existente de sprites de outfit (ordem de direção, fórmula de
  índice de idle/moving) é estendida com o novo contrato de atlas (layout de saída, formato do
  JSON, convenção de chave de frame, e a forma atualizada da referência em monstro/respawn), para
  que tanto este repositório quanto o repositório separado do cliente Phaser possam
  implementar/consumir a partir de uma única fonte de verdade.
- **Consumo no cliente**: as chamadas `load.atlas` do Phaser e a configuração de animação no
  cliente acontecem no repositório separado `tibia-idle` e estão fora do escopo de implementação
  deste repositório — este spec só define e produz o contrato de atlas que aquele repositório vai
  consumir.

## Testing Decisions

- Bons testes aqui exercitam a *saída* da função de empacotamento (contagem de frames,
  ordem/chaves dos frames, dimensões calculadas do atlas, determinismo byte a byte entre execuções
  repetidas), não o mecanismo interno de empacotamento — seguindo o mesmo estilo de
  `extractor/tests/test_render_baked_row.py`: construir fixtures de PNG sintéticos pequenos com PIL
  num `tmp_path`, chamar a função de empacotamento diretamente, e checar o tamanho da imagem
  retornada e a estrutura de mapeamento de frames retornada/escrita (posições, chaves) — não bytes
  de pixel exatos além das cores simples das fixtures.
- Prior art direto: `extractor/tests/test_render_baked_row.py` (função pura que retorna
  `(image, meta)`, testada contra sprites-fixture gerados via PIL) e `extractor/tests/test_is_bakeable.py`
  (testes unitários de predicado de elegibilidade) são os templates diretos — o novo empacotador de
  atlas deve, do mesmo jeito, expor uma função pura e chamável diretamente (dada uma lista de PNGs
  de frame + chaves, retorna a imagem composta e o dicionário de mapeamento de frames), para ser
  testável sem tocar dados reais de outfit nem o sistema de arquivos além de fixtures em `tmp_path`.
- `extractor/tests/test_build_phaser_map_baking.py` é o template para testar o ponto de integração
  com o build por mapa: rodar a função de build de mapa contra uma entrada de fixture pequena e
  checar a estrutura JSON resultante (aqui: que outfits referenciados produzem uma referência de
  atlas em vez de arquivos por frame copiados, e que as chaves de frame dentro das definições de
  monstro/respawn não mudam).
- Uma execução do pipeline completo contra dados reais de outfit já extraídos (do mesmo jeito que
  o trabalho de bake de cenário estático foi validado contra os mapas reais em `raw-maps/`) deve
  ser usada para conferir visualmente que pelo menos um atlas gerado tem seus frames alinhados com
  a direção/índice documentados (ex.: confirmar que o frame de índice 0 renderiza o outfit de
  frente/sul) antes de confiar no pipeline — mesmo padrão de "confiar mas verificar contra dado
  real" usado no trabalho de bake-client.
- Determinismo deve ser testado diretamente: rodar a etapa de atlas duas vezes sobre a mesma
  entrada deve produzir PNG e JSON de saída idênticos byte a byte.

## Out of Scope

- Estender a extração para outfits com mais de 36 sprites (addon/mount) — a convenção de layout de
  frame para esses casos não está documentada em lugar nenhum hoje e exigiria investigação própria.
- Qualquer mudança de código no cliente Phaser/TypeScript (chamadas `load.atlas`, configuração de
  animação, comportamento de cache) — esse trabalho vive no repositório separado `tibia-idle` e só é
  informado por este spec, não implementado como parte dele.
- Um único "mega-atlas" global contendo todos os outfits num arquivo só, ou atlases por mapa —
  explicitamente rejeitados em favor de um atlas compartilhado por ID de outfit, gerado uma vez e
  referenciado por ID.
- Divisão de atlas em múltiplas páginas por limite de tamanho máximo de textura da GPU — não é uma
  preocupação na granularidade por outfit (36 frames de 32×32 cabem confortavelmente numa única
  textura pequena).
- Regeneração incremental/parcial (rebakear só os outfits cujos frames de origem mudaram) — a v1
  faz rebuild completo a cada execução, seguindo o comportamento já existente dos scripts do
  extractor.
- Qualquer mudança nos sistemas de IA de monstro, movimento ou colisão — isso é puramente uma
  otimização de entrega/carregamento de asset.

## Further Notes

- O usuário pediu explicitamente que isso seja um script Python separado de
  `build_phaser_map.py`/`extract_sprites.py`, para manter as preocupações de decodificação e
  empacotamento independentes, e para facilitar inspecionar/acessar as imagens já empacotadas
  diretamente (em vez de só enxergar arquivos de frame individuais).
- A convenção de direção/índice de frame que este spec depende já está totalmente documentada em
  `OUTFIT_SPRITES_DOCUMENTATION.md` e reafirmada em `PHASER_MONSTERS.md` — nenhuma convenção nova
  precisa ser inventada, só carregada adiante para os nomes de chave de frame e o formato do JSON
  do atlas.
- Isso espelha, mas é arquiteturalmente distinto do trabalho já existente de bake-client (bake de
  cenário estático): aquela feature compõe múltiplos objetos numa única imagem congelada (perdendo
  endereçabilidade por frame, aceitável porque o cenário nunca anima); esta feature empacota muitos
  frames que continuam endereçáveis individualmente num único atlas compartilhado, sem compô-los
  entre si, já que a seleção de direção/animação do outfit precisa continuar sendo uma decisão de
  runtime.
