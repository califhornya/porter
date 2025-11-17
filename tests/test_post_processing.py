import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from porter.cli import clean_filename
from porter.models import CardData, PowerCostItem
from porter.post_process import detect_signature_spell, post_process_card_data


def test_post_process_card_data_normalizes_terms_and_effects():
    raw = {
        "name": "Test Card",
        "type": "UNIT",
        "domain": "FURY",
        "cost": {"energy": "3", "power": [{"domain": "body", "amount": 2}]},
        "stats": {"might": 2, "damage": 1, "armor": 0},
        "keywords": ["gear", "Legend", "legend"],
        "tags": ["equipment", "Unit", "EQUIPMENT"],
        "rules_text": "  Score 1 point.\r\n Gain strength.  ",
        "effects": [
            {"effect": "score_point", "params": {"amount": 1}},
            {"effect": "draw_card", "params": {}},
        ],
        "flavor": None,
        "artist": None,
        "card_id": "TEST-001",
    }

    processed = post_process_card_data(raw)
    card = CardData.model_validate(processed)

    assert card.schema_version == 1
    assert card.cost.energy == 3
    assert card.cost.power == [PowerCostItem(domain="BODY", amount=2)]
    assert card.keywords == ["GEAR", "LEGEND"]
    assert card.tags == ["EQUIPMENT", "UNIT"]
    assert card.effects[0].effect == "score_vp"
    assert card.effects[1].effect == "draw_cards"
    assert card.rules_text == "Score 1 point.\nGain strength."


def test_post_process_card_data_two_domains_domain_none():
    raw = {
        "name": "Dual Domain Card",
        "type": "UNIT",
        "domain": "Fury",
        "domains": ["Body"],
        "cost": {"energy": 4, "power": []},
        "stats": {"might": 3, "damage": None, "armor": None},
        "keywords": [],
        "tags": [],
        "rules_text": "",
        "effects": [],
        "flavor": None,
        "artist": None,
        "card_id": "TEST-002",
    }

    processed = post_process_card_data(raw)
    card = CardData.model_validate(processed)

    assert card.domain is None
    assert sorted(card.domains) == ["BODY", "FURY"]


def test_detect_signature_spell_reads_tags_and_text():
    raw = {
        "name": "Signature Spell",
        "type": "SPELL",
        "domain": None,
        "domains": [],
        "cost": {"energy": 1, "power": []},
        "stats": {"might": None, "damage": None, "armor": None},
        "keywords": [],
        "tags": ["Signature", "Jinx"],
        "rules_text": "Signature Spell · JINX",
        "effects": [],
        "flavor": None,
        "artist": None,
        "card_id": "TEST-003",
    }

    assert detect_signature_spell(raw) == "Jinx"


def test_legend_allows_missing_energy_cost():
    raw = {
        "name": "Storm Peak",
        "type": "LEGEND",
        "domain": None,
        "domains": [],
        "cost": {"power": []},
        "stats": {"might": None, "damage": None, "armor": None},
        "keywords": [],
        "tags": ["Volibear"],
        "rules_text": "A place of power.",
        "effects": [],
        "flavor": None,
        "artist": None,
        "card_id": "TEST-LEGEND",
    }

    processed = post_process_card_data(raw)
    card = CardData.model_validate(processed)

    assert card.cost.energy is None


def test_clean_filename_sanitizes_and_collapses_whitespace():
    assert clean_filename("Jinx!  Wild   Ride?") == "Jinx_Wild_Ride"
