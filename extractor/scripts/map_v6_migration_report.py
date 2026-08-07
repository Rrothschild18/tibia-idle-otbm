"""Confere a re-exportação v6 contra o `map.json` v5 de cada mapa.

A pergunta é sempre a mesma: **nenhuma tile perdeu ou ganhou conteúdo na
migração?** Os dois formatos guardam a mesma coisa de jeitos diferentes — o v5
espalha as aparências de uma tile por uma tilelayer de chão e até sete
objectgroups, o v6 põe as mesmas aparências numa pilha só — então o que se
compara é o **conjunto de aparências por tile**, não onde cada uma caiu. É o
critério de aceite dos tickets 04 e 07.

Duas coisas mudam de propósito e não contam como divergência: a ordem dentro da
pilha (é a mudança inteira) e o slot em que uma aparência cai (uma com `bank`
que o v5 empurrava pra um objectgroup vira o chão da tile no v6).

Junto vai o antes-e-depois de folhas de sprite, de posicionamentos e de tamanho
de arquivo, por mapa.

Uso:
    python map_v6_migration_report.py                 # todos os mapas
    python map_v6_migration_report.py --out FILE.md   # grava em markdown
"""

import argparse
import json
import os
import sys
from collections import Counter
from typing import Dict, List, Optional, Tuple

import map_dirs
from sheet_packer import SAFE_TEXTURE_SIZE

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
EXTRACTOR_DIR = os.path.dirname(SCRIPTS_DIR)

READY_MAPS_DIR = os.path.join(EXTRACTOR_DIR, "ready-maps")
READY_MAPS_V6_DIR = os.path.join(EXTRACTOR_DIR, "ready-maps-v6")

TileKey = Tuple[int, int, int]  # (z, tileX, tileY)


def tile_contents_v5(document: Dict) -> Dict[TileKey, Dict]:
    """`{(z, x, y): {named, unnamedGrounds}}` lido de um `map.json` v5.

    - **`named`** — os ids que o arquivo carrega explicitamente: toda entrada de
      objectgroup, mais o chão quando o v5 o desviou pra um objectgroup
      (`stackIndex == -1`).
    - **`unnamedGrounds`** — `1` quando a célula da tilelayer `Ground` está
      ocupada, `0` quando não. É `1` e não o id porque o v5 guarda ali um gid
      contra um sheet compartilhado, sem registrar de que aparência ele veio.

    A separação é o que permite conferir sem reimplementar o empacotamento do
    v5 dentro do próprio conferidor.
    """
    contents: Dict[TileKey, Dict] = {}

    def _tile(key: TileKey) -> Dict:
        return contents.setdefault(key, {"named": [], "unnamedGrounds": 0})

    for floor in document.get("floors", {}).values():
        z = floor["z"]
        for layer in floor.get("layers", []):
            if layer.get("type") == "tilelayer":
                width = layer["width"]
                for index, gid in enumerate(layer.get("data", [])):
                    if gid:
                        _tile((z, index % width, index // width))["unnamedGrounds"] = 1
            else:
                for obj in layer.get("objects", []):
                    # [tileX, tileY, *[appearanceId, stackIndex]]
                    tile = _tile((z, obj[0], obj[1]))
                    tile["named"].extend(appearance_id for appearance_id, _ in obj[2:])

    for tile in contents.values():
        tile["named"].sort()
    return contents


def tile_contents_v6(document: Dict) -> Dict[TileKey, Dict]:
    """`{(z, x, y): {named, unnamedGrounds}}`, no mesmo formato — o v6 nomeia
    tudo, chão inclusive, então `unnamedGrounds` é sempre `0`."""
    contents: Dict[TileKey, Dict] = {}
    for floor in document.get("floors", {}).values():
        z = floor["z"]
        for row in floor.get("tiles", []):
            named = list(row[3:]) + ([row[2]] if row[2] else [])
            contents[(z, row[0], row[1])] = {"named": sorted(named), "unnamedGrounds": 0}
    return contents


def _divergence(key: TileKey, v5_tile: Optional[Dict], v6_tile: Optional[Dict]) -> Optional[Dict]:
    """A razão pela qual esta tile não sobreviveu, ou None se sobreviveu.

    O critério é **o conteúdo**: as mesmas aparências, na mesma quantidade. Em
    que slot cada uma cai muda de propósito — uma aparência com `bank` que o v5
    empurrava pra um objectgroup vira o chão da tile no v6 — e a ordem dentro
    da pilha também. Nenhuma das duas conta como divergência.
    """
    z, x, y = key
    base = {"z": z, "x": x, "y": y}

    if v6_tile is None:
        return {**base, "reason": "tile só no v5", "v5": v5_tile["named"], "v6": []}
    if v5_tile is None:
        return {**base, "reason": "tile só no v6", "v5": [], "v6": v6_tile["named"]}

    v5_named = Counter(v5_tile["named"])
    v6_named = Counter(v6_tile["named"])

    lost = v5_named - v6_named
    if lost:
        return {**base, "reason": f"sumiu no v6: {sorted(lost.elements())}",
                "v5": v5_tile["named"], "v6": v6_tile["named"]}

    # What v6 names and v5 didn't must be exactly the grounds v5 left unnamed
    # in its tilelayer — no more, no less.
    gained = v6_named - v5_named
    if sum(gained.values()) != v5_tile["unnamedGrounds"]:
        return {**base, "reason": f"apareceu no v6: {sorted(gained.elements())}",
                "v5": v5_tile["named"], "v6": v6_tile["named"]}
    return None


def _placements(contents: Dict[TileKey, Dict]) -> int:
    return sum(len(tile["named"]) + tile["unnamedGrounds"] for tile in contents.values())


def compare(v5_document: Dict, v6_document: Dict) -> Dict:
    """Tiles que não sobreviveram, mais os números de antes/depois."""
    v5_contents = tile_contents_v5(v5_document)
    v6_contents = tile_contents_v6(v6_document)

    divergent = []
    for key in sorted(set(v5_contents) | set(v6_contents)):
        divergence = _divergence(key, v5_contents.get(key), v6_contents.get(key))
        if divergence is not None:
            divergent.append(divergence)

    return {
        "tilesV5": len(v5_contents),
        "tilesV6": len(v6_contents),
        "placementsV5": _placements(v5_contents),
        "placementsV6": _placements(v6_contents),
        # v5's `tilesets` entries point at PNGs the `sheets` manifest already
        # lists, so the manifest alone is the count of rendered sheets.
        "sheetsV5": len(v5_document.get("sheets", {})),
        "sheetsV6": len(v6_document.get("sheets", {})),
        "divergentTiles": divergent,
        "matches": not divergent,
    }


def _oversized_sheet_keys(v6_document: Dict, sheets_dir: str) -> List[str]:
    """Folhas cujo PNG gravado passa do limite seguro de textura."""
    from PIL import Image

    oversized = []
    for sheet_key in sorted(v6_document.get("sheets", {})):
        path = os.path.join(sheets_dir, f"{sheet_key}.png")
        if not os.path.exists(path):
            continue
        with Image.open(path) as image:
            if max(image.size) > SAFE_TEXTURE_SIZE:
                oversized.append(f"{sheet_key} ({image.size[0]}×{image.size[1]})")
    return oversized


def discover_map_pairs() -> List[Dict]:
    """`{name, v5, v6}` (diretórios) de cada mapa de hunt.

    Mapas de cidade inteira (`full-maps/`) ficam de fora: eles não têm v6 —
    nunca são renderizados, existem para o `build_travel_fragment.py` ler o
    `objectDefs` do v5.
    """
    pairs = []
    for city in map_dirs.discover_cities(READY_MAPS_DIR):
        city_dir = os.path.join(READY_MAPS_DIR, city)
        for entry in sorted(os.listdir(city_dir)):
            v5_dir = os.path.join(city_dir, entry)
            v6_dir = os.path.join(READY_MAPS_V6_DIR, city, entry)
            if os.path.exists(os.path.join(v5_dir, "map.json")):
                pairs.append({"name": entry, "v5": v5_dir, "v6": v6_dir})
    return pairs


def measure_pair(pair: Dict) -> Dict:
    v5_path = os.path.join(pair["v5"], "map.json")
    v6_path = os.path.join(pair["v6"], "map.json")
    if not os.path.exists(v6_path):
        return {"name": pair["name"], "missingV6": True}

    with open(v5_path, "r", encoding="utf-8") as handler:
        v5_document = json.load(handler)
    with open(v6_path, "r", encoding="utf-8") as handler:
        v6_document = json.load(handler)

    result = compare(v5_document, v6_document)
    result["name"] = pair["name"]
    result["missingV6"] = False
    result["bytesV5"] = os.path.getsize(v5_path)
    result["bytesV6"] = os.path.getsize(v6_path)
    result["oversizedSheets"] = _oversized_sheet_keys(
        v6_document, os.path.join(pair["v6"], "sheets")
    )
    return result


def _kb(num_bytes: int) -> str:
    return f"{num_bytes / 1024:.0f} KB"


def render_markdown(results: List[Dict]) -> str:
    measured = [r for r in results if not r["missingV6"]]
    missing = [r["name"] for r in results if r["missingV6"]]
    mismatched = [r for r in measured if not r["matches"]]
    oversized = [r for r in measured if r["oversizedSheets"]]

    lines = [
        "# 07 — Re-exportação em v6: antes e depois",
        "",
        "Gerado por `extractor/scripts/map_v6_migration_report.py` depois de",
        "`node extractor/scripts/build_map.js --all`. Para regerar:",
        "",
        "```",
        "python extractor/scripts/map_v6_migration_report.py \\",
        "  --out .scratch/modelo-render-rme/reports/07-reexportacao-v6.md",
        "```",
        "",
        "## Resumo",
        "",
        f"- Mapas presentes nos dois formatos: **{len(measured)}**.",
        f"- Com alguma tile cujo conteúdo mudou entre v5 e v6: **{len(mismatched)}**.",
        f"- Com folha acima do limite seguro de textura ({SAFE_TEXTURE_SIZE}px): "
        f"**{len(oversized)}**.",
        "",
        "## Por mapa",
        "",
        "| mapa | folhas v5 → v6 | posicionamentos v5 → v6 | tamanho v5 → v6 | tiles divergentes |",
        "|---|---:|---:|---:|---:|",
    ]

    for result in measured:
        lines.append(
            f"| `{result['name']}` "
            f"| {result['sheetsV5']} → {result['sheetsV6']} "
            f"| {result['placementsV5']} → {result['placementsV6']} "
            f"| {_kb(result['bytesV5'])} → {_kb(result['bytesV6'])} "
            f"| {len(result['divergentTiles'])} |"
        )

    totals_v5 = sum(r["sheetsV5"] for r in measured)
    totals_v6 = sum(r["sheetsV6"] for r in measured)
    bytes_v5 = sum(r["bytesV5"] for r in measured)
    bytes_v6 = sum(r["bytesV6"] for r in measured)
    lines += [
        f"| **total** | **{totals_v5} → {totals_v6}** | | "
        f"**{_kb(bytes_v5)} → {_kb(bytes_v6)}** | "
        f"**{sum(len(r['divergentTiles']) for r in measured)}** |",
        "",
        "Uma tile só conta como divergente quando o **conjunto de aparências** muda. A ordem dentro",
        "da pilha muda de propósito — é a mudança inteira — e não conta.",
        "",
    ]

    if missing:
        lines += ["## Sem v6", "",
                  "\n".join(f"- `{name}`" for name in missing), ""]

    if mismatched:
        lines += ["## Divergências", ""]
        for result in mismatched:
            lines += [f"### `{result['name']}`", ""]
            for tile in result["divergentTiles"][:20]:
                lines.append(
                    f"- z={tile['z']} ({tile['x']}, {tile['y']}) — {tile['reason']}: "
                    f"v5 {tile['v5']}, v6 {tile['v6']}"
                )
            lines.append("")

    if oversized:
        lines += ["## Folhas acima do limite de textura", ""]
        for result in oversized:
            lines.append(f"- `{result['name']}`: {', '.join(result['oversizedSheets'])}")
        lines.append("")

    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=None, help="grava o relatório markdown neste caminho")
    args = parser.parse_args(argv)

    results = [measure_pair(pair) for pair in discover_map_pairs()]
    report = render_markdown(results)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as handler:
            handler.write(report)
        print(f"[OK] Relatório gravado em {args.out}")
    else:
        # The report is UTF-8 (arrows, box glyphs); a Windows console defaults
        # to cp1252 and would raise on them.
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        print(report)

    if any(not r["missingV6"] and not r["matches"] for r in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
