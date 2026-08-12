import city_ids as ci


def test_derive_city_takes_the_first_hyphen_segment():
    assert ci.derive_city("ROOK-HUNT-0002") == "ROOK"
    assert ci.derive_city("ROOK-NPC-obi") == "ROOK"


def test_derive_status_is_test_only_for_the_test_city():
    assert ci.derive_status("TEST") == "test"
    assert ci.derive_status("ROOK") is None


def test_is_conventional_id_accepts_the_standard_shape():
    assert ci.is_conventional_id("ROOK-HUNT-0002") is True
    assert ci.is_conventional_id("TEST-DEPOT-0001") is True


def test_is_conventional_id_rejects_a_scratch_folder_name():
    # These are real ready-maps folders that a `--all` sweep picks up.
    assert ci.is_conventional_id("Nova pasta") is False
    assert ci.is_conventional_id("DEBUG-MAP") is False
    assert ci.is_conventional_id("TEST-WASPS-DEBUG") is False


def test_is_conventional_id_rejects_a_wrong_digit_count():
    assert ci.is_conventional_id("ROOK-HUNT-00015") is False
    assert ci.is_conventional_id("ROOK-HUNT-1") is False
