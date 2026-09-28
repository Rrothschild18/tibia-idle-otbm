"""Recorta uma cidade do mapa-mundo do otservbr, pela máscara da Cyclopedia.

    extractor/full-maps/<CIDADE>/<CIDADE>.otbm
    extractor/full-maps/<CIDADE>/<CIDADE>-{monster,npc,house,zones}.xml
    extractor/full-maps/<CIDADE>/source.json

O escopo **não** é uma caixa: é a união das máscaras de tile das subáreas de
superfície da área escolhida (ver `map_regions.py`), coluna por coluna, em
**todos os andares**. Caixa arrasta vizinho de outra cidade pra dentro — uma
caixa de 401x401 em Carlin já entra com NPC de Kazordoon e com Ghostland.

A coordenada de mundo é preservada: o recorte **não** é rebaseado. Sem isso não
existe procedência — nada liga o recorte ao lugar de onde ele saiu, e uma hunt
pode ser rotulada com a placa de outra sem que nenhum check consiga reprovar.
Rookgaard era a exceção histórica (coordenada local, recortado à mão no
editor); desde que foi refeito por aqui, toda cidade em `full-maps/` está em
coordenada de mundo.

Run: uv run python extractor/scripts/cut_city.py CARLIN --area Carlin
     uv run python extractor/scripts/cut_city.py CARLIN --area Carlin --subareas 271,43,38
"""

import argparse
import json
import os
import sys
import time
import xml.etree.ElementTree as ElementTree

import fetch_assets
import map_regions
import otbm_stream
import paths

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
EXTRACTOR_DIR = os.path.dirname(SCRIPTS_DIR)
FULL_MAPS_DIR = os.path.join(EXTRACTOR_DIR, "full-maps")

WORLD_RELDIR = os.path.join("data-otservbr-global", "world")
WORLD_PREFIX = "otservbr"
SOURCE_MANIFEST = "source.json"


def world_paths(canary_dir: str, world_dir=None, prefix=WORLD_PREFIX) -> dict:
    directory = world_dir or os.path.join(canary_dir, WORLD_RELDIR)
    return {
        "otbm": os.path.join(directory, f"{prefix}.otbm"),
        "monster": os.path.join(directory, f"{prefix}-monster.xml"),
        "npc": os.path.join(directory, f"{prefix}-npc.xml"),
        "house": os.path.join(directory, f"{prefix}-house.xml"),
        "zones": os.path.join(directory, f"{prefix}-zones.xml"),
    }


def square_bounds(columns, margin: int):
    """A caixa quadrada que cobre as máscaras, com folga. -> `(min_x, min_y, max_x, max_y)`.

    O recorte de tiles é o quadrado; o de spawn e NPC continua sendo a máscara.
    A máscara sozinha desenha um minimapa com buraco: onde ela acaba o mapa
    acaba, sem mar e sem costa, e o retrato quadrado do jogo mostra um bloco
    preto que termina do nada. O quadrado dá contexto sem deixar entrar
    conteúdo de fora — bicho e NPC seguem filtrados pela máscara.
    """
    xs = [x for x, _ in columns]
    ys = [y for _, y in columns]
    width = max(xs) - min(xs) + 1
    height = max(ys) - min(ys) + 1
    side = max(width, height) + 2 * margin
    center_x = (min(xs) + max(xs)) // 2
    center_y = (min(ys) + max(ys)) // 2
    half = side // 2
    return (center_x - half, center_y - half, center_x + half, center_y + half)


def resolve_subareas(document, area, selected=None) -> list:
    masks = map_regions.masks_by_subarea(document)
    if selected is None:
        return [sid for sid in area.subarea_id if sid in masks]

    missing = [sid for sid in selected if sid not in masks]
    if missing:
        registry = map_regions.by_id(document)
        names = ", ".join(
            f"{sid} ({registry[sid].name if sid in registry else '?'})" for sid in missing
        )
        sys.exit(
            f"error: subárea sem máscara de contorno: {names}. "
            "Subárea de subsolo não tem contorno na Cyclopedia — ela entra pelos "
            "andares abaixo das subáreas de superfície que você escolher."
        )
    return list(selected)


def filter_spawn_file(source: str, destination: str, columns, tag: str) -> dict:
    tree = ElementTree.parse(source)
    root = tree.getroot()
    kept_groups = 0
    kept_entries = 0

    for group in list(root):
        center_x = int(group.get("centerx"))
        center_y = int(group.get("centery"))
        inside = (center_x, center_y) in columns
        if not inside:
            for entry in group:
                if (center_x + int(entry.get("x")), center_y + int(entry.get("y"))) in columns:
                    inside = True
                    break
        if inside:
            kept_groups += 1
            kept_entries += len(group)
        else:
            root.remove(group)

    ElementTree.indent(tree, space="\t")
    tree.write(destination, encoding="UTF-8", xml_declaration=True)
    return {f"{tag}Groups": kept_groups, f"{tag}Entries": kept_entries}


def filter_house_file(source: str, destination: str, columns) -> dict:
    tree = ElementTree.parse(source)
    root = tree.getroot()
    kept = 0
    for house in list(root):
        entry_x = house.get("entryx")
        entry_y = house.get("entryy")
        if entry_x is None or entry_y is None:
            root.remove(house)
            continue
        if (int(entry_x), int(entry_y)) in columns:
            kept += 1
        else:
            root.remove(house)
    ElementTree.indent(tree, space="\t")
    tree.write(destination, encoding="UTF-8", xml_declaration=True)
    return {"houses": kept}


def guard_destination(destination: str, force: bool) -> None:
    if not os.path.isdir(destination):
        return
    manifest = os.path.join(destination, SOURCE_MANIFEST)
    if not os.path.isfile(manifest):
        sys.exit(
            f"error: {destination} existe e não tem {SOURCE_MANIFEST} — é mapa feito "
            "à mão, e este script sobrescreveria o .otbm. Escolha outro código de "
            "cidade."
        )
    if not force:
        sys.exit(f"error: {destination} já foi recortado; use --force para refazer")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("city", help="código da cidade (pasta em full-maps/, ex: CARLIN)")
    parser.add_argument("--area", required=True, help="nome da área na Cyclopedia (ex: Carlin)")
    parser.add_argument(
        "--subareas",
        help="ids de subárea separados por vírgula; padrão é toda subárea da área que tem contorno",
    )
    parser.add_argument("--canary-dir", help="checkout do canary (fonte do mapa-mundo)")
    parser.add_argument("--client-dir", help="checkout do cliente Tibia extraído")
    parser.add_argument("--world-dir", help="pasta do mapa-mundo, se não for a do canary")
    parser.add_argument(
        "--shape",
        choices=("square", "mask"),
        default="square",
        help="forma do recorte de tiles: quadrado com folga (padrão) ou a máscara exata",
    )
    parser.add_argument(
        "--margin",
        type=int,
        default=16,
        help="folga em tiles ao redor da máscara, no modo quadrado",
    )
    parser.add_argument("--force", action="store_true", help="refaz um recorte já existente")
    args = parser.parse_args()

    city = args.city
    destination = os.path.join(FULL_MAPS_DIR, city)
    guard_destination(destination, args.force)

    client_dir = paths.TIBIA_CLIENT.require(args.client_dir)
    assets_dir = fetch_assets.assets_dir(client_dir, fetch_assets.load_manifest())
    document = map_regions.load(assets_dir)

    area = map_regions.find_area(document, args.area)
    if area is None:
        available = ", ".join(sorted(a.name for a in map_regions.areas(document)))
        sys.exit(f"error: área {args.area!r} não existe; disponíveis: {available}")

    selected = None
    if args.subareas:
        selected = [int(part) for part in args.subareas.split(",") if part.strip()]
    subarea_ids = resolve_subareas(document, area, selected)
    if not subarea_ids:
        sys.exit(f"error: nenhuma subárea com contorno em {area.name!r}")

    masks = map_regions.masks_by_subarea(document)
    registry = map_regions.by_id(document)
    columns = map_regions.union_columns(assets_dir, [masks[sid] for sid in subarea_ids])
    print(f"[OK] {len(subarea_ids)} subáreas, {len(columns):,} colunas de tile:")
    for subarea_id in subarea_ids:
        print(f"       {subarea_id:4d}  {registry[subarea_id].name}")

    canary_dir = paths.CANARY.require(args.canary_dir) if not args.world_dir else ""
    world = world_paths(canary_dir, args.world_dir)
    for kind, path in world.items():
        if not os.path.isfile(path):
            sys.exit(f"error: mapa-mundo sem {kind}: {path}")

    started = time.time()
    with open(world["otbm"], "rb") as handler:
        data = handler.read()
    print(f"[..] {os.path.basename(world['otbm'])}: {len(data) / 1e6:.0f} MB lidos")

    header = otbm_stream.map_header(data)
    if args.shape == "square":
        bounds = square_bounds(columns, args.margin)
        keep_column = lambda x, y: bounds[0] <= x <= bounds[2] and bounds[1] <= y <= bounds[3]
        print(
            f"[OK] recorte quadrado de {bounds[2] - bounds[0] + 1} tiles de lado "
            f"(máscara + {args.margin} de folga)"
        )
    else:
        bounds = (
            min(x for x, _ in columns),
            min(y for _, y in columns),
            max(x for x, _ in columns),
            max(y for _, y in columns),
        )
        keep_column = lambda x, y: (x, y) in columns

    areas = otbm_stream.crop_tiles(
        data,
        keep_column,
        bounds=bounds,
        progress=lambda scanned, kept: print(
            f"     {scanned:,} áreas varridas, {kept:,} tiles mantidos", flush=True
        ),
    )
    tile_count = sum(len(nodes) for _, nodes in areas)
    city_towns = [t for t in otbm_stream.towns(data) if (t["x"], t["y"]) in columns]

    os.makedirs(destination, exist_ok=True)
    written = otbm_stream.write_map(
        os.path.join(destination, f"{city}.otbm"),
        header,
        f"{city} recortado de {os.path.basename(world['otbm'])} por cut_city.py",
        f"{city}-monster.xml",
        f"{city}-house.xml",
        areas,
        city_towns,
    )

    counts = {}
    counts.update(
        filter_spawn_file(
            world["monster"], os.path.join(destination, f"{city}-monster.xml"), columns, "monster"
        )
    )
    counts.update(
        filter_spawn_file(
            world["npc"], os.path.join(destination, f"{city}-npc.xml"), columns, "npc"
        )
    )
    counts.update(
        filter_house_file(world["house"], os.path.join(destination, f"{city}-house.xml"), columns)
    )
    with open(world["zones"], encoding="utf-8") as handler:
        zones = handler.read()
    with open(os.path.join(destination, f"{city}-zones.xml"), "w", encoding="utf-8") as handler:
        handler.write(zones)

    manifest = {
        "city": city,
        "area": {"id": area.id, "name": area.name},
        "subareas": [
            {"id": sid, "name": registry[sid].name} for sid in subarea_ids
        ],
        "world": {
            "file": os.path.basename(world["otbm"]),
            "bytes": len(data),
        },
        "shape": args.shape,
        "bounds": {"minX": bounds[0], "minY": bounds[1], "maxX": bounds[2], "maxY": bounds[3]},
        "columns": len(columns),
        "tiles": written,
        "tileAreas": len(areas),
        "towns": city_towns,
        **counts,
    }
    with open(os.path.join(destination, SOURCE_MANIFEST), "w", encoding="utf-8") as handler:
        json.dump(manifest, handler, indent=2, ensure_ascii=False)
        handler.write("\n")

    floors = sorted({z for (_, _, z), _ in areas})
    print(
        f"[OK] {written:,} tiles em {len(areas):,} áreas, andares {floors[0]}..{floors[-1]} "
        f"-> {destination} ({time.time() - started:.0f}s)"
    )
    print(
        f"[OK] {counts['monsterGroups']} spawns ({counts['monsterEntries']} criaturas), "
        f"{counts['npcEntries']} NPCs, {counts['houses']} casas, {len(city_towns)} towns"
    )


if __name__ == "__main__":
    main()
