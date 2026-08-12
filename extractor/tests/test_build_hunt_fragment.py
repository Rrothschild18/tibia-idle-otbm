import json
import sys

import pytest

import build_hunt_fragment as bhf


_RESPAWN = {
    "mapBoundsRef": {"minX": 0, "minY": 0, "maxX": 10, "maxY": 10},
    "monsterDefs": {},
    "spawns": [],
}


def _make_ready_map(tmp_path, city, folder, with_source=True):
    """The built output under ready-maps/, plus (by default) the source map
    folder it came from — the export refuses a ready-map whose source is
    gone, so a fixture that wants to reach the catalog needs both."""
    map_dir = tmp_path / "ready-maps" / city / folder / "monsters"
    map_dir.mkdir(parents=True)
    (map_dir / "respawn.json").write_text(json.dumps(_RESPAWN), encoding="utf-8")
    if with_source:
        (tmp_path / "maps" / city / folder).mkdir(parents=True)


def _catalog(hunts=None):
    return {"hunts": hunts or [], "locations": [], "travelGraph": []}


class _Target:
    """Where --export writes, in a tmp tibia-idle checkout: the catalog plus
    the three runtime-read files under content/hunts/."""

    def __init__(self, tmp_path):
        self.root = tmp_path / "tibia-idle"
        content = self.root / "apps" / "tibia-idle-api" / "content"
        self.catalog_path = content / "catalog-source.json"
        self.hunts_dir = content / "hunts"

    def write(self, catalog, loot=None):
        self.catalog_path.parent.mkdir(parents=True, exist_ok=True)
        self.catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
        if loot is not None:
            self.hunts_dir.mkdir(parents=True, exist_ok=True)
            (self.hunts_dir / "loot.json").write_text(json.dumps(loot), encoding="utf-8")

    def _read(self, path, fallback=None):
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else fallback

    @property
    def catalog(self):
        return self._read(self.catalog_path)

    @property
    def loot(self):
        return self._read(self.hunts_dir / "loot.json", [])

    @property
    def manifest(self):
        return self._read(self.hunts_dir / "hunts.json", [])

    def respawn(self, map_id):
        return self._read(self.hunts_dir / "respawn" / f"{map_id}.json")


def _run(tmp_path, monkeypatch, argv, catalog=None, loot=None):
    monkeypatch.setattr(bhf, "READY_MAPS_DIR", str(tmp_path / "ready-maps"))
    monkeypatch.setattr(bhf, "MAPS_DIR", str(tmp_path / "maps"))
    target = _Target(tmp_path)
    full_argv = ["build_hunt_fragment.py", *argv]
    if catalog is not None:
        target.write(catalog, loot)
        full_argv += ["--tibia-idle-dir", str(target.root)]
    monkeypatch.setattr(sys, "argv", full_argv)
    bhf.main()
    return target


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


def test_export_writes_the_hunt_to_every_destination_the_back_end_reads(tmp_path, monkeypatch):
    _make_ready_map(tmp_path, "ROOK", "ROOK-HUNT-0020_new-area")

    target = _run(
        tmp_path, monkeypatch,
        ["ROOK-HUNT-0020_new-area", "--map-id", "ROOK-HUNT-0020", "--export"],
        catalog=_catalog(),
    )

    # The catalog gets the hunt; content/hunts/ gets loot + respawn; the
    # manifest is a projection of the catalog, written from the same run.
    assert target.catalog["hunts"][0]["mapId"] == "ROOK-HUNT-0020"
    assert target.loot[0]["mapId"] == "ROOK-HUNT-0020"
    assert target.respawn("ROOK-HUNT-0020") == _RESPAWN
    assert target.manifest == [{
        "id": "ROOK-HUNT-0020",
        "mapId": "ROOK-HUNT-0020",
        "mapUrl": "assets/ROOK-HUNT-0020_new-area-sprites-v6/map.json",
        "startPosition": [5, 5],
    }]


def test_export_respawn_file_carries_no_wrapper_fields(tmp_path, monkeypatch):
    # The back-end hands the payload straight to Phaser, so id/mapId/assetsRoot
    # — the old `monsters` collection's wrapper — must not ride along.
    _make_ready_map(tmp_path, "ROOK", "ROOK-HUNT-0020_new-area")

    target = _run(
        tmp_path, monkeypatch,
        ["ROOK-HUNT-0020_new-area", "--map-id", "ROOK-HUNT-0020", "--export"],
        catalog=_catalog(),
    )

    assert sorted(target.respawn("ROOK-HUNT-0020")) == ["mapBoundsRef", "monsterDefs", "spawns"]


def test_existing_id_without_edit_is_a_hard_error_and_writes_nothing(tmp_path, monkeypatch, capsys):
    _make_ready_map(tmp_path, "ROOK", "ROOK-HUNT-0010_bears-rookguard")
    curated = {"mapId": "ROOK-HUNT-0010", "name": "Curated Bears"}

    with pytest.raises(SystemExit) as exc_info:
        _run(
            tmp_path, monkeypatch,
            ["ROOK-HUNT-0010_bears-rookguard", "--map-id", "ROOK-HUNT-0010", "--export"],
            catalog=_catalog(hunts=[curated]),
        )

    assert exc_info.value.code == 1
    out = capsys.readouterr().out
    assert "ROOK-HUNT-0010" in out
    assert "--edit" in out

    target = _Target(tmp_path)
    assert target.catalog["hunts"] == [curated]
    assert target.loot == []
    assert target.respawn("ROOK-HUNT-0010") is None


def test_export_with_edit_refreshes_the_mechanical_half_but_not_the_curated_hunt(tmp_path, monkeypatch):
    _make_ready_map(tmp_path, "ROOK", "ROOK-HUNT-0010_bears-rookguard")
    curated = {"mapId": "ROOK-HUNT-0010", "name": "Curated Bears"}

    target = _run(
        tmp_path, monkeypatch,
        ["ROOK-HUNT-0010_bears-rookguard", "--map-id", "ROOK-HUNT-0010", "--export", "--edit"],
        catalog=_catalog(hunts=[curated]),
        loot=[{"mapId": "ROOK-HUNT-0010", "drops": [{"itemId": 1, "itemName": "stale"}]}],
    )

    # hunts stays curated (never overwritten by the mechanical export)...
    assert target.catalog["hunts"] == [curated]
    # ...but loot and respawn (100% mechanical) are refreshed.
    assert target.loot == [{"mapId": "ROOK-HUNT-0010", "drops": []}]
    assert target.respawn("ROOK-HUNT-0010") == _RESPAWN


def test_export_skips_a_scratch_folder_whose_name_is_not_an_id(tmp_path, monkeypatch, capsys):
    # `--all` finds every folder with a respawn.json, including scratch ones
    # ("Nova pasta", "DEBUG-MAP"). Their "map id" is just the folder name —
    # fine in a local fragment, not something to write into the catalog.
    _make_ready_map(tmp_path, "TEST", "Nova pasta")

    target = _run(tmp_path, monkeypatch, ["--all", "--export"], catalog=_catalog())

    out = capsys.readouterr().out
    assert "SKIP export" in out
    assert "Nova pasta" in out
    assert target.catalog["hunts"] == []
    assert target.loot == []
    assert target.respawn("Nova pasta") is None
    # The local fragment is still generated — only the export is refused.
    assert (tmp_path / "ready-maps" / "TEST" / "Nova pasta" / "db-fragment.json").exists()


def test_export_still_writes_the_conventional_maps_in_the_same_sweep(tmp_path, monkeypatch):
    _make_ready_map(tmp_path, "TEST", "Nova pasta")
    _make_ready_map(tmp_path, "ROOK", "ROOK-HUNT-0020_new-area")

    target = _run(tmp_path, monkeypatch, ["--all", "--export"], catalog=_catalog())

    assert [h["mapId"] for h in target.catalog["hunts"]] == ["ROOK-HUNT-0020"]


def test_export_leaves_the_other_catalog_collections_alone(tmp_path, monkeypatch):
    # The travel CLI owns locations/travelGraph in the same file; exporting a
    # hunt must not disturb them.
    _make_ready_map(tmp_path, "ROOK", "ROOK-HUNT-0020_new-area")
    catalog = _catalog()
    catalog["locations"] = [{"id": "ROOK-TEMPLE-0001"}]
    catalog["travelGraph"] = [{"from": "A", "to": "B", "tileCount": 3}]

    target = _run(
        tmp_path, monkeypatch,
        ["ROOK-HUNT-0020_new-area", "--map-id", "ROOK-HUNT-0020", "--export"],
        catalog=catalog,
    )

    assert target.catalog["locations"] == [{"id": "ROOK-TEMPLE-0001"}]
    assert target.catalog["travelGraph"] == [{"from": "A", "to": "B", "tileCount": 3}]


def test_export_skips_a_ready_map_whose_source_was_deleted(tmp_path, monkeypatch, capsys):
    # ready-maps/ is gitignored build output, so deleting a map from maps/
    # leaves its build behind and `--all` still finds it. That is how
    # ROOK-HUNT-0013 — a map removed months earlier — came back as a live
    # hunt in the catalog and broke `nx run db:reset`.
    _make_ready_map(tmp_path, "ROOK", "ROOK-HUNT-0013_rats-rookguard", with_source=False)

    target = _run(tmp_path, monkeypatch, ["--all", "--export"], catalog=_catalog())

    out = capsys.readouterr().out
    assert "SKIP export" in out
    assert "não existe mais fonte" in out
    assert target.catalog["hunts"] == []
    assert target.respawn("ROOK-HUNT-0013") is None


def test_export_warns_when_the_source_changed_after_the_last_build(tmp_path, monkeypatch, capsys):
    # ready-maps/ is gitignored, so nothing keeps it in step with maps/.
    # Exporting a stale build publishes OLDER content over newer, and the
    # diff looks exactly like a deliberate prune — hence the warning.
    import os
    import time

    _make_ready_map(tmp_path, "ROOK", "ROOK-HUNT-0020_new-area")
    source = tmp_path / "maps" / "ROOK" / "ROOK-HUNT-0020_new-area" / "new-area.otbm"
    source.write_text("otbm", encoding="utf-8")
    built = tmp_path / "ready-maps" / "ROOK" / "ROOK-HUNT-0020_new-area" / "monsters" / "respawn.json"
    os.utime(built, (time.time() - 60, time.time() - 60))

    _run(tmp_path, monkeypatch, ["--all", "--export"], catalog=_catalog())

    out = capsys.readouterr().out
    assert "a fonte mudou depois do último build" in out
    assert "new-area.otbm" in out


def test_export_is_quiet_when_the_build_is_current(tmp_path, monkeypatch, capsys):
    _make_ready_map(tmp_path, "ROOK", "ROOK-HUNT-0020_new-area")

    _run(tmp_path, monkeypatch, ["--all", "--export"], catalog=_catalog())

    assert "a fonte mudou depois do último build" not in capsys.readouterr().out
