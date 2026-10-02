"""Re-corta uma hunt a partir da máscara desenhada no editor.

O editor (tibia-idle-map-editor) grava hunt-masks/<HUNT-ID>.json com o conjunto
EXATO de tiles (coordenada de mundo, por andar) que o Rault pintou. Aqui esse
conjunto vira o recorte — generalizando a caixa retangular de `write_hunt_map`
pra uma máscara de forma livre (via o parâmetro `tile_in`). É o que resolve a
delimitação em mapa aberto: o limite é desenhado, não adivinhado pelo trim.

Depois recorta, renderiza com build_map.js. Export/publish seguem pelo pipeline
normal.

Run: uv run python scripts/apply_hunt_mask.py CARLIN-HUNT-0003
"""

import argparse
import json
import os
import subprocess
import sys

import build_curated_hunts as bch
import otbm_stream
import paths

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
EXTRACTOR_DIR = os.path.dirname(SCRIPTS_DIR)
MASK_DIR = os.path.join(EXTRACTOR_DIR, "hunt-masks")


def _bundle_slug(assets_dir: str, hunt_id: str) -> str:
    for name in sorted(os.listdir(assets_dir)):
        if name.startswith(f"{hunt_id}_") and name.endswith("-sprites-v6"):
            return name[len(f"{hunt_id}_") : -len("-sprites-v6")]
    sys.exit(f"error: bundle de {hunt_id} não achado em {assets_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("hunt_id")
    parser.add_argument("--tibia-idle-dir")
    parser.add_argument("--no-build", action="store_true", help="só recorta, não roda build_map.js")
    args = parser.parse_args()

    mask_file = os.path.join(MASK_DIR, f"{args.hunt_id}.json")
    if not os.path.exists(mask_file):
        sys.exit(f"error: máscara não encontrada em {mask_file} (salve no editor primeiro)")
    with open(mask_file, encoding="utf-8") as handle:
        mask = json.load(handle)

    city = args.hunt_id.split("-")[0]
    floors = {int(z) for z in mask["floors"]}
    union = {(int(x), int(y)) for cells in mask["floors"].values() for x, y in cells}
    if not union:
        sys.exit("error: máscara vazia")
    xs = [x for x, _ in union]
    ys = [y for _, y in union]
    box = [min(xs), min(ys), max(xs), max(ys)]

    tibia_idle = paths.TIBIA_IDLE.require(args.tibia_idle_dir)
    assets_dir = os.path.join(tibia_idle, "apps", "tibia-idle-front", "public", "assets")
    slug = _bundle_slug(assets_dir, args.hunt_id)
    with open(os.path.join(assets_dir, f"{args.hunt_id}_{slug}-sprites-v6", "map.json"), encoding="utf-8") as h:
        bundle_map = json.load(h)
    b = bundle_map["bounds"]
    start = bundle_map.get("start") or {"x": 0, "y": 0, "z": min(floors)}
    entrance = [b["minX"] + start["x"], b["minY"] + start["y"], start["z"]]
    if (entrance[0], entrance[1]) not in union:
        # a entrada antiga saiu da máscara; pega o tile mascarado mais próximo no mesmo andar
        same = [(x, y) for (x, y) in union] or list(union)
        entrance = [*min(same, key=lambda p: abs(p[0] - entrance[0]) + abs(p[1] - entrance[1])), start["z"]]

    otbm = os.path.join(bch.FULL_MAPS_DIR, city, f"{city}.otbm")
    with open(otbm, "rb") as handle:
        data = handle.read()
    header = otbm_stream.map_header(data)

    hunt = {"id": args.hunt_id, "slug": slug, "folder": f"{args.hunt_id}_{slug}", "name": args.hunt_id}
    result = bch.write_hunt_map(
        city, hunt, data, header, box, floors, entrance=entrance, tile_in=lambda x, y: (x, y) in union
    )
    print(f"[OK] re-corte pela máscara: {result['tiles']} tiles ({len(union)} na máscara), andares {sorted(floors)}")
    if not result["marked"]:
        sys.exit("error: entrada fora do recorte — sem marcador de start")

    if not args.no_build:
        build = subprocess.run(["node", "scripts/build_map.js", hunt["folder"]], cwd=EXTRACTOR_DIR)
        if build.returncode != 0:
            sys.exit(f"error: build_map.js falhou ({build.returncode})")
    print(f"[OK] {hunt['folder']} recortado. Próximo: build_hunt_fragment --export + publish.py pra chegar no jogo.")


if __name__ == "__main__":
    main()
