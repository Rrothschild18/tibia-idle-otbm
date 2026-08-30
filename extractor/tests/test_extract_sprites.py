"""Tests for the sprite index law and the player-outfit extraction path.

The index law gets a test of its own because it is the thing that was wrong:
OUTFIT_SPRITES_DOCUMENTATION.md described the frames as grouped by direction
for a long time, and nobody noticed, because a bare numeric key (`128_17`)
says nothing when the index was summed wrong. Every case below is one a human
can check by hand.
"""

import json
import os

import extract_sprites as es


# ---------------------------------------------------------------------------
# Stand-ins for the protobuf messages, carrying only what the code reads.
# ---------------------------------------------------------------------------

class FakeSpriteInfo:
    def __init__(self, width, height, depth, layers, sprite_count):
        self.pattern_width = width
        self.pattern_height = height
        self.pattern_depth = depth
        self.layers = layers
        self.pattern_frames = 0
        self.sprite_id = list(range(sprite_count))


class FakeFrameGroup:
    def __init__(self, sprite_info):
        self.sprite_info = sprite_info


class FakeAppearance:
    def __init__(self, app_id, frame_groups, sprite_data):
        self.id = app_id
        self.frame_group = frame_groups
        self.sprite_data = sprite_data

    def HasField(self, name):  # noqa: N802 — protobuf's spelling
        return False


def _player_appearance(app_id=128, sprite_data=None):
    """A 432-sprite outfit shaped like the real ones: idle (48) + moving (384)."""
    if sprite_data is None:
        sprite_data = [_solid_png(index) for index in range(432)]
    return FakeAppearance(
        app_id,
        [
            FakeFrameGroup(FakeSpriteInfo(4, 3, 2, 2, 48)),
            FakeFrameGroup(FakeSpriteInfo(4, 3, 2, 2, 384)),
        ],
        sprite_data,
    )


def _solid_png(index):
    """A distinct 1x1 PNG per source index, so a test can tell which flat slot
    a written file actually came from."""
    from io import BytesIO

    from PIL import Image

    buffer = BytesIO()
    Image.new("RGBA", (1, 1), (index % 256, index // 256, 0, 255)).save(buffer, "PNG")
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# frame_index — the law
# ---------------------------------------------------------------------------

def test_player_axes_total_is_432():
    # 4 directions x 3 addons x 2 mounts x 2 layers x 9 phases, the shape
    # every one of the 22 classic outfits has in outfits.aec.
    assert es.PLAYER_SOURCE_AXES.total() == 432


def test_frame_index_of_south_idle_base_is_4():
    # phase 0, no mount, no addon, x=2 (south), base layer. Two layers per
    # direction means south's base sprite sits at 2*2 = 4.
    assert es.frame_index(0, 0, 0, 2, 0) == 4


def test_frame_index_layer_varies_fastest():
    # Adjacent indices are the same frame's base and mask, not two directions.
    assert es.frame_index(0, 0, 0, 0, 0) == 0
    assert es.frame_index(0, 0, 0, 0, 1) == 1
    assert es.frame_index(0, 0, 0, 1, 0) == 2


def test_frame_index_phase_varies_slowest():
    # A whole phase is 4 directions x 3 addons x 2 mounts x 2 layers = 48.
    assert es.frame_index(1, 0, 0, 0, 0) == 48


def test_mask_is_always_at_an_odd_index():
    axes = es.PLAYER_SOURCE_AXES
    for phase in range(axes.phases):
        for z in range(axes.mounts):
            for y in range(axes.addons):
                for x in range(axes.directions):
                    assert es.frame_index(phase, z, y, x, 1) % 2 == 1
                    assert es.frame_index(phase, z, y, x, 0) % 2 == 0


def test_frame_index_covers_every_slot_exactly_once():
    axes = es.PLAYER_SOURCE_AXES
    seen = [
        es.frame_index(phase, z, y, x, layer, axes)
        for phase in range(axes.phases)
        for z in range(axes.mounts)
        for y in range(axes.addons)
        for x in range(axes.directions)
        for layer in range(axes.layers)
    ]
    assert sorted(seen) == list(range(axes.total()))


def test_frame_index_on_creature_axes_reduces_to_direction_modulo_4():
    # A creature has no addon, no mount and one layer, so the law collapses to
    # `phase * 4 + direction` — which is why `frameIndex % 4` works client-side.
    creature = es.SpriteAxes(directions=4, addons=1, mounts=1, layers=1, phases=8)
    assert es.frame_index(0, 0, 0, 2, 0, creature) == 2
    assert es.frame_index(3, 0, 0, 1, 0, creature) == 13
    assert creature.total() == 32


# ---------------------------------------------------------------------------
# The fixed catalogue — outfit_names.json, sourced from Canary's
# data/XML/outfits.xml, not a hardcoded id range
# ---------------------------------------------------------------------------

def test_player_outfit_ids_come_from_the_name_catalogue():
    # Every id extract_sprites treats as a player outfit has a name, and
    # every named id counts — the 22 classics (128-150, 135 skipped: it
    # doesn't exist in outfits.aec) are a subset, not the whole list.
    assert set(es.PLAYER_OUTFIT_IDS) == set(es.OUTFIT_NAMES)
    classics = set(i for i in range(128, 151) if i != 135)
    assert classics <= set(es.PLAYER_OUTFIT_IDS)
    assert len(es.PLAYER_OUTFIT_IDS) > len(classics)


def test_is_player_outfit_only_matches_the_catalogued_ids():
    assert es.is_player_outfit(128)
    assert es.is_player_outfit(150)
    assert not es.is_player_outfit(135)
    assert not es.is_player_outfit(21)     # rat
    assert not es.is_player_outfit(999999)  # not in the catalogue


# ---------------------------------------------------------------------------
# Frame keys
# ---------------------------------------------------------------------------

def test_frame_key_is_self_describing():
    assert es.frame_key(128, layer=1, addon=0, direction=0, phase=2) == "128_mask_a0_north_2"
    assert es.frame_key(128, layer=0, addon=2, direction=2, phase=0) == "128_base_a2_south_0"


def test_player_frame_plan_has_216_entries_and_no_mount_frames():
    plan = es.player_frame_plan(128, es.PLAYER_SOURCE_AXES)

    # 432 source sprites minus the mount axis = 216.
    assert len(plan) == 216
    assert len({key for key, _ in plan}) == 216
    # Every planned source index belongs to the z=0 half of the flat list.
    axes = es.PLAYER_SOURCE_AXES
    mount_indices = {
        es.frame_index(phase, 1, y, x, layer)
        for phase in range(axes.phases)
        for y in range(axes.addons)
        for x in range(axes.directions)
        for layer in range(axes.layers)
    }
    assert not mount_indices & {index for _, index in plan}


def test_player_frame_plan_is_ordered_by_the_index_law():
    plan = es.player_frame_plan(128, es.PLAYER_SOURCE_AXES)
    keys = [key for key, _ in plan]

    # Layer varies fastest, then direction, then addon, then phase — the same
    # order the law walks, so a frame's position in the sheet is predictable.
    assert keys[:4] == [
        "128_base_a0_north_0",
        "128_mask_a0_north_0",
        "128_base_a0_east_0",
        "128_mask_a0_east_0",
    ]
    # One full phase is 4 directions x 3 addons x 2 layers = 24 frames.
    assert keys[24] == "128_base_a0_north_1"


def test_player_frame_plan_indices_are_flat_positions_in_sprite_data():
    plan = dict(es.player_frame_plan(128, es.PLAYER_SOURCE_AXES))

    assert plan["128_base_a0_north_0"] == 0
    assert plan["128_mask_a0_north_0"] == 1
    assert plan["128_base_a0_south_0"] == 4
    # Phase 1 is the first moving phase, one whole phase (48) further in.
    assert plan["128_base_a0_north_1"] == 48


# ---------------------------------------------------------------------------
# The declared axes block
# ---------------------------------------------------------------------------

def test_declared_axes_report_mounts_as_dropped():
    # The source has 2 mount values; the extracted output carries 1, so a
    # consumer never has to deduce the axes from the frame count.
    assert es.PLAYER_DECLARED_AXES == {
        "directions": 4,
        "phases": 9,
        "layers": 2,
        "addons": 3,
        "mounts": 1,
    }


# ---------------------------------------------------------------------------
# source_axes_of — phases come from the sprite count, not pattern_frames
# ---------------------------------------------------------------------------

def test_source_axes_of_sums_phases_across_frame_groups():
    # pattern_frames is 0 on every outfit in outfits.aec, so the phase count
    # has to be divided out: 48/48 idle + 384/48 moving = 9.
    assert es.source_axes_of(_player_appearance()) == es.PLAYER_SOURCE_AXES


def test_source_axes_of_a_creature():
    creature = FakeAppearance(
        21,
        [FakeFrameGroup(FakeSpriteInfo(4, 1, 1, 1, 4)),
         FakeFrameGroup(FakeSpriteInfo(4, 1, 1, 1, 32))],
        [],
    )

    assert es.source_axes_of(creature) == es.SpriteAxes(
        directions=4, addons=1, mounts=1, layers=1, phases=9
    )


# ---------------------------------------------------------------------------
# has_non_creature_axis
# ---------------------------------------------------------------------------

def test_creature_with_animated_idle_is_not_excluded():
    # A Wasp/Ghost-style creature has far more than 36 sprites and still
    # belongs on the creature path — the count was never the criterion.
    busy_creature = FakeAppearance(
        50,
        [FakeFrameGroup(FakeSpriteInfo(4, 1, 1, 1, 40)),
         FakeFrameGroup(FakeSpriteInfo(4, 1, 1, 1, 32))],
        [],
    )

    assert not es.has_non_creature_axis(busy_creature)


def test_appearance_using_addon_mount_or_layer_axis_is_excluded():
    for width, height, depth, layers in [(4, 3, 1, 1), (4, 1, 2, 1), (4, 1, 1, 2)]:
        appearance = FakeAppearance(
            9,
            [FakeFrameGroup(FakeSpriteInfo(width, height, depth, layers, 4))],
            [],
        )
        assert es.has_non_creature_axis(appearance)


# ---------------------------------------------------------------------------
# extract_player_outfit
# ---------------------------------------------------------------------------

def test_extract_player_outfit_writes_216_pngs_and_a_json_with_axes(tmp_path):
    written = es.extract_player_outfit(_player_appearance(), str(tmp_path))

    outfit_dir = tmp_path / "128"
    pngs = sorted(p.name for p in outfit_dir.glob("*.png"))
    assert written == 216
    assert len(pngs) == 216

    data = json.loads((outfit_dir / "128.json").read_text(encoding="utf-8"))
    assert data["id"] == 128
    assert data["axes"] == es.PLAYER_DECLARED_AXES
    assert len(data["spriteId"]) == 216
    # Every key the JSON promises has a file on disk.
    assert all((outfit_dir / f"{key}.png").exists() for key in data["spriteId"])


def test_extract_player_outfit_pulls_the_frame_the_index_law_points_at(tmp_path):
    from PIL import Image

    es.extract_player_outfit(_player_appearance(), str(tmp_path))

    # _solid_png encodes its source index in the red channel; south's idle
    # base frame must come from flat slot 4, and phase 1's north base from 48.
    def source_index_of(key):
        pixel = Image.open(tmp_path / "128" / f"{key}.png").convert("RGBA").getpixel((0, 0))
        return pixel[1] * 256 + pixel[0]

    assert source_index_of("128_base_a0_south_0") == 4
    assert source_index_of("128_mask_a0_north_0") == 1
    assert source_index_of("128_base_a0_north_1") == 48


def test_extract_player_outfit_writes_no_mount_frame(tmp_path):
    from PIL import Image

    es.extract_player_outfit(_player_appearance(), str(tmp_path))

    axes = es.PLAYER_SOURCE_AXES
    mount_indices = {
        es.frame_index(phase, 1, y, x, layer)
        for phase in range(axes.phases)
        for y in range(axes.addons)
        for x in range(axes.directions)
        for layer in range(axes.layers)
    }
    for png in (tmp_path / "128").glob("*.png"):
        pixel = Image.open(png).convert("RGBA").getpixel((0, 0))
        assert pixel[1] * 256 + pixel[0] not in mount_indices


def test_extract_player_outfit_skips_an_outfit_of_unexpected_size(tmp_path, capsys):
    truncated = _player_appearance(sprite_data=[_solid_png(0)] * 200)

    assert es.extract_player_outfit(truncated, str(tmp_path)) == 0
    assert not os.path.exists(tmp_path / "128")
    assert "esperado 432" in capsys.readouterr().out


def test_extract_player_outfit_is_idempotent(tmp_path):
    es.extract_player_outfit(_player_appearance(), str(tmp_path))
    # A second run finds every PNG already on disk and writes none.
    assert es.extract_player_outfit(_player_appearance(), str(tmp_path)) == 0
    assert len(list((tmp_path / "128").glob("*.png"))) == 216
