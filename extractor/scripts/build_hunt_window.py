"""Gera a "janela" de uma hunt: um recorte da cidade = bounds da hunt + margem,
renderizado em v6, pra o editor de máscara (tibia-idle-map-editor) mostrar a hunt
E os vizinhos. Sem isso, o editor só tem o recorte da hunt e o brush só apaga —
com a janela, dá pra ADICIONAR SQM que estão em volta.

A janela é **generosa de propósito**, nas duas direções. Em área, porque faltar
3 SQM pra fechar uma caverna é comum e uma janela que para no bounds da hunt não
tem o que pintar ali. Em andares, porque o recorte de uma candidata de andar
inteiro nasce com um andar só: sem vizinho vertical, o andar de cima que tem os
bichos bons não existe na tela e não há como adicioná-lo.

O custo é `área x andares` no build_map.js, então quem decide o tamanho é o
orçamento de tiles (`--tile-budget`): ele tira margem antes de tirar andar,
porque andar que falta não dá pra pintar de jeito nenhum.

Lê os bounds/andares/entrada do bundle já publicado da hunt
(apps/tibia-idle-front/public/assets/<pasta>/map.json), recorta a caixa+margem
com `build_curated_hunts.write_hunt_map`, renderiza com build_map.js, e copia o
resultado (map.json + sheets/) pra <pasta>/window/ onde o editor o serve.

Run: uv run python scripts/build_hunt_window.py CARLIN-HUNT-0003 --margin 40
"""

import argparse
import json
import os
import shutil
import subprocess
import sys

import build_curated_hunts as bch
import otbm_stream
import paths
import update_canary_data

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))

MAX_FLOOR = 15
MIN_MARGIN = 12


def _with_neighbours(floors, around: int):
    """Os andares da hunt mais `around` acima e abaixo, dentro de 0..15."""
    return {
        z + dz
        for z in floors
        for dz in range(-around, around + 1)
        if 0 <= z + dz <= MAX_FLOOR
    }


def _fit_budget(bounds, floors, margin: int, around: int, budget: int):
    """A maior janela que caiba no orçamento -> `(margem, andares_ao_redor)`.

    Reduz margem primeiro, em passos de 4, até `MIN_MARGIN`; só então abre mão
    de um andar vizinho. Andar é mais valioso que margem porque a máscara pode
    crescer de lado por cima da margem que sobrou, mas não pode pintar um andar
    que a janela não trouxe.
    """
    width = bounds["maxX"] - bounds["minX"]
    height = bounds["maxY"] - bounds["minY"]
    for candidate_around in range(around, -1, -1):
        floor_count = len(_with_neighbours(floors, candidate_around))
        for candidate_margin in range(margin, MIN_MARGIN - 1, -4):
            tiles = (width + 2 * candidate_margin) * (height + 2 * candidate_margin) * floor_count
            if tiles <= budget:
                return candidate_margin, candidate_around
    return MIN_MARGIN, 0


def _bundle_folder(assets_dir: str, hunt_id: str) -> str:
    for name in sorted(os.listdir(assets_dir)):
        if name.startswith(f"{hunt_id}_") and name.endswith("-sprites-v6"):
            return name
    sys.exit(f"error: bundle de {hunt_id} não achado em {assets_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("hunt_id", help="ex: CARLIN-HUNT-0003")
    parser.add_argument("--margin", type=int, default=40, help="margem em tiles ao redor (default 40)")
    parser.add_argument(
        "--floors-around",
        type=int,
        default=2,
        help="andares vizinhos acima e abaixo dos da hunt (default 2)",
    )
    parser.add_argument(
        "--tile-budget",
        type=int,
        default=400_000,
        help="teto de `área x andares`; margem e andares encolhem até caber (default 400k)",
    )
    parser.add_argument("--tibia-idle-dir")
    args = parser.parse_args()

    city = args.hunt_id.split("-")[0]
    tibia_idle = paths.TIBIA_IDLE.require(args.tibia_idle_dir)
    assets_dir = os.path.join(tibia_idle, "apps", "tibia-idle-front", "public", "assets")
    bundle = _bundle_folder(assets_dir, args.hunt_id)

    with open(os.path.join(assets_dir, bundle, "map.json"), encoding="utf-8") as handle:
        bundle_map = json.load(handle)

    b = bundle_map["bounds"]
    floors_in_bundle = {int(z) for z in bundle_map["floors"]}
    m, around = _fit_budget(b, floors_in_bundle, args.margin, args.floors_around, args.tile_budget)
    if (m, around) != (args.margin, args.floors_around):
        print(
            f"[..] orçamento de {args.tile_budget:,} tiles: margem {args.margin}->{m}, "
            f"andares ao redor {args.floors_around}->{around}"
        )
    box = [b["minX"] - m, b["minY"] - m, b["maxX"] + m, b["maxY"] + m]
    floors = _with_neighbours(floors_in_bundle, around)
    start = bundle_map.get("start") or {"x": 0, "y": 0, "z": min(floors_in_bundle)}
    entrance = [b["minX"] + start["x"], b["minY"] + start["y"], start["z"]]

    otbm = os.path.join(bch.FULL_MAPS_DIR, city, f"{city}.otbm")
    if not os.path.exists(otbm):
        sys.exit(f"error: recorte da cidade não encontrado em {otbm} (rode cut_city.py)")
    with open(otbm, "rb") as handle:
        data = handle.read()
    header = otbm_stream.map_header(data)

    hunt = {"id": args.hunt_id, "slug": "window", "folder": f"{args.hunt_id}_window", "name": f"{args.hunt_id} window"}
    result = bch.write_hunt_map(city, hunt, data, header, box, floors, entrance=tuple(entrance))
    print(f"[OK] janela recortada: {result['tiles']} tiles, caixa {box}, andares {sorted(floors)}")

    # renderiza v6 com o build_map.js
    build = subprocess.run(["node", "scripts/build_map.js", hunt["folder"]], cwd=os.path.dirname(SCRIPTS_DIR))
    if build.returncode != 0:
        sys.exit(f"error: build_map.js falhou ({build.returncode})")

    ready = os.path.join(os.path.dirname(SCRIPTS_DIR), "ready-maps", city, hunt["folder"])
    dest = os.path.join(assets_dir, bundle, "window")
    shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(dest, exist_ok=True)
    shutil.copy(os.path.join(ready, "map.json"), os.path.join(dest, "map.json"))
    shutil.copytree(os.path.join(ready, "sheets"), os.path.join(dest, "sheets"))
    if os.path.isdir(os.path.join(ready, "monsters")):
        shutil.copytree(os.path.join(ready, "monsters"), os.path.join(dest, "monsters"))
    print(f"[OK] janela publicada em {dest} — reabra a hunt no editor pra adicionar vizinhos")


if __name__ == "__main__":
    main()
