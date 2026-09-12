# Corpo e respawn de monstro saem do Canary, na mesma chave do loot

A cadeia de corpo (`corpse` → `decayTo` → …) e o `race` de cada monstro são **lidos do checkout do
Canary**, não inventados, e moram numa chave nova do `monster-loot.json` que já existia — não num
arquivo novo.

Registrado aqui porque o porquê vivia só em `.scratch/monstro-respawn-e-corpse/spec.md`, deletado
na limpeza do ticket 11.

## Puxar do Canary, não inventar esquema genérico

A cadeia real varia muito por monstro: um rato tem 1 estágio de 10s, um humano tem 5 ou mais. Um
esquema fixo (N estágios, mesmos tempos para todos) seria menos fiel **e** ainda exigiria inventar
e balancear números à mão. Como o pipeline já lia o Canary para loot, estender a mesma fonte foi
simultaneamente o menor esforço e o mais autêntico — não houve trade-off entre os dois.

Desde o ticket 04 o `items.xml` está vendorizado, então essa leitura não exige mais um clone do
Canary para rodar o pipeline; exige para **atualizar** o `monster-loot.json`.

## Chave nova, não arquivo novo

Recusada a alternativa de um `monster-corpse.json` separado: seria mais um arquivo para manter em
sincronia com o mesmo lookup por nome de monstro que já existe, sem ganho. Loot e corpo saem da
mesma morte e são consumidos juntos; uma chave em cima do que já é lido é a mudança de interface
mínima.

## Escopo do efeito: só o 11

Recusada a extração genérica de todos os magic effects do cliente. O pedido concreto era o efeito
de nascimento de monstro (`CONST_ME_TELEPORT`, id 11), e generalizar sem um segundo caso de uso
conhecido é trabalho especulativo. `bake_effect_atlas.py` ficou simples o bastante para crescer
depois sem retrabalho.
