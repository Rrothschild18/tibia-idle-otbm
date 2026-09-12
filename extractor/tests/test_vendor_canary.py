import json
import os
import sys

import pytest

SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import build_travel_fragment as btf
import update_canary_data as ucd


def test_vendored_files_exist():
    """O ponto do vendor é um clone sem Canary conseguir montar o grafo."""
    assert os.path.exists(ucd.vendored_items_xml())
    assert os.path.exists(ucd.vendored_npc_facts())
    assert os.path.exists(os.path.join(ucd.VENDOR_DIR, ucd.MANIFEST_NAME))


def test_manifest_records_the_canary_commit():
    """Vendor sem procedência é um monte de bytes que ninguém sabe atualizar."""
    with open(os.path.join(ucd.VENDOR_DIR, ucd.MANIFEST_NAME), encoding="utf-8") as handler:
        manifest = json.load(handler)

    assert manifest["canary"]["commit"]
    assert len(manifest["canary"]["commit"]) == 40
    assert manifest["canary"]["origin"].endswith("canary.git")
    assert manifest["generatedAt"]
    assert "update_canary_data" in manifest["command"]


def test_extract_keeps_files_that_have_neither_shop_nor_outfit(tmp_path):
    """A distinção que o consumidor precisa: "nenhum .lua casou" (avisa) versus
    "casou, mas não tem shop" (silencioso). Omitir os vazios colapsaria os dois
    num só e geraria warning falso."""
    (tmp_path / "quest-npc.lua").write_text("local npcConfig = {}\nreturn npcConfig\n")
    (tmp_path / "shopkeeper.lua").write_text(
        "npcConfig.shop = {\n  { itemName = 'bread', clientId = 3600, buy = 3 },\n}\n"
    )

    facts = ucd.extract_npc_facts(str(tmp_path))

    assert set(facts) == {"quest-npc.lua", "shopkeeper.lua"}
    assert facts["quest-npc.lua"] == {"shop": None, "outfit": None}
    assert facts["shopkeeper.lua"]["shop"] is not None


def test_npc_without_matching_lua_is_absent_so_the_cli_can_warn(tmp_path, monkeypatch):
    source = {"bread-seller.lua": {"shop": [{"itemName": "bread"}], "outfit": None}}
    monkeypatch.setattr(btf, "_load_npc_lua_facts_source", lambda canary_dir=None: (source, "fake"))

    facts, _ = btf._build_npc_lua_facts({"Nobody At All"}, None)

    assert facts == {}


def test_npc_matched_with_no_shop_is_present_with_none(monkeypatch):
    source = {"trainer.lua": {"shop": None, "outfit": {"lookType": 128}}}
    monkeypatch.setattr(btf, "_load_npc_lua_facts_source", lambda canary_dir=None: (source, "fake"))

    facts, _ = btf._build_npc_lua_facts({"Trainer"}, None)

    assert facts == {"Trainer": (None, {"lookType": 128})}


def test_missing_vendor_warns_instead_of_crashing(monkeypatch, capsys, tmp_path):
    """Um vendor ausente não pode virar traceback no meio do pipeline."""
    monkeypatch.setattr(ucd, "vendored_npc_facts", lambda: str(tmp_path / "nao-existe.json"))

    source, origin = btf._load_npc_lua_facts_source(None)

    assert source == {}
    assert "update_canary_data" in capsys.readouterr().out


def test_vendored_items_xml_carries_the_floorchange_ids():
    """997 ids é o número que o golden foi gerado com — se o vendor perdesse
    o items.xml, o grafo cairia calado para a heurística de flags."""
    directions = btf._read_floorchange_items(None)

    assert len(directions) == 997
