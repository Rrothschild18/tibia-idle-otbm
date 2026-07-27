from PIL import Image

from build_phaser_map import _render_baked_row


def _make_sprite(tmp_path, name, width, height, color):
    path = tmp_path / name
    Image.new("RGBA", (width, height), color).save(path)
    return str(path)


def _entry(tile_x, stack_index, sprite_path, width, height):
    return {
        "tileX": tile_x,
        "stackIndex": stack_index,
        "analysis": {
            "appearanceId": tile_x * 100 + stack_index,
            "sprites": [{"available": True, "sourcePath": sprite_path, "width": width, "height": height}],
        },
    }


def test_single_32x32_entry_canvas_matches_tile_bounds(tmp_path):
    sprite = _make_sprite(tmp_path, "a.png", 32, 32, (255, 0, 0, 255))
    entries = [_entry(tile_x=5, stack_index=0, sprite_path=sprite, width=32, height=32)]

    image, meta = _render_baked_row(tile_y=3, layer_class="object", entries=entries)

    # bottom-right anchor for tileX=5 is (6*32, 4*32) = (192, 128);
    # a 32x32 sprite anchored there occupies exactly that one tile.
    assert meta == {"worldX": 160, "worldY": 96, "width": 32, "height": 32}
    assert image.size == (32, 32)


def test_wide_sprite_and_tall_sprite_expand_canvas_bbox(tmp_path):
    wide = _make_sprite(tmp_path, "wide.png", 64, 32, (0, 255, 0, 255))
    tall = _make_sprite(tmp_path, "tall.png", 32, 64, (0, 0, 255, 255))
    entries = [
        _entry(tile_x=0, stack_index=0, sprite_path=wide, width=64, height=32),
        _entry(tile_x=3, stack_index=0, sprite_path=tall, width=32, height=64),
    ]

    image, meta = _render_baked_row(tile_y=2, layer_class="object", entries=entries)

    # wide sprite's right edge is at (0+1)*32=32, so it spans x=[-32, 32);
    # tall sprite's right edge is at (3+1)*32=128, spanning x=[96, 128).
    # canvas must cover the union: x=[-32, 128), width=160.
    # tall sprite's top is (2+1)*32 - 64 = 32; wide sprite's top is 96-32=64.
    # canvas top is the smaller value (32), height = bottom(96) - top(32) = 64.
    assert meta == {"worldX": -32, "worldY": 32, "width": 160, "height": 64}
    assert image.size == (160, 64)


def test_composites_in_tilex_then_stackindex_order(tmp_path):
    below = _make_sprite(tmp_path, "below.png", 32, 32, (255, 0, 0, 255))
    above = _make_sprite(tmp_path, "above.png", 32, 32, (0, 0, 255, 255))
    entries = [
        _entry(tile_x=0, stack_index=1, sprite_path=above, width=32, height=32),
        _entry(tile_x=0, stack_index=0, sprite_path=below, width=32, height=32),
    ]

    image, _meta = _render_baked_row(tile_y=0, layer_class="object", entries=entries)

    # higher stackIndex composites last (on top), regardless of input order
    assert image.getpixel((16, 16)) == (0, 0, 255, 255)
