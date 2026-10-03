"""Casa placa numerada do mapa-mundo com candidata de ANDAR INTEIRO
(`candidates-full.json`, de `build_full_floor_candidates.py`), escreve
`sign-groups.json` por cidade.

Uma placa (item 2017, texto só dígito — "6005") é a resposta manual de quem
andou pelo editor pra "qual o formato do mapa em que esses clusters
existem": o mesmo número em andares diferentes marca que são a mesma hunt. A
tela `new-hunts` lê o `sign-groups.json` daqui e pré-aplica essas junções
como se fosse o botão direito do mapa (`candidates.ts.clusterCandidates`,
parâmetro `manualMerges`).

Decisão do Rault (2026-10-02): a candidata **não é clusterizada por raio nem
filtrada por contagem mínima** — é o componente caminhável do andar inteiro,
e toda placa vira hunt, do tamanho que for. Sem isso, CARLIN-HUNT-0001/0010
saíram com 1-4 bichos em vez do andar inteiro.

**Placa duplicada por engano:** o mesmo número às vezes aparece em dois
lugares bem distantes do mapa — número reaproveitado sem querer no editor
(achado: 6005, 6011, 6017, 6018, 6042, todos >60 tiles de distância entre os
dois grupos). Antes de juntar os andares de uma placa, as posições físicas
são clusterizadas por proximidade (x,y, ignorando z — liga-se transitivamente
até `SPLIT_DISTANCE_TILES`); se sobra mais de um grupo espacial, cada um vira
uma hunt separada (sufixo `-A`, `-B`, ...) e um aviso é impresso — não é
decisão silenciosa, é pra o Rault corrigir a placa se não for intenção.

O casamento busca no **pool combinado** das cidades passadas, não só na
própria candidates-full.json da cidade da placa: o recorte quadrado de uma
cidade grande (Thais corta 1683 tiles de lado) engole área de vizinha, e
casar placa só contra "sua" cidade erra por centenas de tiles quando ela é de
verdade da vizinha. Resolvido por **menor soma de distância** entre as
cidades candidatas (não "a primeira que bate") — ver `resolve_city`.

Entrada: `raw-maps/<CIDADE>.raw.json` e `full-maps/<CIDADE>/candidates-full.json`
de cada cidade (rode `build_full_floor_candidates.py` antes).

Run: uv run python extractor/scripts/sign_groups.py CARLIN THAIS VENORE KAZORDOON
"""

import argparse
import json
import math
import os
import sys

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
EXTRACTOR_DIR = os.path.dirname(SCRIPTS_DIR)
RAW_MAPS_DIR = os.path.join(EXTRACTOR_DIR, "raw-maps")
FULL_MAPS_DIR = os.path.join(EXTRACTOR_DIR, "full-maps")

sys.path.insert(0, SCRIPTS_DIR)
import hunt_candidates  # noqa: E402

SIGN_ITEM_ID = 2017
DEFAULT_MARGIN_TILES = 150
SPLIT_DISTANCE_TILES = 60

# Andar de superfície (e alguns subterrâneos abertos) não tem parede
# separando "hunt" de "resto da cidade" — o componente caminhável é a área
# inteira explorável, não uma sala. Medido: CARLIN z7 tinha 152 bichos em
# 297x242 tiles (toda a área externa), VENORE z7 tinha 678 em 524x483 (o
# mapa inteiro). Candidata com lado maior que isto não é uma hunt — é
# recortada ao redor da placa (ver `trim_to_sign`), como o sistema antigo de
# raio fazia, só que agora só entra em cena quando a geometria pede.
MAX_COMPONENT_DIMENSION = 150
TRIM_RADIUS_TILES = 40


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
        path = os.path.join(FULL_MAPS_DIR, city, "candidates-full.json")
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


def spatial_clusters(placements, threshold=SPLIT_DISTANCE_TILES):
    """Liga placas da mesma ID por proximidade (x,y, ignora z) — único-
    ligação transitiva. Duas placas no mesmo grupo espacial se há uma cadeia
    de vizinhos a <= threshold entre elas; grupos sem cadeia nenhuma entre si
    saem separados."""
    clusters = [[p] for p in placements]
    changed = True
    while changed:
        changed = False
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                if any(
                    math.hypot(p["x"] - q["x"], p["y"] - q["y"]) <= threshold
                    for p in clusters[i]
                    for q in clusters[j]
                ):
                    clusters[i].extend(clusters.pop(j))
                    changed = True
                    break
            if changed:
                break
    # Determinístico: maior grupo primeiro, depois por posição.
    clusters.sort(key=lambda c: (-len(c), min(p["x"] for p in c), min(p["y"] for p in c)))
    return clusters


def resolve_city(placements, pool_by_city, margin):
    """A cidade cuja soma de distâncias (sign -> candidata mais próxima no
    andar certo) é menor, considerando TODAS as placas do grupo espacial —
    não "a primeira que bate" num único andar. `matched[i]` casa com
    `placements[i]` — a ordem é preservada pra quem for recortar depois saber
    qual placa gerou qual candidata."""
    best_city = None
    best_total = None
    for city, pool in pool_by_city.items():
        total = 0
        matched = []
        ok = True
        for placement in placements:
            candidate, dist = nearest_candidate(placement, pool, margin)
            if candidate is None:
                ok = False
                break
            total += dist
            matched.append(candidate)
        if not ok:
            continue
        if best_total is None or total < best_total:
            best_total = total
            best_city = (city, matched)
    return best_city


def oversized(candidate):
    extent = candidate["extent"]
    width = extent["maxX"] - extent["minX"]
    height = extent["maxY"] - extent["minY"]
    return width > MAX_COMPONENT_DIMENSION or height > MAX_COMPONENT_DIMENSION


def trim_to_sign(candidate, sign, label, radius=TRIM_RADIUS_TILES):
    """Superfície (e subterrâneo aberto) não tem parede separando hunt do
    resto da cidade — a candidata de andar inteiro vira "o mapa todo". Corta
    de volta pro raio ao redor da placa, do jeito que o sistema antigo
    fazia, só que só entra em cena quando a geometria pede (`oversized`)."""
    nearby = [
        spawn
        for spawn in candidate["spawns"]
        if max(abs(spawn["x"] - sign["x"]), abs(spawn["y"] - sign["y"])) <= radius
    ]
    if not nearby:
        # Placa de superfície sem bicho a `radius` tiles — não finge que achou
        # uma hunt; pega só os mais próximos, pra não sair vazia.
        nearby = sorted(
            candidate["spawns"],
            key=lambda s: math.hypot(s["x"] - sign["x"], s["y"] - sign["y"]),
        )[:5]

    trimmed = {
        "id": f"{candidate['id']}-TRIM-{label}",
        "city": candidate["_city"],
        "floor": candidate["floor"],
        "component": candidate["component"],
        "creatures": len(nearby),
        "species": hunt_candidates._species(nearby),
        "extent": hunt_candidates._extent(nearby),
        "subareaId": candidate["subareaId"],
        "spawns": nearby,
        "_city": candidate["_city"],
        "_trimmedFrom": candidate["id"],
    }
    return trimmed


def build_groups(signs, pool, margin):
    by_city_pool = {}
    for candidate in pool:
        by_city_pool.setdefault(candidate["_city"], []).append(candidate)

    by_id = {}
    for sign in signs:
        by_id.setdefault(sign["id"], []).append(sign)

    by_city = {}
    unresolved = []
    split_report = []
    trim_report = []
    extra_candidates = {}

    for sign_id, placements in sorted(by_id.items(), key=lambda kv: int(kv[0])):
        clusters = spatial_clusters(placements)
        suffixes = "ABCDEFGH"
        multi = len(clusters) > 1
        if multi:
            split_report.append((sign_id, clusters))

        for index, cluster in enumerate(clusters):
            label = sign_id if not multi else f"{sign_id}-{suffixes[index]}"
            resolved = resolve_city(cluster, by_city_pool, margin)
            if resolved is None:
                unresolved.append((label, cluster))
                continue
            city, matched = resolved

            ids = []
            for placement, candidate in zip(cluster, matched):
                if oversized(candidate):
                    trimmed = trim_to_sign(candidate, placement, label)
                    extra_candidates.setdefault(city, {})[trimmed["id"]] = trimmed
                    trim_report.append((label, candidate, trimmed))
                    ids.append(trimmed["id"])
                else:
                    ids.append(candidate["id"])
            by_city.setdefault(city, {})[label] = sorted(set(ids))

    return by_city, unresolved, split_report, trim_report, extra_candidates


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("cities", nargs="+", help="códigos de cidade, ex: CARLIN THAIS")
    parser.add_argument("--margin", type=int, default=DEFAULT_MARGIN_TILES)
    parser.add_argument("--split-distance", type=int, default=SPLIT_DISTANCE_TILES)
    args = parser.parse_args()

    signs = load_signs_deduped(args.cities)
    pool = load_candidate_pool(args.cities)
    by_city, unresolved, split_report, trim_report, extra_candidates = build_groups(
        signs, pool, args.margin
    )

    total_groups = sum(len(g) for g in by_city.values())
    print(f"{len(signs)} placas numéricas únicas, {total_groups} hunt(s)\n")

    if trim_report:
        print(
            f"[AVISO] {len(trim_report)} placa(s) bateram num componente maior que "
            f"{MAX_COMPONENT_DIMENSION} tiles (superfície sem parede) — recortado "
            f"pro raio de {TRIM_RADIUS_TILES} tiles ao redor da placa:"
        )
        for label, original, trimmed in trim_report:
            ow = original["extent"]["maxX"] - original["extent"]["minX"]
            oh = original["extent"]["maxY"] - original["extent"]["minY"]
            print(
                f"  placa {label}: {original['id']} ({original['creatures']} bichos, "
                f"{ow}x{oh} tiles) -> {trimmed['id']} ({trimmed['creatures']} bichos)"
            )
        print()

    if split_report:
        print("[AVISO] placa com o mesmo número em lugares distantes — revisar se não for intenção:")
        for sign_id, clusters in split_report:
            print(f"  ID {sign_id}: {len(clusters)} grupo(s) espaciais")
            for cluster in clusters:
                xs = [p["x"] for p in cluster]
                ys = [p["y"] for p in cluster]
                zs = sorted({p["z"] for p in cluster})
                print(f"      ({min(xs)}-{max(xs)}, {min(ys)}-{max(ys)}) z={zs}")
        print()

    for city in args.cities:
        extras = extra_candidates.get(city)
        if extras:
            candidates_path = os.path.join(FULL_MAPS_DIR, city, "candidates-full.json")
            with open(candidates_path, encoding="utf-8") as handle:
                document = json.load(handle)
            by_existing_id = {c["id"]: c for c in document["candidates"]}
            for trimmed_id, trimmed in extras.items():
                clean = {k: v for k, v in trimmed.items() if not k.startswith("_")}
                by_existing_id[trimmed_id] = clean
            document["candidates"] = list(by_existing_id.values())
            with open(candidates_path, "w", encoding="utf-8") as handle:
                json.dump(document, handle, indent=2, ensure_ascii=False)
                handle.write("\n")

    for city in args.cities:
        groups = by_city.get(city, {})
        out = {
            "city": city,
            "groups": [
                {"signId": sign_id, "candidateIds": ids}
                for sign_id, ids in groups.items()
            ],
        }
        out_path = os.path.join(FULL_MAPS_DIR, city, "sign-groups.json")
        with open(out_path, "w", encoding="utf-8") as handle:
            json.dump(out, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        print(f"{city}: {len(groups)} hunt(s) -> {out_path}")
        for sign_id, ids in groups.items():
            print(f"    sinal {sign_id}: {ids}")

    if unresolved:
        print(f"\n{len(unresolved)} grupo(s) sem cidade resolvida (nenhuma bate em todos os andares):")
        for label, cluster in unresolved:
            for p in cluster:
                print(f"    ID {label} em ({p['x']},{p['y']},z{p['z']})")


if __name__ == "__main__":
    main()
