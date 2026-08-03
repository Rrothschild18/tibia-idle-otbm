import city_ids as ci


def test_derive_city_takes_the_first_hyphen_segment():
    assert ci.derive_city("ROOK-HUNT-0002") == "ROOK"
    assert ci.derive_city("ROOK-NPC-obi") == "ROOK"


def test_derive_status_is_test_only_for_the_test_city():
    assert ci.derive_status("TEST") == "test"
    assert ci.derive_status("ROOK") is None
