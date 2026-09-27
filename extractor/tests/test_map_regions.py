import json
import os
import sys

import pytest
from PIL import Image

SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import MapRegions_pb2 as pb
import map_regions


def _document():
    document = pb.MapRegions()
    document.min_position.x, document.min_position.y = 31872, 30976
    document.max_position.x, document.max_position.y = 34143, 33023

    area = document.region.add()
    area.id, area.name, area.kind = 3, "Carlin", pb.AREA
    area.subarea_id.extend([271, 37])
    area.center.x, area.center.y, area.center.z = 32364, 31706, 7

    city = document.region.add()
    city.id, city.name, city.kind = 271, "Carlin City", pb.SUBAREA
    city.center.x, city.center.y, city.center.z = 32340, 31789, 7

    underground = document.region.add()
    underground.id, underground.name, underground.kind = 37, "Carlin Underground", pb.SUBAREA

    mask = document.image.add()
    mask.kind, mask.subarea_id, mask.file = pb.SUBAREA_MASK, 271, "mask.bmp.lzma"
    mask.position.x, mask.position.y, mask.position.z = 100, 200, 7
    mask.width, mask.height = 3, 2

    satellite = document.image.add()
    satellite.kind, satellite.file = pb.SATELLITE, "satellite.bmp.lzma"

    poi = document.point_of_interest.add()
    poi.name, poi.subarea_id = "Alia", 271
    poi.position.x, poi.position.y, poi.position.z = 32360, 31785, 7

    return document


def test_areas_subareas_and_parents_are_separated_by_kind():
    document = _document()

    assert [a.name for a in map_regions.areas(document)] == ["Carlin"]
    assert sorted(s.name for s in map_regions.subareas(document)) == [
        "Carlin City",
        "Carlin Underground",
    ]
    assert map_regions.area_ids_by_subarea(document) == {271: [3], 37: [3]}
    assert map_regions.find_area(document, "Carlin").id == 3
    assert map_regions.find_area(document, "Thais") is None


def test_only_subarea_masks_are_indexed_by_subarea():
    masks = map_regions.masks_by_subarea(_document())

    assert list(masks) == [271]
    assert masks[271].width == 3


def test_mask_columns_are_world_coordinates_of_the_opaque_pixels(tmp_path, monkeypatch):
    picture = Image.new("RGBA", (3, 2), (0, 0, 0, 0))
    picture.putpixel((0, 0), (255, 255, 255, 255))
    picture.putpixel((2, 1), (255, 255, 255, 255))
    monkeypatch.setattr(map_regions, "mask_image", lambda assets_dir, image: picture)
    image = map_regions.masks_by_subarea(_document())[271]

    columns = map_regions.mask_columns("ignored", image)

    assert columns == {(100, 200), (102, 201)}


def test_to_catalog_keeps_the_mask_path_and_reports_the_ones_without_it():
    catalog = map_regions.to_catalog(
        _document(), mask_file_for=lambda subarea_id, image: f"masks/{subarea_id:04d}.png"
    )

    assert catalog["worldBounds"]["min"]["x"] == 31872
    assert catalog["areas"][0]["subareas"] == [37, 271]

    by_id = {entry["id"]: entry for entry in catalog["subareas"]}
    assert by_id[271]["mask"]["file"] == "masks/0271.png"
    assert by_id[271]["mask"]["origin"] == {"x": 100, "y": 200, "z": 7}
    assert by_id[37]["mask"] is None
    assert by_id[37]["areaIds"] == [3]
    assert catalog["pointsOfInterest"][0]["name"] == "Alia"
    assert json.dumps(catalog)


def test_missing_catalog_entry_says_what_to_run(tmp_path):
    with open(os.path.join(tmp_path, map_regions.CATALOG_NAME), "w", encoding="utf-8") as handler:
        json.dump([{"type": "appearances", "file": "appearances.dat"}], handler)

    with pytest.raises(map_regions.MissingMapDataError) as failure:
        map_regions.map_data_path(str(tmp_path))

    assert "type='map'" in str(failure.value)
