"""Escolhe as candidatas que viram hunt e escreve o `curation.json` da cidade.

A regra é explícita de propósito, porque ela vai ser revista: por cidade, até
`--max` hunts, vindas de três perguntas diferentes — as mais densas (caso de
lure, bolsão misto), as maiores de espécie única (caso de kite, leitura limpa)
e as que a wiki nomeia com nível baixo (bancada de low level). Depois disso,
completa pelas maiores que sobraram.

Os ids começam em 0101 pra não colidirem com a leva antiga, que ainda tem dump
por hunt em `raw-maps/<CIDADE>-HUNT-NNNN_*.raw.json` com outra curadoria.

Uso: uv run python .scratch/hunts-mundo/selecionar.py YALAHAR --max 6 [--write]
"""

import argparse
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
EXTRACTOR = os.path.join(HERE, "..", "..", "extractor")
FIRST_ID = 101


def read(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def wiki_index():
    doc = read(os.path.join(EXTRACTOR, "hunt-catalog", "hunts-identified.json"))
    out = []
    for hunt in doc["hunts"]:
        for entrance in hunt.get("entrances") or []:
            if entrance.get("x"):
                out.append((entrance, hunt))
    return out


def wiki_match(candidate, catalog, margin=12, require_species=False):
    """A hunt da wiki cuja entrada cai dentro da candidata, no mesmo andar.

    Com `require_species`, só casa se as duas compartilharem bicho: a entrada
    da wiki é um ponto, e um ponto dentro da caixa não garante que seja a mesma
    hunt — foi assim que o componente de Lizard Chosen ganhou o nome de
    "Brimstone Bug Cave", que começa no mesmo lugar.
    """
    box, floor = candidate["extent"], candidate["floor"]
    ours = {species["name"] for species in candidate["species"]}
    for entrance, hunt in catalog:
        if abs(int(entrance.get("z", -99)) - floor) > 1:
            continue
        if not (box["minX"] - margin <= entrance["x"] <= box["maxX"] + margin):
            continue
        if not (box["minY"] - margin <= entrance["y"] <= box["maxY"] + margin):
            continue
        if require_species and not (ours & set(hunt.get("species_found") or {})):
            continue
        return hunt
    return None


def side(candidate):
    box = candidate["extent"]
    return max(box["maxX"] - box["minX"], box["maxY"] - box["minY"])


def select(candidates, catalog, limit, floor_min, max_side, pinned=()):
    # Componente de superfície de cidade inteira chega a 320 tiles de lado e 100
    # mil tiles de recorte: ele é o mapa, não uma hunt. O corte é por tamanho
    # de caixa, não por contagem de bicho, porque é a caixa que vira bundle.
    pool = [c for c in candidates if c["creatures"] >= floor_min and side(c) <= max_side]
    by_size = sorted(pool, key=lambda c: -c["creatures"])
    chosen, reasons = [], {}
    # Espécie dominante só entra uma vez: sem isso Ankrahmun devolve seis
    # cavernas de Larva, e a bancada vira um teste repetido seis vezes.
    dominant = set()

    def take(candidate, reason, allow_repeat=False):
        top = candidate["species"][0]["name"]
        if candidate["id"] in reasons or len(chosen) >= limit:
            return
        if top in dominant and not allow_repeat:
            return
        chosen.append(candidate)
        reasons[candidate["id"]] = reason
        dominant.add(top)

    by_id = {c["id"]: c for c in candidates}
    for candidate_id in pinned:
        if candidate_id not in by_id:
            raise SystemExit(f"error: candidata {candidate_id} não existe neste recorte")
        take(by_id[candidate_id], "pedida à mão", allow_repeat=True)
    for candidate in by_size[:2]:
        take(candidate, "mais densa")
    for candidate in by_size:
        if len(candidate["species"]) == 1 and candidate["creatures"] >= 10:
            take(candidate, "espécie única")
        if sum(1 for r in reasons.values() if r == "espécie única") >= 2:
            break
    for candidate in by_size:
        hunt = wiki_match(candidate, catalog)
        if hunt and (hunt.get("level_min") or 999) <= 60:
            take(candidate, f"wiki lvl {hunt['level_min']}+")
        if sum(1 for r in reasons.values() if r.startswith("wiki")) >= 2:
            break
    for candidate in by_size:
        take(candidate, "maior restante")
    for candidate in by_size:
        take(candidate, "maior restante (espécie repetida)", allow_repeat=True)

    return chosen, reasons


def hunt_name(candidate, catalog, subareas):
    hunt = wiki_match(candidate, catalog, require_species=True)
    if hunt:
        return hunt["name"]
    top = candidate["species"][0]["name"]
    place = subareas.get(candidate.get("subareaId")) or candidate["city"].title()
    return f"{top}s — {place} z{candidate['floor']}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("city")
    parser.add_argument("--max", type=int, default=6)
    parser.add_argument("--min-creatures", type=int, default=8)
    parser.add_argument("--max-side", type=int, default=200, help="lado máximo da caixa, em tiles")
    parser.add_argument("--include", default="", help="ids de candidata que entram antes da regra")
    parser.add_argument("--write", action="store_true", help="grava o curation.json")
    args = parser.parse_args()

    city_dir = os.path.join(EXTRACTOR, "full-maps", args.city)
    doc = read(os.path.join(city_dir, "candidates-full.json"))
    source = read(os.path.join(city_dir, "source.json"))
    subareas = {entry["id"]: entry["name"] for entry in doc["subareas"]}
    catalog = wiki_index()

    chosen, reasons = select(
        doc["candidates"],
        catalog,
        args.max,
        args.min_creatures,
        args.max_side,
        [part.strip() for part in args.include.split(",") if part.strip()],
    )
    hunts = []
    used_names = set()
    for offset, candidate in enumerate(chosen):
        name = hunt_name(candidate, catalog, subareas)
        if name in used_names:
            name = f"{name} z{candidate['floor']}"
        while name in used_names:
            name = f"{name} ({candidate['component']})"
        used_names.add(name)
        hunts.append(
            {
                "id": f"{args.city}-HUNT-{FIRST_ID + offset:04d}",
                "name": name,
                "floors": [candidate["floor"]],
                "candidateIds": [candidate["id"]],
                "species": None,
                "creatures": candidate["creatures"],
                "extent": candidate["extent"],
                "subareaId": candidate.get("subareaId"),
                "walkTilesFromTemple": None,
            }
        )
        species = ", ".join(f"{s['name']} x{s['count']}" for s in candidate["species"][:4])
        print(
            f"{hunts[-1]['id']}  z{candidate['floor']:>2}  {candidate['creatures']:>3} bichos"
            f"  {side(candidate):>3} de lado  [{reasons[candidate['id']]}]  {name}\n"
            f"    {species}"
        )

    if args.write:
        curation = {
            "city": args.city,
            "area": source["area"]["name"],
            "subareas": [entry["id"] for entry in doc["subareas"]],
            "hunts": hunts,
        }
        destination = os.path.join(city_dir, "curation.json")
        if os.path.exists(destination):
            raise SystemExit(f"error: {destination} já existe — não sobrescrevo curadoria.")
        with open(destination, "w", encoding="utf-8") as handle:
            json.dump(curation, handle, ensure_ascii=False, indent=2)
        print(f"\n[OK] {len(hunts)} hunts -> {destination}")


if __name__ == "__main__":
    main()
