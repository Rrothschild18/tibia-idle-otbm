import os
import sys

SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import curated_hunts as ch


# ======================================================
# training_hunt_from_sign
# ======================================================


def _sign(sign_id, x=1000, y=2000, z=8):
    return {"id": sign_id, "type": "TRAINING", "x": x, "y": y, "z": z}


def test_training_hunt_from_sign_uses_the_sign_floor_and_its_neighbours():
    hunt = ch.training_hunt_from_sign(_sign("CARLIN-TRAINING-0001", z=8), max_floor=15)

    assert hunt["floors"] == [7, 8, 9]
    assert hunt["entranceZ"] == 8


def test_training_hunt_from_sign_never_crosses_the_map_floor_bounds():
    hunt = ch.training_hunt_from_sign(_sign("CARLIN-TRAINING-0001", z=0), max_floor=15)
    assert hunt["floors"] == [0, 1]

    hunt = ch.training_hunt_from_sign(_sign("CARLIN-TRAINING-0001", z=15), max_floor=15)
    assert hunt["floors"] == [14, 15]


def test_training_hunt_from_sign_extent_is_a_point_at_the_sign():
    hunt = ch.training_hunt_from_sign(_sign("CARLIN-TRAINING-0001", x=1000, y=2000, z=8), max_floor=15)

    assert hunt["extent"] == {
        "minX": 1000, "minY": 2000, "maxX": 1000, "maxY": 2000,
        "centerX": 1000, "centerY": 2000,
    }


def test_training_hunt_from_sign_derives_a_readable_name_from_the_id():
    hunt = ch.training_hunt_from_sign(_sign("CARLIN-TRAINING-0001"), max_floor=15)
    assert hunt["name"] == "Carlin Training 0001"


def test_training_hunt_from_sign_carries_the_sign_id_and_no_candidates():
    hunt = ch.training_hunt_from_sign(_sign("CARLIN-TRAINING-0001"), max_floor=15)

    assert hunt["id"] == "CARLIN-TRAINING-0001"
    assert hunt["type"] == "TRAINING"
    assert hunt["candidateIds"] == []
    assert hunt["creatures"] == 0
    assert hunt["subareaId"] is None
    assert hunt["walkTilesFromTemple"] is None


# ======================================================
# assign
# ======================================================


def test_assign_numbers_hunts_without_an_id_sequentially():
    hunts = [{"name": "Rats"}, {"name": "Bugs"}]

    assigned = ch.assign("CARLIN", hunts)

    assert [h["id"] for h in assigned] == ["CARLIN-HUNT-0001", "CARLIN-HUNT-0002"]


def test_assign_passes_through_a_hunt_that_already_carries_an_id():
    training = ch.training_hunt_from_sign(_sign("CARLIN-TRAINING-0003"), max_floor=15)

    assigned = ch.assign("CARLIN", [training])

    assert assigned[0]["id"] == "CARLIN-TRAINING-0003"
    assert assigned[0]["folder"] == "CARLIN-TRAINING-0003_carlin-training-0003"


def test_assign_never_lets_training_ids_collide_with_or_shift_hunt_numbering():
    training = ch.training_hunt_from_sign(_sign("CARLIN-TRAINING-0001"), max_floor=15)
    hunts = [training, {"name": "Rats"}, {"name": "Bugs"}]

    assigned = ch.assign("CARLIN", hunts)

    assert [h["id"] for h in assigned] == [
        "CARLIN-TRAINING-0001",
        "CARLIN-HUNT-0001",
        "CARLIN-HUNT-0002",
    ]


# ======================================================
# build_location
# ======================================================


def test_build_location_sets_type_training_and_a_huntid_with_no_todo():
    training = ch.training_hunt_from_sign(_sign("CARLIN-TRAINING-0001"), max_floor=15)
    hunt = ch.assign("CARLIN", [training])[0]

    location = ch.build_location(hunt, (1000, 2000, 8))

    assert location["type"] == "TRAINING"
    assert location["huntId"] == "CARLIN-TRAINING-0001"
    assert "_todo" not in location


def test_is_training_is_false_for_a_regular_hunt():
    assert ch.is_training({"name": "Rats"}) is False
    assert ch.is_training({"type": "TRAINING"}) is True


# ======================================================
# training_entrance_of
# ======================================================


def test_training_entrance_of_uses_the_signs_own_tile_when_walkable():
    hunt = ch.training_hunt_from_sign(_sign("CARLIN-TRAINING-0001", x=1000, y=2000, z=8), max_floor=15)
    walkable = {(1000, 2000, 8)}

    assert ch.training_entrance_of(hunt, walkable) == (1000, 2000, 8)


def test_training_entrance_of_falls_back_to_a_cardinal_neighbor():
    hunt = ch.training_hunt_from_sign(_sign("CARLIN-TRAINING-0001", x=1000, y=2000, z=8), max_floor=15)
    walkable = {(1001, 2000, 8)}

    assert ch.training_entrance_of(hunt, walkable) == (1001, 2000, 8)


def test_training_entrance_of_never_looks_diagonally():
    hunt = ch.training_hunt_from_sign(_sign("CARLIN-TRAINING-0001", x=1000, y=2000, z=8), max_floor=15)
    walkable = {(1001, 2001, 8)}

    assert ch.training_entrance_of(hunt, walkable) is None


def test_training_entrance_of_is_none_without_any_walkable_neighbor():
    hunt = ch.training_hunt_from_sign(_sign("CARLIN-TRAINING-0001", x=1000, y=2000, z=8), max_floor=15)

    assert ch.training_entrance_of(hunt, walkable=set()) is None
