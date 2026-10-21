import apply_pending_masks as apm


def test_resolve_hunt_name_prefers_the_catalog_over_the_masks_snapshot():
    assert apm.resolve_hunt_name(
        {"name": "Necromancers & Undeads Darama Desert 2"},
        "Vampires Undeads Darama Desert Z14",
    ) == "Vampires Undeads Darama Desert Z14"


def test_resolve_hunt_name_falls_back_to_the_mask_for_a_brand_new_hunt():
    assert apm.resolve_hunt_name({"name": "Werehyaenas Cave"}, None) == "Werehyaenas Cave"


def test_resolve_hunt_name_none_when_neither_has_one():
    assert apm.resolve_hunt_name({}, None) is None
