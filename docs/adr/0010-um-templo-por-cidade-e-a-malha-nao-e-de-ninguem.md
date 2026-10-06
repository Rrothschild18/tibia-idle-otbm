# Um templo por cidade, e a malha inter-cidade não é de cidade nenhuma

Duas mudanças que parecem independentes e são o mesmo erro visto de dois lados: **identidade
derivada de descoberta**. O templo de uma cidade passa a ser um só, escolhido pelo nome da área
curada; e a aresta templo↔templo entre cidades deixa de pertencer a qualquer cidade, ganhando um
passo próprio (`build_intercity_mesh.py`).

Registrado porque os dois consertos reviram decisões que estavam escritas e testadas como
intencionais — `merge_travel_graph_into_catalog` tinha um teste fixando o comportamento que esta ADR
derruba em parte, e sem a razão no papel o próximo leitor "arruma" de volta.

## O que quebrou, medido

O re-export das cinco cidades (`498c5ce`) registrou "HUNT/TEMPLE/DEPOT intactos em 65/7/5" e passou.
Sete templos para cinco cidades não é intacto: o recorte de THAIS trazia **três**.

```
THAIS-TEMPLE-0001  32097,32219  "Rookgaard"
THAIS-TEMPLE-0002  32091,32027  "Island of Destiny"
THAIS-TEMPLE-0003  32369,32241  "Thais"
```

No catálogo do `tibia-idle`, o `THAIS-TEMPLE-0001` apareceu com a coordenada de Rookgaard **e o
`displayName` "Thais"**. Não é inconsistência do merge — é o merge funcionando como documentado:
campo mecânico (posição) toma o valor fresco, campo curado (`displayName`) é preservado. O id era a
chave, e o id tinha virado outra coisa.

Efeito em produção: personagem com templo-casa em Thais nascia no tile de Rookgaard, "viajar para
Thais" levava para lá, e a lista de cidades mostrava Thais três vezes. Ficou no ar de 2026-10-04 a
2026-10-06.

E a malha entre as quatro cidades mainland **deixou de existir** no mesmo dia, por outro motivo:
`_touches_city` tratava aresta com um pé na cidade publicada como "deste run". Uma Carlin↔Kazordoon
tem um pé em cada, e o fragmento de uma cidade só conhece o recorte dela — nenhum dos dois pode
produzi-la. Publicar qualquer uma apagava. As seis arestas tinham sido medidas numa rodada manual
(`0a1bb168` no `tibia-idle` tocou só o catálogo e um spec, nenhum script) e nasceram condenadas.

## Por que o nome da área, e não a máscara

A tentação é dizer "o recorte já tem máscara de subárea, use ela". Não serve, e isto é o achado que
custou mais tempo: `cut_city.py:243` **já** filtra town por máscara estrita
(`if (t["x"], t["y"]) in columns`). Rookgaard e a Island of Destiny saírem no recorte de THAIS prova
que as colunas deles estão dentro da união das 17 subáreas curadas de Thais — os três dividem a
área 24 da Cyclopedia. A máscara não os separa porque, para a Cyclopedia, são o mesmo lugar.

Quem separa é o nome da área, que o `source.json` carrega em `area` e que é curado por gente:

| cidade | `area` | towns no recorte | ramo |
|---|---|---|---|
| CARLIN / KAZORDOON / VENORE | = nome do town | 1 | nome casa |
| THAIS | "Thais" | Rookgaard, Island of Destiny, **Thais** | nome casa |
| ROOK | **"Thais"** | **Rookgaard** | town único |

O fallback de town único não é defensivo, é obrigatório: ROOK é talhado da área "Thais" e o town
dele é "Rookgaard". Casar nome sem o fallback deixaria Rookgaard sem templo.

**Vários towns e nenhum com o nome da área não emite templo.** Faltar templo quebra alto — o
fragmento reclama, a cidade não tem de onde partir. Templo no lugar errado quebrou calado por dois
dias. Entre as duas, a que grita.

## A malha é uma unidade, e não é de cidade nenhuma

`is_intercity_mesh_edge` é o recorte: templo↔templo entre cidades **diferentes**. Só isso escapa do
publish de uma cidade, e `merge_intercity_mesh_into_catalog` é quem a substitui — inteira, não por
upsert, pelo mesmo motivo que a de cidade (aresta que nenhuma busca produziu não sobrevive à busca
que deixou de produzi-la).

O recorte é estreito de propósito. Qualquer outra aresta cross-city continua órfã e continua saindo:
a proteção da ADR-0009 e o teste de `ROOK-A<->CARL-B` seguem valendo. Dois templos da **mesma**
cidade também não são malha — é grafo interno, e o fragmento daquela cidade manda nele.

A medida sai de **um** recorte que contenha todos os templos, hoje o de THAIS, cujo box de 1682×1682
cobre as quatro cidades com os corredores entre elas — é o "veio de graça" que o `0a1bb168` notou. O
script confere a cobertura e **recusa** em vez de medir pela metade: malha com par faltando é
indistinguível, do lado do jogo, de cidade inalcançável.

## ROOK fica fora por regra, não por geografia

`DEFAULT_EXCLUDED = ("ROOK",)`. Rookgaard foi feita à mão e ninguém de lá alcança a mainland nem o
contrário — é decisão de produto. A reachability do grafo provavelmente diria o mesmo, porque a ilha
é cercada de água, mas depender disso deixaria a regra invisível no código e um quirk de mapa
publicaria uma viagem que o jogo não permite.

## Trade-off aceito

O nome da área é dado curado, então um `curation.json` com `area` errado volta a escolher o templo
errado — a diferença é que agora erra em um lugar nomeado, e o caso ambíguo avisa em vez de chutar.

A malha ainda depende de um recorte grande existir. Se os recortes encolherem até nenhum conter os
quatro templos, o script recusa e alguém precisa recortar maior — que é exatamente a conversa que o
`0a1bb168` registrou ter evitado por sorte, e que esta ADR prefere ter explícita a ter por acidente.

E o `tileCount` da malha é tile andado de verdade, mas entre **templos**: a viagem que o jogador faz
soma POI→templo próprio + templo→templo + templo→POI destino. Nenhuma dessas pernas é medida junto
com as outras, então o total é soma de medidas independentes, não uma única busca ponta a ponta. Foi
decisão de desenho do `tibia-idle` (o POI de uma cidade não conhece a árvore de outra), e a malha
existe para servir exatamente esse modelo.
