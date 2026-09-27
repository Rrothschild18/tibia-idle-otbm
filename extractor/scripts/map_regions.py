"""As regiões oficiais do Tibia (Areas/Subareas da Cyclopedia), lidas do cliente.

Fonte: `map-<sha>.dat` da pasta `assets/` do cliente — a entrada `type: "map"`
do `catalog-content.json`. Schema em `MapRegions.proto` (reconstruído por
inspeção; ver o cabeçalho de lá).

O que o arquivo dá, e o que não dá:

- 28 Areas e 424 Subareas com id, nome, centro e a lista de subáreas de cada
  área. Uma subárea pode pertencer a mais de uma área (Tibiadrome está em Thais
  e em Kazordoon), então a volta é `areaIds`, plural.
- Máscara de tile só das subáreas de **superfície** (204 das 424): a Cyclopedia
  pinta o mapa de cima, então toda subárea de subsolo — Carlin Underground,
  Kazordoon Dwarf Mines, Mintwallin — existe como nome e não como contorno.
  Quem precisa de subsolo usa a coluna x/y da superfície e desce de andar.
- 1211 pontos de interesse (NPC e boss) com posição e a subárea a que pertencem.

A máscara é **um pixel por tile**: pixel opaco em `(px, py)` é o tile
`(origin.x + px, origin.y + py)`, em qualquer andar.
"""

import json
import os
from typing import Dict, Iterable, List, Optional, Set, Tuple

import client_sprites

import MapRegions_pb2 as map_regions_pb2

CATALOG_NAME = "catalog-content.json"
MAP_CATALOG_TYPE = "map"


class MissingMapDataError(Exception):
    """O cliente extraído não tem a entrada `type: "map"` no catálogo."""


def map_data_path(assets_dir: str) -> str:
    catalog_path = os.path.join(assets_dir, CATALOG_NAME)
    if not os.path.isfile(catalog_path):
        raise MissingMapDataError(
            f"esperava {CATALOG_NAME} em {assets_dir}; rode fetch_assets.py"
        )

    with open(catalog_path, encoding="utf-8") as handler:
        catalog = json.load(handler)

    for entry in catalog:
        if entry.get("type") == MAP_CATALOG_TYPE:
            return os.path.join(assets_dir, entry["file"])

    raise MissingMapDataError(
        f"{CATALOG_NAME} não tem entrada type={MAP_CATALOG_TYPE!r} em {assets_dir}"
    )


def load(assets_dir: str) -> map_regions_pb2.MapRegions:
    document = map_regions_pb2.MapRegions()
    with open(map_data_path(assets_dir), "rb") as handler:
        document.ParseFromString(handler.read())
    return document


def areas(document) -> List:
    return [r for r in document.region if r.kind == map_regions_pb2.AREA]


def subareas(document) -> List:
    return [r for r in document.region if r.kind == map_regions_pb2.SUBAREA]


def by_id(document) -> Dict[int, object]:
    return {r.id: r for r in document.region}


def area_ids_by_subarea(document) -> Dict[int, List[int]]:
    parents: Dict[int, List[int]] = {}
    for area in areas(document):
        for subarea_id in area.subarea_id:
            parents.setdefault(subarea_id, []).append(area.id)
    return parents


def masks_by_subarea(document) -> Dict[int, object]:
    return {
        image.subarea_id: image
        for image in document.image
        if image.kind == map_regions_pb2.SUBAREA_MASK and image.subarea_id
    }


def find_area(document, name: str):
    for area in areas(document):
        if area.name == name:
            return area
    return None


def mask_image(assets_dir: str, image):
    """A máscara descomprimida, em RGBA. Pixel opaco = o tile pertence."""
    path = os.path.join(assets_dir, image.file)
    with open(path, "rb") as handler:
        return client_sprites.decode_sheet(handler.read()).convert("RGBA")


def mask_columns(assets_dir: str, image) -> Set[Tuple[int, int]]:
    """A máscara como conjunto de colunas `(x, y)` em coordenada de mundo."""
    picture = mask_image(assets_dir, image)
    pixels = picture.load()
    width, height = picture.size
    origin_x, origin_y = image.position.x, image.position.y
    columns = set()
    for py in range(height):
        for px in range(width):
            red, green, blue, alpha = pixels[px, py]
            if alpha and (red or green or blue):
                columns.add((origin_x + px, origin_y + py))
    return columns


def union_columns(assets_dir: str, images: Iterable) -> Set[Tuple[int, int]]:
    union: Set[Tuple[int, int]] = set()
    for image in images:
        union |= mask_columns(assets_dir, image)
    return union


def _position(position) -> Optional[Dict[str, int]]:
    if not position.ByteSize():
        return None
    return {"x": position.x, "y": position.y, "z": position.z}


def to_catalog(document, mask_file_for=None) -> Dict:
    """O documento como JSON estável, para revisão e para o front consumir.

    `mask_file_for(subarea_id, image)` decide o caminho publicado da máscara;
    sem ele o caminho é o nome do arquivo do próprio cliente.
    """
    parents = area_ids_by_subarea(document)
    masks = masks_by_subarea(document)

    def mask_entry(subarea_id):
        image = masks.get(subarea_id)
        if image is None:
            return None
        return {
            "file": (
                mask_file_for(subarea_id, image) if mask_file_for else image.file
            ),
            "origin": _position(image.position),
            "width": image.width,
            "height": image.height,
        }

    return {
        "worldBounds": {
            "min": _position(document.min_position),
            "max": _position(document.max_position),
        },
        "areas": [
            {
                "id": area.id,
                "name": area.name,
                "hidden": area.hidden,
                "center": _position(area.center),
                "subareas": sorted(area.subarea_id),
            }
            for area in sorted(areas(document), key=lambda a: a.id)
        ],
        "subareas": [
            {
                "id": subarea.id,
                "name": subarea.name,
                "areaIds": sorted(parents.get(subarea.id, [])),
                "center": _position(subarea.center),
                "mask": mask_entry(subarea.id),
            }
            for subarea in sorted(subareas(document), key=lambda s: s.id)
        ],
        "pointsOfInterest": [
            {
                "name": poi.name,
                "x": poi.position.x,
                "y": poi.position.y,
                "z": poi.position.z,
                "subareaId": poi.subarea_id,
            }
            for poi in sorted(
                document.point_of_interest,
                key=lambda p: (p.subarea_id, p.name, p.position.x, p.position.y),
            )
        ],
    }
