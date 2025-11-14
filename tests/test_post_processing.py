from extract_riftbound_card import CardData, post_process_card_data


def test_post_process_card_data_normalizes_terms_and_effects():
    raw = {
        "name": "Test Card",
        "type": "UNIT",
        "domain": "FURY",
        "cost": {"energy": 3, "power": None},
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
    assert card.keywords == ["GEAR", "LEGEND"]
    assert card.tags == ["EQUIPMENT", "UNIT"]
    assert card.effects[0].effect == "score_vp"
    assert card.effects[1].effect == "draw_cards"
    assert card.rules_text == "Score 1 point.\nGain strength."