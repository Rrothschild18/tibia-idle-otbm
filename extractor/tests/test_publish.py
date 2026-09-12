import json
import os
import sys

import pytest

SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import publish


@pytest.fixture
def bundle(tmp_path):
    """Um bundle construído, como o build_map.js deixa em ready-maps/."""
    map_dir = tmp_path / "ready" / "ROOK" / "ROOK-HUNT-0001_rats"
    (map_dir / "sheets").mkdir(parents=True)
    (map_dir / "monsters").mkdir()
    (map_dir / "map.json").write_text(json.dumps({
        "assetsRoot": "assets/ROOK-HUNT-0001_rats-sprites-v6",
        "floors": {},
    }))
    (map_dir / "sheets" / "sheet-32.png").write_bytes(b"\x89PNG-fake")
    (map_dir / "monsters" / "respawn.json").write_text(json.dumps({
        "monsterDefs": {"21": {"atlas": {"image": "assets/outfits/21.png",
                                         "json": "assets/outfits/21.json"}}},
        "spawns": [],
    }))
    return map_dir


def test_bundle_dir_name_comes_from_the_map_itself(bundle):
    """O `assetsRoot` que o mapa declara **é** o caminho que o jogo pede.
    Remontar o nome aqui criaria uma segunda fonte de verdade, e divergir
    significa 404 no bundle inteiro."""
    assert publish.bundle_dir_name(str(bundle)) == "ROOK-HUNT-0001_rats-sprites-v6"


def test_referenced_atlases_are_read_from_the_respawn(bundle):
    assert publish.referenced_atlases(str(bundle)) == {"outfits"}


def test_bundle_without_respawn_references_no_atlas(tmp_path):
    map_dir = tmp_path / "sem-monstro"
    map_dir.mkdir()
    assert publish.referenced_atlases(str(map_dir)) == set()


def test_missing_atlas_is_an_error_naming_the_bake_command(tmp_path, monkeypatch):
    """O caso real: `assets/outfits/` faltava no front enquanto o respawn.json
    apontava pra lá, e nada reclamava."""
    monkeypatch.setattr(publish, "ATLASES_DIR", str(tmp_path))

    with pytest.raises(publish.MissingAtlasError) as excinfo:
        publish.check_atlases({"outfits"})

    message = str(excinfo.value)
    assert "atlases/outfits/" in message
    assert "bake_outfit_atlas.py" in message


def test_empty_atlas_dir_counts_as_missing(tmp_path, monkeypatch):
    (tmp_path / "outfits").mkdir()
    monkeypatch.setattr(publish, "ATLASES_DIR", str(tmp_path))

    with pytest.raises(publish.MissingAtlasError):
        publish.check_atlases({"outfits"})


def test_baked_atlas_passes(tmp_path, monkeypatch):
    (tmp_path / "outfits").mkdir()
    (tmp_path / "outfits" / "21.png").write_bytes(b"x")
    monkeypatch.setattr(publish, "ATLASES_DIR", str(tmp_path))

    publish.check_atlases({"outfits"})


def test_sync_tree_copies_subdirectories(bundle, tmp_path):
    """O respawn.json fica em monsters/. Uma cópia plana o deixaria de fora —
    que é exatamente o que os bundles publicados à mão mostram."""
    destination = tmp_path / "front"

    copied, unchanged = publish.sync_tree(str(bundle), str(destination))

    assert (destination / "map.json").exists()
    assert (destination / "sheets" / "sheet-32.png").exists()
    assert (destination / "monsters" / "respawn.json").exists()
    assert copied == 3 and unchanged == 0


def test_second_sync_copies_nothing(bundle, tmp_path):
    destination = tmp_path / "front"
    publish.sync_tree(str(bundle), str(destination))

    copied, unchanged = publish.sync_tree(str(bundle), str(destination))

    assert copied == 0 and unchanged == 3


def test_changed_bytes_are_recopied(bundle, tmp_path):
    destination = tmp_path / "front"
    publish.sync_tree(str(bundle), str(destination))
    (bundle / "sheets" / "sheet-32.png").write_bytes(b"\x89PNG-outro")

    copied, _ = publish.sync_tree(str(bundle), str(destination))

    assert copied == 1


def test_prune_lists_without_removing_when_not_applied(tmp_path, capsys):
    front = tmp_path / "assets"
    (front / "VELHO-sprites-v6").mkdir(parents=True)
    (front / "ATUAL-sprites-v6").mkdir()

    publish.prune_bundles(str(front), keep={"ATUAL-sprites-v6"}, apply=False)

    assert (front / "VELHO-sprites-v6").exists()
    assert "VELHO-sprites-v6" in capsys.readouterr().out


def test_prune_removes_only_when_applied(tmp_path):
    front = tmp_path / "assets"
    (front / "VELHO-sprites-v6").mkdir(parents=True)
    (front / "ATUAL-sprites-v6").mkdir()

    publish.prune_bundles(str(front), keep={"ATUAL-sprites-v6"}, apply=True)

    assert not (front / "VELHO-sprites-v6").exists()
    assert (front / "ATUAL-sprites-v6").exists()


def test_prune_never_touches_non_bundle_directories(tmp_path):
    """O front tem muita coisa em assets/ que não é bundle — atlas, fontes,
    imagens soltas. Só pastas com `-sprites-v` entram no escopo."""
    front = tmp_path / "assets"
    (front / "outfits").mkdir(parents=True)
    (front / "fonts").mkdir()
    (front / "VELHO-sprites-v6").mkdir()

    publish.prune_bundles(str(front), keep=set(), apply=True)

    assert (front / "outfits").exists()
    assert (front / "fonts").exists()
    assert not (front / "VELHO-sprites-v6").exists()


def test_every_atlas_target_names_a_bake_command():
    """Um alvo sem comando transformaria o erro de atlas faltando em
    '(bake desconhecido)', que é a mensagem que não ajuda ninguém."""
    for name, command in publish.ATLAS_TARGETS.items():
        assert command.endswith(".py") or command.endswith(".js"), name


def test_the_four_atlases_the_old_sync_forgot_are_covered():
    assert {"outfits", "effects", "corpses", "pools"} <= set(publish.ATLAS_TARGETS)


def test_prune_requires_all(monkeypatch, capsys):
    """Bug real, pego na revisão: `--atlases-only --prune` passava um conjunto
    de referência **vazio** para o prune, e teria apagado todo bundle publicado.
    Um run parcial não sabe o que deveria existir."""
    import subprocess
    import sys as _sys

    for argv in (["--atlases-only", "--prune"], ["UM-MAPA", "--prune"]):
        result = subprocess.run(
            [_sys.executable, os.path.join(SCRIPTS_DIR, "publish.py"), *argv],
            capture_output=True, text=True,
        )
        assert result.returncode != 0, argv
        assert "--prune só com --all" in result.stderr, argv


def test_map_json_without_assets_root_says_what_to_do(tmp_path):
    """Bundle de uma versão antiga do pipeline: melhor uma mensagem que diz
    'reconstrua' do que um KeyError cru no meio da publicação."""
    map_dir = tmp_path / "antigo"
    map_dir.mkdir()
    (map_dir / "map.json").write_text(json.dumps({"floors": {}}))

    with pytest.raises(publish.MissingAtlasError) as excinfo:
        publish.bundle_dir_name(str(map_dir))

    assert "assetsRoot" in str(excinfo.value)
    assert "build_map.js" in str(excinfo.value)
