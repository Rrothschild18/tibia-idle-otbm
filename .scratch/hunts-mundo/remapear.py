"""Guarda e reaponta os `candidateIds` da curadoria quando a cidade é re-cortada.

Recortar a cidade com outra caixa muda o grafo de tiles, e o índice de
componente — que é a última parte do id da candidata — é derivado dele. Então
`CIDADE-FULL-z11-53` pode passar a ser outro lugar. A curadoria aponta por id,
logo ela precisa ser reapontada.

O casamento é por geometria, não por número: a candidata nova é a que, **no
mesmo andar**, contém o centro da caixa antiga e compartilha espécie com ela.
Em Darashia isso casou 21 de 21.

    uv run python .scratch/hunts-mundo/remapear.py DARASHIA --snapshot   # ANTES do recorte
    uv run python .scratch/hunts-mundo/remapear.py DARASHIA --apply      # DEPOIS
"""

import argparse
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
EXTRACTOR = os.path.join(HERE, "..", "..", "extractor")


def paths(city: str):
    city_dir = os.path.join(EXTRACTOR, "full-maps", city)
    return (
        os.path.join(city_dir, "curation.json"),
        os.path.join(city_dir, "candidates-full.json"),
        os.path.join(HERE, f"{city.lower()}-curation-antes.json"),
    )


def read(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def snapshot(city: str) -> None:
    curation_path, candidates_path, snapshot_path = paths(city)
    candidates = {c["id"]: c for c in read(candidates_path)["candidates"]}
    out = []
    for hunt in read(curation_path)["hunts"]:
        out.append(
            {
                "id": hunt["id"],
                "name": hunt["name"],
                "candidates": [
                    {
                        "id": cid,
                        "floor": candidates[cid]["floor"],
                        "creatures": candidates[cid]["creatures"],
                        "extent": candidates[cid]["extent"],
                        "species": [s["name"] for s in candidates[cid]["species"][:3]],
                    }
                    for cid in hunt["candidateIds"]
                    if cid in candidates
                ],
            }
        )
    with open(snapshot_path, "w", encoding="utf-8") as handle:
        json.dump(out, handle, ensure_ascii=False, indent=2)
    print(f"[OK] {city}: retrato de {len(out)} hunts -> {os.path.basename(snapshot_path)}")


def best_match(old, by_floor):
    center_x = (old["extent"]["minX"] + old["extent"]["maxX"]) // 2
    center_y = (old["extent"]["minY"] + old["extent"]["maxY"]) // 2
    wanted = set(old["species"])
    found = []
    for candidate in by_floor.get(old["floor"], []):
        box = candidate["extent"]
        if not (box["minX"] <= center_x <= box["maxX"] and box["minY"] <= center_y <= box["maxY"]):
            continue
        shared = wanted & {s["name"] for s in candidate["species"]}
        if shared:
            found.append((len(shared), candidate["creatures"], candidate))
    found.sort(key=lambda item: (-item[0], -item[1]))
    return found[0][2] if found else None


def apply(city: str) -> None:
    curation_path, candidates_path, snapshot_path = paths(city)
    if not os.path.isfile(snapshot_path):
        raise SystemExit(f"error: sem retrato de {city} — rode --snapshot antes do recorte")
    candidates = read(candidates_path)["candidates"]
    by_floor = {}
    for candidate in candidates:
        by_floor.setdefault(candidate["floor"], []).append(candidate)
    by_id = {c["id"]: c for c in candidates}

    curation = read(curation_path)
    hunts = {h["id"]: h for h in curation["hunts"]}
    orphans = []
    for old_hunt in read(snapshot_path):
        hunt = hunts.get(old_hunt["id"])
        if not hunt:
            continue
        novos = []
        for old in old_hunt["candidates"]:
            match = best_match(old, by_floor)
            if match is None:
                orphans.append((old_hunt["id"], old["id"]))
                continue
            novos.append(match["id"])
            flag = "" if match["id"] == old["id"] else "  <= mudou"
            print(
                f"  {old_hunt['id']:<22} {old['id']:<24} -> {match['id']:<24}"
                f" {old['creatures']:>4} -> {match['creatures']:<4}{flag}"
            )
        if not novos:
            continue
        hunt["candidateIds"] = novos
        boxes = [by_id[c]["extent"] for c in novos]
        extent = {
            "minX": min(b["minX"] for b in boxes),
            "minY": min(b["minY"] for b in boxes),
            "maxX": max(b["maxX"] for b in boxes),
            "maxY": max(b["maxY"] for b in boxes),
        }
        extent["centerX"] = (extent["minX"] + extent["maxX"]) // 2
        extent["centerY"] = (extent["minY"] + extent["maxY"]) // 2
        hunt["extent"] = extent
        hunt["creatures"] = sum(by_id[c]["creatures"] for c in novos)

    with open(curation_path, "w", encoding="utf-8") as handle:
        json.dump(curation, handle, ensure_ascii=False, indent=2)
    if orphans:
        print("[!!] sem casamento (curadoria mantida como estava):")
        for hunt_id, candidate_id in orphans:
            print(f"       {hunt_id}  {candidate_id}")
    # Hunt com máscara salva não é re-cortada pela curadoria: o recorte dela é a
    # máscara, e ela pega o conteúdo novo no "Re-cortar" do editor.
    livres = [
        h["id"]
        for h in curation["hunts"]
        if not os.path.isfile(os.path.join(EXTRACTOR, "hunt-masks", f"{h['id']}.json"))
    ]
    print("RECORTAR:" + " ".join(livres))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("city")
    parser.add_argument("--snapshot", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.snapshot:
        snapshot(args.city)
    elif args.apply:
        apply(args.city)
    else:
        raise SystemExit("use --snapshot ou --apply")


if __name__ == "__main__":
    main()
