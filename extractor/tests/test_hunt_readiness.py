import os
import sys

SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import hunt_readiness as hr


def _candidate(floor, min_x, min_y, max_x, max_y, **species_counts):
    return {
        "floor": floor,
        "extent": {"minX": min_x, "minY": min_y, "maxX": max_x, "maxY": max_y},
        "species": [{"name": name, "count": count} for name, count in species_counts.items()],
    }


def _wiki_hunt(name, x, y, z, creatures, city="Carlin"):
    return {
        "name": name,
        "city": city,
        "coords": [{"x": x, "y": y, "z": z}],
        "floors": [z],
        "creatures": creatures,
    }


def test_ready_when_a_nearby_candidate_on_the_same_floor_shares_most_creatures():
    hunt = _wiki_hunt("Rotworm Cave", 100, 100, 7, ["rotworm", "rat"])
    candidates = [_candidate(7, 90, 90, 110, 110, Rotworm=10, Rat=3)]

    assert hr.is_ready(hunt, candidates) is True


def test_not_ready_without_any_candidate_nearby():
    hunt = _wiki_hunt("Rotworm Cave", 100, 100, 7, ["rotworm"])
    candidates = [_candidate(7, 900, 900, 910, 910, Rotworm=10)]

    assert hr.is_ready(hunt, candidates) is False


def test_not_ready_on_the_wrong_floor_even_if_the_column_matches():
    hunt = _wiki_hunt("Rotworm Cave", 100, 100, 8, ["rotworm"])
    candidates = [_candidate(7, 90, 90, 110, 110, Rotworm=10)]

    assert hr.is_ready(hunt, candidates) is False


def test_not_ready_when_the_species_do_not_overlap():
    hunt = _wiki_hunt("Dragon Lair", 100, 100, 7, ["dragon", "dragon lord"])
    candidates = [_candidate(7, 90, 90, 110, 110, Rat=20, Bug=5)]

    assert hr.is_ready(hunt, candidates) is False


def test_unmeasurable_without_a_wiki_species_list():
    """Das 699 hunts só 398 têm `creatures` preenchido — sem gabarito de
    espécie a pergunta não tem resposta, e não é o mesmo que "não pronta"."""
    hunt = _wiki_hunt("Sem criaturas", 100, 100, 7, [])
    candidates = [_candidate(7, 90, 90, 110, 110, Rotworm=10)]

    assert hr.is_ready(hunt, candidates) is None


def test_ready_pools_species_across_every_nearby_candidate_on_the_floor():
    hunt = _wiki_hunt("Mixed", 100, 100, 7, ["ghoul", "skeleton"])
    candidates = [
        _candidate(7, 90, 90, 100, 100, Ghoul=5),
        _candidate(7, 101, 90, 110, 100, Skeleton=3),
    ]

    assert hr.is_ready(hunt, candidates) is True


def test_city_of_matches_by_coordinate_bounds_not_by_name():
    """O nome da cidade na wiki ('Gray Beach') não precisa bater com o
    código (`GRAYBEACH`) — a coluna de mundo decide."""
    bounds_by_city = {
        "CARLIN": {"minX": 0, "minY": 0, "maxX": 100, "maxY": 100},
        "GRAYBEACH": {"minX": 200, "minY": 200, "maxX": 300, "maxY": 300},
    }
    hunt = _wiki_hunt("Qualquer", 250, 250, 7, ["rat"], city="Gray Beach")

    assert hr.city_of(hunt, bounds_by_city) == "GRAYBEACH"


def test_city_of_is_none_outside_every_recorte():
    bounds_by_city = {"CARLIN": {"minX": 0, "minY": 0, "maxX": 100, "maxY": 100}}
    hunt = _wiki_hunt("Fora do mapa", 99999, 99999, 7, ["rat"])

    assert hr.city_of(hunt, bounds_by_city) is None


# ---------------------------------------------------------------------------
# Por subárea — o critério fiel à decisão 18, sem distância nenhuma
# ---------------------------------------------------------------------------


def _subarea_candidate(floor, subarea_id, **species_counts):
    return {
        "floor": floor,
        "subareaId": subarea_id,
        "extent": {"minX": 0, "minY": 0, "maxX": 0, "maxY": 0},
        "species": [{"name": name, "count": count} for name, count in species_counts.items()],
    }


def test_subarea_of_reads_the_column_owner_not_the_coordinate_itself():
    owner = {(100, 100): 40}
    hunt = _wiki_hunt("Qualquer", 100, 100, 7, ["rat"])

    assert hr.subarea_of(hunt, owner) == 40


def test_subarea_of_is_none_outside_every_mask():
    owner = {(100, 100): 40}
    hunt = _wiki_hunt("Fora da mascara", 999, 999, 7, ["rat"])

    assert hr.subarea_of(hunt, owner) is None


def test_ready_by_subarea_ignores_extent_and_only_cares_about_the_subarea_id():
    owner = {(100, 100): 40}
    hunt = _wiki_hunt("Rotworm Cave", 100, 100, 7, ["rotworm"])
    candidates = [_subarea_candidate(7, subarea_id=40, Rotworm=10)]

    assert hr.is_ready_by_subarea(hunt, candidates, owner) is True


def test_ready_by_subarea_rejects_the_right_floor_in_the_wrong_subarea():
    owner = {(100, 100): 40}
    hunt = _wiki_hunt("Rotworm Cave", 100, 100, 7, ["rotworm"])
    candidates = [_subarea_candidate(7, subarea_id=99, Rotworm=10)]

    assert hr.is_ready_by_subarea(hunt, candidates, owner) is False


def test_ready_by_subarea_is_false_outside_every_mask():
    owner = {}
    hunt = _wiki_hunt("Sem mascara", 100, 100, 7, ["rotworm"])
    candidates = [_subarea_candidate(7, subarea_id=40, Rotworm=10)]

    assert hr.is_ready_by_subarea(hunt, candidates, owner) is False


def test_preferring_subarea_falls_back_to_extent_without_a_mask():
    """Subsolo sem gêmeo de superfície, ou órfã do ticket 03: sem subárea
    resolvida, a extensão ainda decide."""
    owner = {}
    hunt = _wiki_hunt("Orfa", 100, 100, 7, ["rotworm"])
    candidates = [_candidate(7, 90, 90, 110, 110, Rotworm=10)]

    assert hr.is_ready_preferring_subarea(hunt, candidates, owner) is True


def test_preferring_subarea_uses_subarea_when_it_resolves():
    owner = {(100, 100): 40}
    hunt = _wiki_hunt("Rotworm Cave", 100, 100, 7, ["rotworm"])
    # A extensão NÃO cobre a coordenada — só bate pela subárea.
    candidates = [_subarea_candidate(7, subarea_id=40, Rotworm=10)]

    assert hr.is_ready_preferring_subarea(hunt, candidates, owner) is True
