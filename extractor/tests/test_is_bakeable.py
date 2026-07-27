import item_classifier
from build_phaser_map import _is_bakeable


def _analysis(**overrides):
    base = {
        "appearanceId": 9001,
        "type": "static",
        "animated": False,
        "random": False,
    }
    base.update(overrides)
    return base


def test_plain_static_object_is_bakeable():
    assert _is_bakeable(_analysis(), "object") is True


def test_animated_item_is_not_bakeable():
    assert _is_bakeable(_analysis(animated=True), "object") is False


def test_random_variant_item_is_not_bakeable():
    assert _is_bakeable(_analysis(random=True), "object") is False


def test_unknown_type_is_not_bakeable():
    assert _is_bakeable(_analysis(type="unknown"), "object") is False


def test_interactive_item_is_not_bakeable(monkeypatch):
    monkeypatch.setattr(item_classifier, "INTERACTIVE_IDS", {9001})
    assert _is_bakeable(_analysis(appearanceId=9001), "object") is False


def test_roof_layer_is_never_bakeable():
    assert _is_bakeable(_analysis(), "roof") is False


def test_border_layer_is_never_bakeable():
    assert _is_bakeable(_analysis(), "border") is False
