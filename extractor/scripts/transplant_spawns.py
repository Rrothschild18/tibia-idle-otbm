"""
CLI: copia para o mapa de destino os grupos de spawn que um humano acrescentou
ao XML de spawn de outro mapa, aplicando o mesmo offset do transplante de itens.

Spawn não vive no OTBM — vive no `<MAPA>-monster.xml` ao lado dele. Então quem
pinta o caminho de uma quest no editor e coloca os bichos dela mexe em **dois**
arquivos, e um transplante que leva só os itens entrega um corredor vazio.

O que copiar é decidido pelo **que o autor mudou**, não por conter numa caixa:
a caixa da quest também contém spawn que o mapa-mundo tem e o mapa de destino
não (recorte à mão é mais apertado que o mundo), e copiar aquilo seria
acrescentar conteúdo que ninguém pediu. A fonte da verdade é a diferença entre
o XML de agora e a versão limpa dele — no caso do otservbr, `git show HEAD:`.

O grupo é a unidade: acrescentar uma criatura a um grupo que já existia faz o
grupo inteiro voltar como mudado, e o destino recebe a versão nova, não duas.

Run: python transplant_spawns.py --from <xml atual> --pristine <xml limpo> \\
        --into extractor/full-maps/ROOK/ROOK-monster.xml --offset -30958,-31074,0
"""

import argparse
import os
import re
import subprocess
import sys
from typing import Dict, List, Optional, Sequence, Tuple

_GROUP_RE = re.compile(
    r'<monster\s+centerx="(-?\d+)"\s+centery="(-?\d+)"\s+centerz="(-?\d+)"\s+radius="(\d+)"\s*>'
    r"(.*?)</monster\s*>",
    re.S,
)
_CREATURE_RE = re.compile(
    r'<monster\s+name="([^"]*)"\s+x="(-?\d+)"\s+y="(-?\d+)"\s+z="(-?\d+)"\s+spawntime="(\d+)"\s*/>'
)


def parse_spawn_groups(xml: str) -> List[Dict]:
    """Todo `<monster center...>` do XML como
    `{center, radius, creatures:[{name,x,y,z,spawntime}]}`."""
    groups: List[Dict] = []

    for match in _GROUP_RE.finditer(xml):
        creatures = [
            {"name": name, "x": int(x), "y": int(y), "z": int(z), "spawntime": int(t)}
            for name, x, y, z, t in _CREATURE_RE.findall(match.group(5))
        ]
        groups.append({
            "center": (int(match.group(1)), int(match.group(2)), int(match.group(3))),
            "radius": int(match.group(4)),
            "creatures": creatures,
        })

    return groups


def _fingerprint(group: Dict) -> Tuple:
    return (
        group["center"],
        group["radius"],
        tuple(sorted(
            (c["name"], c["x"], c["y"], c["z"], c["spawntime"]) for c in group["creatures"]
        )),
    )


def added_groups(current_xml: str, pristine_xml: str) -> List[Dict]:
    """Os grupos que existem no XML de agora e não existiam no limpo."""
    pristine = {_fingerprint(g) for g in parse_spawn_groups(pristine_xml)}
    return [g for g in parse_spawn_groups(current_xml) if _fingerprint(g) not in pristine]


def shift_group(group: Dict, offset: Sequence[int]) -> Dict:
    """O mesmo grupo com o centro deslocado.

    `x`/`y` de cada criatura são **relativos ao centro** e por isso não se
    deslocam; `z` é absoluto e acompanha o offset de andar."""
    cx, cy, cz = group["center"]
    return {
        "center": (cx + offset[0], cy + offset[1], cz + offset[2]),
        "radius": group["radius"],
        "creatures": [{**c, "z": c["z"] + offset[2]} for c in group["creatures"]],
    }


def render_group(group: Dict) -> str:
    cx, cy, cz = group["center"]
    lines = [f'\t<monster centerx="{cx}" centery="{cy}" centerz="{cz}" radius="{group["radius"]}">']
    for c in group["creatures"]:
        lines.append(
            f'\t\t<monster name="{c["name"]}" x="{c["x"]}" y="{c["y"]}" z="{c["z"]}"'
            f' spawntime="{c["spawntime"]}" />'
        )
    lines.append("\t</monster>")
    return "\n".join(lines)


def merge_groups(destination_xml: str, groups: Sequence[Dict]) -> str:
    """Os grupos entram antes do `</monsters>` que fecha o arquivo.

    Idempotente: um grupo cuja impressão digital já está no destino não entra
    de novo — rodar duas vezes não dobra o spawn."""
    present = {_fingerprint(g) for g in parse_spawn_groups(destination_xml)}
    fresh = [g for g in groups if _fingerprint(g) not in present]
    if not fresh:
        return destination_xml

    closing = destination_xml.rindex("</monsters>")
    block = "\n".join(render_group(g) for g in fresh) + "\n"
    return destination_xml[:closing] + block + destination_xml[closing:]


# ======================================================
# CLI
# ======================================================

def _parse_offset(raw: str) -> Tuple[int, int, int]:
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) != 3:
        sys.exit("error: --offset quer três inteiros, ex: -30958,-31074,0")
    return (int(parts[0]), int(parts[1]), int(parts[2]))


def _pristine_from_git(path: str) -> Optional[str]:
    """A versão commitada do arquivo, que é a referência de 'limpo'."""
    directory = os.path.dirname(os.path.abspath(path))
    done = subprocess.run(
        ["git", "-C", directory, "ls-files", "--full-name", os.path.basename(path)],
        capture_output=True, text=True, check=False,
    )
    relative = done.stdout.strip()
    if done.returncode != 0 or not relative:
        return None
    show = subprocess.run(
        ["git", "-C", directory, "show", f"HEAD:{relative}"],
        capture_output=True, text=True, check=False,
    )
    return show.stdout if show.returncode == 0 else None


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--from", dest="source", required=True, help="XML de spawn de agora")
    parser.add_argument("--pristine", help="XML de spawn limpo; default: a versão do git")
    parser.add_argument("--into", dest="destination", required=True,
                        help="XML de spawn de destino, reescrito no lugar")
    parser.add_argument("--offset", required=True, help="dx,dy,dz, ex: -30958,-31074,0")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    offset = _parse_offset(args.offset)

    for path in (args.source, args.destination):
        if not os.path.exists(path):
            sys.exit(f"error: não encontrado: {path}")

    current = open(args.source, encoding="utf-8", errors="replace").read()

    if args.pristine:
        pristine = open(args.pristine, encoding="utf-8", errors="replace").read()
    else:
        pristine = _pristine_from_git(args.source)
        if pristine is None:
            sys.exit(
                f"error: não consegui a versão limpa de {args.source} pelo git — passe --pristine.\n"
                f"       sem referência de 'limpo' não há como saber o que foi acrescentado"
            )

    added = added_groups(current, pristine)
    moved = [shift_group(g, offset) for g in added]

    by_name: Dict[str, int] = {}
    for group in moved:
        for creature in group["creatures"]:
            by_name[creature["name"]] = by_name.get(creature["name"], 0) + 1

    print(f"acrescentados na fonte: {len(added)} grupo(s)")
    for group in moved:
        names = ", ".join(c["name"] for c in group["creatures"])
        print(f"  {group['center']}  r={group['radius']}  {names}")
    print(f"criaturas por nome: {by_name}")

    if not moved:
        print("  nada a copiar")
        return

    destination = open(args.destination, encoding="utf-8", errors="replace").read()
    merged = merge_groups(destination, moved)

    if merged == destination:
        print("  destino já tem todos — nada escrito")
        return
    if args.dry_run:
        print("  (dry-run: nada escrito)")
        return

    with open(args.destination, "w", encoding="utf-8") as handle:
        handle.write(merged)
    print(f"  -> {args.destination}")


if __name__ == "__main__":
    main()
