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
