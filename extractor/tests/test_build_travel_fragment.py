import json

import build_travel_fragment as btf
from travel_graph import SIGN_ITEM_ID

# A ground tile with no flags at all is walkable, so a fixture only has to
# say where the tiles are; `unpass` never comes up unless a test wants it.
WALKABLE_GROUND = 1


def _dump_with_signs(signs, npc_tiles=()):
    """signs: list of (uid, text) -> a minimal raw-otbm dump with one sign
    per tile, matching the shape travel_graph.py's _iter_dump_tiles expects.
    `npc_tiles` adds plain walkable tiles at given (x, y) so an NPC standing
    there has somewhere to stand."""
    tiles = [
        {"x": i, "y": 0, "tileid": WALKABLE_GROUND,
         "items": [{"id": SIGN_ITEM_ID, "uid": uid, "text": text}]}
        for i, (uid, text) in enumerate(signs)
    ]
    tiles += [{"x": x, "y": y, "tileid": WALKABLE_GROUND, "items": []} for x, y in npc_tiles]
    return {"data": {"nodes": [{"features": [{"x": 0, "y": 0, "z": 7, "tiles": tiles}]}]}}


def _write_city_fixture(tmp_path, monkeypatch, signs, npcs=(), hunt_folders=()):
    raw_maps_dir = tmp_path / "raw-maps"
    full_maps_dir = tmp_path / "full-maps" / "ROOK"
    raw_maps_dir.mkdir(parents=True)
    full_maps_dir.mkdir(parents=True)

    (raw_maps_dir / "ROOK.raw.json").write_text(
        json.dumps(_dump_with_signs(signs, [(x, y) for _, x, y in npcs])), encoding="utf-8"
    )
    (full_maps_dir / "map.json").write_text(json.dumps({"objectDefs": {}}), encoding="utf-8")

    if npcs:
        placements = "".join(
            f'<npc centerx="{x}" centery="{y}" centerz="7" radius="1">'
            f'<npc name="{name}" x="0" y="0" z="7" spawntime="60" /></npc>'
            for name, x, y in npcs
        )
        (full_maps_dir / "ROOK-npc.xml").write_text(f"<npcs>{placements}</npcs>", encoding="utf-8")

    for folder in hunt_folders:
        (tmp_path / "maps" / "ROOK" / folder).mkdir(parents=True)

    monkeypatch.setattr(btf, "RAW_MAPS_DIR", str(raw_maps_dir))
    monkeypatch.setattr(btf, "FULL_MAPS_DIR", str(tmp_path / "full-maps"))
    monkeypatch.setattr(btf, "MAPS_DIR", str(tmp_path / "maps"))


def test_build_city_fragment_warns_specifically_about_a_malformed_sign(tmp_path, monkeypatch, capsys):
    # Real bug: a 5-digit typo (ROOK-HUNT-00015) used to print the exact same
    # generic message as a duplicate-id sign — must now name the real reason.
    _write_city_fixture(tmp_path, monkeypatch, [(10015, "ROOK-HUNT-00015")])

    btf.build_city_fragment("ROOK", str(tmp_path / "no-canary-here"))

    out = capsys.readouterr().out
    assert "fora do formato CIDADE-TIPO-NNNN" in out
    assert "id duplicado" not in out


def test_build_city_fragment_warns_specifically_about_a_duplicate_sign(tmp_path, monkeypatch, capsys):
    # Real bug: ROOK-HUNT-0006 placed twice (same uid/text) is a perfectly
    # well-formed id — must not be misreported as a format problem.
    _write_city_fixture(
        tmp_path, monkeypatch, [(10006, "ROOK-HUNT-0006"), (10006, "ROOK-HUNT-0006")]
    )

    btf.build_city_fragment("ROOK", str(tmp_path / "no-canary-here"))

    out = capsys.readouterr().out
    assert "id duplicado" in out
    assert "fora do formato CIDADE-TIPO-NNNN" not in out


def test_build_city_fragment_takes_a_single_city_argument_no_separate_prefix(tmp_path, monkeypatch):
    # Ticket 05: `region` (positional) + `--city-prefix` collapse into one
    # argument — the city code doubles as both the full-maps/<CIDADE>/
    # lookup key and the NPC id prefix.
    _write_city_fixture(tmp_path, monkeypatch, [])

    fragment, rejections = btf.build_city_fragment("ROOK", str(tmp_path / "no-canary-here"))

    assert fragment == {"locations": [], "travelGraph": []}
    assert rejections == []


def test_build_city_fragment_makes_every_npc_a_node_of_the_travel_graph(tmp_path, monkeypatch):
    # The gap this ticket closes: the CLI already loaded NPC coordinates and
    # simply never handed them to the BFS, so "viajar até a Norma" had no
    # destination to travel to.
    _write_city_fixture(
        tmp_path, monkeypatch,
        signs=[(10001, "ROOK-TEMPLE-0001")],
        npcs=[("Norma", 1, 0), ("Obi", 2, 0)],
    )

    fragment, rejections = btf.build_city_fragment("ROOK", str(tmp_path / "no-canary-here"))

    ids = {loc["id"] for loc in fragment["locations"]}
    assert ids == {"ROOK-TEMPLE-0001", "ROOK-NPC-norma", "ROOK-NPC-obi"}
    by_pair = {frozenset((e["from"], e["to"])): e["tileCount"] for e in fragment["travelGraph"]}
    # Tiles actually walked, not a coordinate subtraction: the temple sits on
    # tile 0, Norma on 1, Obi on 2, all in one walkable row.
    assert by_pair[frozenset(("ROOK-TEMPLE-0001", "ROOK-NPC-norma"))] == 1
    assert by_pair[frozenset(("ROOK-TEMPLE-0001", "ROOK-NPC-obi"))] == 2
    assert by_pair[frozenset(("ROOK-NPC-norma", "ROOK-NPC-obi"))] == 1
    assert rejections == []


def test_build_city_fragment_rejects_a_poi_that_reaches_nothing(tmp_path, monkeypatch):
    # Two signs on tiles 0 and 1 reach each other; the NPC is dropped far
    # away on a tile that touches nothing.
    _write_city_fixture(
        tmp_path, monkeypatch,
        signs=[(10001, "ROOK-TEMPLE-0001"), (10002, "ROOK-DEPOT-0001")],
        npcs=[("Norma", 40, 40)],
    )

    fragment, rejections = btf.build_city_fragment("ROOK", str(tmp_path / "no-canary-here"))

    assert {loc["id"] for loc in fragment["locations"]} == {"ROOK-TEMPLE-0001", "ROOK-DEPOT-0001"}
    assert rejections == [{"reason": "poi-without-edge", "id": "ROOK-NPC-norma", "type": "NPC",
                           "x": 40, "y": 40, "z": 7}]


def test_build_city_fragment_reports_a_hunt_map_whose_entrance_has_no_sign(tmp_path, monkeypatch):
    _write_city_fixture(
        tmp_path, monkeypatch,
        signs=[(10001, "ROOK-TEMPLE-0001"), (10002, "ROOK-HUNT-0001")],
        hunt_folders=["ROOK-HUNT-0001_rats-sewers", "ROOK-HUNT-0018_bugs-rookguard", "training-spots"],
    )

    _, rejections = btf.build_city_fragment("ROOK", str(tmp_path / "no-canary-here"))

    assert rejections == [{"reason": "hunt-without-poi", "id": "ROOK-HUNT-0018",
                           "name": "bugs-rookguard"}]


def test_discover_hunt_maps_skips_folders_with_no_id_prefix(tmp_path, monkeypatch):
    _write_city_fixture(
        tmp_path, monkeypatch, signs=[],
        hunt_folders=["ROOK-HUNT-0002_rats-sewers", "training-spots", "TEST-HUNT-0001_scratch"],
    )

    assert btf.discover_hunt_maps("ROOK") == [{"id": "ROOK-HUNT-0002", "name": "rats-sewers"}]
