"""Casa placa numerada do mapa-mundo com candidata de `candidates.json`,
escreve `sign-groups.json` por cidade.

Uma placa (item 2017, texto só dígito — "6005") é a resposta manual de quem
andou pelo editor pra "qual o formato do mapa em que esses clusters
existem": o mesmo número em andares diferentes marca que são a mesma hunt. A
tela `new-hunts` lê o `sign-groups.json` daqui e pré-aplica essas junções
como se fosse o botão direito do mapa (`candidates.ts.clusterCandidates`,
parâmetro `manualMerges`).

O casamento busca no **pool combinado** das cidades passadas, não só na
própria candidates.json da cidade da placa: o recorte quadrado de uma
cidade grande (Thais corta 1683 tiles de lado) engole área de cidade
vizinha, e casar placa só contra "sua" cidade erra por centenas de tiles
quando ela é de verdade da vizinha (medido: Thais sozinha errava a 300-600
tiles em placas que são de Venore). ID que casa em candidatas de **duas**
cidades diferentes não é escrito — fica pra revisão humana, não decisão
errada silenciosa.

Entrada: `raw-maps/<CIDADE>.raw.json` (rode `dump_otbm.js` antes) e
`full-maps/<CIDADE>/candidates.json` de cada cidade.

Run: uv run python extractor/scripts/sign_groups.py CARLIN THAIS VENORE KAZORDOON
"""

import argparse
import json
import os

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
EXTRACTOR_DIR = os.path.dirname(SCRIPTS_DIR)
RAW_MAPS_DIR = os.path.join(EXTRACTOR_DIR, "raw-maps")
FULL_MAPS_DIR = os.path.join(EXTRACTOR_DIR, "full-maps")

SIGN_ITEM_ID = 2017
DEFAULT_MARGIN_TILES = 20


def _iter_tiles(dump):
    for node in dump.get("data", {}).get("nodes", []):
        for feature in node.get("features", []):
            base_x = feature.get("x", 0)
            base_y = feature.get("y", 0)
            z = feature.get("z", 7)
            for tile in feature.get("tiles", []):
                tx, ty = tile.get("x"), tile.get("y")
                if tx is None or ty is None:
                    continue
                yield base_x + tx, base_y + ty, z, tile


def load_signs_deduped(cities):
    """1 placa por (x,y,z,text) real — dedup entre os dumps das cidades
    pedidas, que repetem a mesma placa física onde os recortes se sobrepoem."""
    seen = {}
    for city in cities:
        path = os.path.join(RAW_MAPS_DIR, f"{city}.raw.json")
        with open(path, encoding="utf-8") as handle:
            dump = json.load(handle)
        for x, y, z, tile in _iter_tiles(dump):
            for item in tile.get("items", []):
                if item.get("id") != SIGN_ITEM_ID:
                    continue
                text = item.get("text", "")
                if not text.strip().isdigit():
                    continue
                seen[(x, y, z, text)] = {"x": x, "y": y, "z": z, "id": text}
    return list(seen.values())


def load_candidate_pool(cities):
    pool = []
    for city in cities:
        path = os.path.join(FULL_MAPS_DIR, city, "candidates.json")
        with open(path, encoding="utf-8") as handle:
            doc = json.load(handle)
        for candidate in doc["candidates"]:
            candidate["_city"] = city
            pool.append(candidate)
    return pool


def _extent_distance(extent, x, y):
    dx = max(extent["minX"] - x, 0, x - extent["maxX"])
    dy = max(extent["minY"] - y, 0, y - extent["maxY"])
    return dx + dy


def nearest_candidate(sign, candidates, margin=None):
    """A candidata mais perto da placa, no mesmo andar — `margin` filtra por
    distância; sem ele, devolve a mais perto a qualquer distância (pro
    relatório de órfã dizer o quão longe ficou, não só "não achei")."""
    best = None
    best_dist = None
    for candidate in candidates:
        if candidate["floor"] != sign["z"]:
            continue
        dist = _extent_distance(candidate["extent"], sign["x"], sign["y"])
        if margin is not None and dist > margin:
            continue
        if best is None or dist < best_dist:
            best = candidate
            best_dist = dist
    return best, best_dist


def build_groups(signs, pool, margin):
    """`(por cidade: {signId: [candidateId,...]}, órfãs, ambíguas)`."""
    matches = {}
    orphans = []
    for sign in signs:
        candidate, _dist = nearest_candidate(sign, pool, margin)
        if candidate is None:
            nearest, dist = nearest_candidate(sign, pool)
            orphans.append((sign, nearest, dist))
            continue
        matches.setdefault(sign["id"], set()).add((candidate["_city"], candidate["id"]))

    by_city = {}
    ambiguous = []
    for sign_id, members in matches.items():
        cities_here = {c for c, _ in members}
        if len(cities_here) > 1:
            ambiguous.append((sign_id, sorted(members)))
            continue
        ids = sorted(cid for _, cid in members)
        if len(ids) < 2:
            continue
        city = next(iter(cities_here))
        by_city.setdefault(city, {})[sign_id] = ids

    return by_city, orphans, ambiguous


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("cities", nargs="+", help="códigos de cidade, ex: CARLIN THAIS")
    parser.add_argument("--margin", type=int, default=DEFAULT_MARGIN_TILES)
    args = parser.parse_args()

    signs = load_signs_deduped(args.cities)
    pool = load_candidate_pool(args.cities)
    by_city, orphans, ambiguous = build_groups(signs, pool, args.margin)

    print(f"{len(signs)} placas numéricas únicas, {sum(len(g) for g in by_city.values())} grupos reais\n")

    for sign_id, members in ambiguous:
        print(f"[!!] ID {sign_id} casou em MAIS DE UMA CIDADE: {members} — não escrevo, revisar à mão")

    for city in args.cities:
        groups = by_city.get(city, {})
        out = {
            "city": city,
            "groups": [
                {"signId": sign_id, "candidateIds": ids}
                for sign_id, ids in sorted(groups.items(), key=lambda kv: int(kv[0]))
            ],
        }
        out_path = os.path.join(FULL_MAPS_DIR, city, "sign-groups.json")
        with open(out_path, "w", encoding="utf-8") as handle:
            json.dump(out, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        print(f"{city}: {len(groups)} grupo(s) -> {out_path}")
        for sign_id, ids in sorted(groups.items(), key=lambda kv: int(kv[0])):
            floors = sorted({c["floor"] for c in pool if c["id"] in ids})
            print(f"    sinal {sign_id}: {ids} (z={floors})")

    print(f"\n{len(orphans)} placa(s) sem candidata a <={args.margin} tiles em nenhuma das cidades pedidas:")
    for sign, nearest, dist in orphans:
        if nearest is None:
            print(f"    ID {sign['id']} em ({sign['x']},{sign['y']},z{sign['z']}): nenhuma candidata nesse andar")
        else:
            print(
                f"    ID {sign['id']} em ({sign['x']},{sign['y']},z{sign['z']}): "
                f"mais perto = {nearest['_city']}/{nearest['id']} a {dist} tiles"
            )


if __name__ == "__main__":
    main()
