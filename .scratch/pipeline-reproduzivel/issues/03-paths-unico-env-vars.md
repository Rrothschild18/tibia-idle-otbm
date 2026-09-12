Status: ready-for-agent

# 03 — Um `paths.py` único, com env var e erro alto

**What to build:** Colapsar os três `DEFAULT_TIBIA_IDLE_DIR` copiados
(`build_hunt_fragment.py:57`, `build_travel_fragment.py:72`, `sync_items_to_tibia_idle.py:39`) e os
dois `DEFAULT_CANARY_DIR` (`build_travel_fragment.py:75`, `build_monster_loot_index.py:20`) num
módulo só.

Os dois defaults de hoje estão **errados**, não só duplicados: o do tibia-idle resolve pra
`<workspace>/tibia-idle/tibia-idle` (uma pasta aninhada que não existe — o checkout real é
`<workspace>/tibia-idle`), e o do Canary é `C:\canary-3.2.1`, caminho Windows num fluxo que é
Linux-only. Na prática `--tibia-idle-dir` e `--canary-dir` são obrigatórios hoje, e ninguém
documentou isso.

Precedência: `--flag` > env var (`TIBIA_IDLE_DIR`, `CANARY_DIR`) > layout irmão (`../tibia-idle`,
`../canary`).

**Blocked by:** nada.

- [x] `extractor/scripts/paths.py` é a única definição desses caminhos; nenhum `os.path.join` de
      caminho de repo irmão sobra espalhado
- [x] `C:\canary-3.2.1` não existe mais em lugar nenhum do repo
- [x] Diretório ausente → erro citando o caminho tentado, a env var e a flag
      (ex: `"esperava um checkout do tibia-idle em /home/x/Projects/tibia-idle; passe
      --tibia-idle-dir ou defina TIBIA_IDLE_DIR"`) — nunca um traceback de arquivo não encontrado
- [x] README documenta as duas env vars
- [x] Coberto por teste: flag vence env var, env var vence fallback, ausente dá erro com mensagem

## Comments

`extractor/scripts/paths.py` é a única definição. Um `SiblingRepo` com `resolve()` (aplica a
precedência) e `require()` (exige que exista), mais `MissingRepoError` — exceção própria, não
`FileNotFoundError`, porque quem chama precisa distinguir "não configurado" de "arquivo sumiu no
meio do pipeline".

Removidos: três cópias de `DEFAULT_TIBIA_IDLE_DIR` (`build_hunt_fragment.py`,
`build_travel_fragment.py`, `sync_items_to_tibia_idle.py`) e duas de `DEFAULT_CANARY_DIR`
(`build_travel_fragment.py`, `build_monster_loot_index.py`). `C:\canary-3.2.1` não existe mais em
nenhum arquivo vivo — as ocorrências que restam estão em specs antigos do `.scratch/`, que são
registro histórico do que era verdade na época e não foram reescritos.

Os defaults novos **funcionam**, que é a diferença que importa. Isto agora roda sem flag nenhuma:

```
uv run python extractor/scripts/build_travel_fragment.py ROOK
[OK] 997 ids com floorchange lidos de /home/rroth/Projects/canary/data/items/items.xml
```

E o erro fala o que fazer:

```
error: esperava um checkout do canary em /nao/existe; passe --canary-dir ou defina CANARY_DIR
```

### O teste pegou um bug real

`test_sibling_fallback_is_the_workspace_neighbour` falhou na primeira implementação: eu tinha
juntado o irmão a `REPO_DIR` em vez de `dirname(REPO_DIR)`, produzindo
`tibia-idle-otbm/tibia-idle` — que é a **mesma classe de erro** que o ticket existe para corrigir,
um nível a mais de aninhamento. Daí `WORKSPACE_DIR` ser uma constante nomeada agora, e não um
`os.path.join(..., "..")` embutido.

9 testes em `extractor/tests/test_paths.py`, incluindo um `autouse` que limpa `TIBIA_IDLE_DIR` e
`CANARY_DIR` do ambiente — sem isso a suíte passaria nesta máquina e falharia noutra.

Regressão: 388 passando (379 antes + 9 novos), mesmas duas falhas pré-existentes do ticket 02.
Fragmento do ROOK continua **idêntico ao golden do 01**.
