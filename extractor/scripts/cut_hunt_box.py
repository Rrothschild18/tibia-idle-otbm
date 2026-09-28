"""
CLI: recorta um mapa de hunt de uma caixa do mapa da cidade.

O README manda recortar mapa de hunt à mão no editor, e é assim que as 15 hunts
de Rookgaard nasceram. Quando a área da hunt já está **marcada dentro do mapa**
— um caminho pintado de item-marcador, uma placa na entrada —, a caixa é
derivável e o recorte deixa de precisar de mão: é a mesma operação que
`build_curated_hunts.write_hunt_map` faz para uma cidade recortada do mundo,
só que a caixa vem de um argumento em vez de uma tela de curadoria.

A margem em volta do caminho não é estética. O cliente mostra um viewport de
15x11 tiles (`VIEW_RADIUS_X = 7`, `VIEW_RADIUS_Y = 5` no `tibia-idle`), então
uma margem menor que 7 deixaria o jogador ver borda preta ao andar na ponta do
caminho.

Run: python cut_hunt_box.py ROOK ROOK-HUNT-0013 copper-shield-quest \\
        --box 1177,1122,1241,1157 --floors 7,8,9 --entrance 1188,1134,7 \\
        --name "Copper Shield Quest"
"""

import argparse
import os
import sys

import build_curated_hunts as bch
import otbm_stream


def _ints(raw: str, count: int, flag: str):
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) != count:
        sys.exit(f"error: {flag} quer {count} inteiros separados por vírgula, recebi {raw!r}")
    try:
        return tuple(int(p) for p in parts)
    except ValueError:
        sys.exit(f"error: {flag} não é numérico: {raw!r}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("city", help="código da cidade de origem, ex: ROOK")
    parser.add_argument("hunt_id", help="id da hunt, ex: ROOK-HUNT-0013")
    parser.add_argument("slug", help="nome descritivo em minúsculas, ex: copper-shield-quest")
    parser.add_argument("--box", required=True, help="minX,minY,maxX,maxY na coordenada da cidade")
    parser.add_argument("--floors", required=True, help="andares a incluir, ex: 7,8,9")
    parser.add_argument("--entrance", required=True,
                        help="x,y,z do tile de entrada (recebe o marcador de start)")
    parser.add_argument("--name", required=True, help="nome curado da hunt")
    args = parser.parse_args()

    box = _ints(args.box, 4, "--box")
    floors = set(_ints(args.floors, len(args.floors.split(",")), "--floors"))
    entrance = _ints(args.entrance, 3, "--entrance")

    otbm = os.path.join(bch.FULL_MAPS_DIR, args.city, f"{args.city}.otbm")
    if not os.path.exists(otbm):
        sys.exit(f"error: mapa da cidade não encontrado em {otbm}")

    with open(otbm, "rb") as handle:
        data = handle.read()
    header = otbm_stream.map_header(data)

    hunt = {
        "id": args.hunt_id,
        "slug": args.slug,
        "folder": f"{args.hunt_id}_{args.slug}",
        "name": args.name,
    }

    result = bch.write_hunt_map(
        args.city, hunt, data, header, box, floors, entrance=entrance
    )

    print(f"{args.hunt_id} ({args.name})")
    print(f"  caixa: x[{box[0]}..{box[2]}] y[{box[1]}..{box[3]}]  andares {sorted(floors)}")
    print(f"  tiles: {result['tiles']}   spawns: {result['spawns']}")
    print(f"  marcador de entrada em {entrance}: {'plantado' if result['marked'] else 'NAO PLANTADO'}")
    print(f"  -> {result['folder']}")

    if not result["marked"]:
        sys.exit(
            "error: o tile de entrada não estava no recorte — sem marcador de start o bundle não "
            "tem `start` e o gerador de rota não sabe por onde começar"
        )


if __name__ == "__main__":
    main()
