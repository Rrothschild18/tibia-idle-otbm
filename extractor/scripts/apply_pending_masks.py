"""Diff entre a máscara desenhada no editor e o que está publicado no jogo.

Desenhar máscara no editor não muda o jogo: ela fica em `hunt-masks/<ID>.json`
e espera por `apply_hunt_mask.py`. Em 2026-10-17 isso tinha acumulado **41
máscaras** que nunca chegaram ao jogo — o editor mostrava o recorte refinado, e
o jogo continuava com os andares e as espécies que a pessoa tinha tirado. O
sintoma é a rota de waypoint passeando por monstro que "não existe".

Este comando é o diff que faltava. Sem `--apply` ele só relata e sai com 1 se
houver pendência (serve de porta); com `--apply` ele fecha a diferença, hunt por
hunt, rodando a cadeia inteira:

    apply_hunt_mask.py <ID>                    re-corta e assa (build_map.js)
    build_hunt_fragment.py <pasta> --map-id    regera o db-fragment.json
    publish.py <pasta>                         copia o bundle pro jogo
    nx run hunt-add:add --from <bundle>        registra respawn, loot e nome

O passo do fragmento está aí porque `publish.py` **não** o regera: a exclusão de
espécie que o editor pediu entra no `monsters/respawn.json`, mas quem o
`hunt-add` lê é o `db-fragment.json`. Sem esse passo no meio, a espécie excluída
volta para o servidor.

O que conta como pendência:

- **espécie excluída no editor ainda presente** no respawn do bundle;
- **andares diferentes** dos que a máscara mantém (`floors` menos
  `excludedFloors`) — o recorte por máscara não estende andar;
- **máscara em outro espaço de coordenada** que o bundle (Rookgaard: as
  máscaras são de quando o recorte era local, ~1000, e o OTBM de hoje é
  ~32000). Isso não é pendência que `--apply` resolva — cortaria 0 tiles —, e é
  relatado como incompatível.

Spot de treino fica de fora por padrão (`--include-training` traz): quem refina
treino costuma estar mexendo em outra coisa, e re-cortar sem pedir surpreende.

Run: uv run python extractor/scripts/apply_pending_masks.py
     uv run python extractor/scripts/apply_pending_masks.py --apply
     uv run python extractor/scripts/apply_pending_masks.py --apply --only CARLIN-HUNT-0003
"""

import argparse
import json
import os
import subprocess
import sys
import time
from typing import Dict, List, Optional, Tuple

import paths

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
EXTRACTOR_DIR = os.path.dirname(SCRIPTS_DIR)
REPO_ROOT = os.path.dirname(EXTRACTOR_DIR)
MASK_DIR = os.path.join(EXTRACTOR_DIR, "hunt-masks")

ASSETS_RELPATH = os.path.join("apps", "tibia-idle-front", "public", "assets")
CATALOG_RELPATH = os.path.join("apps", "tibia-idle-api", "content", "catalog-source.json")
HUNTS_RELPATH = os.path.join("apps", "tibia-idle-api", "content", "hunts", "hunts.json")

BUNDLE_SUFFIX = "-sprites-v6"

# Todo passo da cadeia roda da raiz do repo, pelo mesmo python do uv.
SCRIPT = ["uv", "run", "python", "-u"]


def read_json(path: str):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: str, value) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def mask_ids() -> List[str]:
    if not os.path.isdir(MASK_DIR):
        return []
    return sorted(
        name[: -len(".json")]
        for name in os.listdir(MASK_DIR)
        if name.endswith(".json")
    )


def bundle_of(assets_dir: str, hunt_id: str) -> Tuple[Optional[str], Optional[str]]:
    """`(pasta sem o sufixo, pasta do bundle)` do hunt publicado, ou `(None, None)`."""
    for name in sorted(os.listdir(assets_dir)):
        if name.startswith(f"{hunt_id}_") and name.endswith(BUNDLE_SUFFIX):
            return name[: -len(BUNDLE_SUFFIX)], name

    return None, None


def kept_floors(mask: Dict) -> List[int]:
    excluded = {int(z) for z in (mask.get("excludedFloors") or [])}
    return sorted(
        int(z)
        for z, cells in mask["floors"].items()
        if cells and int(z) not in excluded
    )


def mask_sample(mask: Dict) -> Optional[Tuple[int, int]]:
    for cells in mask["floors"].values():
        if cells:
            x, y = cells[0]
            return int(x), int(y)
    return None


def city_bounds(city: str) -> Optional[Dict]:
    """A caixa do recorte da cidade, em coordenada de mundo — ou `None`."""
    path = os.path.join(EXTRACTOR_DIR, "full-maps", city, "source.json")
    if not os.path.isfile(path):
        return None
    return read_json(path).get("bounds")


def pending_reason(mask: Dict, bundle_dir: str, city_box: Optional[Dict]) -> Optional[str]:
    """Por que esta máscara ainda não está no jogo — ou `None` se já está."""
    map_json = read_json(os.path.join(bundle_dir, "map.json"))

    # A comparação de coordenada é contra o mapa **da cidade**, não contra o
    # bundle: quem corta é o `apply_hunt_mask.py`, e ele corta do
    # `full-maps/<CIDADE>/<CIDADE>.otbm`. O bundle de Rookgaard é da época em
    # que o recorte era local, então a máscara cabe nele e não cabe na cidade —
    # comparar com o bundle diria que está tudo bem e o recorte cortaria 0
    # tiles.
    sample = mask_sample(mask)
    if sample is not None and city_box:
        x, y = sample
        inside_x = city_box["minX"] <= x <= city_box["maxX"]
        inside_y = city_box["minY"] <= y <= city_box["maxY"]
        if not (inside_x and inside_y):
            return (
                f"incompatível: máscara em ({x}, {y}), cidade em "
                f"{city_box['minX']}–{city_box['maxX']}, {city_box['minY']}–{city_box['maxY']}"
            )

    floors_in_bundle = sorted(int(z) for z in map_json.get("floors", {}))
    floors_in_mask = kept_floors(mask)
    if floors_in_mask and floors_in_bundle != floors_in_mask:
        return f"andares: bundle {floors_in_bundle}, máscara {floors_in_mask}"

    excluded = set(mask.get("excludedSpecies") or [])
    respawn_path = os.path.join(bundle_dir, "monsters", "respawn.json")
    if excluded and os.path.isfile(respawn_path):
        present = {spawn["name"] for spawn in read_json(respawn_path).get("spawns", [])}
        leaked = sorted(present & excluded)
        if leaked:
            return f"espécie excluída presente: {', '.join(leaked)}"

    return None


def run(command: List[str], cwd: str) -> Tuple[int, str]:
    done = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    return done.returncode, done.stdout + done.stderr


def last_line(log: str) -> str:
    lines = [line for line in log.strip().splitlines() if line.strip()]
    return lines[-1] if lines else "(sem saída)"


def catalog_name(game_dir: str, hunt_id: str) -> Optional[str]:
    catalog = read_json(os.path.join(game_dir, CATALOG_RELPATH))
    for hunt in catalog["hunts"]:
        if hunt["id"] == hunt_id:
            return hunt.get("name")
    return None


def restore_start_position(game_dir: str, hunt_id: str, entrance) -> None:
    """A entrada curada de volta nos dois arquivos de conteúdo.

    O `hunt-add` sobrescreve `startPosition` com o centro geométrico que vem do
    fragmento marcado `_todo`, e perde o andar no caminho (ticket 37 da
    bancada). Enquanto ele fizer isso, quem aplica máscara desfaz — a entrada
    que vale é a que foi marcada no editor.
    """
    for relpath, key in ((CATALOG_RELPATH, "hunts"), (HUNTS_RELPATH, None)):
        path = os.path.join(game_dir, relpath)
        document = read_json(path)
        rows = document[key] if key else document
        for hunt in rows:
            if hunt["id"] == hunt_id:
                hunt["startPosition"] = list(entrance)
        write_json(path, document)


def apply_one(game_dir: str, hunt_id: str, folder: str, bundle: str, mask: Dict) -> Tuple[bool, str]:
    started = time.time()

    code, log = run(SCRIPT + [os.path.join("extractor", "scripts", "apply_hunt_mask.py"), hunt_id], REPO_ROOT)
    if code != 0:
        return False, f"apply_hunt_mask: {last_line(log)}"
    recut = next((line.strip() for line in log.splitlines() if "re-corte pela máscara" in line), "")
    excluded = next((line.strip() for line in log.splitlines() if "excluídos" in line), "")

    code, log = run(SCRIPT + [os.path.join("extractor", "scripts", "build_hunt_fragment.py"), folder, "--map-id", hunt_id], REPO_ROOT)
    if code != 0:
        return False, f"build_hunt_fragment: {last_line(log)}"

    code, log = run(SCRIPT + [os.path.join("extractor", "scripts", "publish.py"), folder], REPO_ROOT)
    if code != 0:
        return False, f"publish: {last_line(log)}"

    command = ["bunx", "nx", "run", "hunt-add:add", "--", "--from", bundle]
    name = mask.get("name") or catalog_name(game_dir, hunt_id)
    if name:
        command += ["--name", name]
    code, log = run(command, game_dir)
    if code != 0:
        return False, f"hunt-add: {last_line(log)}"

    if mask.get("entrance"):
        restore_start_position(game_dir, hunt_id, mask["entrance"])

    detail = " ".join(part for part in (recut, excluded) if part)
    return True, f"{detail} ({time.time() - started:.0f}s)"


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--apply", action="store_true", help="fecha a diferença, não só relata")
    parser.add_argument("--only", action="append", metavar="ID", help="só este id (repetível)")
    parser.add_argument(
        "--include-training",
        action="store_true",
        help="inclui spot de treino (CIDADE-TRAINING-NNNN), que por padrão fica de fora",
    )
    parser.add_argument("--tibia-idle-dir")
    args = parser.parse_args()

    game_dir = paths.TIBIA_IDLE.require(args.tibia_idle_dir)
    assets_dir = os.path.join(game_dir, ASSETS_RELPATH)

    wanted = set(args.only or [])
    pending: List[Tuple[str, str, str, str, Dict]] = []
    incompatible: List[Tuple[str, str]] = []
    skipped_training: List[str] = []
    unpublished: List[str] = []
    in_sync = 0

    for hunt_id in mask_ids():
        if wanted and hunt_id not in wanted:
            continue
        if "-TRAINING-" in hunt_id and not args.include_training:
            skipped_training.append(hunt_id)
            continue

        mask = read_json(os.path.join(MASK_DIR, f"{hunt_id}.json"))
        folder, bundle = bundle_of(assets_dir, hunt_id)
        if not bundle:
            unpublished.append(hunt_id)
            continue

        city = hunt_id.split('-')[0]
        reason = pending_reason(mask, os.path.join(assets_dir, bundle), city_bounds(city))
        if reason is None:
            in_sync += 1
        elif reason.startswith("incompatível"):
            incompatible.append((hunt_id, reason))
        else:
            pending.append((hunt_id, reason, folder, bundle, mask))

    print(f"[OK] {in_sync} máscara(s) já no jogo")
    for hunt_id in unpublished:
        print(f"[--] {hunt_id}: sem bundle publicado")
    for hunt_id, reason in incompatible:
        print(f"[!!] {hunt_id}: {reason}")
    if skipped_training:
        print(f"[--] {len(skipped_training)} spot(s) de treino fora (use --include-training)")

    if not pending:
        # Incompatível não derruba a porta: é estado conhecido e permanente
        # (Rookgaard), não trabalho esperando por alguém. Fica no relatório.
        print("[OK] nada pendente")
        sys.exit(0)

    print(f"\n{len(pending)} máscara(s) pendente(s):")
    for hunt_id, reason, _, _, _ in pending:
        print(f"  {hunt_id}: {reason}")

    if not args.apply:
        print("\nRode de novo com --apply para fechar a diferença.")
        sys.exit(1)

    print()
    failures = 0
    for hunt_id, _, folder, bundle, mask in pending:
        ok, detail = apply_one(game_dir, hunt_id, folder, bundle, mask)
        print(("[OK] " if ok else "[ERRO] ") + f"{hunt_id}: {detail}", flush=True)
        failures += 0 if ok else 1

    print(
        f"\n{len(pending) - failures}/{len(pending)} aplicada(s). "
        "O conteúdo do jogo mudou — rode `nx run db:provision` (ou `db:reset`) pra ver no jogo."
    )
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
