import asyncio
from types import SimpleNamespace

import pytest

from services.llm.extraction import ExtractionError, extract_spec


class FakeCompletions:
    def __init__(self, contents: list[str]):
        self.contents = list(contents)
        self.calls = 0

    async def create(self, **kwargs):
        self.calls += 1
        content = self.contents.pop(0)
        message = SimpleNamespace(content=content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class FakeClient:
    def __init__(self, contents: list[str]):
        self.completions = FakeCompletions(contents)
        self.chat = SimpleNamespace(completions=self.completions)


def test_valid_json_is_parsed():
    client = FakeClient(['{"application": {"app_type": "web_app"}}'])
    spec = asyncio.run(extract_spec("texte", client=client))
    assert spec.application.app_type is not None
    assert client.completions.calls == 1


def test_invalid_value_triggers_one_retry():
    client = FakeClient(
        [
            '{"application": {"app_type": "n_importe_quoi"}}',
            '{"application": {"app_type": "web_app"}}',
        ]
    )
    spec = asyncio.run(extract_spec("texte", client=client))
    assert spec.application.app_type is not None
    assert client.completions.calls == 2


def test_two_invalid_answers_raise():
    client = FakeClient(["pas du json", "toujours pas du json"])
    with pytest.raises(ExtractionError):
        asyncio.run(extract_spec("texte", client=client))
    assert client.completions.calls == 2


def test_unknown_list_is_always_reset():
    client = FakeClient(['{"unknown": ["traffic.daily_users"]}'])
    spec = asyncio.run(extract_spec("texte", client=client))
    assert spec.unknown == []