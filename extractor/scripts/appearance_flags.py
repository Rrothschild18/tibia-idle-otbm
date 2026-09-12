"""Tabela de flags por appearance, versionada, com curadoria ao lado.

O travel-graph nunca leu "um mapa": de `full-maps/<CIDADE>/map.json` ele usava
**só** `objectDefs[<id>].flags` — nunca `floors`, `sheets`, `tilesets` ou
`animations`. Os tiles vêm do dump cru. Para alimentar uma tabela de ~2100
entradas, o pipeline gerava 20,3 MB de `map.json` e jogava fora.

Dois arquivos por cidade, e a separação é a regra mecânico-vs-curado do
`CONTEXT.md`:

- `appearance-flags/<CIDADE>.json` — **100% mecânico**, derivado dos metadados
  de appearance. Regenerar sobrescreve sem dó.
- `appearance-flags/<CIDADE>.overrides.json` — **curado**, pequeno, versionado,
  e **sempre vence**. Regenerar nunca o toca.
"""

import json
import os

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
EXTRACTOR_DIR = os.path.dirname(SCRIPTS_DIR)
FLAGS_DIR = os.path.join(EXTRACTOR_DIR, "appearance-flags")


class MissingFlagsTableError(Exception):
    """Tabela ausente, com o comando que a gera."""


def table_path(city: str, flags_dir=None) -> str:
    return os.path.join(flags_dir or FLAGS_DIR, f"{city}.json")


def overrides_path(city: str, flags_dir=None) -> str:
    return os.path.join(flags_dir or FLAGS_DIR, f"{city}.overrides.json")


def _read(path):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as handler:
        return json.load(handler)


def load_flags(city: str, flags_dir=None) -> dict:
    """{appearance id (str): {flag: valor}} com os overrides já aplicados.

    O override **substitui a entrada inteira**, não mescla chave a chave: ele é
    a resposta final para aquele id. Mesclar deixaria a derivação reintroduzir
    pela porta dos fundos justamente o valor que a curadoria existe para
    corrigir.
    """
    table = _read(table_path(city, flags_dir))
    if table is None:
        raise MissingFlagsTableError(
            f"tabela de flags de {city} não encontrada em {table_path(city, flags_dir)}; "
            f"gere com 'uv run python extractor/scripts/build_appearance_flags.py {city}'"
        )

    overrides = _read(overrides_path(city, flags_dir)) or {}
    merged = dict(table)
    merged.update(overrides)
    return merged


def write_table(city: str, flags_by_id: dict, flags_dir=None) -> str:
    """Grava só o arquivo mecânico. Nunca toca no de overrides.

    Flags falsas são descartadas — mesma convenção do `objectDefs` que esta
    tabela substitui, onde ausência e `False` já queriam dizer a mesma coisa.
    """
    directory = flags_dir or FLAGS_DIR
    os.makedirs(directory, exist_ok=True)

    truthy = {}
    for appearance_id, flags in flags_by_id.items():
        kept = {key: value for key, value in (flags or {}).items() if value}
        if kept:
            truthy[str(appearance_id)] = kept

    path = table_path(city, flags_dir)
    with open(path, "w", encoding="utf-8") as handler:
        json.dump(truthy, handler, indent=2, ensure_ascii=False, sort_keys=True)
        handler.write("\n")
    return path
