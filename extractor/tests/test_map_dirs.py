import os

import map_dirs as md


def _make_map(root, city, pasta, *files):
    map_dir = os.path.join(root, city, pasta)
    os.makedirs(map_dir, exist_ok=True)
    for relpath in files:
        full = os.path.join(map_dir, relpath)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write("")
    return map_dir


def test_discover_cities_lists_every_city_folder_sorted(tmp_path):
    _make_map(tmp_path, "ROOK", "ROOK-HUNT-0001_bears")
    _make_map(tmp_path, "TEST", "TEST-HUNT-0001_dragon")

    assert md.discover_cities(str(tmp_path)) == ["ROOK", "TEST"]


def test_discover_cities_empty_when_root_does_not_exist(tmp_path):
    assert md.discover_cities(str(tmp_path / "nope")) == []


def test_find_two_level_dir_locates_pasta_under_its_city(tmp_path):
    expected = _make_map(tmp_path, "ROOK", "ROOK-HUNT-0001_bears")

    assert md.find_two_level_dir(str(tmp_path), "ROOK-HUNT-0001_bears") == expected


def test_find_two_level_dir_returns_none_when_missing(tmp_path):
    _make_map(tmp_path, "ROOK", "ROOK-HUNT-0001_bears")

    assert md.find_two_level_dir(str(tmp_path), "nonexistent") is None


def test_discover_two_level_names_filters_by_marker_file(tmp_path):
    _make_map(tmp_path, "ROOK", "ROOK-HUNT-0001_bears", "monsters/respawn.json")
    _make_map(tmp_path, "ROOK", "ROOK-HUNT-0002_rats")  # no respawn.json — no spawns
    _make_map(tmp_path, "TEST", "TEST-HUNT-0001_dragon", "monsters/respawn.json")

    names = md.discover_two_level_names(str(tmp_path), "monsters/respawn.json")

    assert names == ["ROOK-HUNT-0001_bears", "TEST-HUNT-0001_dragon"]
