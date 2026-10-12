import json
import os
import sys

import pytest

import dump_marker_signs as dms
from travel_graph import SIGN_ITEM_ID

WALKABLE_GROUND = 1


def _dump(items_by_tile):
    """items_by_tile: list of (x, y, z, [item dicts]) -> minimal raw-otbm dump
    in the shape travel_graph._iter_dump_tiles expects (one feature per z)."""
    by_z = {}
    for x, y, z, items in items_by_tile:
        by_z.setdefault(z, []).append({"x": x, "y": y, "tileid": WALKABLE_GROUND, "items": items})
    return {"data": {"nodes": [{"features": [
        {"x": 0, "y": 0, "z": z, "tiles": tiles} for z, tiles in sorted(by_z.items())
    ]}]}}


def _sign(uid, text):
    return {"id": SIGN_ITEM_ID, "uid": uid, "text": text}


def test_snapshot_carries_uid_and_text_verbatim():
    # The uid is what ticket 03 needs to re-inject the sign, and
    # parse_marker_signs alone never returns it -- it collapses the sign to
    # id/type/x/y/z. Losing it here would make the transplant impossible.
    dump = _dump([
        (10, 20, 7, [_sign(10003, "ROOK-HUNT-0003")]),
        (11, 21, 8, [_sign(10001, "ROOK-TEMPLE-0001")]),
    ])

    snapshot = dms.build_snapshot(dump, city="ROOK", source_commit="abc123", source_otbm="x/ROOK.otbm")

    by_id = {s["id"]: s for s in snapshot["signs"]}
    assert by_id["ROOK-HUNT-0003"] == {
        "id": "ROOK-HUNT-0003", "type": "HUNT",
        "x": 10, "y": 20, "z": 7,
        "uid": 10003, "text": "ROOK-HUNT-0003",
    }
    assert by_id["ROOK-TEMPLE-0001"]["uid"] == 10001
    assert by_id["ROOK-TEMPLE-0001"]["z"] == 8


def test_snapshot_records_its_provenance():
    # An offset or a sign set with no provenance is a magic number; the
    # snapshot has to say which commit and which file it came from.
    snapshot = dms.build_snapshot(_dump([]), city="ROOK", source_commit="deadbee", source_otbm="a/b.otbm")

    assert snapshot["city"] == "ROOK"
    assert snapshot["sourceCommit"] == "deadbee"
    assert snapshot["sourceOtbm"] == "a/b.otbm"
    assert snapshot["signCount"] == 0
    assert snapshot["signs"] == []


def test_snapshot_is_ordered_by_id_so_two_runs_diff_cleanly():
    dump = _dump([
        (3, 3, 7, [_sign(10009, "ROOK-HUNT-0009")]),
        (1, 1, 7, [_sign(10002, "ROOK-DEPOT-0001")]),
        (2, 2, 7, [_sign(10005, "ROOK-HUNT-0005")]),
    ])

    snapshot = dms.build_snapshot(dump, city="ROOK", source_commit="c", source_otbm="o")

    assert [s["id"] for s in snapshot["signs"]] == [
        "ROOK-DEPOT-0001", "ROOK-HUNT-0005", "ROOK-HUNT-0009",
    ]


def test_an_ordinary_in_game_sign_is_not_a_marker():
    # uid below the reserved range is a real sign a player reads, not pipeline
    # input -- it must not end up in the snapshot, and must not be an issue.
    dump = _dump([
        (5, 5, 7, [_sign(200, "Welcome to Rookgaard")]),
        (6, 6, 7, [_sign(10004, "ROOK-HUNT-0004")]),
    ])

    snapshot = dms.build_snapshot(dump, city="ROOK", source_commit="c", source_otbm="o")

    assert [s["id"] for s in snapshot["signs"]] == ["ROOK-HUNT-0004"]
    assert snapshot["issues"] == []


def test_a_malformed_marker_is_carried_as_an_issue_not_dropped():
    # The 5-digit typo that happened live (ROOK-HUNT-00015). Silently dropping
    # it would make a POI vanish with no trace of why.
    dump = _dump([(7, 7, 7, [_sign(10015, "ROOK-HUNT-00015")])])

    snapshot = dms.build_snapshot(dump, city="ROOK", source_commit="c", source_otbm="o")

    assert snapshot["signs"] == []
    assert len(snapshot["issues"]) == 1
    assert snapshot["issues"][0]["reason"] == "invalid-sign-format"
    assert snapshot["issues"][0]["text"] == "ROOK-HUNT-00015"


def test_comparison_passes_when_the_id_sets_match():
    snapshot = {"signs": [{"id": "ROOK-HUNT-0001"}, {"id": "ROOK-TEMPLE-0001"}]}
    catalog = [
        {"id": "ROOK-TEMPLE-0001", "city": "ROOK"},
        {"id": "ROOK-HUNT-0001", "city": "ROOK"},
    ]

    result = dms.compare_with_catalog(snapshot, catalog, city="ROOK")

    assert result["ok"] is True
    assert result["matched"] == 2
    assert result["missingFromSnapshot"] == []
    assert result["missingFromCatalog"] == []


def test_comparison_names_a_poi_the_catalog_has_and_the_map_does_not():
    # This is the stop condition of ticket 01: catalog and map already
    # disagree, and cutting on top of that propagates the disagreement.
    snapshot = {"signs": [{"id": "ROOK-HUNT-0001"}]}
    catalog = [{"id": "ROOK-HUNT-0001", "city": "ROOK"}, {"id": "ROOK-HUNT-0002", "city": "ROOK"}]

    result = dms.compare_with_catalog(snapshot, catalog, city="ROOK")

    assert result["ok"] is False
    assert result["missingFromSnapshot"] == ["ROOK-HUNT-0002"]
    assert result["missingFromCatalog"] == []


def test_comparison_names_a_sign_with_no_catalog_entry():
    snapshot = {"signs": [{"id": "ROOK-HUNT-0001"}, {"id": "ROOK-QUEST-0001"}]}
    catalog = [{"id": "ROOK-HUNT-0001", "city": "ROOK"}]

    result = dms.compare_with_catalog(snapshot, catalog, city="ROOK")

    assert result["ok"] is False
    assert result["missingFromCatalog"] == ["ROOK-QUEST-0001"]


def test_comparison_ignores_npc_locations_and_other_cities():
    # NPC POIs come from <CIDADE>-npc.xml, never from a sign, so they can
    # never be in the snapshot -- counting them as missing would make the
    # gate fail on every healthy map. Another city's rows are not ours.
    snapshot = {"signs": [{"id": "ROOK-HUNT-0001"}]}
    catalog = [
        {"id": "ROOK-HUNT-0001", "city": "ROOK"},
        {"id": "ROOK-NPC-0007", "city": "ROOK", "type": "NPC"},
        {"id": "CARLIN-HUNT-0001", "city": "CARLIN"},
    ]

    result = dms.compare_with_catalog(snapshot, catalog, city="ROOK")

    assert result["ok"] is True
    assert result["matched"] == 1


def test_comparison_still_sees_a_row_that_lost_its_city_field():
    # ROOK-HUNT-0013 entrou no catálogo sem `city`. Filtrando só pelo campo, a
    # linha sai da conferência calada — e um portão que se desliga porque um
    # campo sumiu não é portão.
    snapshot = {"signs": [{"id": "ROOK-HUNT-0001"}]}
    catalog = [
        {"id": "ROOK-HUNT-0001", "city": "ROOK"},
        {"id": "ROOK-HUNT-0002", "type": "HUNT"},
    ]

    result = dms.compare_with_catalog(snapshot, catalog, city="ROOK")

    assert result["ok"] is False
    assert result["missingFromSnapshot"] == ["ROOK-HUNT-0002"]


def test_comparison_ignores_a_poi_born_from_a_quest_slug_marker():
    # A terceira procedência de POI não-NPC: item com uid na faixa de quest e o
    # slug no texto, que o autor pinta no mapa. Ele não tem placa e não deveria
    # ter — cobrar placa dele pararia o pipeline num mapa saudável.
    snapshot = {"signs": [{"id": "ROOK-HUNT-0001"}]}
    catalog = [
        {"id": "ROOK-HUNT-0001", "city": "ROOK", "x": 1, "y": 1, "z": 7},
        {"id": "ROOK-HUNT-0013", "city": "ROOK", "type": "HUNT", "x": 1188, "y": 1134, "z": 7},
    ]

    result = dms.compare_with_catalog(
        snapshot, catalog, city="ROOK", marker_positions={(1188, 1134, 7)}
    )

    assert result["ok"] is True
    assert result["matched"] == 1


def test_two_signs_with_the_same_text_on_one_tile_keep_the_first_uid():
    # parse_marker_signs promotes the FIRST occurrence and reports the rest as
    # duplicates. The uid join has to agree with it: keying by position+text
    # alone, a second sign on the same tile would overwrite the first's uid and
    # the transplant would silently re-inject the wrong one. O tipo é DEPOT, de
    # um tile só: em HUNT/TRAINING, placa repetida deixou de ser duplicata e
    # passou a ser o jeito de marcar os andares da hunt.
    dump = _dump([(4, 4, 7, [_sign(10007, "ROOK-DEPOT-0007"), _sign(10099, "ROOK-DEPOT-0007")])])

    snapshot = dms.build_snapshot(dump, city="ROOK", source_commit="c", source_otbm="o")

    assert len(snapshot["signs"]) == 1
    assert snapshot["signs"][0]["uid"] == 10007
    assert [i["reason"] for i in snapshot["issues"]] == ["duplicate-sign-id"]


def test_the_same_sign_text_at_two_positions_keeps_each_uid_apart():
    # A copy-pasted sign moved elsewhere: only the first becomes a location,
    # but the join must not confuse the two positions.
    dump = _dump([
        (1, 1, 7, [_sign(10007, "ROOK-HUNT-0007")]),
        (9, 9, 8, [_sign(10077, "ROOK-HUNT-0007")]),
    ])

    snapshot = dms.build_snapshot(dump, city="ROOK", source_commit="c", source_otbm="o")

    assert len(snapshot["signs"]) == 1
    assert snapshot["signs"][0] == {
        "id": "ROOK-HUNT-0007", "type": "HUNT", "x": 1, "y": 1, "z": 7,
        "uid": 10007, "text": "ROOK-HUNT-0007",
    }


# ======================================================
# CLI — the stop condition lives here, so it gets tested here
# ======================================================

def _city_fixture(tmp_path, monkeypatch, signs, catalog_locations, with_monster_xml=True, extra_tiles=()):
    """Lays out the three directories main() reads, plus a catalog to check
    against, and points the module's path constants at them — the same shape
    test_build_travel_fragment.py uses."""
    raw_maps = tmp_path / "raw-maps"
    full_maps = tmp_path / "full-maps" / "ROOK"
    snapshots = tmp_path / "sign-snapshots"
    raw_maps.mkdir(parents=True)
    full_maps.mkdir(parents=True)

    otbm = full_maps / "ROOK.otbm"
    otbm.write_bytes(b"not really an otbm, but it has bytes to hash")
    dump = _dump(
        [(i, 0, 7, [_sign(uid, text)]) for i, (uid, text) in enumerate(signs)] + list(extra_tiles)
    )
    (raw_maps / "ROOK.raw.json").write_text(json.dumps(dump), encoding="utf-8")
    # The dump must look newer than the .otbm or the freshness gate fires.
    os.utime(raw_maps / "ROOK.raw.json", (os.path.getmtime(otbm) + 10,) * 2)

    if with_monster_xml:
        (full_maps / "ROOK-monster.xml").write_text("<monsters></monsters>", encoding="utf-8")

    tibia_idle = tmp_path / "tibia-idle"
    catalog_path = tibia_idle / "catalog-source.json"
    tibia_idle.mkdir()
    catalog_path.write_text(json.dumps({"locations": catalog_locations}), encoding="utf-8")

    monkeypatch.setattr(dms, "RAW_MAPS_DIR", str(raw_maps))
    monkeypatch.setattr(dms, "FULL_MAPS_DIR", str(tmp_path / "full-maps"))
    monkeypatch.setattr(dms, "SNAPSHOTS_DIR", str(snapshots))
    monkeypatch.setattr(dms.paths.TIBIA_IDLE, "require", lambda from_flag=None: str(tibia_idle))
    monkeypatch.setattr(dms.content_export, "catalog_source_path", lambda d: str(catalog_path))
    monkeypatch.setattr(dms, "_source_commit", lambda otbm_path: "abc1234")
    monkeypatch.setattr(sys, "argv", ["dump_marker_signs.py", "ROOK"])
    return snapshots, otbm


def test_cli_writes_the_snapshot_when_map_and_catalog_agree(tmp_path, monkeypatch, capsys):
    snapshots, _ = _city_fixture(
        tmp_path, monkeypatch,
        signs=[(10001, "ROOK-HUNT-0001"), (10013, "ROOK-TEMPLE-0001")],
        catalog_locations=[
            {"id": "ROOK-HUNT-0001", "city": "ROOK", "type": "HUNT"},
            {"id": "ROOK-TEMPLE-0001", "city": "ROOK", "type": "TEMPLE"},
            {"id": "ROOK-NPC-0001", "city": "ROOK", "type": "NPC"},
        ],
    )

    dms.main()

    written = json.loads((snapshots / "ROOK-abc1234.json").read_text(encoding="utf-8"))
    assert [s["id"] for s in written["signs"]] == ["ROOK-HUNT-0001", "ROOK-TEMPLE-0001"]
    assert written["sourceSha256"]
    assert (snapshots / "ROOK-abc1234-monster.xml").exists()


def test_cli_stops_and_writes_nothing_when_the_catalog_has_a_poi_the_map_lacks(tmp_path, monkeypatch, capsys):
    # The stop condition of ticket 01: map and catalog already disagree, so
    # cutting a new map on top of it would propagate the disagreement.
    snapshots, _ = _city_fixture(
        tmp_path, monkeypatch,
        signs=[(10001, "ROOK-HUNT-0001")],
        catalog_locations=[
            {"id": "ROOK-HUNT-0001", "city": "ROOK", "type": "HUNT"},
            {"id": "ROOK-HUNT-0002", "city": "ROOK", "type": "HUNT"},
        ],
    )

    with pytest.raises(SystemExit) as exit_info:
        dms.main()

    assert exit_info.value.code != 0
    assert "discordam" in str(exit_info.value.code)
    assert "ROOK-HUNT-0002" in capsys.readouterr().out
    assert not snapshots.exists(), "um snapshot escrito depois da parada seria lido como bom"


def test_cli_stops_when_the_raw_dump_is_older_than_the_otbm(tmp_path, monkeypatch):
    snapshots, otbm = _city_fixture(
        tmp_path, monkeypatch,
        signs=[(10001, "ROOK-HUNT-0001")],
        catalog_locations=[{"id": "ROOK-HUNT-0001", "city": "ROOK", "type": "HUNT"}],
    )
    dump_path = os.path.join(dms.RAW_MAPS_DIR, "ROOK.raw.json")
    os.utime(dump_path, (os.path.getmtime(otbm) - 10,) * 2)

    with pytest.raises(SystemExit) as exit_info:
        dms.main()

    assert "mais antigo" in str(exit_info.value.code)
    assert "dump_otbm.js ROOK" in str(exit_info.value.code)
    assert not snapshots.exists()


def test_cli_warns_but_does_not_fail_when_the_spawn_export_is_missing(tmp_path, monkeypatch, capsys):
    snapshots, _ = _city_fixture(
        tmp_path, monkeypatch,
        signs=[(10001, "ROOK-HUNT-0001")],
        catalog_locations=[{"id": "ROOK-HUNT-0001", "city": "ROOK", "type": "HUNT"}],
        with_monster_xml=False,
    )

    dms.main()

    assert (snapshots / "ROOK-abc1234.json").exists()
    assert "conferência de roster" in capsys.readouterr().out


def test_cli_does_not_demand_a_sign_for_a_poi_that_stands_on_a_quest_marker(tmp_path, monkeypatch):
    # O caso real de ROOK-HUNT-0013: POI não-NPC, sem placa, nascido do marcador
    # `copper_shield_quest`. O marcador é pintado no mapa-mundo e sobrevive ao
    # recorte sozinho, então exigir placa dele pararia o pipeline sem motivo.
    snapshots, _ = _city_fixture(
        tmp_path, monkeypatch,
        signs=[(10001, "ROOK-HUNT-0001")],
        catalog_locations=[
            {"id": "ROOK-HUNT-0001", "city": "ROOK", "type": "HUNT", "x": 0, "y": 0, "z": 7},
            {"id": "ROOK-HUNT-0013", "type": "HUNT", "x": 40, "y": 41, "z": 7},
        ],
        extra_tiles=[(40, 41, 7, [{"id": 2014, "uid": 20001, "text": "copper_shield_quest"}])],
    )

    dms.main()

    written = json.loads((snapshots / "ROOK-abc1234.json").read_text(encoding="utf-8"))
    assert [s["id"] for s in written["signs"]] == ["ROOK-HUNT-0001"]
