import json
import os
import sys

import pytest

SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import appearance_flags as af


def _write(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handler:
        json.dump(payload, handler, indent=2, sort_keys=True)
        handler.write("\n")


def test_table_without_overrides_is_pure_derivation(tmp_path):
    _write(str(tmp_path / "ROOK.json"), {"100": {"unpass": True}})

    merged = af.load_flags("ROOK", flags_dir=str(tmp_path))

    assert merged == {"100": {"unpass": True}}


def test_override_wins_over_the_derived_value(tmp_path):
    _write(str(tmp_path / "ROOK.json"), {"100": {"unpass": True}})
    _write(str(tmp_path / "ROOK.overrides.json"), {"100": {"unpass": False}})

    merged = af.load_flags("ROOK", flags_dir=str(tmp_path))

    assert merged["100"]["unpass"] is False


def test_override_replaces_the_entry_rather_than_merging_keys(tmp_path):
    """Um override é a resposta final para aquele id. Mesclar chave a chave
    deixaria a derivação reintroduzir pela porta dos fundos justamente o valor
    que a curadoria existe para corrigir."""
    _write(str(tmp_path / "ROOK.json"), {"100": {"unpass": True, "bank": 1}})
    _write(str(tmp_path / "ROOK.overrides.json"), {"100": {"bank": 1}})

    merged = af.load_flags("ROOK", flags_dir=str(tmp_path))

    assert merged["100"] == {"bank": 1}
    assert "unpass" not in merged["100"]


def test_override_can_add_an_id_the_derivation_never_saw(tmp_path):
    _write(str(tmp_path / "ROOK.json"), {"100": {"unpass": True}})
    _write(str(tmp_path / "ROOK.overrides.json"), {"999": {"isFloorTransition": True}})

    merged = af.load_flags("ROOK", flags_dir=str(tmp_path))

    assert merged["999"] == {"isFloorTransition": True}
    assert merged["100"] == {"unpass": True}


def test_regenerating_the_table_never_touches_the_overrides_file(tmp_path):
    """A regra mecânico-vs-curado do CONTEXT.md: regenerar não pode destruir
    informação, senão --force vira armadilha."""
    overrides_path = str(tmp_path / "ROOK.overrides.json")
    _write(overrides_path, {"100": {"unpass": False}})
    before = open(overrides_path, encoding="utf-8").read()

    af.write_table("ROOK", {"100": {"unpass": True}, "200": {}}, flags_dir=str(tmp_path))

    assert open(overrides_path, encoding="utf-8").read() == before
    assert af.load_flags("ROOK", flags_dir=str(tmp_path))["100"]["unpass"] is False


def test_written_table_drops_falsy_flags(tmp_path):
    """Mesma convenção do objectDefs que a tabela substitui: só flag verdadeira
    é gravada, então ausência e falso são a mesma coisa para quem lê."""
    af.write_table("ROOK", {"100": {"unpass": True, "top": False}}, flags_dir=str(tmp_path))

    with open(str(tmp_path / "ROOK.json"), encoding="utf-8") as handler:
        written = json.load(handler)

    assert written["100"] == {"unpass": True}


def test_missing_table_fails_loudly_naming_the_generator(tmp_path):
    with pytest.raises(af.MissingFlagsTableError) as excinfo:
        af.load_flags("NOWHERE", flags_dir=str(tmp_path))

    assert "build_appearance_flags" in str(excinfo.value)
    assert "NOWHERE" in str(excinfo.value)


def test_missing_overrides_file_is_fine(tmp_path):
    _write(str(tmp_path / "ROOK.json"), {"100": {"unpass": True}})

    assert af.load_flags("ROOK", flags_dir=str(tmp_path)) == {"100": {"unpass": True}}
