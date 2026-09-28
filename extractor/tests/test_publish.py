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


def test_atlases_only_dry_run_says_what_it_would_do(tmp_path, monkeypatch, capsys):
    """`--atlases-only --dry-run` não imprimia nada: a publicação de atlas
    inteira era pulada no dry-run. Dry-run silencioso é pior que não ter —
    quem roda para conferir conclui que não há nada a fazer."""
    atlases = tmp_path / "atlases"
    (atlases / "outfits").mkdir(parents=True)
    (atlases / "outfits" / "21.png").write_bytes(b"x")
    monkeypatch.setattr(publish, "ATLASES_DIR", str(atlases))
    destino = tmp_path / "front"

    publish.publish_atlases(str(destino), dry_run=True)

    saida = capsys.readouterr().out
    assert "[dry-run]" in saida and "outfits" in saida
    assert not destino.exists(), "dry-run não pode escrever"


def test_atlases_publish_actually_copies_when_not_dry_run(tmp_path, monkeypatch):
    atlases = tmp_path / "atlases"
    (atlases / "outfits").mkdir(parents=True)
    (atlases / "outfits" / "21.png").write_bytes(b"x")
    monkeypatch.setattr(publish, "ATLASES_DIR", str(atlases))
    destino = tmp_path / "front"

    publish.publish_atlases(str(destino), dry_run=False)

    assert (destino / "outfits" / "21.png").read_bytes() == b"x"


# ======================================================
# Minimapa da cidade
# ======================================================


@pytest.fixture
def full_maps(tmp_path, monkeypatch):
    """full-maps/<CIDADE>/minimap/, como o build_city_minimap.py deixa."""
    root = tmp_path / "full-maps"
    minimap = root / "ROOK" / "minimap"
    minimap.mkdir(parents=True)
    (minimap / "z7.png").write_bytes(b"\x89PNG-fake")
    (minimap / "bounds.json").write_text(json.dumps({"city": "ROOK"}))
    (root / "CARL").mkdir()
    monkeypatch.setattr(publish, "FULL_MAPS_DIR", str(root))
    return root


def test_minimap_publishes_under_the_city_folder(tmp_path, full_maps):
    """O minimapa nasce em full-maps/, não em ready-maps/ — sem esta rota ele
    simplesmente nunca chegaria ao front."""
    destino = tmp_path / "front"

    publish.publish_minimaps(str(destino), dry_run=False)

    assert (destino / "minimaps" / "ROOK" / "z7.png").read_bytes() == b"\x89PNG-fake"
    assert (destino / "minimaps" / "ROOK" / "bounds.json").exists()


def test_a_city_without_minimap_says_which_command_generates_it(tmp_path, full_maps, capsys):
    publish.publish_minimaps(str(tmp_path / "front"), dry_run=False)

    saida = capsys.readouterr().out
    assert "CARL" in saida and "build_city_minimap.py" in saida


def test_minimap_dry_run_writes_nothing(tmp_path, full_maps, capsys):
    destino = tmp_path / "front"

    publish.publish_minimaps(str(destino), dry_run=True)

    assert "[dry-run]" in capsys.readouterr().out
    assert not destino.exists(), "dry-run não pode escrever"


# ======================================================
# A rota pintada à mão
# ======================================================


def test_publish_bundle_carries_the_painted_route(bundle, tmp_path, monkeypatch):
    """`routes/route-anchors.json` é o único artefato do bundle que o jogo lê e
    que ninguém tinha conferido chegar. O `map.json` + `sheets/` do bundle de
    uma quest publicada antes do painted-route existir chegaram sozinhos, e a
    rota ficou em ready-maps/ — publicar de novo é o que a leva. Este teste
    prende isso: um artefato novo dentro do bundle nasce publicado."""
    (bundle / "routes").mkdir()
    (bundle / "routes" / "route-anchors.json").write_text(json.dumps({
        "mapId": "ROOK-HUNT-0001",
        "start": {"x": 1188, "y": 1134, "z": 7},
        "waypoints": [{"x": 1188, "y": 1134, "z": 7, "kind": "path"}],
    }))

    atlases = tmp_path / "atlases"
    (atlases / "outfits").mkdir(parents=True)
    (atlases / "outfits" / "21.png").write_bytes(b"x")
    monkeypatch.setattr(publish, "ATLASES_DIR", str(atlases))
    monkeypatch.setattr(publish, "READY_MAPS_DIR", str(bundle.parent.parent))

    front = tmp_path / "front"
    publish.publish_bundle("ROOK-HUNT-0001_rats", str(front))

    published = front / "ROOK-HUNT-0001_rats-sprites-v6" / "routes" / "route-anchors.json"
    assert published.exists(), "bundle publicado sem a rota pintada"
    assert json.loads(published.read_text())["mapId"] == "ROOK-HUNT-0001"
