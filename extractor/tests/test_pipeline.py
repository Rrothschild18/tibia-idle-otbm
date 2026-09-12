import json
import os
import sys

import pytest

SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import pipeline


@pytest.fixture(autouse=True)
def _isolated_stamps(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "STAMP_DIR", str(tmp_path / "stamps"))


def test_content_change_without_touching_mtime_invalidates_the_stamp(tmp_path):
    """O coração do ticket. `git checkout` reescreve mtime e cópia preserva, ou
    seja, mtime mente exatamente quando dói. O modo de falha é servir saída
    velha em silêncio, o pior que um pipeline tem."""
    entrada = tmp_path / "entrada.json"
    entrada.write_text('{"a": 1}')
    mtime_antes = (os.path.getatime(entrada), os.path.getmtime(entrada))

    antes = pipeline.input_hash([str(entrada)])

    entrada.write_text('{"a": 2}')
    os.utime(entrada, mtime_antes)          # mtime idêntico ao de antes
    assert os.path.getmtime(entrada) == mtime_antes[1]

    assert pipeline.input_hash([str(entrada)]) != antes


def test_identical_content_with_different_mtime_keeps_the_hash(tmp_path):
    """O outro lado da moeda: `git checkout` mexe no mtime sem mudar bytes, e
    isso não pode forçar um rebuild."""
    entrada = tmp_path / "entrada.json"
    entrada.write_text('{"a": 1}')
    antes = pipeline.input_hash([str(entrada)])

    os.utime(entrada, (0, 0))

    assert pipeline.input_hash([str(entrada)]) == antes


def test_hash_covers_file_names_not_just_bytes(tmp_path):
    """Renomear sem mudar conteúdo é mudança: o consumidor endereça por nome."""
    directory = tmp_path / "arvore"
    directory.mkdir()
    (directory / "a.png").write_bytes(b"x")
    antes = pipeline.input_hash([str(directory)])

    os.rename(directory / "a.png", directory / "b.png")

    assert pipeline.input_hash([str(directory)]) != antes


def test_missing_input_hashes_as_absent_rather_than_raising(tmp_path):
    """Entrada ausente é problema do check, que sabe dizer como resolver — não
    do hash, que viraria traceback."""
    digest = pipeline.input_hash([str(tmp_path / "nao-existe")])

    assert digest


def test_input_appearing_changes_the_hash(tmp_path):
    alvo = tmp_path / "aparece.json"
    antes = pipeline.input_hash([str(alvo)])

    alvo.write_text("{}")

    assert pipeline.input_hash([str(alvo)]) != antes


def test_stage_skips_when_the_stamp_matches(tmp_path, capsys):
    entrada = tmp_path / "entrada.txt"
    entrada.write_text("a")
    marcador = tmp_path / "rodou.txt"
    stage = pipeline.Stage(
        "teste", "descrição",
        ["python3", "-c", f"open({str(marcador)!r}, 'a').write('x')"],
        inputs=[str(entrada)],
    )

    assert stage.run()
    assert marcador.read_text() == "x"

    assert stage.run()
    assert marcador.read_text() == "x"          # não rodou de novo
    assert "[skip]" in capsys.readouterr().out


def test_force_reruns_even_with_a_valid_stamp(tmp_path):
    entrada = tmp_path / "entrada.txt"
    entrada.write_text("a")
    marcador = tmp_path / "rodou.txt"
    stage = pipeline.Stage(
        "teste", "descrição",
        ["python3", "-c", f"open({str(marcador)!r}, 'a').write('x')"],
        inputs=[str(entrada)],
    )

    stage.run()
    stage.run(force=True)

    assert marcador.read_text() == "xx"


def test_changed_input_reruns_the_stage(tmp_path):
    entrada = tmp_path / "entrada.txt"
    entrada.write_text("a")
    marcador = tmp_path / "rodou.txt"
    stage = pipeline.Stage(
        "teste", "descrição",
        ["python3", "-c", f"open({str(marcador)!r}, 'a').write('x')"],
        inputs=[str(entrada)],
    )

    stage.run()
    mtime = (os.path.getatime(entrada), os.path.getmtime(entrada))
    entrada.write_text("b")
    os.utime(entrada, mtime)                    # de novo: só o conteúdo muda

    stage.run()

    assert marcador.read_text() == "xx"


def test_a_failed_stage_writes_no_stamp(tmp_path):
    """Estágio que falhou não pode ser pulado na próxima rodada."""
    entrada = tmp_path / "entrada.txt"
    entrada.write_text("a")
    stage = pipeline.Stage("falha", "descrição", ["python3", "-c", "raise SystemExit(3)"],
                           inputs=[str(entrada)])

    assert stage.run() is False
    assert pipeline.read_stamp("falha") is None


def test_missing_requirement_blocks_the_stage_and_names_the_fix(tmp_path, capsys):
    stage = pipeline.Stage(
        "teste", "descrição", ["python3", "-c", "pass"],
        requires=[(str(tmp_path / "ausente"), "rode o comando tal")],
    )

    assert stage.run() is False
    out = capsys.readouterr().out
    assert "rode o comando tal" in out


def test_every_declared_stage_has_inputs_or_says_why():
    """Estágio sem entradas declarada roda sempre — pode ser certo, mas tem
    que ser escolha, não esquecimento."""
    for stage in pipeline.build_stages():
        assert stage.inputs, f"{stage.name} não declara entradas"


def test_every_requirement_names_a_command():
    for stage in pipeline.build_stages():
        for path, how in stage.requires:
            assert how and not how.startswith("("), f"{stage.name}: {path}"


def test_the_client_assets_dir_is_never_hashed():
    """A exceção declarada: hashear centenas de MB por invocação não paga, e o
    assets-manifest.json já decide a versão do cliente por checksum."""
    for stage in pipeline.build_stages():
        for entry in stage.inputs:
            assert "tibia-client" not in entry


def test_cities_come_from_the_folder_not_a_hardcoded_list(tmp_path, monkeypatch):
    """O repo trata adicionar cidade como 'pasta nova, sem mudar código'
    (build_map.js faz o mesmo). Uma lista fixa faria a segunda cidade ser
    ignorada em silêncio."""
    full_maps = tmp_path / "full-maps"
    (full_maps / "ROOK").mkdir(parents=True)
    (full_maps / "CARL").mkdir()
    (full_maps / "um-arquivo.txt").write_text("não é cidade")
    monkeypatch.setattr(pipeline, "EXTRACTOR_DIR", str(tmp_path))

    assert pipeline._cities() == ["CARL", "ROOK"]


def test_a_second_city_gets_its_own_stages(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "_cities", lambda: ["CARL", "ROOK"])

    names = [stage.name for stage in pipeline.build_stages()]

    assert "flags:CARL" in names and "flags:ROOK" in names
    assert "travel-graph:CARL" in names and "travel-graph:ROOK" in names


def test_no_stage_hardcodes_a_city_in_its_command():
    """Se um comando trouxesse 'ROOK' fixo, a cidade nova rodaria o estágio
    contra a cidade errada."""
    for stage in pipeline.build_stages():
        if ":" in stage.name:
            city = stage.name.split(":", 1)[1]
            assert city in " ".join(stage.command)


def test_every_bake_script_is_reachable_from_the_pipeline():
    """O `bake_player_outfit_sheet.py` ficou fora do pipeline na primeira
    versão: os 242 outfits de jogador eram extraídos e nunca bakeados, e nada
    reclamava — `publish` só dizia '[--] não bakeado'. Este teste é o guarda.

    Um bake é coberto se for estágio direto ou se um estágio o invocar
    (os dois de item rodam dentro do `build_items.js`).
    """
    import pathlib

    scripts = pathlib.Path(pipeline.SCRIPTS_DIR)
    bakes = {path.name for path in scripts.glob("bake_*.py")}

    # Não é um bake: virou a biblioteca de classificação que os dois bakers de
    # item importam (is_equipment_candidate, _list_item_ids, ...). Ver o
    # comentário no topo de build_items.js.
    bakes.discard("bake_item_atlas.py")

    comandos = " ".join(" ".join(stage.command) for stage in pipeline.build_stages())
    runner = (scripts / "build_items.js").read_text()

    for bake in sorted(bakes):
        assert bake in comandos or bake in runner, (
            f"{bake} não é estágio do pipeline nem é chamado por um — "
            f"ele nunca vai rodar num `pipeline --all`"
        )
