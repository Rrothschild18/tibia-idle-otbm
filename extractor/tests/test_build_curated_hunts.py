import os
import sys

SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import build_curated_hunts as bch
import render_map_v6


def test_surface_hunt_crops_down_to_sea_level():
    assert sorted(bch.crop_floors_for({5})) == [5, 6, 7]


def test_underground_hunt_crops_two_floors_below():
    assert sorted(bch.crop_floors_for({8})) == [8, 9, 10]


def test_the_floors_in_between_still_come_along():
    assert sorted(bch.crop_floors_for({2, 3, 4, 7})) == [2, 3, 4, 5, 6, 7, 8, 9]


def test_the_depth_is_the_front_rule_and_never_passes_the_last_floor():
    assert max(bch.crop_floors_for({5})) == render_map_v6.last_visible_floor(5)
    assert max(bch.crop_floors_for({15})) == bch.MAX_FLOOR


# ======================================================
# merge_manifest (rodada parcial, --only)
# ======================================================


def test_merge_manifest_replaces_in_place_and_keeps_the_rest():
    previous = [{"id": "A", "tiles": 1}, {"id": "B", "tiles": 2}, {"id": "C", "tiles": 3}]
    written = [{"id": "B", "tiles": 99}]

    merged = bch.merge_manifest(previous, written)

    assert [hunt["id"] for hunt in merged] == ["A", "B", "C"]
    assert merged[1]["tiles"] == 99


def test_merge_manifest_appends_an_id_the_file_did_not_have():
    merged = bch.merge_manifest([{"id": "A"}], [{"id": "Z"}])

    assert [hunt["id"] for hunt in merged] == ["A", "Z"]


def _write_monster_xml(path, groups):
    """`groups` é uma lista de (centerx, centery, centerz, [(x, y, name), ...])."""
    lines = ["<monsters>"]
    for center_x, center_y, center_z, entries in groups:
        lines.append(
            f'\t<monster centerx="{center_x}" centery="{center_y}" centerz="{center_z}" '
            f'radius="1">'
        )
        for x, y, name in entries:
            lines.append(f'\t\t<monster name="{name}" x="{x}" y="{y}" spawntime="30"/>')
        lines.append("\t</monster>")
    lines.append("</monsters>\n")
    path.write_text("\n".join(lines), encoding="utf-8")


def test_read_hunt_spawns_returns_absolute_tiles_and_names(tmp_path):
    folder = tmp_path / "CARLIN-HUNT-0001_rats"
    folder.mkdir()
    _write_monster_xml(
        folder / "rats-monster.xml",
        [(1000, 2000, 7, [(1, 1, "Rat"), (-1, 0, "Rat")])],
    )

    spawns = bch.read_hunt_spawns(str(folder), "rats")

    assert spawns == {(1001, 2001, 7, "Rat"), (999, 2000, 7, "Rat")}


def test_read_hunt_spawns_is_empty_when_the_file_does_not_exist(tmp_path):
    assert bch.read_hunt_spawns(str(tmp_path), "missing") == set()


def test_merge_manifest_does_not_reorder():
    # A ordem do arquivo é a da curadoria, não alfabética — reordenar faria todo
    # diff vir cheio de movimentação sem mudança.
    previous = [{"id": "CARLIN-TRAINING-0005"}, {"id": "CARLIN-HUNT-0001"}]

    merged = bch.merge_manifest(previous, [{"id": "CARLIN-HUNT-0001"}])

    assert [hunt["id"] for hunt in merged] == [
        "CARLIN-TRAINING-0005",
        "CARLIN-HUNT-0001",
    ]
