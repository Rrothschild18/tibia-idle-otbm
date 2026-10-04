import collections
import json
import os
import sys

import pytest

SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import build_travel_fragment as btf
import travel_graph as tg
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
    assert facts["quest-npc.lua"] == {"shop": None, "outfit": None, "services": []}
    assert facts["shopkeeper.lua"]["shop"] is not None


def test_npc_without_matching_lua_is_absent_so_the_cli_can_warn(tmp_path, monkeypatch):
    source = {"bread-seller.lua": {"shop": [{"itemName": "bread"}], "outfit": None, "services": []}}
    monkeypatch.setattr(btf, "_load_npc_lua_facts_source", lambda canary_dir=None: (source, "fake"))

    facts, _ = btf._build_npc_lua_facts({"Nobody At All"}, None)

    assert facts == {}


def test_npc_matched_with_no_shop_is_present_with_none(monkeypatch):
    source = {"trainer.lua": {"shop": None, "outfit": {"lookType": 128}, "services": []}}
    monkeypatch.setattr(btf, "_load_npc_lua_facts_source", lambda canary_dir=None: (source, "fake"))

    facts, _ = btf._build_npc_lua_facts({"Trainer"}, None)

    assert facts == {"Trainer": {"shop": None, "outfit": {"lookType": 128}, "services": []}}


def test_missing_vendor_warns_instead_of_crashing(monkeypatch, capsys, tmp_path):
    """Um vendor ausente não pode virar traceback no meio do pipeline."""
    monkeypatch.setattr(ucd, "vendored_npc_facts", lambda: str(tmp_path / "nao-existe.json"))

    source, origin = btf._load_npc_lua_facts_source(None)

    assert source == {}
    assert "update_canary_data" in capsys.readouterr().out


def test_vendored_items_xml_carries_the_floorchange_ids():
    """434 ids: se o vendor perdesse o items.xml, o grafo cairia calado para a
    heurística de flags.

    Eram 997 enquanto `_iter_declared_items` lia sempre até o próximo
    `</item>` — 804 deles eram do item errado e 241 dos certos ficavam de fora.
    Não é o vendor que encolheu."""
    directions, _ = ucd.read_floor_change_rules(None)

    assert len(directions) == 434
    assert directions[7542] == "east"
    assert 7541 not in directions


def test_vendored_items_xml_carries_the_ladder_ids():
    """1948 e 5542 são 100% das transições dos mapas de hunt: sem elas a rota
    de andar múltiplo não tem por onde subir."""
    _, ladders = ucd.read_floor_change_rules(None)

    assert {1948, 5542} <= ladders


# ======================================================
# services: o fato que deixa o filtro de NPC existir
# ======================================================


SERVICE_CASES = [
    ("travel", "    keywordHandler:addKeyword({'carlin'}, StdModule.travel, {})\n"),
    ("bank", "    if npc:parseBank(message, npc, creature, npcHandler) then\n"),
    ("bless", "    keywordHandler:addKeyword({'bless'}, StdModule.bless, { bless = 1 })\n"),
    ("promote", "    keywordHandler:addKeyword({'promot'}, StdModule.promotePlayer, {})\n"),
    ("spell", "    keywordHandler:addKeyword({'light'}, StdModule.learnSpell, {})\n"),
]


@pytest.mark.parametrize("service,line", SERVICE_CASES)
def test_each_engine_signature_is_detected(service, line):
    assert tg.parse_npc_services_lua(line) == [service]


def test_no_service_is_an_empty_list_not_none():
    """Lista vazia e não None: "não presta serviço" e "não foi olhado" precisam
    ser distinguíveis, a mesma razão pela qual o extrato guarda arquivo sem
    shop nem outfit."""
    assert tg.parse_npc_services_lua("local npcConfig = {}\nreturn npcConfig\n") == []


def test_parse_bank_messages_alone_is_not_a_bank():
    """`parseBankMessages` é outra função, chamada pelos mesmos NPCs. Sem o `(`
    na assinatura, um grep por `parseBank` casaria com as duas e todo NPC que só
    imprime as mensagens do banco entraria como banqueiro."""
    assert tg.parse_npc_services_lua("    npc:parseBankMessages(message, npc, creature)\n") == []


def test_talking_about_travel_without_the_engine_call_is_not_travel():
    """O caso Captain Tiberius: o `.lua` dele diz "I transport my passengers back
    to the continent." e não tem keyword nenhum nem teleportTo. Qualquer
    heurística por nome ou por texto de diálogo o aceitaria como barqueiro."""
    lua = (
        "npcConfig.name = 'Captain Tiberius'\n"
        "keywordHandler:addKeyword({'passengers'}, StdModule.say,\n"
        "  { text = 'I transport my passengers back to the continent.' })\n"
    )

    assert tg.parse_npc_services_lua(lua) == []


def test_an_npc_can_hold_more_than_one_service():
    """Lokur é banco **e** vende o passe de vagonete; Brodrosch e Gewen são
    travel e vendem o mesmo passe. Acumular cargo é comum e o fato tem que
    carregar os dois."""
    lua = (
        "    if npc:parseBank(message, npc, creature, npcHandler) then\n"
        "    keywordHandler:addKeyword({'farmine'}, StdModule.travel, {})\n"
    )

    assert tg.parse_npc_services_lua(lua) == ["travel", "bank"]


def test_vendored_extract_carries_the_service_counts_the_engine_declares():
    """As cinco assinaturas contadas sobre os 1035 `.lua`. Se o vendor for
    regenerado de um Canary onde o motor mudou de nome, é aqui que aparece —
    silenciosamente, o filtro de NPC passaria a cortar barqueiro e banco."""
    with open(ucd.vendored_npc_facts(), encoding="utf-8") as handler:
        facts = json.load(handler)

    counts = collections.Counter(
        service for entry in facts.values() for service in entry["services"]
    )

    assert counts == {"travel": 73, "bank": 25, "bless": 27, "promote": 6, "spell": 51}


def test_a_vendor_from_before_services_raises_instead_of_cutting_the_map(monkeypatch, tmp_path):
    """Um extrato velho viraria `services: []` por omissão, e o filtro cortaria
    todo barqueiro, banco, bênção e promoção sem uma linha de erro."""
    stale = tmp_path / "npc-lua-facts.json"
    stale.write_text(json.dumps({"obi.lua": {"shop": None, "outfit": None}}), encoding="utf-8")
    monkeypatch.setattr(ucd, "vendored_npc_facts", lambda: str(stale))

    with pytest.raises(btf.StaleNpcFactsError, match="update_canary_data"):
        btf._load_npc_lua_facts_source(None)
