import json

import build_travel_fragment as btf
from travel_graph import SIGN_ITEM_ID


def _dump_with_signs(signs):
    """signs: list of (uid, text) -> a minimal raw-otbm dump with one sign
    per tile, matching the shape otbm_dump.iter_tiles expects."""
    tiles = [
        {"x": i, "y": 0, "items": [{"id": SIGN_ITEM_ID, "uid": uid, "text": text}]}
        for i, (uid, text) in enumerate(signs)
    ]
    return {"data": {"nodes": [{"features": [{"x": 0, "y": 0, "z": 7, "tiles": tiles}]}]}}


def _write_region_fixture(tmp_path, monkeypatch, signs):
    raw_maps_dir = tmp_path / "raw-maps"
    full_maps_dir = tmp_path / "full-maps" / "ROOK"
    raw_maps_dir.mkdir(parents=True)
    full_maps_dir.mkdir(parents=True)

    (raw_maps_dir / "ROOK.raw.json").write_text(
        json.dumps(_dump_with_signs(signs)), encoding="utf-8"
    )
    (full_maps_dir / "map.json").write_text(json.dumps({"objectDefs": {}}), encoding="utf-8")

    monkeypatch.setattr(btf, "RAW_MAPS_DIR", str(raw_maps_dir))
    monkeypatch.setattr(btf, "FULL_MAPS_DIR", str(tmp_path / "full-maps"))


def test_build_region_fragment_warns_specifically_about_a_malformed_sign(tmp_path, monkeypatch, capsys):
    # Real bug: a 5-digit typo (ROOK-HUNT-00015) used to print the exact same
    # generic message as a duplicate-id sign — must now name the real reason.
    _write_region_fixture(tmp_path, monkeypatch, [(10015, "ROOK-HUNT-00015")])

    btf.build_region_fragment("ROOK", str(tmp_path / "no-canary-here"))

    out = capsys.readouterr().out
    assert "fora do formato CIDADE-TIPO-NNNN" in out
    assert "id duplicado" not in out


def test_build_region_fragment_warns_specifically_about_a_duplicate_sign(tmp_path, monkeypatch, capsys):
    # Real bug: ROOK-HUNT-0006 placed twice (same uid/text) is a perfectly
    # well-formed id — must not be misreported as a format problem.
    _write_region_fixture(
        tmp_path, monkeypatch, [(10006, "ROOK-HUNT-0006"), (10006, "ROOK-HUNT-0006")]
    )

    btf.build_region_fragment("ROOK", str(tmp_path / "no-canary-here"))

    out = capsys.readouterr().out
    assert "id duplicado" in out
    assert "fora do formato CIDADE-TIPO-NNNN" not in out


def test_build_region_fragment_takes_a_single_city_argument_no_separate_prefix(tmp_path, monkeypatch):
    # Ticket 05: `region` (positional) + `--city-prefix` collapse into one
    # argument — the city code doubles as both the full-maps/<CIDADE>/
    # lookup key and the NPC id prefix.
    _write_region_fixture(tmp_path, monkeypatch, [])

    fragment = btf.build_region_fragment("ROOK", str(tmp_path / "no-canary-here"))

    assert fragment == {"locations": [], "travelGraph": []}
