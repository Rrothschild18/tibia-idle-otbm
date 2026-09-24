"""Gera o minimapa de uma cidade: um PNG indexado por andar, um pixel por tile.

    extractor/full-maps/<CIDADE>/minimap/z<Z>.png
    extractor/full-maps/<CIDADE>/minimap/bounds.json

O mapa de cidade inteira nunca gerou artefato de render — `build_phaser_map.py`
sai cedo nele, porque a folha de sprites de uma cidade inteira não se paga. O
minimapa não esbarra nisso: ele não usa sprite nenhum, só o `automapColor` que
`build_appearance_flags.py` já grava por appearance. Daí este estágio ser
separado, e não um ramo daquele.

Lê `raw-maps/<CIDADE>.raw.json` (os tiles) e `appearance-flags/<CIDADE>.json`
(a cor de cada appearance, overrides incluídos). Nada fora de `extractor/` é
tocado — publicar é `publish.py`.

Run: uv run python extractor/scripts/build_city_minimap.py ROOK
"""

import argparse
import json
import os
import sys

from PIL import Image

import appearance_flags
import map_v6
import minimap

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
EXTRACTOR_DIR = os.path.dirname(SCRIPTS_DIR)
RAW_MAPS_DIR = os.path.join(EXTRACTOR_DIR, "raw-maps")
FULL_MAPS_DIR = os.path.join(EXTRACTOR_DIR, "full-maps")
MINIMAP_DIR_NAME = "minimap"
BOUNDS_NAME = "bounds.json"


def minimap_dir(city: str) -> str:
    return os.path.join(FULL_MAPS_DIR, city, MINIMAP_DIR_NAME)


def colors_by_appearance(city: str) -> dict:
    """`{appearance id: índice de cor}` a partir da tabela de flags. Só quem
    tem cor entra — a tabela já descarta valor falso, e um id ausente vale 0
    para `minimap.city_minimap`."""
    table = appearance_flags.load_flags(city)
    return {
        int(appearance_id): flags["automapColor"]
        for appearance_id, flags in table.items()
        if flags.get("automapColor")
    }


def write_floor_png(path: str, pixels, width: int, height: int) -> None:
    """PNG indexado de 8 bits com a paleta do Tibia. O índice 0 é a ausência
    de tile e sai transparente: um andar de caverna é quase todo buraco, e
    preto opaco esconderia a superfície embaixo dele no front."""
    image = Image.new("P", (width, height))
    image.putpalette(minimap.palette_bytes())
    image.putdata(pixels)
    image.save(path, format="PNG", optimize=True, transparency=minimap.EMPTY_COLOR)


def build_city_minimap(city: str) -> dict:
    """-> o `bounds.json` escrito. Um PNG por andar com tile, e nada mais."""
    dump_path = os.path.join(RAW_MAPS_DIR, f"{city}.raw.json")
    if not os.path.exists(dump_path):
        print(f"[ERROR] dump não encontrado em {dump_path}")
        print(f"        rode 'node extractor/scripts/dump_otbm.js {city}' primeiro")
        sys.exit(1)

    with open(dump_path, "r", encoding="utf-8") as handler:
        dump = json.load(handler)

    try:
        colors = colors_by_appearance(city)
    except appearance_flags.MissingFlagsTableError as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)

    # Os mesmos bounds que o `respawn.json` do full-map usa: união entre
    # andares, porque (x, y) é a mesma coluna física em todo andar.
    bounds = map_v6.map_bounds(dump)
    floors = minimap.city_minimap(dump, colors)

    output_dir = minimap_dir(city)
    os.makedirs(output_dir, exist_ok=True)

    document = minimap.bounds_document(city, bounds, floors)
    with open(os.path.join(output_dir, BOUNDS_NAME), "w", encoding="utf-8") as handler:
        json.dump(document, handler, indent=2, ensure_ascii=False)
        handler.write("\n")

    total_tiles = 0
    for z in document["floors"]:
        colors_here = floors[z]
        total_tiles += len(colors_here)
        pixels = minimap.floor_pixels(colors_here, bounds)
        png_path = os.path.join(output_dir, f"z{z}.png")
        write_floor_png(png_path, pixels, document["width"], document["height"])
        painted = sum(1 for color in colors_here.values() if color)
        print(f"[OK] z{z}: {len(colors_here)} tiles ({painted} com cor) -> "
              f"{os.path.basename(png_path)} "
              f"({os.path.getsize(png_path) / 1024:.1f} KB)")

    print(f"[OK] {len(document['floors'])} andares, {total_tiles} tiles, "
          f"{document['width']}x{document['height']} -> {output_dir}")
    return document


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("city", help="Código da cidade (ex: ROOK)")
    args = parser.parse_args()
    build_city_minimap(args.city)


if __name__ == "__main__":
    main()
