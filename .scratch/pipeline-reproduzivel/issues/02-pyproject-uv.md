Status: ready-for-agent

# 02 — Declarar as dependências Python com `pyproject.toml` + `uv`

**What to build:** Hoje não existe manifesto nenhum: `Pillow`, `protobuf` e `pytest` são
conhecimento tribal, e você descobre a falta quando o import estoura. Criar `pyproject.toml` com as
deps reais + lockfile do `uv`, e passar os comandos a rodar pelo interpretador da env.

Atenção ao `build_map.js:54`, que hoje spawna literalmente `"python"` — resolve por acaso via shim
do mise, e vai continuar quebrando diferente em cada máquina até apontar pra env.

**Blocked by:** nada.

- [x] `pyproject.toml` lista as deps de runtime (`Pillow`, `protobuf`) e as de dev (`pytest`)
- [x] `uv.lock` commitado
- [x] `build_map.js` invoca o interpretador da env, não `python` cru
- [ ] `uv sync && uv run pytest extractor/tests` roda os 27 arquivos de teste num clone limpo
- [x] README documenta o setup em um bloco só: `uv sync`

## Comments

`pyproject.toml` + `uv.lock` na raiz. Deps de runtime: `pillow>=10.0`, `protobuf>=6.33.5`. Dev:
`pytest>=8.0`. `uv sync` é o único passo de setup, documentado numa seção `## Setup` no topo do
`extractor/README.md`.

O piso do protobuf não é decorativo: `Appearances_pb2.py` foi gerado por protoc 6.33.5 e chama
`ValidateProtobufRuntimeVersion(PUBLIC, 6, 33, 5)` **no import**. Um runtime mais velho não falha
quando você usa o módulo, falha ao importá-lo — e a mensagem não diz "instale protobuf mais novo".

`build_map.js` ganhou `resolvePython()`: `$PYTHON` > `.venv/bin/python` do repo > `uv run python`,
mais um erro nomeado quando nada resolve (`ENOENT` virava um traceback do Node). O `spawnSync("python")`
cru resolvia por acaso pelo shim do mise.

`.venv/` adicionado ao `.gitignore` — o uv já escreve um `.venv/.gitignore` com `*`, mas deixar
explícito evita surpresa se a env for criada por outra ferramenta.

### Um critério ficou por fazer, e não é acidente

> - [ ] `uv sync && uv run pytest extractor/tests` roda os 27 arquivos de teste num clone limpo

Rodam **24 dos 27**, com 388 passando. Três não coletam:

```
test_build_monster_respawn_atlas.py
test_build_phaser_map_ground_sheets.py
test_build_phaser_map_sheets.py
```

Todos pelo mesmo motivo: importam `build_phaser_map`, que faz
`raise FileNotFoundError("Nenhuma pasta de sprites encontrada.")` na linha 87, **em tempo de
import**. Sem `extractor/sprites/` não há coleta. Isso é o ticket 08/13, não o 02 — nenhuma
declaração de dependência Python resolve a falta da biblioteca de sprites.

Dois desses três arquivos (`..._sheets.py` e `..._ground_sheets.py`) morrem no ticket 07 junto com
o v5, então o alvo real depois de 07+08 são 25 arquivos, não 27.

Além disso, duas falhas **pré-existentes**, pela mesma causa (ausência de `extractor/sprites/`),
não introduzidas aqui:

```
test_build_item_index.py::test_generate_item_index_no_orphan_frame_keys_against_real_data
test_ground_equivalent_report.py::test_every_strict_border_id_in_the_vendored_file_is_itself_a_ground
```

A primeira chama `generate_item_index()` e recebe `{}`; a segunda chama `appearance_flags()`, que
devolve `{}` quando o JSON do sprite não existe (`ground_equivalent_report.py:98-111`).
