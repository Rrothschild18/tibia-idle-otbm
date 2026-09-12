"""O único comando que escreve no checkout do `tibia-idle`.

Antes disto **nenhum script** levava um bundle pro repo irmão: a cópia era
manual. A prova estava no que chegou — os bundles publicados carregam
`map.json` + `sheets/` mas **não** o `monsters/respawn.json` que o mesmo passo
escreve. Cópia seletiva de humano, não sync.

E a cobertura de atlas estava invertida: o `sync_items` cobria `items-static/`,
`items-animated/`, `items-index.json` e `player-outfits/`, e **não** cobria
`outfits/`, `effects/`, `corpses/`, `pools/` — enquanto o `respawn.json` aponta
os monstros justamente para `assets/outfits/...`. No front existiam os três
copiados à mão e faltavam os que o sync cobria.

A separação do `CONTEXT.md` continua intacta, e fica **mais forte**: gerar
fragmento nunca escreve fora de `extractor/`; publicar é este comando, e só ele.

Run: uv run python extractor/scripts/publish.py <mapa|--all> [--prune]
"""

import argparse
import json
import os
import shutil
import sys

import map_dirs
import paths

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
EXTRACTOR_DIR = os.path.dirname(SCRIPTS_DIR)
ATLASES_DIR = os.path.join(EXTRACTOR_DIR, "atlases")
READY_MAPS_DIR = os.path.join(EXTRACTOR_DIR, "ready-maps")

FRONT_ASSETS_RELPATH = os.path.join("apps", "tibia-idle-front", "public", "assets")

# Todo atlas que o front serve, com o comando que o gera. O erro de um atlas
# faltando tem que dizer o que rodar — foi a falta disso que deixou
# `assets/outfits/` ausente no front enquanto o respawn.json apontava pra lá.
ATLAS_TARGETS = {
    "items-static": "node extractor/scripts/build_items.js",
    "items-animated": "node extractor/scripts/build_items.js",
    "outfits": "uv run python extractor/scripts/bake_outfit_atlas.py",
    "player-outfits": "uv run python extractor/scripts/bake_player_outfit_sheet.py",
    "effects": "uv run python extractor/scripts/bake_effect_atlas.py",
    "corpses": "uv run python extractor/scripts/bake_corpse_atlas.py",
    "pools": "uv run python extractor/scripts/bake_pool_atlas.py",
}

ATLAS_FILES = {
    "items-index.json": "node extractor/scripts/build_items.js",
}


class MissingAtlasError(Exception):
    """Atlas referenciado que nunca foi bakeado, com o comando que o gera."""


def files_differ(src_path: str, dst_path: str) -> bool:
    if not os.path.exists(dst_path):
        return True
    if os.path.getsize(src_path) != os.path.getsize(dst_path):
        return True
    with open(src_path, "rb") as src, open(dst_path, "rb") as dst:
        return src.read() != dst.read()


def copy_if_different(src_path: str, dst_path: str) -> bool:
    """Copia só se os bytes diferem. Evita mexer em mtime e sujar diff."""
    if not files_differ(src_path, dst_path):
        return False
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    shutil.copyfile(src_path, dst_path)
    return True


def sync_tree(src_dir: str, dst_dir: str):
    """Copia recursivamente, comparando conteúdo. -> (copiados, iguais)."""
    copied = unchanged = 0
    for root, _dirs, files in os.walk(src_dir):
        for name in sorted(files):
            src_path = os.path.join(root, name)
            relative = os.path.relpath(src_path, src_dir)
            if copy_if_different(src_path, os.path.join(dst_dir, relative)):
                copied += 1
            else:
                unchanged += 1
    return copied, unchanged


def bundle_dir_name(map_dir: str) -> str:
    """`<MAP>-sprites-v<N>` — lido do próprio `map.json`, não remontado.

    O `assetsRoot` que o mapa declara **é** o caminho que o jogo vai pedir.
    recalcular aqui criaria uma segunda fonte de verdade para o mesmo nome, e
    divergir significa o front servir 404 no bundle inteiro.
    """
    map_json = os.path.join(map_dir, "map.json")
    with open(map_json, "r", encoding="utf-8") as handler:
        document = json.load(handler)

    assets_root = document.get("assetsRoot")
    if not assets_root:
        raise MissingAtlasError(
            f"{map_json} não declara `assetsRoot` — bundle de uma versão antiga do "
            f"pipeline. Reconstrua com 'node extractor/scripts/build_map.js <pasta>'."
        )
    return os.path.basename(assets_root.rstrip("/"))


def referenced_atlases(map_dir: str):
    """Os atlases que este bundle precisa, lidos do `respawn.json`.

    Hoje é só `outfits/` (o monsterDef aponta `assets/outfits/<id>.png`); os
    outros são globais do front. Ler em vez de assumir é o que faz o erro
    aparecer aqui e não como imagem quebrada na tela.
    """
    respawn_path = os.path.join(map_dir, "monsters", "respawn.json")
    if not os.path.exists(respawn_path):
        return set()

    with open(respawn_path, "r", encoding="utf-8") as handler:
        respawn = json.load(handler)

    needed = set()
    for definition in respawn.get("monsterDefs", {}).values():
        atlas = definition.get("atlas")
        if not atlas:
            continue
        for key in ("image", "json"):
            value = atlas.get(key)
            if value and value.startswith("assets/"):
                needed.add(value.split("/")[1])
    return needed


def check_atlases(required) -> None:
    missing = []
    for name in sorted(required):
        source = os.path.join(ATLASES_DIR, name)
        if not os.path.isdir(source) or not os.listdir(source):
            missing.append((name, ATLAS_TARGETS.get(name, "(bake desconhecido)")))
    if missing:
        lines = "\n".join(f"  - atlases/{name}/  ->  {command}" for name, command in missing)
        raise MissingAtlasError(
            "atlas referenciado pelo bundle que nunca foi bakeado:\n" + lines
        )


def publish_bundle(map_name: str, front_assets: str, dry_run=False):
    map_dir = map_dirs.find_two_level_dir(READY_MAPS_DIR, map_name)
    if map_dir is None:
        raise SystemExit(
            f"[ERRO] mapa '{map_name}' não encontrado em {READY_MAPS_DIR}; "
            f"rode 'node extractor/scripts/build_map.js {map_name}'"
        )

    check_atlases(referenced_atlases(map_dir))

    destination = os.path.join(front_assets, bundle_dir_name(map_dir))
    if dry_run:
        print(f"[dry-run] {map_name} -> {destination}")
        return 0, 0

    copied, unchanged = sync_tree(map_dir, destination)
    print(f"[OK] {map_name}: {copied} copiados, {unchanged} já atualizados -> {destination}")
    return copied, unchanged


def publish_atlases(front_assets: str, dry_run=False):
    for name in sorted(ATLAS_TARGETS):
        source = os.path.join(ATLASES_DIR, name)
        if not os.path.isdir(source):
            print(f"[--] atlases/{name}/: não bakeado ({ATLAS_TARGETS[name]})")
            continue
        if dry_run:
            total = sum(len(files) for _root, _dirs, files in os.walk(source))
            print(f"[dry-run] atlases/{name}/: {total} arquivo(s) -> "
                  f"{os.path.join(front_assets, name)}")
            continue
        copied, unchanged = sync_tree(source, os.path.join(front_assets, name))
        print(f"[OK] atlases/{name}/: {copied} copiados, {unchanged} já atualizados")

    for name, command in ATLAS_FILES.items():
        source = os.path.join(ATLASES_DIR, name)
        if not os.path.exists(source):
            print(f"[--] atlases/{name}: não gerado ({command})")
            continue
        if dry_run:
            print(f"[dry-run] atlases/{name} -> {os.path.join(front_assets, name)}")
            continue
        changed = copy_if_different(source, os.path.join(front_assets, name))
        print(f"[OK] atlases/{name}: {'copiado' if changed else 'já atualizado'}")


def prune_bundles(front_assets: str, keep, apply: bool):
    """Remove bundles publicados que o conjunto atual não referencia.

    Só com `--prune`, e listando antes. Um comando que apaga no repo irmão por
    padrão é lamentado exatamente uma vez.
    """
    if not os.path.isdir(front_assets):
        return
    stale = sorted(
        name for name in os.listdir(front_assets)
        if "-sprites-v" in name
        and os.path.isdir(os.path.join(front_assets, name))
        and name not in keep
    )
    if not stale:
        print("[OK] --prune: nada a remover")
        return

    print(f"[!] --prune removeria {len(stale)} bundle(s) não referenciado(s):")
    for name in stale:
        print(f"      {name}")
    if not apply:
        return
    for name in stale:
        shutil.rmtree(os.path.join(front_assets, name))
    print(f"[OK] {len(stale)} bundle(s) removido(s)")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("map", nargs="?", help="pasta do mapa (ex: ROOK-HUNT-0001_rats-sewers-2-rookguard)")
    parser.add_argument("--all", action="store_true", help="publica todo mapa construído em ready-maps/")
    parser.add_argument("--atlases-only", action="store_true", help="publica só os atlases globais")
    parser.add_argument("--prune", action="store_true",
                        help="remove do destino os bundles que este run não publicou (lista antes)")
    parser.add_argument("--dry-run", action="store_true", help="diz o que faria, sem escrever")
    parser.add_argument("--tibia-idle-dir", default=None,
                        help=f"checkout do tibia-idle (default: ${paths.TIBIA_IDLE.env_var} "
                             f"ou {paths.TIBIA_IDLE.sibling_default()})")
    args = parser.parse_args()

    if not args.map and not args.all and not args.atlases_only:
        parser.error("passe um mapa, --all ou --atlases-only")

    # `--prune` só faz sentido com `--all`: o conjunto de referência é "o que
    # este run publicou", e num run de um mapa só (ou só de atlas) esse
    # conjunto é vazio ou quase — apagaria todo o resto do front.
    if args.prune and not args.all:
        parser.error("--prune só com --all: o conjunto de referência é o que o run publicou, "
                     "e um run parcial apagaria os bundles que ele simplesmente não tocou")

    try:
        tibia_idle_dir = paths.TIBIA_IDLE.require(args.tibia_idle_dir)
    except paths.MissingRepoError as exc:
        parser.error(str(exc))

    front_assets = os.path.join(tibia_idle_dir, FRONT_ASSETS_RELPATH)
    if not os.path.isdir(front_assets):
        parser.error(f"pasta de assets do front não encontrada em {front_assets}")

    map_names = []
    if args.all:
        map_names = map_dirs.discover_two_level_names(READY_MAPS_DIR, "map.json")
        if not map_names:
            parser.error(f"nenhum mapa construído em {READY_MAPS_DIR}")
    elif args.map:
        map_names = [args.map]

    published = set()
    try:
        for map_name in map_names:
            map_dir = map_dirs.find_two_level_dir(READY_MAPS_DIR, map_name)
            if map_dir is not None:
                published.add(bundle_dir_name(map_dir))
            publish_bundle(map_name, front_assets, dry_run=args.dry_run)
    except MissingAtlasError as exc:
        print(f"[ERRO] {exc}")
        sys.exit(1)

    publish_atlases(front_assets, dry_run=args.dry_run)

    if args.prune:
        prune_bundles(front_assets, published, apply=not args.dry_run)


if __name__ == "__main__":
    main()
