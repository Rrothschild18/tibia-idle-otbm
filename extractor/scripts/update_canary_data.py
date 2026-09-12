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
import datetime
import glob
import json
import os
import shutil
import subprocess

import paths
from travel_graph import parse_npc_outfit_lua, parse_npc_shop_lua

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


def extract_npc_facts(canary_npc_dir: str) -> dict:
    """{nome do .lua: {"shop": ..., "outfit": ...}} para **todo** arquivo.

    Todo arquivo, inclusive os sem nenhuma das duas tabelas: quem consome
    distingue "nenhum .lua casou com esse NPC" (avisa) de "casou, mas não tem
    shop" (silencioso). Omitir os vazios colapsaria os dois casos num só e
    produziria warning falso.
    """
    facts = {}
    for path in sorted(glob.glob(os.path.join(canary_npc_dir, "*.lua"))):
        with open(path, "r", encoding="utf-8", errors="replace") as handler:
            text = handler.read()
        facts[os.path.basename(path)] = {
            "shop": parse_npc_shop_lua(text),
            "outfit": parse_npc_outfit_lua(text),
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
    print(f"[OK] {len(facts)} NPCs ({with_shop} com shop, {with_outfit} com outfit) -> {vendored_npc_facts()}")

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
