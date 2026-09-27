"""Emite o catálogo de regiões do Tibia e as máscaras de subárea como PNG.

    extractor/map-regions/regions.json
    extractor/map-regions/masks/<id>.png     (só as 204 subáreas de superfície)

Lê o `map-<sha>.dat` do cliente extraído (ver `map_regions.py`) e nada mais.
Nada fora de `extractor/` é tocado.

Run: uv run python extractor/scripts/build_map_regions.py
     uv run python extractor/scripts/build_map_regions.py --area Carlin
"""

import argparse
import json
import os
import sys

import fetch_assets
import map_regions
import paths

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
EXTRACTOR_DIR = os.path.dirname(SCRIPTS_DIR)
OUTPUT_DIR = os.path.join(EXTRACTOR_DIR, "map-regions")
MASKS_DIR_NAME = "masks"


def mask_file_name(subarea_id: int) -> str:
    return f"{MASKS_DIR_NAME}/{subarea_id:04d}.png"


def write_masks(document, assets_dir: str, output_dir: str) -> int:
    masks_dir = os.path.join(output_dir, MASKS_DIR_NAME)
    os.makedirs(masks_dir, exist_ok=True)

    written = 0
    for subarea_id, image in sorted(map_regions.masks_by_subarea(document).items()):
        picture = map_regions.mask_image(assets_dir, image)
        picture.save(os.path.join(output_dir, mask_file_name(subarea_id)))
        written += 1
    return written


def report_area(document, assets_dir: str, name: str) -> None:
    area = map_regions.find_area(document, name)
    if area is None:
        available = ", ".join(sorted(a.name for a in map_regions.areas(document)))
        sys.exit(f"error: área {name!r} não existe; disponíveis: {available}")

    masks = map_regions.masks_by_subarea(document)
    registry = map_regions.by_id(document)
    print(f"\n{area.name} (id {area.id}) — {len(area.subarea_id)} subáreas")
    total = 0
    for subarea_id in area.subarea_id:
        subarea = registry.get(subarea_id)
        image = masks.get(subarea_id)
        if image is None:
            print(f"  {'':>8}  {subarea_id:4d}  {subarea.name if subarea else '?'}")
            continue
        columns = map_regions.mask_columns(assets_dir, image)
        total += len(columns)
        print(
            f"  {len(columns):>8,}  {subarea_id:4d}  {subarea.name if subarea else '?'}"
        )
    print(f"  {total:>8,}  colunas somadas (com sobreposição entre subáreas)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-dir", help="checkout do cliente Tibia extraído")
    parser.add_argument("--area", help="imprime o detalhe de uma área e sai")
    parser.add_argument("--output-dir", default=OUTPUT_DIR)
    args = parser.parse_args()

    client_dir = paths.TIBIA_CLIENT.require(args.client_dir)
    manifest = fetch_assets.load_manifest()
    assets_dir = fetch_assets.assets_dir(client_dir, manifest)

    document = map_regions.load(assets_dir)

    if args.area:
        report_area(document, assets_dir, args.area)
        return

    os.makedirs(args.output_dir, exist_ok=True)
    catalog = map_regions.to_catalog(
        document, mask_file_for=lambda subarea_id, image: mask_file_name(subarea_id)
    )
    catalog_path = os.path.join(args.output_dir, "regions.json")
    with open(catalog_path, "w", encoding="utf-8") as handler:
        json.dump(catalog, handler, indent=2, ensure_ascii=False)
        handler.write("\n")

    masks = write_masks(document, assets_dir, args.output_dir)
    print(
        f"[OK] {len(catalog['areas'])} áreas, {len(catalog['subareas'])} subáreas, "
        f"{len(catalog['pointsOfInterest'])} POIs -> {catalog_path}"
    )
    print(f"[OK] {masks} máscaras de subárea -> {os.path.join(args.output_dir, MASKS_DIR_NAME)}")


if __name__ == "__main__":
    main()
