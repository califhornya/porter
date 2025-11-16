import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.append(str(Path(__file__).resolve().parents[1]))

import porter.client as client_module


class FakeChatMessage(SimpleNamespace):
    pass


class FakeChoice(SimpleNamespace):
    pass


class FakeChatResponse(SimpleNamespace):
    pass


class FallbackClient:
    def __init__(self, response_text: str):
        self.responses = SimpleNamespace(create=self._raise_type_error)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._chat_create))
        self._response_text = response_text

    def _raise_type_error(self, **_):
        raise TypeError("Unexpected keyword argument 'response_format'")

    def _chat_create(self, **_):
        message = FakeChatMessage(content=self._response_text)
        choice = FakeChoice(message=message)
        return FakeChatResponse(choices=[choice])


class FallbackClientWithListContent(FallbackClient):
    def _chat_create(self, **_):
        message = FakeChatMessage(content=[{"type": "text", "text": self._response_text}])
        choice = FakeChoice(message=message)
        return FakeChatResponse(choices=[choice])


def test_attempt_repair_json_falls_back_to_chat_completion():
    client = FallbackClient(json.dumps({"repaired": True}))

    result = client_module.attempt_repair_json(client, "{}", model="dummy")

    assert result == {"repaired": True}


def test_extract_card_json_falls_back_to_chat_completion(monkeypatch, tmp_path: Path):
    client = FallbackClientWithListContent(json.dumps({"name": "Card"}))

    dummy_image = tmp_path / "card.png"
    dummy_image.write_text("irrelevant")

    monkeypatch.setattr(client_module, "image_to_data_url", lambda _: "data:image/jpeg;base64,abc==")

    result = client_module.extract_card_json(
        client,
        image_path=dummy_image,
        model="dummy",
    )

    assert result == {"name": "Card"}
