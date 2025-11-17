from pathlib import Path

from PIL import Image

from porter.image_utils import infer_domains_from_image
from porter.post_process import post_process_card_data


def _make_mock_card(path: Path, color: tuple[int, int, int]) -> Path:
    img = Image.new("RGB", (400, 600), (10, 10, 10))
    left = int(img.width * 0.65)
    top = int(img.height * 0.02)
    right = int(img.width * 0.95)
    bottom = int(img.height * 0.18)
    for x in range(left, right):
        for y in range(top, bottom):
            img.putpixel((x, y), color)
    img.save(path)
    return path


def test_infer_domains_from_image_detects_primary_hue(tmp_path):
    image_path = _make_mock_card(tmp_path / "fury.png", (200, 40, 40))
    sample = infer_domains_from_image(image_path)

    assert sample.domains[0] == "FURY"
    assert sample.confidence > 0.6


def test_color_hint_overrides_llm_domain_when_confident(tmp_path):
    image_path = _make_mock_card(tmp_path / "orange.png", (230, 140, 50))
    raw = {
        "name": "Test Spell",
        "type": "SPELL",
        "domain": "CHAOS",
        "domains": ["CHAOS"],
        "cost": {"energy": 2, "power": [{"domain": "CHAOS", "amount": 1}]},
        "stats": {"might": None, "damage": None, "armor": None},
        "keywords": [],
        "tags": [],
        "rules_text": "Do a thing.",
        "effects": [],
        "flavor": None,
        "artist": None,
        "card_id": "TEST-COLOR",
    }

    processed = post_process_card_data(raw, image_path=image_path)

    assert processed["domains"] == ["BODY"]
    assert processed["domain"] == "BODY"
    assert processed["cost"]["power"] == [{"domain": "BODY", "amount": 1}]
