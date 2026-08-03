import json
import sys

import pytest

import build_hunt_fragment as bhf


_RESPAWN = {
    "mapBoundsRef": {"minX": 0, "minY": 0, "maxX": 10, "maxY": 10},
    "monsterDefs": {},
    "spawns": [],
}


def _make_ready_map(tmp_path, city, folder):
    map_dir = tmp_path / "ready-maps" / city / folder / "monsters"
    map_dir.mkdir(parents=True)
    (map_dir / "respawn.json").write_text(json.dumps(_RESPAWN), encoding="utf-8")


def _db(hunts=None, monsters=None, loot=None):
    return {"hunts": hunts or [], "monsters": monsters or [], "loot": loot or []}


def _write_db(tmp_path, db):
    db_dir = tmp_path / "tibia-idle" / "apps" / "tibia-idle-mock-api"
    db_dir.mkdir(parents=True)
    db_path = db_dir / "db.json"
    db_path.write_text(json.dumps(db), encoding="utf-8")
    return str(db_path)


def _run(tmp_path, monkeypatch, argv, db=None):
    monkeypatch.setattr(bhf, "READY_MAPS_DIR", str(tmp_path / "ready-maps"))
    db_path = _write_db(tmp_path, db) if db is not None else None
    full_argv = ["build_hunt_fragment.py", *argv]
    if db is not None:
        full_argv += ["--tibia-idle-dir", str(tmp_path / "tibia-idle")]
    monkeypatch.setattr(sys, "argv", full_argv)
    bhf.main()
    return db_path


def test_folder_id_matching_map_id_succeeds(tmp_path, monkeypatch):
    _make_ready_map(tmp_path, "ROOK", "ROOK-HUNT-0010_bears-rookguard")

    _run(tmp_path, monkeypatch, ["ROOK-HUNT-0010_bears-rookguard", "--map-id", "ROOK-HUNT-0010"])

    fragment_path = tmp_path / "ready-maps" / "ROOK" / "ROOK-HUNT-0010_bears-rookguard" / "db-fragment.json"
    assert fragment_path.exists()
    fragment = json.loads(fragment_path.read_text(encoding="utf-8"))
    assert fragment["hunts"]["mapId"] == "ROOK-HUNT-0010"


def test_map_id_diverging_from_folder_id_is_a_hard_error(tmp_path, monkeypatch, capsys):
    _make_ready_map(tmp_path, "ROOK", "ROOK-HUNT-0014_bears-rookguard")

    with pytest.raises(SystemExit) as exc_info:
        _run(tmp_path, monkeypatch, ["ROOK-HUNT-0014_bears-rookguard", "--map-id", "ROOK-HUNT-0013"])

    assert exc_info.value.code == 1
    out = capsys.readouterr().out
    assert "ROOK-HUNT-0013" in out
    assert "ROOK-HUNT-0014" in out


def test_new_id_without_edit_succeeds_as_a_fresh_creation(tmp_path, monkeypatch):
    _make_ready_map(tmp_path, "ROOK", "ROOK-HUNT-0020_new-area")
    db_path = _run(
        tmp_path, monkeypatch,
        ["ROOK-HUNT-0020_new-area", "--map-id", "ROOK-HUNT-0020", "--write-db"],
        db=_db(),
    )

    db = json.loads(open(db_path, encoding="utf-8").read())
    assert db["hunts"][0]["mapId"] == "ROOK-HUNT-0020"
    assert db["monsters"][0]["mapId"] == "ROOK-HUNT-0020"


def test_existing_id_without_edit_is_a_hard_error_and_writes_nothing(tmp_path, monkeypatch, capsys):
    _make_ready_map(tmp_path, "ROOK", "ROOK-HUNT-0010_bears-rookguard")
    db_path = str(tmp_path / "tibia-idle" / "apps" / "tibia-idle-mock-api" / "db.json")

    with pytest.raises(SystemExit) as exc_info:
        _run(
            tmp_path, monkeypatch,
            ["ROOK-HUNT-0010_bears-rookguard", "--map-id", "ROOK-HUNT-0010", "--write-db"],
            db=_db(hunts=[{"mapId": "ROOK-HUNT-0010", "name": "Curated Bears"}]),
        )

    assert exc_info.value.code == 1
    out = capsys.readouterr().out
    assert "ROOK-HUNT-0010" in out
    assert "--edit" in out

    db = json.loads(open(db_path, encoding="utf-8").read())
    assert db["hunts"] == [{"mapId": "ROOK-HUNT-0010", "name": "Curated Bears"}]
    assert db["monsters"] == []


def test_existing_id_with_edit_succeeds_and_updates_mechanical_collections(tmp_path, monkeypatch):
    _make_ready_map(tmp_path, "ROOK", "ROOK-HUNT-0010_bears-rookguard")

    db_path = _run(
        tmp_path, monkeypatch,
        ["ROOK-HUNT-0010_bears-rookguard", "--map-id", "ROOK-HUNT-0010", "--write-db", "--edit"],
        db=_db(
            hunts=[{"mapId": "ROOK-HUNT-0010", "name": "Curated Bears"}],
            monsters=[{"mapId": "ROOK-HUNT-0010", "monsterDefs": {"stale": True}}],
        ),
    )

    db = json.loads(open(db_path, encoding="utf-8").read())
    # hunts stays curated (never overwritten by the mechanical merge)...
    assert db["hunts"] == [{"mapId": "ROOK-HUNT-0010", "name": "Curated Bears"}]
    # ...but monsters/loot (100% mechanical) are refreshed.
    assert db["monsters"][0]["monsterDefs"] == {}
