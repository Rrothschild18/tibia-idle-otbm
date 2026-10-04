"""Regenera `extractor/vendor/canary/` a partir de um checkout do Canary.

O pipeline lia direto de um clone inteiro do Canary: `data/items/items.xml`
(3,5 MB), 1035 `.lua` de NPC (9 MB) e 1656 `.lua` de monstro (7,5 MB). Só quem
tivesse o clone conseguia rodar o grafo de viagem.

Vendorizamos o que é de fato lido, no padrão que o repo já pratica com
`monster-loot.json`. Misto, de propósito:

- **`items.xml` cru** — é um arquivo só, e é fonte de duas coisas (floorchange
  para o grafo, nome↔id e decay para o loot). Cru continua auditável e evita
  inventar um formato intermediário.
- **Extrato dos `.lua` de NPC como JSON** — ninguém revisa 1035 arquivos num
  diff. O extrato carrega exatamente o que o pipeline lê: a tabela `shop` e a
  tabela `outfit`.

Os `.lua` de monstro não entram aqui: o extrato deles já existe e já é
versionado, é o `extractor/monster-loot.json` que `build_monster_loot_index.py`
gera.

Run: uv run python extractor/scripts/update_canary_data.py [--canary-dir PATH]
"""

import argparse
import collections
import datetime
import glob
import json
import os
import shutil
import subprocess

import paths
from travel_graph import (
    parse_floorchange_items,
    parse_ladder_items,
    parse_npc_outfit_lua,
    parse_npc_services_lua,
    parse_npc_shop_lua,
)

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
EXTRACTOR_DIR = os.path.dirname(SCRIPTS_DIR)
VENDOR_DIR = os.path.join(EXTRACTOR_DIR, "vendor", "canary")

ITEMS_XML_NAME = "items.xml"
NPC_FACTS_NAME = "npc-lua-facts.json"
MANIFEST_NAME = "MANIFEST.json"


def vendored_items_xml() -> str:
    return os.path.join(VENDOR_DIR, ITEMS_XML_NAME)


def vendored_npc_facts() -> str:
    return os.path.join(VENDOR_DIR, NPC_FACTS_NAME)


def read_items_xml(canary_dir=None) -> str:
    """O `items.xml` inteiro, do vendor ou do checkout. Arquivo ausente vira
    string vazia: quem chama perde a regra que ia tirar dali e não inventa
    nenhuma, no mesmo espírito de `read_floor_change_rules`."""
    path = (
        os.path.join(canary_dir, "data", "items", ITEMS_XML_NAME)
        if canary_dir
        else vendored_items_xml()
    )
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as items_file:
            return items_file.read()
    except OSError:
        print(f"[WARN] {path} não encontrado")
        return ""


def read_floor_change_rules(canary_dir=None):
    """`items.xml` -> `({id: direção do floorchange}, {ids de escada de mão})`.

    As duas metades da geometria de andar saem do mesmo arquivo e da mesma
    leitura, então saem juntas: quem calcula aresta precisa das duas ou de
    nenhuma. Lê o `items.xml` vendorizado por padrão; `--canary-dir` lê do
    checkout, que é como um vendor velho é pego.

    Arquivo ausente é **aviso, não falha**: sem ele o grafo perde ligação e
    não inventa nenhuma. Quebrar aqui faria um caminho do Canary derrubar
    toda exportação."""
    path = (
        os.path.join(canary_dir, "data", "items", ITEMS_XML_NAME)
        if canary_dir
        else vendored_items_xml()
    )

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as items_file:
            items_xml = items_file.read()
    except OSError:
        print(f"[WARN] {path} não encontrado — escada/rampa vão depender só da "
              f"heurística de flags, e caverna entrada por rampa pode sair como ilhada")
        return {}, set()

    directions = parse_floorchange_items(items_xml)
    ladders = parse_ladder_items(items_xml)
    print(f"[OK] {len(directions)} ids com floorchange e {len(ladders)} escadas "
          f"de mão lidos de {path}")
    return directions, ladders


def extract_npc_facts(canary_npc_dir: str) -> dict:
    """{nome do .lua: {"shop": ..., "outfit": ..., "services": [...]}} para
    **todo** arquivo.

    Todo arquivo, inclusive os sem nenhuma das três coisas: quem consome
    distingue "nenhum .lua casou com esse NPC" (avisa) de "casou, mas não tem
    shop" (silencioso). Omitir os vazios colapsaria os dois casos num só e
    produziria warning falso. `services` sai lista vazia pelo mesmo motivo, em
    vez de ausente.

    `services` é o que deixa o filtro de NPC existir sem lista de nome escrita à
    mão: `shop` responde "vende?", e ele responde "faz alguma outra coisa?" —
    viagem, banco, bênção, promoção ou magia. Ver `parse_npc_services_lua`.
    """
    facts = {}
    for path in sorted(glob.glob(os.path.join(canary_npc_dir, "*.lua"))):
        with open(path, "r", encoding="utf-8", errors="replace") as handler:
            text = handler.read()
        facts[os.path.basename(path)] = {
            "shop": parse_npc_shop_lua(text),
            "outfit": parse_npc_outfit_lua(text),
            "services": parse_npc_services_lua(text),
        }
    return facts


def _canary_commit(canary_dir: str) -> dict:
    """Sem o commit de origem o vendor é um monte de bytes sem procedência."""
    def git(*args):
        try:
            out = subprocess.run(
                ["git", "-C", canary_dir, *args],
                capture_output=True, text=True, check=True,
            )
            return out.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None

    return {
        "commit": git("rev-parse", "HEAD"),
        "describe": git("describe", "--tags", "--always"),
        "committedAt": git("log", "-1", "--format=%cs"),
        "origin": git("remote", "get-url", "origin"),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--canary-dir",
        default=None,
        help=f"checkout do Canary (default: ${paths.CANARY.env_var} ou {paths.CANARY.sibling_default()})",
    )
    args = parser.parse_args()

    try:
        canary_dir = paths.CANARY.require(args.canary_dir)
    except paths.MissingRepoError as exc:
        parser.error(str(exc))

    items_src = os.path.join(canary_dir, "data", "items", ITEMS_XML_NAME)
    if not os.path.exists(items_src):
        parser.error(f"{ITEMS_XML_NAME} não encontrado em {items_src}")

    npc_dir = os.path.join(canary_dir, "data-otservbr-global", "npc")
    if not os.path.isdir(npc_dir):
        parser.error(f"pasta de NPCs não encontrada em {npc_dir}")

    os.makedirs(VENDOR_DIR, exist_ok=True)

    shutil.copyfile(items_src, vendored_items_xml())
    print(f"[OK] {ITEMS_XML_NAME} -> {vendored_items_xml()}")

    facts = extract_npc_facts(npc_dir)
    with open(vendored_npc_facts(), "w", encoding="utf-8") as handler:
        # Sem sort_keys: as chaves de topo já saem ordenadas do sorted(glob),
        # e ordenar as internas reordenaria as linhas de shop e do outfit,
        # mudando o JSON do fragmento sem mudar o conteúdo.
        json.dump(facts, handler, indent=2, ensure_ascii=False)
        handler.write("\n")
    with_shop = sum(1 for entry in facts.values() if entry["shop"] is not None)
    with_outfit = sum(1 for entry in facts.values() if entry["outfit"] is not None)
    by_service = collections.Counter(
        service for entry in facts.values() for service in entry["services"]
    )
    services = ", ".join(f"{count} {name}" for name, count in sorted(by_service.items()))
    print(f"[OK] {len(facts)} NPCs ({with_shop} com shop, {with_outfit} com outfit) -> {vendored_npc_facts()}")
    print(f"[OK] serviços de motor: {services}")

    manifest = {
        "source": "opentibiabr/canary",
        "canary": _canary_commit(canary_dir),
        "generatedAt": datetime.date.today().isoformat(),
        "command": "uv run python extractor/scripts/update_canary_data.py",
        "files": {
            ITEMS_XML_NAME: "cópia crua de data/items/items.xml",
            NPC_FACTS_NAME: "tabelas shop e outfit de data-otservbr-global/npc/*.lua",
        },
    }
    with open(os.path.join(VENDOR_DIR, MANIFEST_NAME), "w", encoding="utf-8") as handler:
        json.dump(manifest, handler, indent=2, ensure_ascii=False)
        handler.write("\n")
    print(f"[OK] manifesto (canary {manifest['canary']['describe']}) -> {os.path.join(VENDOR_DIR, MANIFEST_NAME)}")


if __name__ == "__main__":
    main()
