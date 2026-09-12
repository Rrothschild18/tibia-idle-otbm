import json
import os
import sys

import pytest

SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import fetch_assets as fa


def _fake_client(tmp_path, manifest, *, assets_sha=None, catalog_entries=None, package_json=True):
    base = tmp_path / manifest["assets"]["pathInZip"]
    (base / "assets").mkdir(parents=True)
    (base / "assets.json.sha256").write_text(
        (assets_sha or manifest["assets"]["assetsJsonSha256"]) + "\n"
    )
    count = manifest["assets"]["catalogEntries"] if catalog_entries is None else catalog_entries
    (base / "assets" / "catalog-content.json").write_text(
        json.dumps([{"type": "sprite"}] * count)
    )
    if package_json:
        (base / "package.json").write_text(json.dumps({"version": manifest["clientVersion"]}))
    return str(tmp_path)


@pytest.fixture
def manifest():
    return fa.load_manifest()


def test_real_manifest_pins_a_version_and_two_checksums(manifest):
    assert manifest["clientVersion"] == "15.25.0a00a0"
    assert len(manifest["release"]["sha256"]) == 64
    assert len(manifest["assets"]["assetsJsonSha256"]) == 64
    assert manifest["release"]["tag"] in manifest["release"]["url"]


def test_a_valid_extraction_passes(tmp_path, manifest):
    client_dir = _fake_client(tmp_path, manifest)
    fa.verify_extracted(client_dir, manifest)


def test_different_assets_checksum_is_an_error_not_a_warning(tmp_path, manifest):
    """O modo de falha é silencioso: id de aparência deslocado vira sprite
    trocado seis estágios adiante, nunca erro. Tem que parar aqui."""
    client_dir = _fake_client(tmp_path, manifest, assets_sha="0" * 64)

    with pytest.raises(fa.ClientVersionMismatch) as excinfo:
        fa.verify_extracted(client_dir, manifest)

    assert "versão diferente" in str(excinfo.value)


def test_different_catalog_size_is_caught(tmp_path, manifest):
    client_dir = _fake_client(tmp_path, manifest, catalog_entries=17)

    with pytest.raises(fa.ClientVersionMismatch) as excinfo:
        fa.verify_extracted(client_dir, manifest)

    assert "17" in str(excinfo.value)


def test_missing_package_json_is_caught_and_says_why(tmp_path, manifest):
    """Extrair só assets/ é o erro fácil: o RME recusa a pasta com uma
    mensagem que fala do catálogo, não do package.json."""
    client_dir = _fake_client(tmp_path, manifest, package_json=False)

    with pytest.raises(fa.ClientVersionMismatch) as excinfo:
        fa.verify_extracted(client_dir, manifest)

    assert "package.json" in str(excinfo.value)
    assert "não só assets/" in str(excinfo.value)


def test_truncated_extraction_is_caught(tmp_path, manifest):
    base = tmp_path / manifest["assets"]["pathInZip"]
    base.mkdir(parents=True)

    with pytest.raises(fa.ClientVersionMismatch) as excinfo:
        fa.verify_extracted(str(tmp_path), manifest)

    assert "extração incompleta" in str(excinfo.value)


def test_sha256_mismatch_names_both_hashes(tmp_path):
    blob = tmp_path / "blob.bin"
    blob.write_bytes(b"nao e o cliente")

    with pytest.raises(fa.ClientVersionMismatch) as excinfo:
        fa.verify_sha256(str(blob), "a" * 64, "zip do cliente")

    message = str(excinfo.value)
    assert "a" * 64 in message
    assert fa.sha256_file(str(blob)) in message
    assert "assets-manifest.json" in message


def test_the_client_on_this_machine_matches_the_manifest(manifest):
    """Se o cliente já estiver baixado, ele tem que ser o do manifesto —
    é a verificação que o resto da suíte não consegue fazer com fixture."""
    import paths

    client_dir = paths.TIBIA_CLIENT.resolve(None)
    if not os.path.isdir(fa.assets_dir(client_dir, manifest)):
        pytest.skip("cliente não baixado nesta máquina")

    fa.verify_extracted(client_dir, manifest)
