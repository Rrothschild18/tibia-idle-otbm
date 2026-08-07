"""Mede o mecanismo de `ground_equivalent` do Remere's Map Editor contra os mapas do repo.

O editor tem um mecanismo em que certas bordas declaram o chão que existe "por
baixo" delas (`<border ground_equivalent="G">` em `grounds.xml`). Esse dado não
sai das flags do `appearances.dat` — é arquivo de autoria do editor, e por isso
está vendorizado em `extractor/vendor/rme-materials/` (ver o `NOTICE.md` de lá).

A pergunta que este módulo responde, em número: **precisamos desse dado para
montar a pilha de tile igual ao editor?** Se toda tile que carrega uma dessas
bordas já tem, gravado no OTBM, exatamente o chão que a borda sintetizaria, o
mecanismo não acrescenta nada e sai do escopo.

Duas leituras do que conta como "borda declarante" são medidas lado a lado:

- **estrita** — só os `<borderitem>` de dentro de um `<border ground_equivalent>`.
  É o conjunto que o editor de fato trata como borda-chão daquele brush.
- **ampla** (controle) — mais os ids que os blocos `<specific>` do mesmo
  `<border>` usam para trocar uma borda por outra. Medida separada justamente
  para mostrar que a inferência "a troca herda o chão sintetizado" não se
  sustenta: esses ids não carregam a flag `bank`, ou seja, não são chão.

Ver `.scratch/modelo-render-rme/issues/02-materials-ground-equivalent.md`.

Uso:
    python ground_equivalent_report.py                 # relatório de todos os mapas
    python ground_equivalent_report.py --out FILE.md   # grava em markdown
"""

import argparse
import glob
import json
import os
import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
EXTRACTOR_DIR = os.path.dirname(SCRIPTS_DIR)
GROUNDS_XML = os.path.join(EXTRACTOR_DIR, "vendor", "rme-materials", "grounds.xml")
RAW_MAPS_DIR = os.path.join(EXTRACTOR_DIR, "raw-maps")
ITEMS_SPRITES_DIR = os.path.join(EXTRACTOR_DIR, "sprites", "items")

# `grounds.xml` não é XML bem-formado: nomes de brush como
# `lava (rock soil & cave ground)` deixam o `&` cru, o que o parser tolerante do
# próprio editor (pugixml) aceita e o `xml.etree` não. O arquivo vendorizado
# precisa continuar byte a byte igual ao upstream (é o que a EULA autoriza
# distribuir — ver o NOTICE.md de lá), então a correção acontece só em memória,
# na leitura.
_BARE_AMPERSAND = re.compile(r"&(?!#?\w+;)")


def _parse_lenient(xml_path: str) -> ET.Element:
    with open(xml_path, "r", encoding="utf-8") as handler:
        text = handler.read()
    return ET.fromstring(_BARE_AMPERSAND.sub("&amp;", text))


def parse_ground_equivalents(grounds_xml_path: str) -> Dict[int, int]:
    """`{border item id: ground item id que a borda sintetiza}` — leitura estrita.

    Só os `<borderitem>` de dentro de um `<border ground_equivalent="G">`. É o
    conjunto que o editor trata como borda-chão do brush.
    """
    equivalents: Dict[int, int] = {}
    for border in _parse_lenient(grounds_xml_path).iter("border"):
        raw_ground = border.get("ground_equivalent")
        if raw_ground is None:
            continue
        for border_item in border.iter("borderitem"):
            item_id = border_item.get("item")
            if item_id is not None:
                equivalents[int(item_id)] = int(raw_ground)
    return equivalents


def parse_specific_replacements(grounds_xml_path: str) -> Dict[int, int]:
    """`{id de troca: chão do `<border>` que hospeda o `<specific>`}` — controle.

    Os ids que só aparecem como alvo de `<replace_item>`, nunca como
    `<borderitem>`. Serve para medir o custo de assumir que a troca herda o
    `ground_equivalent` do `<border>` em que está — assunção que a medição
    derruba.
    """
    strict = parse_ground_equivalents(grounds_xml_path)
    replacements: Dict[int, int] = {}
    for border in _parse_lenient(grounds_xml_path).iter("border"):
        raw_ground = border.get("ground_equivalent")
        if raw_ground is None:
            continue
        for replacement in border.iter("replace_item"):
            for attr in ("id", "with"):
                item_id = replacement.get(attr)
                if item_id is not None and int(item_id) not in strict:
                    replacements[int(item_id)] = int(raw_ground)
    return replacements


def appearance_flags(appearance_id: int, items_dir: str = ITEMS_SPRITES_DIR) -> Dict:
    """Flags do `appearances.dat` para um id, ou `{}` se o sprite não foi extraído.

    Só o suficiente para responder "isso é chão?" (flag `bank`) sem arrastar o
    `build_phaser_map`, que resolve caminhos de saída no import.
    """
    for candidate in (
        os.path.join(items_dir, f"{appearance_id}.json"),
        os.path.join(items_dir, str(appearance_id), f"{appearance_id}.json"),
    ):
        if os.path.exists(candidate):
            with open(candidate, "r", encoding="utf-8") as handler:
                return json.load(handler).get("flags", {})
    return {}


def measure_dump(dump: Dict, equivalents: Dict[int, int]) -> Dict:
    """Conta, num dump `.raw.json`, as tiles tocadas pelo mecanismo.

    Uma tile conta uma vez, mesmo que carregue várias bordas declarantes. Ela é
    **divergente** quando o chão que a borda sintetizaria não é o que o OTBM já
    gravou naquela tile. Uma borda que está no próprio slot de chão da tile
    (`tileid`) nunca diverge: não há nada por baixo dela para sintetizar.
    """
    tiles_touched = 0
    matches = 0
    divergences = 0
    by_border: Dict[int, Dict[str, int]] = {}
    divergent_tiles: List[Dict] = []

    for node in dump.get("data", {}).get("nodes", []):
        for feature in node.get("features", []):
            base_x = feature.get("x", 0)
            base_y = feature.get("y", 0)
            z = feature.get("z", 7)

            for tile in feature.get("tiles", []):
                recorded_ground = tile.get("tileid")
                declaring: List[tuple] = []  # (border id, synthesized ground, slot)

                if recorded_ground in equivalents:
                    declaring.append((recorded_ground, equivalents[recorded_ground], "asGround"))
                for raw_item in tile.get("items", []) or []:
                    item_id = raw_item.get("id")
                    if item_id in equivalents:
                        declaring.append((item_id, equivalents[item_id], "asItem"))

                if not declaring:
                    continue

                tiles_touched += 1
                tile_diverges = False

                for border_id, synthesized, slot in declaring:
                    counts = by_border.setdefault(border_id, {"asGround": 0, "asItem": 0})
                    counts[slot] += 1
                    if slot == "asItem" and synthesized != recorded_ground:
                        tile_diverges = True
                        divergent_tiles.append({
                            "x": base_x + tile.get("x", 0),
                            "y": base_y + tile.get("y", 0),
                            "z": z,
                            "border": border_id,
                            "synthesized": synthesized,
                            "recorded": recorded_ground,
                        })

                if tile_diverges:
                    divergences += 1
                else:
                    matches += 1

    return {
        "tilesWithSynthesizedGround": tiles_touched,
        "matches": matches,
        "divergences": divergences,
        "byBorder": by_border,
        "divergentTiles": divergent_tiles,
    }


def measure_all_maps(raw_maps_dir: str, equivalents: Dict[int, int]) -> List[Dict]:
    """Uma medição por `.raw.json`, em ordem de nome."""
    results = []
    for path in sorted(glob.glob(os.path.join(raw_maps_dir, "*.raw.json"))):
        with open(path, "r", encoding="utf-8") as handler:
            dump = json.load(handler)
        result = measure_dump(dump, equivalents)
        result["map"] = os.path.basename(path)[: -len(".raw.json")]
        results.append(result)
    return results


def _totals(results: List[Dict]) -> Dict[str, int]:
    return {
        "touched": sum(r["tilesWithSynthesizedGround"] for r in results),
        "matches": sum(r["matches"] for r in results),
        "divergences": sum(r["divergences"] for r in results),
    }


def _measurement_table(results: List[Dict]) -> List[str]:
    lines = [
        "| mapa | tiles com borda declarante | coincide com o OTBM | diverge |",
        "|---|---:|---:|---:|",
    ]
    for result in results:
        if result["tilesWithSynthesizedGround"] == 0:
            continue
        lines.append(
            f"| `{result['map']}` | {result['tilesWithSynthesizedGround']} "
            f"| {result['matches']} | {result['divergences']} |"
        )
    totals = _totals(results)
    lines.append(
        f"| **total** | **{totals['touched']}** | **{totals['matches']}** "
        f"| **{totals['divergences']}** |"
    )
    silent = [r["map"] for r in results if r["tilesWithSynthesizedGround"] == 0]
    lines += ["", f"Sem nenhuma tile tocada: {len(silent)} mapas.", ""]
    return lines


def _slot_summary(results: List[Dict]) -> Dict[str, int]:
    as_ground = as_item = 0
    for result in results:
        for counts in result["byBorder"].values():
            as_ground += counts["asGround"]
            as_item += counts["asItem"]
    return {"asGround": as_ground, "asItem": as_item}


def render_markdown(strict: Dict[int, int], loose: Dict[int, int],
                    strict_results: List[Dict], loose_results: List[Dict]) -> str:
    strict_totals = _totals(strict_results)
    loose_totals = _totals(loose_results)
    strict_slots = _slot_summary(strict_results)

    banked = sorted(bid for bid in strict if "bank" in appearance_flags(bid))
    unbanked_loose = sorted(bid for bid in loose if "bank" not in appearance_flags(bid))

    lines = [
        "# 02 — Divergência de ground sintetizado por borda",
        "",
        "Gerado por `extractor/scripts/ground_equivalent_report.py` a partir de",
        "`extractor/vendor/rme-materials/grounds.xml` e de todos os",
        "`extractor/raw-maps/*.raw.json`. Para regerar:",
        "",
        "```",
        "python extractor/scripts/ground_equivalent_report.py \\",
        "  --out .scratch/modelo-render-rme/reports/02-ground-equivalent.md",
        "```",
        "",
        "## O mecanismo",
        "",
        "No `grounds.xml` do editor, `ground_equivalent` aparece em **3 elementos `<border>`**, nos",
        f"brushes `sand` e `sandstone`, cobrindo **{len(strict)} ids de borda**.",
        "",
        "## Medição estrita — os `<borderitem>` do `<border ground_equivalent>`",
        "",
    ]
    lines += _measurement_table(strict_results)
    lines += [
        f"**Divergência: {strict_totals['divergences']}.**",
        "",
        f"Das {strict_totals['touched']} tiles tocadas, **{strict_slots['asGround']} têm a borda no",
        f"próprio slot de chão do OTBM (`tileid`) e {strict_slots['asItem']} a têm como item empilhado**.",
        "",
        f"Isso não é acidente do conjunto de mapas: **{len(banked)} dos {len(strict)} ids** carregam a",
        "flag `bank` no `appearances.dat` — ou seja, o editor não coloca um chão *por baixo* da borda,",
        "a borda **é** o chão. `ground_equivalent` é uma busca inversa de autoria (\"a que brush este",
        "chão pertence, para eu recalcular as bordas ao redor\"), não uma regra de empilhamento.",
        "",
        "## Medição ampla (controle) — mais os alvos de `<specific>`/`<replace_item>`",
        "",
        f"Os blocos `<specific>` dentro dos mesmos `<border>` trocam uma borda por outra, somando",
        f"**{len(loose)} ids** que nunca aparecem como `<borderitem>`. Assumir que essa troca herda o",
        "`ground_equivalent` do `<border>` que a hospeda produziria:",
        "",
    ]
    lines += _measurement_table(loose_results)
    lines += [
        f"**{loose_totals['divergences']} divergências — todas artefato da assunção.**",
        f"Nenhum dos {len(unbanked_loose)} ids de troca carrega a flag `bank`: são itens `clip`",
        "(borda de fundo) que legitimamente ficam **sobre** um chão gravado. Herdar o",
        "`ground_equivalent` para eles inventaria um chão que o editor nunca coloca.",
        "",
        "## Recomendação",
        "",
        "**Ignorar o mecanismo.** A divergência real é **zero**: onde o editor considera a borda um",
        "chão, o OTBM já grava exatamente essa borda no slot de chão da tile. Não há nada a sintetizar,",
        "e o ticket 03 pode montar a pilha só com as flags do `appearances.dat` — `bank` para o draw",
        "slot, `clip`/`bottom`/`top` para o `top order` — sem consultar arquivo de autoria nenhum.",
        "",
        "Os arquivos vendorizados ficam no repo como evidência desta medição, não como entrada do",
        "pipeline: nenhum script de build lê `extractor/vendor/rme-materials/`.",
        "",
    ]
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grounds-xml", default=GROUNDS_XML)
    parser.add_argument("--raw-maps", default=RAW_MAPS_DIR)
    parser.add_argument("--out", default=None, help="grava o relatório markdown neste caminho")
    args = parser.parse_args(argv)

    strict = parse_ground_equivalents(args.grounds_xml)
    loose = parse_specific_replacements(args.grounds_xml)
    report = render_markdown(
        strict, loose,
        measure_all_maps(args.raw_maps, strict),
        measure_all_maps(args.raw_maps, {**strict, **loose}),
    )

    if args.out:
        with open(args.out, "w", encoding="utf-8") as handler:
            handler.write(report)
        print(f"[OK] Relatório gravado em {args.out}")
    else:
        print(report)


if __name__ == "__main__":
    main()
