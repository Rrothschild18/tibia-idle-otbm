"""O pipeline inteiro, um comando, incremental por hash de conteúdo.

Eram ~8 invocações manuais numa ordem que não estava escrita em lugar nenhum
como sequência. O alvo é o clone numa máquina nova:

    uv sync
    uv run python extractor/scripts/fetch_assets.py
    uv run python extractor/scripts/pipeline.py --all

**Staleness é hash de conteúdo**, gravado num `.stamp` por estágio. Não mtime:
`git checkout` reescreve mtime e cópia preserva, ou seja, mtime mente
exatamente quando dói — e o modo de falha é servir saída velha em silêncio, o
pior que um pipeline tem.

A única exceção é a pasta `assets/` do cliente: hashear centenas de MB a cada
invocação não se paga, e o `assets-manifest.json` já decide essa versão por
checksum (ticket 13).

Cada estágio **verifica antes de gastar tempo** e diz o que falta com o comando
que resolve. Os scripts individuais continuam falhando bem sozinhos, para quem
entra pelo meio.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys

import fetch_assets
import paths

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
EXTRACTOR_DIR = os.path.dirname(SCRIPTS_DIR)
REPO_DIR = os.path.dirname(EXTRACTOR_DIR)
STAMP_DIR = os.path.join(EXTRACTOR_DIR, ".stamps")

_HASH_CHUNK = 1024 * 1024
# Extensões que contam como entrada. Um diretório de sprites tem 200 mil PNGs;
# hashear os bytes deles a cada run custaria mais que refazer o estágio, então
# para árvore grande o que entra no hash é o inventário (caminho + tamanho).
_INVENTORY_ONLY = {"sprites", "atlases"}


def _hash_file(path, digest):
    digest.update(path.encode("utf-8"))
    with open(path, "rb") as handler:
        for chunk in iter(lambda: handler.read(_HASH_CHUNK), b""):
            digest.update(chunk)


def _hash_inventory(root, digest):
    """Caminho + tamanho de cada arquivo, sem ler bytes.

    Para `sprites/` (204 mil PNGs) e `atlases/`: ler o conteúdo inteiro a cada
    invocação custaria mais do que refazer o estágio. Um arquivo editado sem
    mudar de tamanho escaparia — o que nesses diretórios só acontece se alguém
    editar um PNG à mão, e para isso existe `--force`.
    """
    for current, dirs, files in os.walk(root):
        dirs.sort()
        for name in sorted(files):
            full = os.path.join(current, name)
            relative = os.path.relpath(full, root)
            digest.update(relative.encode("utf-8"))
            digest.update(str(os.path.getsize(full)).encode("utf-8"))


def input_hash(inputs) -> str:
    """Hash das entradas declaradas de um estágio. Entrada ausente conta como
    ausente (string fixa), não como erro: é o check que reclama, não o hash."""
    digest = hashlib.sha256()
    for entry in inputs:
        digest.update(b"\x00" + entry.encode("utf-8"))
        if not os.path.exists(entry):
            digest.update(b"<ausente>")
        elif os.path.isdir(entry):
            if os.path.basename(entry) in _INVENTORY_ONLY:
                _hash_inventory(entry, digest)
            else:
                for current, dirs, files in os.walk(entry):
                    dirs.sort()
                    for name in sorted(files):
                        _hash_file(os.path.join(current, name), digest)
        else:
            _hash_file(entry, digest)
    return digest.hexdigest()


def stamp_path(stage_name: str) -> str:
    return os.path.join(STAMP_DIR, f"{stage_name}.stamp")


def read_stamp(stage_name: str):
    path = stamp_path(stage_name)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as handler:
        return json.load(handler).get("inputHash")


def write_stamp(stage_name: str, digest: str) -> None:
    os.makedirs(STAMP_DIR, exist_ok=True)
    with open(stamp_path(stage_name), "w", encoding="utf-8") as handler:
        json.dump({"stage": stage_name, "inputHash": digest}, handler, indent=2)
        handler.write("\n")


class Stage:
    """Um passo do pipeline: o que precisa, o que lê, e o comando que roda."""

    def __init__(self, name, description, command, inputs=(), requires=()):
        self.name = name
        self.description = description
        self.command = command
        self.inputs = list(inputs)
        # (caminho, como obter) — o check, com a solução junto.
        self.requires = list(requires)

    def missing(self):
        return [(path, how) for path, how in self.requires if not os.path.exists(path)]

    def run(self, force=False, dry_run=False):
        missing = self.missing()
        if missing:
            print(f"[ERRO] {self.name}: falta o que este estágio precisa")
            for path, how in missing:
                print(f"         {os.path.relpath(path, REPO_DIR)}  ->  {how}")
            return False

        digest = input_hash(self.inputs) if self.inputs else None
        if not force and digest is not None and read_stamp(self.name) == digest:
            print(f"[skip] {self.name}: entradas não mudaram")
            return True

        printable = " ".join(self.command)
        if dry_run:
            print(f"[dry-run] {self.name}: {printable}")
            return True

        print(f"[..] {self.name}: {self.description}")
        result = subprocess.run(self.command, cwd=REPO_DIR)
        if result.returncode != 0:
            print(f"[ERRO] {self.name} falhou (exit {result.returncode}): {printable}")
            return False

        if digest is not None:
            # Rehash depois de rodar: um estágio que gera entrada de si mesmo
            # (raro, mas o bake de atlas encosta nisso) travaria num loop de
            # "sempre stale" se gravássemos o hash de antes.
            write_stamp(self.name, input_hash(self.inputs))
        return True


def _python():
    venv = os.path.join(REPO_DIR, ".venv", "bin", "python")
    return [venv] if os.path.exists(venv) else ["uv", "run", "python"]


def build_stages():
    py = _python()
    client_dir = paths.TIBIA_CLIENT.resolve(None)
    manifest = fetch_assets.load_manifest()
    client_assets = fetch_assets.assets_dir(client_dir, manifest)

    sprites = os.path.join(EXTRACTOR_DIR, "sprites")
    atlases = os.path.join(EXTRACTOR_DIR, "atlases")
    maps_dir = os.path.join(EXTRACTOR_DIR, "maps")
    vendor = os.path.join(EXTRACTOR_DIR, "vendor", "canary")

    fetch_cmd = "uv run python extractor/scripts/fetch_assets.py"

    return [
        Stage(
            "sprites",
            "recorta os PNGs do cliente para extractor/sprites/",
            py + [os.path.join(SCRIPTS_DIR, "extract_sprites.py"),
                  "--group", "items", "--group", "outfits",
                  "--group", "effects", "--group", "missiles"],
            # A pasta assets/ do cliente é a exceção declarada: o manifesto já
            # decide essa versão por checksum, hashear centenas de MB não paga.
            inputs=[os.path.join(EXTRACTOR_DIR, "assets-manifest.json")],
            requires=[(client_assets, fetch_cmd)],
        ),
        Stage(
            "items",
            "bakeia as folhas de item e o items-index.json",
            ["node", os.path.join(SCRIPTS_DIR, "build_items.js")],
            inputs=[os.path.join(sprites, "items")],
            requires=[(os.path.join(sprites, "items"),
                       "uv run python extractor/scripts/extract_sprites.py --group items")],
        ),
        Stage(
            "outfit-atlas",
            "bakeia um atlas por outfit de criatura",
            py + [os.path.join(SCRIPTS_DIR, "bake_outfit_atlas.py")],
            inputs=[os.path.join(sprites, "outfits")],
            requires=[(os.path.join(sprites, "outfits"),
                       "uv run python extractor/scripts/extract_sprites.py --group outfits")],
        ),
        Stage(
            "maps",
            "OTBM -> map.json + sheets/ + respawn.json de todo hunt",
            ["node", os.path.join(SCRIPTS_DIR, "build_map.js"), "--all"],
            inputs=[maps_dir, os.path.join(sprites, "items")],
            requires=[(maps_dir, "adicione um .otbm em extractor/maps/<CIDADE>/<pasta>/")],
        ),
        Stage(
            "effect-atlas",
            "bakeia o atlas de efeitos",
            py + [os.path.join(SCRIPTS_DIR, "bake_effect_atlas.py")],
            inputs=[os.path.join(sprites, "effects")],
            requires=[(os.path.join(sprites, "effects"),
                       "uv run python extractor/scripts/extract_sprites.py --group effects")],
        ),
        Stage(
            "corpse-atlas",
            "bakeia o atlas de corpos, lido dos respawn.json construídos",
            py + [os.path.join(SCRIPTS_DIR, "bake_corpse_atlas.py")],
            inputs=[os.path.join(EXTRACTOR_DIR, "ready-maps"),
                    os.path.join(EXTRACTOR_DIR, "monster-loot.json")],
            requires=[(os.path.join(EXTRACTOR_DIR, "monster-loot.json"),
                       "uv run python extractor/scripts/build_monster_loot_index.py")],
        ),
        Stage(
            "pool-atlas",
            "bakeia o atlas de poças",
            py + [os.path.join(SCRIPTS_DIR, "bake_pool_atlas.py")],
            inputs=[os.path.join(sprites, "items")],
        ),
        Stage(
            "flags",
            "tabela de flags por appearance, para o travel-graph",
            py + [os.path.join(SCRIPTS_DIR, "build_appearance_flags.py"), "ROOK"],
            inputs=[os.path.join(EXTRACTOR_DIR, "raw-maps", "ROOK.raw.json"),
                    os.path.join(sprites, "items")],
            requires=[(os.path.join(EXTRACTOR_DIR, "raw-maps", "ROOK.raw.json"),
                       "node extractor/scripts/dump_otbm.js ROOK")],
        ),
        Stage(
            "travel-graph",
            "locations + travelGraph do ROOK",
            py + [os.path.join(SCRIPTS_DIR, "build_travel_fragment.py"), "ROOK"],
            inputs=[os.path.join(EXTRACTOR_DIR, "raw-maps", "ROOK.raw.json"),
                    os.path.join(EXTRACTOR_DIR, "appearance-flags"),
                    vendor],
            requires=[(vendor, "uv run python extractor/scripts/update_canary_data.py")],
        ),
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--all", action="store_true", help="roda a sequência inteira")
    parser.add_argument("--stage", action="append", dest="stages", help="roda só este estágio (repetível)")
    parser.add_argument("--force", action="store_true", help="refaz mesmo com stamp válido")
    parser.add_argument("--check", action="store_true", help="só diz o que falta, não roda nada")
    parser.add_argument("--dry-run", action="store_true", help="diz o que rodaria")
    parser.add_argument("--list", action="store_true", help="lista os estágios em ordem")
    args = parser.parse_args()

    stages = build_stages()
    by_name = {stage.name: stage for stage in stages}

    if args.list:
        for stage in stages:
            print(f"  {stage.name:<14} {stage.description}")
        return

    if args.stages:
        unknown = [name for name in args.stages if name not in by_name]
        if unknown:
            parser.error(f"estágio desconhecido: {', '.join(unknown)}. "
                         f"Conhecidos: {', '.join(by_name)}")
        stages = [by_name[name] for name in args.stages]
    elif not args.all and not args.check:
        parser.error("passe --all, --stage <nome> ou --check")

    if args.check:
        problems = 0
        for stage in stages:
            missing = stage.missing()
            if not missing:
                print(f"[OK] {stage.name}")
                continue
            problems += 1
            print(f"[!!] {stage.name}: falta")
            for path, how in missing:
                print(f"       {os.path.relpath(path, REPO_DIR)}  ->  {how}")
        print(f"\n{len(stages) - problems}/{len(stages)} estágios prontos para rodar")
        sys.exit(1 if problems else 0)

    for stage in stages:
        if not stage.run(force=args.force, dry_run=args.dry_run):
            sys.exit(1)

    print("\nDONE ✔")


if __name__ == "__main__":
    main()
