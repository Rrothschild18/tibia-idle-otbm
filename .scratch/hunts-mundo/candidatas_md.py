"""Lista de revisão das candidatas de uma cidade, cruzada com o catálogo de wiki.

A candidata vem de `build_full_floor_candidates.py` (componente caminhável de
andar inteiro, sem filtro). O nome vem de `hunt-catalog/hunts-identified.json`
(699 hunts nomeadas nas wikis BR/EN, 30/09) e é casado por **coordenada**, não
pelo rótulo de cidade: entrada da wiki dentro da extensão da candidata, no
mesmo andar ou num vizinho. Sem casamento a candidata continua na lista, só sem
nome — é o Rault que decide.

Uso: uv run python .scratch/hunts-mundo/candidatas_md.py YALAHAR --min 6
"""

import argparse
import json
import os

EXTRACTOR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "extractor")


def read(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def wiki_hunts():
    doc = read(os.path.join(EXTRACTOR, "hunt-catalog", "hunts-identified.json"))
    out = []
    for hunt in doc["hunts"]:
        for entrance in hunt.get("entrances") or []:
            if entrance.get("x"):
                out.append((entrance, hunt))
    return out


def names_for(candidate, catalog, margin=12):
    box = candidate["extent"]
    floor = candidate["floor"]
    found = []
    for entrance, hunt in catalog:
        if abs(int(entrance.get("z", -99)) - floor) > 1:
            continue
        if not (box["minX"] - margin <= entrance["x"] <= box["maxX"] + margin):
            continue
        if not (box["minY"] - margin <= entrance["y"] <= box["maxY"] + margin):
            continue
        label = hunt["name"]
        if hunt.get("level_min"):
            label += f" (lvl {hunt['level_min']}+)"
        if label not in found:
            found.append(label)
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("city")
    parser.add_argument("--min", type=int, default=6, help="criaturas mínimas pra entrar na lista")
    args = parser.parse_args()

    city_dir = os.path.join(EXTRACTOR, "full-maps", args.city)
    doc = read(os.path.join(city_dir, "candidates-full.json"))
    subareas = {entry["id"]: entry["name"] for entry in doc["subareas"]}
    catalog = wiki_hunts()

    kept = [c for c in doc["candidates"] if c["creatures"] >= args.min]
    by_subarea = {}
    for candidate in kept:
        by_subarea.setdefault(candidate.get("subareaId"), []).append(candidate)

    lines = [
        f"# Candidatas de {args.city}",
        "",
        f"{len(doc['candidates'])} componentes caminháveis, {len(kept)} com >= {args.min} criaturas.",
        f"Área: {doc['area']['name']}. Criaturas no recorte: "
        f"{sum(c['creatures'] for c in doc['candidates'])}.",
        "",
        "Cada linha é um componente de andar inteiro: tudo que anda ali dentro está na conta.",
        "O nome em **negrito** vem da wiki, casado por coordenada de entrada.",
        "",
    ]

    for subarea_id, group in sorted(
        by_subarea.items(), key=lambda item: -sum(c["creatures"] for c in item[1])
    ):
        label = subareas.get(subarea_id) or f"subárea {subarea_id}"
        lines.append(f"## {label} — {len(group)} candidatas, {sum(c['creatures'] for c in group)} criaturas")
        lines.append("")
        for candidate in sorted(group, key=lambda c: -c["creatures"]):
            box = candidate["extent"]
            species = ", ".join(f"{s['name']} x{s['count']}" for s in candidate["species"][:6])
            found = names_for(candidate, catalog)
            head = f"- `{candidate['id']}` z{candidate['floor']}, {candidate['creatures']} criaturas"
            if found:
                head += " — **" + " / ".join(found[:3]) + "**"
            lines.append(head)
            lines.append(
                f"  - caixa {box['minX']},{box['minY']} -> {box['maxX']},{box['maxY']}"
                f" (centro {box['centerX']},{box['centerY']})"
            )
            lines.append(f"  - {species}")
        lines.append("")

    print("\n".join(lines))


if __name__ == "__main__":
    main()
