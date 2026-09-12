Status: ready-for-agent

# 02 — Declarar as dependências Python com `pyproject.toml` + `uv`

**What to build:** Hoje não existe manifesto nenhum: `Pillow`, `protobuf` e `pytest` são
conhecimento tribal, e você descobre a falta quando o import estoura. Criar `pyproject.toml` com as
deps reais + lockfile do `uv`, e passar os comandos a rodar pelo interpretador da env.

Atenção ao `build_map.js:54`, que hoje spawna literalmente `"python"` — resolve por acaso via shim
do mise, e vai continuar quebrando diferente em cada máquina até apontar pra env.

**Blocked by:** nada.

- [ ] `pyproject.toml` lista as deps de runtime (`Pillow`, `protobuf`) e as de dev (`pytest`)
- [ ] `uv.lock` commitado
- [ ] `build_map.js` invoca o interpretador da env, não `python` cru
- [ ] `uv sync && uv run pytest extractor/tests` roda os 27 arquivos de teste num clone limpo
- [ ] README documenta o setup em um bloco só: `uv sync`
