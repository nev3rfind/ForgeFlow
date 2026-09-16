import pytest
from unittest.mock import patch, MagicMock
from pydantic import BaseModel

import google.antigravity as ag
from app.integrations.antigravity_adapter import AntigravityProvider, AntigravityProviderError


class DummySchema(BaseModel):
    answer: str
    confidence: float


class FakeResponse:
    def __init__(self, structured=None, text_value="", chunks=None):
        self._structured = structured
        self._text_value = text_value
        self._chunks = chunks or []

    async def structured_output(self):
        return self._structured

    async def text(self):
        return self._text_value

    @property
    async def _chunks_gen(self):
        for c in self._chunks:
            yield c

    @property
    def chunks(self):
        chunks = self._chunks

        async def _gen():
            for c in chunks:
                yield c

        return _gen()


class FakeAgent:
    last_config = None

    def __init__(self, config):
        FakeAgent.last_config = config
        self._response = None

    def set_response(self, response):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def chat(self, prompt):
        return self._response


def make_fake_agent_factory(response):
    def factory(config):
        agent = FakeAgent(config)
        agent.set_response(response)
        return agent

    return factory


@pytest.mark.asyncio
async def test_chat_returns_validated_structured_output():
    provider = AntigravityProvider(api_key="test-key")
    response = FakeResponse(structured={"answer": "42", "confidence": 0.9})

    with patch.object(ag, "Agent", side_effect=make_fake_agent_factory(response)):
        result = await provider.chat("prompt", DummySchema, "system", [])

    assert isinstance(result, DummySchema)
    assert result.answer == "42"
    assert result.confidence == 0.9


@pytest.mark.asyncio
async def test_build_config_includes_finish_tool_instruction():
    provider = AntigravityProvider()
    config = provider._build_config(DummySchema, "Base system instruction.", [])

    assert "finish" in config.system_instructions.lower()
    assert "Base system instruction." in config.system_instructions
    assert "must" in config.system_instructions.lower()
    assert "DummySchema" in config.response_schema
    assert "answer" in config.response_schema


@pytest.mark.asyncio
async def test_chat_falls_back_to_json_parsing_when_structured_output_is_none():
    provider = AntigravityProvider()
    response = FakeResponse(
        structured=None,
        text_value='Here is my result:\n```json\n{"answer": "fallback", "confidence": 0.5}\n```',
    )

    with patch.object(ag, "Agent", side_effect=make_fake_agent_factory(response)):
        result = await provider.chat("prompt", DummySchema, "system", [])

    assert isinstance(result, DummySchema)
    assert result.answer == "fallback"
    assert result.confidence == 0.5


@pytest.mark.asyncio
async def test_chat_raises_clear_error_when_no_structured_output_and_invalid_text():
    provider = AntigravityProvider()
    response = FakeResponse(structured=None, text_value="I am done, but not in JSON.")

    with patch.object(ag, "Agent", side_effect=make_fake_agent_factory(response)):
        with pytest.raises(AntigravityProviderError) as exc:
            await provider.chat("prompt", DummySchema, "system", [])

    assert "did not invoke the finish tool" in str(exc.value)


@pytest.mark.asyncio
async def test_stream_chat_yields_structured_output_from_fallback_text():
    provider = AntigravityProvider()
    text_chunk = ag.types.Text(text="Result: ", step_index=0)
    text_chunk2 = ag.types.Text(text='{"answer": "streamed", "confidence": 0.7}', step_index=0)
    response = FakeResponse(structured=None, chunks=[text_chunk, text_chunk2])

    with patch.object(ag, "Agent", side_effect=make_fake_agent_factory(response)):
        events = []
        async for event in provider.stream_chat("prompt", DummySchema, "system", []):
            events.append(event)

    structured_events = [e for e in events if e["type"] == "structured_output"]
    assert len(structured_events) == 1
    assert structured_events[0]["data"]["answer"] == "streamed"
