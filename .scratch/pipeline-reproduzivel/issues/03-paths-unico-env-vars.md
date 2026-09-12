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

- [ ] `extractor/scripts/paths.py` é a única definição desses caminhos; nenhum `os.path.join` de
      caminho de repo irmão sobra espalhado
- [ ] `C:\canary-3.2.1` não existe mais em lugar nenhum do repo
- [ ] Diretório ausente → erro citando o caminho tentado, a env var e a flag
      (ex: `"esperava um checkout do tibia-idle em /home/x/Projects/tibia-idle; passe
      --tibia-idle-dir ou defina TIBIA_IDLE_DIR"`) — nunca um traceback de arquivo não encontrado
- [ ] README documenta as duas env vars
- [ ] Coberto por teste: flag vence env var, env var vence fallback, ausente dá erro com mensagem
