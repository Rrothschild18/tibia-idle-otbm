import transplant_spawns as ts

OFFSET = (-30958, -31074, 0)

PRISTINE = """<?xml version="1.0"?>
<monsters>
\t<monster centerx="32100" centery="32200" centerz="7" radius="3">
\t\t<monster name="Rat" x="0" y="0" z="7" spawntime="60" />
\t</monster>
</monsters>
"""

EDITED = """<?xml version="1.0"?>
<monsters>
\t<monster centerx="32100" centery="32200" centerz="7" radius="3">
\t\t<monster name="Rat" x="0" y="0" z="7" spawntime="60" />
\t</monster>
\t<monster centerx="32190" centery="32208" centerz="9" radius="1">
\t\t<monster name="Dragon Hatchling" x="0" y="0" z="9" spawntime="60" />
\t</monster>
</monsters>
"""


def test_added_groups_are_what_the_edit_introduced_and_nothing_else():
    # Guiado pelo que o autor mudou, não por conter numa caixa: a caixa também
    # contém spawn do mundo que o mapa de destino simplesmente não tem, e
    # copiar aquilo seria adicionar conteúdo que ninguém pediu.
    added = ts.added_groups(EDITED, PRISTINE)

    assert len(added) == 1
    assert added[0]["center"] == (32190, 32208, 9)
    assert [c["name"] for c in added[0]["creatures"]] == ["Dragon Hatchling"]


def test_nothing_added_means_nothing_to_copy():
    assert ts.added_groups(PRISTINE, PRISTINE) == []


def test_a_creature_added_to_an_existing_group_counts_as_a_changed_group():
    # Ele acrescentou um rotworm a um grupo que já existia. O grupo inteiro é a
    # unidade do XML, então ele volta como adicionado — e o destino recebe a
    # versão nova, não duas.
    grown = PRISTINE.replace(
        '\t\t<monster name="Rat" x="0" y="0" z="7" spawntime="60" />\n',
        '\t\t<monster name="Rat" x="0" y="0" z="7" spawntime="60" />\n'
        '\t\t<monster name="Rat" x="1" y="0" z="7" spawntime="60" />\n',
    )

    added = ts.added_groups(grown, PRISTINE)

    assert len(added) == 1
    assert len(added[0]["creatures"]) == 2


def test_shift_moves_the_group_and_every_creature_keeps_its_relative_offset():
    group = ts.added_groups(EDITED, PRISTINE)[0]

    moved = ts.shift_group(group, OFFSET)

    assert moved["center"] == (1232, 1134, 9)
    # x/y da criatura são relativos ao centro: não se deslocam.
    assert moved["creatures"][0]["x"] == 0
    assert moved["creatures"][0]["z"] == 9


def test_merge_puts_the_new_groups_before_the_closing_tag_and_touches_nothing_else():
    group = ts.shift_group(ts.added_groups(EDITED, PRISTINE)[0], OFFSET)
    destination = '<?xml version="1.0"?>\n<monsters>\n\t<monster centerx="1" centery="2" centerz="7" radius="1">\n\t\t<monster name="Rat" x="0" y="0" z="7" spawntime="60" />\n\t</monster>\n</monsters>\n'

    merged = ts.merge_groups(destination, [group])

    assert merged.count("</monsters>") == 1
    assert merged.index('centerx="1"') < merged.index('centerx="1232"')
    assert merged.rstrip().endswith("</monsters>")
    assert 'name="Dragon Hatchling"' in merged


def test_merge_is_idempotent_so_running_twice_does_not_double_the_spawns():
    group = ts.shift_group(ts.added_groups(EDITED, PRISTINE)[0], OFFSET)
    destination = '<?xml version="1.0"?>\n<monsters>\n</monsters>\n'

    once = ts.merge_groups(destination, [group])
    twice = ts.merge_groups(once, [group])

    assert once == twice
