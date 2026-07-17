"""
item_classifier.py
==================
Sistema de classificação manual de IDs de appearances.

Para cada ID listado aqui, a classificação de layer é FORÇADA,
sobrepondo completamente o sistema automático de flags.

Fluxo de decisão no converter:
    1. ID está em OVERRIDES?     → usar categoria do override (prioridade máxima)
    2. ID está em alguma set?    → usar essa categoria
    3. Nenhum match              → fallback para flags automáticas (comportamento antigo)

Categorias disponíveis:
    "ground"      → tilelayer base (terreno caminhável)
    "border"      → objectgroup Borders (transições de terreno) — SOMENTE MANUAL
    "bottom"      → objectgroup Bottom (decorações de chão)
    "walls"       → paredes genéricas — converter resolve em walls_east/walls_south via hook
    "walls_east"  → objectgroup WallsEast (paredes verticais, depth alto) — força orientação
    "walls_south" → objectgroup WallsSouth (paredes horizontais + cantos, depth baixo)
    "object"      → objectgroup Objects (móveis, árvores)
    "top"         → objectgroup Top (tetos/signs, flag top)
    "roof"        → objectgroup Roof (bloqueio de visão) — SOMENTE MANUAL

Como popular:
    Execute o converter e inspecione os IDs marcados como "unknown" ou
    mal classificados no map.json. Adicione-os nas sets abaixo.

    Dica rápida: python item_classifier.py --dump-unknown map.json
    (lista IDs classificados somente por flags, sem correspondência manual)
"""

import sys
import json
from typing import Dict, Optional, Set

# ======================================================
# OVERRIDES: ID → categoria forçada (maior prioridade)
# ======================================================
# Use para IDs específicos que o sistema automático classifica errado.
# Exemplo: { 4526: "roof", 101: "ground" }

OVERRIDES: Dict[int, str] = {
    # Exemplos (descomente e adicione conforme necessário):
    # 101:  "ground",   # Void/black tile
    # 4526: "roof",
}

# ======================================================
# SETS POR CATEGORIA
# ======================================================
# IDs listados aqui recebem a categoria correspondente.
# Conflitos: se um ID aparecer em múltiplas sets, OVERRIDES tem prioridade,
# depois a ordem: roof > top > border > bottom > object > ground

ROOF_IDS: Set[int] = {1128, 4427, 1316}
# Telhados e coberturas
# Ex: ROOF_IDS = {4526, 4527, 4528}

TOP_IDS: Set[int] = set()
# Items com bandeiras, sinais, lampiões suspensos
# Ex: TOP_IDS = {2700, 2701}

BORDER_IDS: Set[int] = {
    1723, 1729, 1730, 1731, 1732,
    2727, 2731, 3993,
    4411, 4412, 4413, 4414, 4415, 4416, 4417, 4418,
    4419, 4420, 4421, 4422, 4423, 4424, 4425, 4426,
}
# Bordas e transições de terreno (clip)
# Ex: BORDER_IDS = {1706, 1707, 1708}

BOTTOM_IDS: Set[int] = set()
# Decorações de chão (baixas, abaixo de criaturas)
# Ex: BOTTOM_IDS = {2016, 2017}

WALL_IDS: Set[int] = {
    1026, 1027, 1032, 1033, 1034,
    1927, 4747, 4748,
    7541, 8201, 8202, 8203, 8204, 8205, 8206,
    4429, 4430, 4431, 4432
} | set(range(1294, 1302))
# Paredes genéricas — o converter resolve em walls_east/walls_south via hookDirection
# Use WALL_EAST_IDS ou WALL_SOUTH_IDS para forçar orientação manualmente

WALL_EAST_IDS: Set[int] = set()
# Paredes verticais (borda oeste da sala) — depth alto, renderiza POR CIMA do jogador
# Ex: WALL_EAST_IDS = {1294, 1300}

WALL_SOUTH_IDS: Set[int] = set()
# Paredes horizontais + cantos (borda norte da sala) — depth baixo, renderiza ATRÁS
# Ex: WALL_SOUTH_IDS = {1295, 1296, 1302}

OBJECT_IDS: Set[int] = set()
# Móveis, árvores, objetos interativos
# Ex: OBJECT_IDS = {1515, 2356}

GROUND_IDS: Set[int] = set()
# Terrenos caminháveis (normalmente já vão para tilelayer via tileid)
# Ex: GROUND_IDS = {100, 105, 4526}

# ======================================================
# API PÚBLICA
# ======================================================

_CATEGORY_PRIORITY = ["roof", "top", "walls_east", "walls_south", "walls", "border", "bottom", "object", "ground"]

_SET_MAP: Dict[str, Set[int]] = {
    "roof":        ROOF_IDS,
    "top":         TOP_IDS,
    "walls_east":  WALL_EAST_IDS,
    "walls_south": WALL_SOUTH_IDS,
    "walls":       WALL_IDS,
    "border":      BORDER_IDS,
    "bottom":      BOTTOM_IDS,
    "object":      OBJECT_IDS,
    "ground":      GROUND_IDS,
}


def classify(appearance_id: int) -> Optional[str]:
    """
    Classifica um appearance ID manualmente.

    Returns:
        str com a categoria, ou None se não houver mapeamento manual
        (sinalizando que o converter deve usar o sistema de flags).
    """
    # 1. Override explícito
    if appearance_id in OVERRIDES:
        return OVERRIDES[appearance_id]

    # 2. Busca nas sets (ordem de prioridade)
    for category in _CATEGORY_PRIORITY:
        if appearance_id in _SET_MAP[category]:
            return category

    return None  # sem mapeamento manual → usar flags automáticas


def add(appearance_id: int, category: str) -> None:
    """Adiciona um ID a uma categoria em runtime (não persiste)."""
    if category == "override":
        OVERRIDES[appearance_id] = category
        return
    if category in _SET_MAP:
        _SET_MAP[category].add(appearance_id)
        # Remove de outras sets para evitar conflitos
        for cat, s in _SET_MAP.items():
            if cat != category:
                s.discard(appearance_id)


def all_manual_ids() -> Set[int]:
    """Retorna todos os IDs com classificação manual."""
    ids = set(OVERRIDES.keys())
    for s in _SET_MAP.values():
        ids |= s
    return ids


# ======================================================
# CLI: python item_classifier.py --dump-unknown map.json
# ======================================================

def _dump_unknown(map_json_path: str) -> None:
    """Lista IDs que dependem somente de flags (sem classificação manual)."""
    with open(map_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    object_defs = data.get("objectDefs", {})
    manual = all_manual_ids()

    unknown: Dict[str, list] = {}
    for id_str, defn in object_defs.items():
        aid = int(id_str)
        if aid not in manual:
            layer = defn.get("layerClass", "?")
            unknown.setdefault(layer, []).append(aid)

    if not unknown:
        print("Todos os IDs têm classificação manual.")
        return

    total = sum(len(v) for v in unknown.values())
    print(f"IDs classificados SOMENTE por flags ({total} total):\n")
    for layer in _CATEGORY_PRIORITY + ["?"]:
        ids = sorted(unknown.get(layer, []))
        if ids:
            print(f"  [{layer}]  ({len(ids)} IDs)")
            for chunk_start in range(0, len(ids), 10):
                chunk = ids[chunk_start:chunk_start + 10]
                print("    " + ", ".join(str(i) for i in chunk))
    print(f"\nAdicione os IDs que precisam de correção nas sets em item_classifier.py.")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--dump-unknown":
        _dump_unknown(sys.argv[2])
    else:
        print("Uso: python item_classifier.py --dump-unknown <map.json>")
        print("     Lista IDs sem classificação manual no arquivo gerado.")
