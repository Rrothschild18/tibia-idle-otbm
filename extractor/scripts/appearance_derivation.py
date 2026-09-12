"""Flags derivadas a partir das flags cruas de uma appearance.

Uma definição só, porque dois lugares precisam da mesma resposta e divergir
entre eles é silencioso: `build_phaser_map.analyze_item` (que monta o mapa) e
`build_appearance_flags` (que monta a tabela que o travel-graph lê).

A primeira versão da tabela de flags dumpava as flags **cruas** do
`appearances.dat`. O `unpass` batia, porque é cru — mas `isFloorTransition` e
`isRoof` **não existem** no protobuf: são heurísticas derivadas aqui. A tabela
saiu com `isFloorTransition` em zero, o BFS perdeu as escadas, e uma location
de hunt sumiu do grafo sem erro nenhum. Daí este módulo.
"""

TILE_SIZE = 32


def derived_flags(raw_flags: dict, sprite_info: dict) -> dict:
    """`{isRoof, isFloorTransition, hookDirection}` a partir do que o
    `appearances.dat` traz cru."""
    flags = raw_flags or {}
    info = sprite_info or {}

    has_unmove = flags.get("unmove", False)
    has_unpass = flags.get("unpass", False)
    has_unsight = flags.get("unsight", False)
    has_automap = flags.get("automap") is not None
    has_bank = flags.get("bank") is not None
    has_usable = flags.get("usable", False)
    has_forceuse = flags.get("forceuse", False)

    hook_raw = flags.get("hook", {})
    hook_direction = hook_raw.get("direction") if isinstance(hook_raw, dict) else None

    pattern_width = info.get("patternWidth", 1)
    pattern_height = info.get("patternHeight", 1)
    pattern_depth = info.get("patternDepth", 1)
    bounding_square = pattern_width * pattern_height * TILE_SIZE

    # Telhado: unpass + unmove + unsight + automap + bank, área de pelo menos
    # dois tiles e caixa por direção.
    is_roof = (
        has_unmove
        and has_unpass
        and has_unsight
        and has_automap
        and has_bank
        and bounding_square >= 64
        and pattern_depth >= 1
    )

    # Escada/buraco não tem flag dedicada no OTBM — esta é a combinação
    # observada em toda appearance conhecida de transição (386, 421, 1948,
    # 12202; ver ADR 0002). `bank` é deliberadamente **não** exigido: o item
    # 1948, a escada de skeletons-rookguard, não o tem — e nenhum item
    # não-transição do conjunto compartilha esta combinação de 4 flags, então
    # dispensar `bank` não introduz falso positivo.
    is_floor_transition = has_usable and has_forceuse and has_unmove and has_automap

    return {
        "isRoof": is_roof,
        "isFloorTransition": is_floor_transition,
        "hookDirection": hook_direction,
    }


# As flags cruas que o pipeline de fato consome. O `appearances.dat` traz
# dezenas de outras (`market`, `take`, `light`, `cyclopediaitem`…) que só
# engordariam a tabela versionada sem consumidor nenhum.
CONSUMED_RAW_FLAGS = (
    "fullbank", "unmove", "unpass", "unsight", "automap", "bank",
    "clip", "bottom", "top", "hang", "usable", "forceuse",
)


def pipeline_flags(raw_flags: dict, sprite_info: dict) -> dict:
    """As flags como `analyze_item` as emite: as cruas consumidas + as derivadas.

    É esta forma — e não a crua — que a tabela de `appearance-flags/` guarda,
    porque é esta que `travel_graph` lê.
    """
    flags = raw_flags or {}
    result = {}
    for name in CONSUMED_RAW_FLAGS:
        if name in ("automap", "bank"):
            result[name] = flags.get(name) is not None
        else:
            result[name] = flags.get(name, False)
    result.update(derived_flags(flags, sprite_info))
    return result
