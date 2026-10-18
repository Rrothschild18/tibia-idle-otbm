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
    parser.add_argument(
        "--slug",
        help="slug da pasta de uma hunt que ainda NÃO tem bundle publicado — é o caso do "
        "split de andar feito no editor. Sem isto, o slug é descoberto no bundle.",
    )
    parser.add_argument("--no-build", action="store_true", help="só recorta, não roda build_map.js")
    args = parser.parse_args()

    mask_file = os.path.join(MASK_DIR, f"{args.hunt_id}.json")
    if not os.path.exists(mask_file):
        sys.exit(f"error: máscara não encontrada em {mask_file} (salve no editor primeiro)")
    with open(mask_file, encoding="utf-8") as handle:
        mask = json.load(handle)

    city = args.hunt_id.split("-")[0]
    # máscara EXATA por andar: {z: {(x,y), ...}}; andar vazio = excluído da hunt
    # (erro do nosso script que incluiu um andar que não era pra entrar).
    mask_by_floor = {int(z): {(int(x), int(y)) for x, y in cells} for z, cells in mask["floors"].items()}
    excluded_floors = {int(z) for z in mask.get("excludedFloors", [])}
    mask_by_floor = {z: cells for z, cells in mask_by_floor.items() if cells and z not in excluded_floors}
    floors = set(mask_by_floor)
    union = set().union(*mask_by_floor.values()) if mask_by_floor else set()
    if not union:
        sys.exit("error: máscara vazia")
    xs = [x for x, _ in union]
    ys = [y for _, y in union]
    box = [min(xs), min(ys), max(xs), max(ys)]  # só pra otimização de bounds do crop

    tibia_idle = paths.TIBIA_IDLE.require(args.tibia_idle_dir)
    assets_dir = os.path.join(tibia_idle, "apps", "tibia-idle-front", "public", "assets")
    # Hunt nascida de split de andar ainda não tem bundle: o slug vem por flag e
    # não há start pra ler. Fora desse caso, os dois saem do bundle publicado.
    slug = args.slug or _bundle_slug(assets_dir, args.hunt_id)
    # entrada: a editada no editor (overrides, coord de mundo) tem prioridade;
    # senão o start do bundle — e, numa hunt sem bundle, o centro da máscara,
    # que o ajuste logo abaixo encosta num tile que existe de verdade.
    if mask.get("entrance"):
        entrance = list(mask["entrance"])
    elif args.slug:
        entrance = [(min(xs) + max(xs)) // 2, (min(ys) + max(ys)) // 2, min(floors)]
    else:
        with open(
            os.path.join(assets_dir, f"{args.hunt_id}_{slug}-sprites-v6", "map.json"),
            encoding="utf-8",
        ) as handle:
            bundle_map = json.load(handle)
        b = bundle_map["bounds"]
        start = bundle_map.get("start") or {"x": 0, "y": 0, "z": min(floors)}
        entrance = [b["minX"] + start["x"], b["minY"] + start["y"], start["z"]]
    if (entrance[0], entrance[1]) not in mask_by_floor.get(entrance[2], set()):
        # a entrada antiga saiu da máscara; escolhe um andar que ainda tem máscara
        # (o da entrada se sobreviveu, senão o mais raso) e o tile mais próximo NELE
        # — garante que o marcador cai num tile que existe no recorte.
        target_z = entrance[2] if entrance[2] in mask_by_floor else min(floors)
        ex, ey = min(mask_by_floor[target_z], key=lambda p: abs(p[0] - entrance[0]) + abs(p[1] - entrance[1]))
        entrance = [ex, ey, target_z]

    otbm = os.path.join(bch.FULL_MAPS_DIR, city, f"{city}.otbm")
    with open(otbm, "rb") as handle:
        data = handle.read()
    header = otbm_stream.map_header(data)

    hunt = {"id": args.hunt_id, "slug": slug, "folder": f"{args.hunt_id}_{slug}", "name": args.hunt_id}
    result = bch.write_hunt_map(
        city, hunt, data, header, box, floors, entrance=tuple(entrance),
        tile_in_floor=lambda x, y, z: (x, y) in mask_by_floor.get(z, set()),
    )
    print(f"[OK] re-corte pela máscara: {result['tiles']} tiles ({len(union)} na máscara), andares {sorted(floors)}")
    if not result["marked"]:
        sys.exit("error: entrada fora do recorte — sem marcador de start")

    if not args.no_build:
        build = subprocess.run(["node", "scripts/build_map.js", hunt["folder"]], cwd=EXTRACTOR_DIR)
        if build.returncode != 0:
            sys.exit(f"error: build_map.js falhou ({build.returncode})")

    # monstros excluídos no editor: tira os spawns (e os defs órfãos) do respawn.json
    excluded = set(mask.get("excludedSpecies") or [])
    if excluded and not args.no_build:
        respawn_path = os.path.join(EXTRACTOR_DIR, "ready-maps", city, hunt["folder"], "monsters", "respawn.json")
        if os.path.exists(respawn_path):
            with open(respawn_path, encoding="utf-8") as h:
                rj = json.load(h)
            before = len(rj.get("spawns", []))
            rj["spawns"] = [s for s in rj.get("spawns", []) if s.get("name") not in excluded]
            alive = {s.get("name") for s in rj["spawns"]}
            rj["monsterDefs"] = {k: v for k, v in rj.get("monsterDefs", {}).items() if v.get("name") in alive}
            with open(respawn_path, "w", encoding="utf-8") as h:
                json.dump(rj, h, ensure_ascii=False)
            print(f"[OK] excluídos {sorted(excluded)}: {before} -> {len(rj['spawns'])} spawns")

    # monstros cravados no editor: respawn manual pra andar/área que o OTBM não
    # tinha (falha do mapa original, não nossa). Reusa o def da espécie — que já
    # existe na hunt — e injeta um ponto de respawn novo.
    added = mask.get("addedSpawns") or []
    if added and not args.no_build:
        respawn_path = os.path.join(EXTRACTOR_DIR, "ready-maps", city, hunt["folder"], "monsters", "respawn.json")
        map_json_path = os.path.join(EXTRACTOR_DIR, "ready-maps", city, hunt["folder"], "map.json")
        if os.path.exists(respawn_path) and os.path.exists(map_json_path):
            with open(respawn_path, encoding="utf-8") as h:
                rj = json.load(h)
            with open(map_json_path, encoding="utf-8") as h:
                fb = json.load(h)["bounds"]
            defs = rj.setdefault("monsterDefs", {})
            spawns = rj.setdefault("spawns", [])
            # def da espécie sem spawn no recorte: do bundle/janela que o editor renderizou
            src_defs = {}
            for cand in (
                os.path.join(assets_dir, f"{args.hunt_id}_{slug}-sprites-v6", "window", "monsters", "respawn.json"),
                os.path.join(assets_dir, f"{args.hunt_id}_{slug}-sprites-v6", "monsters", "respawn.json"),
            ):
                if os.path.exists(cand):
                    with open(cand, encoding="utf-8") as h:
                        src_defs = json.load(h).get("monsterDefs", {})
                    break

            def _spawntime(name):
                for s in spawns:
                    if s.get("name") == name and s.get("spawntime"):
                        return s["spawntime"]
                return 60

            injected = 0
            for a in added:
                oid = str(a["outfitId"])
                if oid not in defs and oid in src_defs:
                    defs[oid] = src_defs[oid]
                if oid not in defs:
                    print(f"[warn] sem def pra outfit {oid} ({a.get('name')}); cravado ignorado")
                    continue
                wx, wy, wz = int(a["worldX"]), int(a["worldY"]), int(a["worldZ"])
                spawns.append({
                    "name": a.get("name") or defs[oid].get("name"),
                    "outfitId": int(a["outfitId"]),
                    "tileX": wx - fb["minX"],
                    "tileY": wy - fb["minY"],
                    "worldX": wx, "worldY": wy, "worldZ": wz,
                    "radius": int(a.get("radius", 2)),
                    "spawntime": _spawntime(a.get("name")),
                })
                injected += 1
            with open(respawn_path, "w", encoding="utf-8") as h:
                json.dump(rj, h, ensure_ascii=False)
            print(f"[OK] cravados {injected} spawn(s) manual(is)")

    # O fragmento é regerado aqui, e não deixado pro próximo passo, porque é
    # dele que o `hunt-add` lê o respawn — e o `publish.py` **não** o regera. A
    # exclusão de espécie acima entrava no `monsters/respawn.json` e não no
    # fragmento, então a espécie excluída voltava pro servidor com o bundle
    # certo em mãos. Sem `--export`: quem escreve no jogo é o `hunt-add`.
    if not args.no_build:
        fragment = subprocess.run(
            [
                sys.executable,
                os.path.join(SCRIPTS_DIR, "build_hunt_fragment.py"),
                hunt["folder"],
                "--map-id",
                args.hunt_id,
            ],
            cwd=SCRIPTS_DIR,
        )
        if fragment.returncode != 0:
            sys.exit(f"error: build_hunt_fragment.py falhou ({fragment.returncode})")

    print(f"[OK] {hunt['folder']} recortado. Próximo: publish.py + hunt-add pra chegar no jogo.")


if __name__ == "__main__":
    main()
