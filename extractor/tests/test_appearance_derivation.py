import os
import sys

SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import appearance_derivation as ad

STAIRS = {"usable": True, "forceuse": True, "unmove": True, "automap": {"color": 210}}
ROOF = {"unmove": True, "unpass": True, "unsight": True,
        "automap": {"color": 0}, "bank": {"waypoints": 1}}
BIG = {"patternWidth": 2, "patternHeight": 1, "patternDepth": 1}


def test_stairs_combo_is_a_floor_transition():
    assert ad.derived_flags(STAIRS, {})["isFloorTransition"] is True


def test_bank_is_not_required_for_a_floor_transition():
    """Item 1948, a escada de skeletons-rookguard, não tem `bank` — exigir
    `bank` a deixaria de fora e a hunt ficaria inalcançável."""
    assert "bank" not in STAIRS
    assert ad.derived_flags(STAIRS, {})["isFloorTransition"] is True


def test_dropping_any_of_the_four_flags_stops_being_a_transition():
    for missing in ("usable", "forceuse", "unmove", "automap"):
        flags = {k: v for k, v in STAIRS.items() if k != missing}
        assert ad.derived_flags(flags, {})["isFloorTransition"] is False, missing


def test_roof_needs_two_tiles_of_area():
    assert ad.derived_flags(ROOF, BIG)["isRoof"] is True
    assert ad.derived_flags(ROOF, {"patternWidth": 1, "patternHeight": 1})["isRoof"] is False


def test_hook_direction_is_read_out_of_the_hook_table():
    assert ad.derived_flags({"hook": {"direction": "south"}}, {})["hookDirection"] == "south"
    assert ad.derived_flags({}, {})["hookDirection"] is None


def test_hook_that_is_not_a_table_does_not_explode():
    assert ad.derived_flags({"hook": True}, {})["hookDirection"] is None


def test_pipeline_flags_carry_the_derived_ones():
    """O bug que o golden pegou: a tabela de flags nasceu dumpando as flags
    **cruas** do appearances.dat. `unpass` batia, mas `isFloorTransition` não
    existe lá — é derivada. A tabela saiu com zero transições, o BFS perdeu as
    escadas, e uma location de hunt sumiu do grafo sem erro nenhum."""
    result = ad.pipeline_flags(STAIRS, {})

    assert result["isFloorTransition"] is True
    assert result["unpass"] is False


def test_pipeline_flags_drop_raw_keys_nothing_consumes():
    """O appearances.dat traz dezenas de flags (`market`, `take`, `light`…) que
    só engordariam a tabela versionada sem consumidor."""
    result = ad.pipeline_flags({"market": {"category": 1}, "take": True, "unpass": True}, {})

    assert "market" not in result
    assert "take" not in result
    assert result["unpass"] is True


def test_automap_and_bank_become_booleans():
    """As duas chegam como tabela no protobuf; o pipeline só pergunta se existem."""
    result = ad.pipeline_flags({"automap": {"color": 210}, "bank": {"waypoints": 1}}, {})

    assert result["automap"] is True
    assert result["bank"] is True


def test_the_real_rook_table_still_has_its_four_transitions():
    """Regressão direta do bug: a tabela versionada tem que carregar as quatro
    transições de andar do ROOK. Zero aqui significa grafo sem escadas."""
    import json
    path = os.path.join(SCRIPTS_DIR, "..", "appearance-flags", "ROOK.json")
    if not os.path.exists(path):
        import pytest
        pytest.skip("tabela do ROOK não gerada nesta máquina")

    with open(path, encoding="utf-8") as handler:
        table = json.load(handler)

    transitions = [i for i, f in table.items() if f.get("isFloorTransition")]
    assert len(transitions) == 4, transitions
