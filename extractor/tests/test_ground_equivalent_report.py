import textwrap

import ground_equivalent_report as ger


def _write(tmp_path, name, body):
    path = tmp_path / name
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return str(path)


def test_parses_border_item_to_ground_equivalent(tmp_path):
    xml = _write(tmp_path, "grounds.xml", """\
        <materials>
          <brush name="sand" type="ground" lookid="231">
            <item id="231" chance="1"/>
            <border align="inner" to="sea" ground_equivalent="231">
              <borderitem edge="n" item="4621"/>
              <borderitem edge="e" item="4624"/>
            </border>
          </brush>
        </materials>
    """)

    assert ger.parse_ground_equivalents(xml) == {4621: 231, 4624: 231}


def test_borders_without_ground_equivalent_are_ignored(tmp_path):
    xml = _write(tmp_path, "grounds.xml", """\
        <materials>
          <brush name="grass" type="ground" lookid="4526">
            <item id="4526" chance="1"/>
            <border align="outer" id="1">
              <borderitem edge="n" item="4530"/>
            </border>
          </brush>
        </materials>
    """)

    assert ger.parse_ground_equivalents(xml) == {}


_SAND_WITH_SPECIFIC = """\
    <materials>
      <brush name="sand" type="ground" lookid="231">
        <border align="inner" to="sea" ground_equivalent="231">
          <borderitem edge="s" item="4623"/>
          <specific>
            <conditions><match_item id="4623"/></conditions>
            <actions><replace_item id="4623" with="4661"/></actions>
          </specific>
        </border>
      </brush>
    </materials>
"""


def test_strict_reading_leaves_specific_replacements_out(tmp_path):
    xml = _write(tmp_path, "grounds.xml", _SAND_WITH_SPECIFIC)

    assert ger.parse_ground_equivalents(xml) == {4623: 231}


def test_loose_reading_collects_only_ids_that_are_not_already_borderitems(tmp_path):
    # 4623 is a <borderitem> of the same <border>, so it belongs to the strict
    # set; only 4661 is new to the control measurement.
    xml = _write(tmp_path, "grounds.xml", _SAND_WITH_SPECIFIC)

    assert ger.parse_specific_replacements(xml) == {4661: 231}


def _dump(tiles):
    """tiles: list of (tileid, [item ids])."""
    return {
        "data": {
            "nodes": [{
                "features": [{
                    "x": 0, "y": 0, "z": 7,
                    "tiles": [
                        {"x": i, "y": 0, "tileid": tileid,
                         "items": [{"id": item_id} for item_id in items]}
                        for i, (tileid, items) in enumerate(tiles)
                    ],
                }]
            }]
        }
    }


def test_counts_nothing_when_no_border_declares_a_synthesized_ground():
    result = ger.measure_dump(_dump([(4526, [1234])]), {4621: 231})

    assert result["tilesWithSynthesizedGround"] == 0
    assert result["matches"] == 0
    assert result["divergences"] == 0
    assert result["byBorder"] == {}


def test_border_as_tileid_counts_as_matching_when_it_is_its_own_ground():
    # The OTBM stores the border itself in the tile's ground slot — nothing is
    # synthesized under it, so there is nothing to diverge from.
    result = ger.measure_dump(_dump([(4621, [])]), {4621: 231})

    assert result["tilesWithSynthesizedGround"] == 1
    assert result["matches"] == 1
    assert result["divergences"] == 0
    assert result["byBorder"] == {4621: {"asGround": 1, "asItem": 0}}


def test_border_as_item_over_a_different_ground_counts_as_divergence():
    result = ger.measure_dump(_dump([(4526, [4621])]), {4621: 231})

    assert result["tilesWithSynthesizedGround"] == 1
    assert result["matches"] == 0
    assert result["divergences"] == 1
    assert result["divergentTiles"] == [
        {"x": 0, "y": 0, "z": 7, "border": 4621, "synthesized": 231, "recorded": 4526}
    ]


def test_border_as_item_over_its_own_ground_equivalent_matches():
    result = ger.measure_dump(_dump([(231, [4621])]), {4621: 231})

    assert result["matches"] == 1
    assert result["divergences"] == 0
    assert result["byBorder"] == {4621: {"asGround": 0, "asItem": 1}}


def test_one_tile_with_two_declaring_borders_counts_the_tile_once():
    result = ger.measure_dump(_dump([(231, [4621, 4624])]), {4621: 231, 4624: 231})

    assert result["tilesWithSynthesizedGround"] == 1
    assert result["matches"] == 1
    assert result["byBorder"] == {4621: {"asGround": 0, "asItem": 1},
                                  4624: {"asGround": 0, "asItem": 1}}


def test_parses_the_vendored_grounds_xml_despite_its_bare_ampersands(tmp_path):
    # RME ships brush names like `lava (rock soil & cave ground)` with the `&`
    # unescaped. The vendored copy must stay byte-identical to upstream, so the
    # parser has to cope rather than the file being fixed.
    xml = _write(tmp_path, "grounds.xml", """\
        <materials>
          <brush name="lava (rock soil & cave ground)" type="ground">
            <border align="inner" ground_equivalent="923">
              <borderitem edge="n" item="924"/>
            </border>
          </brush>
        </materials>
    """)

    assert ger.parse_ground_equivalents(xml) == {924: 923}


def test_vendored_materials_parse_and_declare_the_known_border_ids():
    equivalents = ger.parse_ground_equivalents(ger.GROUNDS_XML)

    # sand ↔ sea borders synthesize sand (231); the sandstone brush synthesizes
    # sandstone (923). Nothing else in the shipped file declares a ground.
    assert set(equivalents.values()) == {231, 923}
    assert equivalents[4621] == 231
    assert equivalents[924] == 923


def test_every_strict_border_id_in_the_vendored_file_is_itself_a_ground():
    # The crux of the ticket's finding: RME's ground_equivalent borders all
    # carry `bank`, so the editor never stacks a synthesized ground under them.
    strict = ger.parse_ground_equivalents(ger.GROUNDS_XML)

    assert strict
    assert all("bank" in ger.appearance_flags(border_id) for border_id in strict)


def test_no_specific_replacement_in_the_vendored_file_is_a_ground():
    loose = ger.parse_specific_replacements(ger.GROUNDS_XML)

    assert loose
    assert all("bank" not in ger.appearance_flags(border_id) for border_id in loose)
