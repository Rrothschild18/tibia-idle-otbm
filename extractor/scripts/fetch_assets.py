"""Baixa e verifica o cliente Tibia de onde saem todos os sprites.

A versão do cliente está fixada em `extractor/assets-manifest.json` e em nenhum
outro lugar: trocar de cliente é editar aquele arquivo. Isso importa porque o
modo de falha é silencioso — um cliente mais novo desloca ids de aparência, e o
sintoma aparece seis estágios adiante como **sprite trocado**, nunca como erro.
Por isso checksum divergente aqui é erro, não aviso.

A release é pública e imutável (uma tag do GitHub), então não há bucket privado,
credencial nem env var secreta. A pasta extraída fica fora do git; qualquer
clone a busca sozinho.

Run: uv run python extractor/scripts/fetch_assets.py [--client-dir PATH] [--force]
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import urllib.request
import zipfile

import paths

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
EXTRACTOR_DIR = os.path.dirname(SCRIPTS_DIR)
MANIFEST_PATH = os.path.join(EXTRACTOR_DIR, "assets-manifest.json")

_CHUNK = 1024 * 1024


class ClientVersionMismatch(Exception):
    """Checksum diferente do manifesto: é outro cliente, não um download torto."""


def load_manifest(path=None) -> dict:
    with open(path or MANIFEST_PATH, "r", encoding="utf-8") as handler:
        return json.load(handler)


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handler:
        for chunk in iter(lambda: handler.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_sha256(path: str, expected: str, what: str) -> None:
    actual = sha256_file(path)
    if actual != expected:
        raise ClientVersionMismatch(
            f"{what}: cliente de versão diferente do fixado no manifesto.\n"
            f"  esperado: {expected}\n"
            f"  obtido:   {actual}\n"
            f"  arquivo:  {path}\n"
            f"Um cliente diferente desloca ids de aparência e produz sprite trocado lá na frente, "
            f"sem erro. Se a troca é intencional, edite extractor/assets-manifest.json."
        )


def assets_dir(client_dir: str, manifest: dict) -> str:
    """Onde `packages/Tibia/assets/` fica depois de extraído."""
    return os.path.join(client_dir, manifest["assets"]["pathInZip"], "assets")


def package_json_path(client_dir: str, manifest: dict) -> str:
    """O RME e o próprio cliente leem a versão daqui; sem ele o RME recusa a pasta."""
    return os.path.join(client_dir, manifest["assets"]["pathInZip"], "package.json")


def verify_extracted(client_dir: str, manifest: dict) -> None:
    """Confere o que o pipeline vai de fato abrir.

    `assets.json.sha256` é o mecanismo de integridade do próprio cliente:
    conferi-lo pega uma extração truncada, que o hash do zip não pegaria porque
    o zip já foi apagado a essa altura.
    """
    base = os.path.join(client_dir, manifest["assets"]["pathInZip"])
    sha_file = os.path.join(base, "assets.json.sha256")
    if not os.path.exists(sha_file):
        raise ClientVersionMismatch(f"assets.json.sha256 ausente em {base} — extração incompleta")

    with open(sha_file, "r", encoding="utf-8") as handler:
        actual = handler.read().strip()
    expected = manifest["assets"]["assetsJsonSha256"]
    if actual != expected:
        raise ClientVersionMismatch(
            f"assets.json.sha256: cliente de versão diferente do fixado no manifesto.\n"
            f"  esperado: {expected}\n  obtido:   {actual}"
        )

    catalog = os.path.join(assets_dir(client_dir, manifest), "catalog-content.json")
    if not os.path.exists(catalog):
        raise ClientVersionMismatch(f"catalog-content.json ausente em {catalog}")

    with open(catalog, "r", encoding="utf-8") as handler:
        entries = json.load(handler)
    if len(entries) != manifest["assets"]["catalogEntries"]:
        raise ClientVersionMismatch(
            f"catalog-content.json tem {len(entries)} entradas, "
            f"manifesto diz {manifest['assets']['catalogEntries']} — cliente diferente"
        )

    if not os.path.exists(package_json_path(client_dir, manifest)):
        raise ClientVersionMismatch(
            f"package.json ausente em {package_json_path(client_dir, manifest)} — "
            f"extraia o zip inteiro, não só assets/"
        )


def check_canary_agreement(client_dir: str, manifest: dict, canary_dir=None):
    """O `appearances.dat` do cliente tem que ser o mesmo do Canary.

    Divergência significa que servidor e cliente discordam sobre metadado de
    item — id, flag, animação. O pipeline lê o do cliente e o servidor roda com
    o dele; a discordância não dá erro em lugar nenhum, ela aparece seis
    estágios adiante como sprite ou comportamento errado.

    -> (ok, mensagem). `None` em `ok` quando não há Canary para comparar, que
    não é falha: o checkout virou opcional no ticket 04.
    """
    expected = manifest["assets"].get("appearancesSha256")
    client_file = os.path.join(
        assets_dir(client_dir, manifest), manifest["assets"]["appearancesFile"]
    )
    if not os.path.exists(client_file):
        return False, f"appearances do cliente ausente em {client_file}"

    client_sha = sha256_file(client_file)
    if expected and client_sha != expected:
        return False, (
            f"appearances.dat do cliente não bate com o manifesto\n"
            f"  esperado: {expected}\n  obtido:   {client_sha}"
        )

    try:
        canary = paths.CANARY.require(canary_dir)
    except paths.MissingRepoError:
        return None, "sem checkout do Canary para comparar (opcional)"

    canary_file = os.path.join(canary, "data", "items", "appearances.dat")
    if not os.path.exists(canary_file):
        return None, f"Canary sem {canary_file} para comparar (opcional)"

    canary_sha = sha256_file(canary_file)
    if canary_sha != client_sha:
        return False, (
            f"cliente e Canary discordam sobre appearances.dat — metadado de item "
            f"diferente entre quem renderiza e quem simula\n"
            f"  cliente: {client_sha}\n  canary:  {canary_sha}"
        )
    return True, f"cliente e Canary concordam sobre appearances.dat ({client_sha[:16]}…)"


def _download(url: str, destination: str) -> None:
    print(f"[..] baixando {url}")
    with urllib.request.urlopen(url) as response, open(destination, "wb") as handler:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = response.read(_CHUNK)
            if not chunk:
                break
            handler.write(chunk)
            done += len(chunk)
            if total:
                print(f"\r     {done / 1048576:.0f}/{total / 1048576:.0f} MB", end="", flush=True)
        print()


def _extract(zip_path: str, client_dir: str, manifest: dict) -> None:
    """Extrai `packages/Tibia/` — assets/ **e** package.json.

    Extrair só `assets/` é o erro fácil e custa caro: o RME recusa a pasta com
    "The file package.json is not present", e a mensagem fala do catálogo.
    """
    prefix = manifest["assets"]["pathInZip"] + "/"
    with zipfile.ZipFile(zip_path) as archive:
        members = [name for name in archive.namelist() if name.startswith(prefix)]
        if not members:
            raise ClientVersionMismatch(f"o zip não contém {prefix} — release inesperada")
        print(f"[..] extraindo {len(members)} arquivos de {prefix}")
        archive.extractall(client_dir, members)


def _report_canary_agreement(client_dir: str, manifest: dict) -> None:
    ok, message = check_canary_agreement(client_dir, manifest)
    if ok is False:
        print(f"[ERROR] {message}")
        sys.exit(1)
    print(f"[{'OK' if ok else 'INFO'}] {message}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--client-dir",
        default=None,
        help=f"onde extrair (default: ${paths.TIBIA_CLIENT.env_var} ou {paths.TIBIA_CLIENT.sibling_default()})",
    )
    parser.add_argument("--force", action="store_true", help="rebaixa mesmo se já estiver extraído e válido")
    args = parser.parse_args()

    manifest = load_manifest()
    client_dir = paths.TIBIA_CLIENT.resolve(args.client_dir)

    if not args.force and os.path.isdir(assets_dir(client_dir, manifest)):
        try:
            verify_extracted(client_dir, manifest)
        except ClientVersionMismatch as exc:
            print(f"[ERROR] {exc}")
            sys.exit(1)
        print(f"[OK] cliente {manifest['clientVersion']} já presente e íntegro em {client_dir}")
        print(f"     assets: {assets_dir(client_dir, manifest)}")
        _report_canary_agreement(client_dir, manifest)
        return

    os.makedirs(client_dir, exist_ok=True)
    release = manifest["release"]

    with tempfile.TemporaryDirectory(dir=client_dir) as workdir:
        zip_path = os.path.join(workdir, os.path.basename(release["url"]))
        try:
            _download(release["url"], zip_path)
            verify_sha256(zip_path, release["sha256"], "zip do cliente")
            print(f"[OK] sha256 do zip confere ({release['sha256'][:16]}…)")
            _extract(zip_path, client_dir, manifest)
        except ClientVersionMismatch as exc:
            print(f"[ERROR] {exc}")
            sys.exit(1)
        except OSError as exc:
            print(f"[ERROR] falha baixando {release['url']}: {exc}")
            sys.exit(1)

    try:
        verify_extracted(client_dir, manifest)
    except ClientVersionMismatch as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)

    print(f"[OK] cliente {manifest['clientVersion']} pronto em {client_dir}")
    print(f"     assets: {assets_dir(client_dir, manifest)}")
    _report_canary_agreement(client_dir, manifest)


if __name__ == "__main__":
    main()
