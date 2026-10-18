"""Abre os andares de uma curadoria já escrita, sem tocar no que o Rault mexeu.

A candidata é de um andar só, e a primeira leva foi recortada assim: `floors`
com um andar, e a lista branca de spawn das candidatas. Resultado — os andares
vizinhos não existiam no recorte, e onde existiam vinham sem bicho. Isto abre
`floors` pra `z-1, z, z+1` e imprime os ids que podem ser re-cortados.

Hunt com máscara salva **não** entra: ela já foi curada no editor, e re-cortar
jogaria o recorte dela pra trás. Essas se resolvem pela janela (que agora vem
generosa) ou pelo fork de andar.

Uso: uv run python .scratch/hunts-mundo/generoso.py ANKRAHMUN [--write]
"""

import argparse
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
EXTRACTOR = os.path.join(HERE, "..", "..", "extractor")
MAX_FLOOR = 15


def _candidate_floor(hunt):
    for candidate_id in hunt.get("candidateIds") or []:
        match = re.search(r"-FULL-z(\d+)-", candidate_id)
        if match:
            return int(match.group(1))
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("city")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    curation_path = os.path.join(EXTRACTOR, "full-maps", args.city, "curation.json")
    with open(curation_path, encoding="utf-8") as handle:
        curation = json.load(handle)

    mask_dir = os.path.join(EXTRACTOR, "hunt-masks")
    ids = []
    for hunt in curation["hunts"]:
        if os.path.exists(os.path.join(mask_dir, f"{hunt['id']}.json")):
            continue
        # O andar vem do id da candidata (`…-FULL-zNN-###`), não de `floors[0]`:
        # numa curadoria já aberta, `floors[0]` é o z-1 e abrir de novo andaria
        # pra baixo a cada rodada.
        floor = _candidate_floor(hunt)
        if floor is None:
            continue
        opened = [z for z in (floor - 1, floor, floor + 1) if 0 <= z <= MAX_FLOOR]
        if opened == hunt["floors"]:
            continue
        hunt["floors"] = opened
        ids.append(hunt["id"])

    if args.write and ids:
        with open(curation_path, "w", encoding="utf-8") as handle:
            json.dump(curation, handle, ensure_ascii=False, indent=2)
    print(" ".join(ids))


if __name__ == "__main__":
    main()
