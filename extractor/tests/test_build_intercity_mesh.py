import pytest

import build_intercity_mesh as bim


def _temple(city, x, y):
    return {"id": f"{city}-TEMPLE-0001", "type": "TEMPLE", "x": x, "y": y, "z": 7}


THAIS_BOUNDS = {"minX": 31893, "minY": 31485, "maxX": 33575, "maxY": 33167}


def test_covered_by_accepts_the_four_mainland_temples_in_the_thais_cut():
    temples = [
        _temple("CARLIN", 32360, 31782),
        _temple("KAZORDOON", 32649, 31925),
        _temple("THAIS", 32369, 32241),
        _temple("VENORE", 32957, 32076),
    ]

    inside, outside = bim.covered_by(THAIS_BOUNDS, temples)

    assert [t["id"] for t in inside] == [t["id"] for t in temples]
    assert outside == []


def test_covered_by_separates_a_temple_outside_the_cut():
    dentro = _temple("THAIS", 32369, 32241)
    fora = _temple("EDRON", 33217, 31814)

    inside, outside = bim.covered_by({"minX": 32000, "minY": 32000, "maxX": 33000, "maxY": 33000}, [dentro, fora])

    assert [t["id"] for t in inside] == ["THAIS-TEMPLE-0001"]
    assert [t["id"] for t in outside] == ["EDRON-TEMPLE-0001"]


@pytest.mark.parametrize("bounds", [None, {}, {"minX": 0, "minY": 0, "maxX": 10}])
def test_covered_by_refuses_bounds_it_cannot_read(bounds):
    # O default de zero disse que o recorte de THAIS não cobre o templo de
    # Thais: `0 <= 32369 <= 0` é falso para tudo. Recusar é o conserto.
    with pytest.raises(bim.MissingBoundsError):
        bim.covered_by(bounds, [_temple("THAIS", 32369, 32241)])


def test_temples_of_catalog_takes_one_per_city_and_honours_the_exclusion():
    catalog = {
        "locations": [
            _temple("THAIS", 32369, 32241),
            _temple("CARLIN", 32360, 31782),
            _temple("ROOK", 32097, 32219),
            {"id": "THAIS-HUNT-0001", "type": "HUNT", "x": 1, "y": 1, "z": 7},
        ]
    }

    temples = bim.temples_of_catalog(catalog, {"ROOK"})

    assert [t["id"] for t in temples] == ["CARLIN-TEMPLE-0001", "THAIS-TEMPLE-0001"]


def test_temples_of_catalog_refuses_a_city_with_two_temples():
    # O estado que o bug produzia: três templos marcados city=THAIS, e a malha
    # sem saber qual é o ponto de junção. Melhor parar que escolher.
    catalog = {
        "locations": [
            _temple("THAIS", 32369, 32241),
            {"id": "THAIS-TEMPLE-0002", "type": "TEMPLE", "x": 32091, "y": 32027, "z": 7},
        ]
    }

    with pytest.raises(SystemExit):
        bim.temples_of_catalog(catalog, set())
