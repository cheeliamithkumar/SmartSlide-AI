"""AI provider abstraction: JSON validation, grounding, HTTP providers and fallback."""
import json

import httpx
import pytest

from app.schemas import ChunkAnalysis, Slide, SlideType
from app.services.ai.base import AIProviderError, extract_json, ground_analysis, parse_model
from app.services.ai.claude_provider import ClaudeProvider
from app.services.ai.factory import ResilientProvider, get_provider
from app.services.ai.gemini_provider import GeminiProvider
from app.services.ai.mock_provider import MockProvider

CHUNK = """[Page 4]
## Enzymes
An enzyme is a biological catalyst that speeds up chemical reactions. Enzymes are proteins.
For example, amylase breaks down starch into sugars.

[Page 5]
Temperature affects enzyme activity. Very high temperatures denature enzymes."""

VALID = {
    "topics": [{
        "title": "Enzymes", "summary": "Enzymes speed up reactions.", "importance": 5, "pages": [4],
        "key_points": [{"text": "Enzymes are biological catalysts", "pages": [4]},
                       {"text": "Temperature affects activity", "pages": [5, 99]}],
        "simplified_points": ["Enzymes speed up reactions"],
        "definitions": [{"term": "Enzyme", "definition": "a biological catalyst", "pages": [4]},
                        {"term": "Quantum flux capacitor", "definition": "invented", "pages": [4]}],
        "examples": [{"text": "amylase breaks down starch", "pages": [42]}],
        "process_steps": [], "comparisons": [],
    }]
}


def test_extract_json_handles_fences_and_prose():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Sure! Here it is: {"a": [1, 2,]} hope it helps') == {"a": [1, 2]}
    with pytest.raises(AIProviderError):
        extract_json("no json here")


def test_parse_model_rejects_schema_violations():
    with pytest.raises(AIProviderError):
        parse_model('{"topics": [{"title": ""}]}', ChunkAnalysis)
    ok = parse_model(json.dumps(VALID), ChunkAnalysis)
    assert ok.topics[0].title == "Enzymes"


def test_importance_is_clamped():
    data = {"topics": [{"title": "X", "importance": 11, "summary": "s"}]}
    assert parse_model(json.dumps(data), ChunkAnalysis).topics[0].importance == 5


def test_grounding_removes_hallucinations():
    analysis = parse_model(json.dumps(VALID), ChunkAnalysis)
    grounded = ground_analysis(analysis, CHUNK, [4, 5])
    topic = grounded.topics[0]
    assert [d.term for d in topic.definitions] == ["Enzyme"]  # invented term removed
    assert topic.key_points[1].pages == [5]  # out-of-range page dropped
    assert topic.examples[0].pages == [4]  # invalid page replaced by topic pages


def _transport(responses):
    calls = {"n": 0, "requests": []}

    def handler(request: httpx.Request):
        calls["requests"].append(request)
        resp = responses[min(calls["n"], len(responses) - 1)]
        calls["n"] += 1
        return resp

    return httpx.MockTransport(handler), calls


def _claude_resp(text):
    return httpx.Response(200, json={"content": [{"type": "text", "text": text}], "stop_reason": "end_turn"})


def test_claude_provider_parses_and_grounds():
    transport, calls = _transport([_claude_resp(json.dumps(VALID))])
    p = ClaudeProvider("test-key", "claude-test", client=httpx.Client(transport=transport), max_retries=0)
    result = p.analyze_chunk(CHUNK, [4, 5], {"doc_name": "bio.pdf"})
    assert result.topics[0].definitions[0].term == "Enzyme"
    req = calls["requests"][0]
    assert req.headers["x-api-key"] == "test-key"
    body = json.loads(req.content)
    assert body["model"] == "claude-test"
    assert "SOURCE TEXT" in body["messages"][0]["content"]


def test_claude_provider_retries_on_invalid_json():
    transport, calls = _transport([_claude_resp("oops not json"), _claude_resp(json.dumps(VALID))])
    p = ClaudeProvider("k", "m", client=httpx.Client(transport=transport), max_retries=0)
    assert p.analyze_chunk(CHUNK, [4, 5], {}).topics
    assert calls["n"] == 2


def test_claude_provider_auth_error():
    transport, _ = _transport([httpx.Response(401, json={"error": "bad key"})])
    p = ClaudeProvider("k", "m", client=httpx.Client(transport=transport), max_retries=0)
    with pytest.raises(AIProviderError, match="rejected the API key"):
        p.analyze_chunk(CHUNK, [4, 5], {})


def test_gemini_provider_parses():
    resp = httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": json.dumps(VALID)}]}}]})
    transport, calls = _transport([resp])
    p = GeminiProvider("g-key", "gemini-test", client=httpx.Client(transport=transport), max_retries=0)
    assert p.analyze_chunk(CHUNK, [4, 5], {}).topics[0].title == "Enzymes"
    assert calls["requests"][0].headers["x-goog-api-key"] == "g-key"
    assert "gemini-test:generateContent" in str(calls["requests"][0].url)


def test_missing_key_falls_back_to_offline_mode(monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "ai_provider", "claude")
    provider = get_provider()
    assert provider.primary is None
    assert any("API key" in w for w in provider.warnings)
    assert provider.analyze_chunk(CHUNK, [4, 5], {}).topics


def test_resilient_provider_falls_back_on_error():
    class Broken(MockProvider):
        name = "broken"

        def analyze_chunk(self, *a):
            raise AIProviderError("HTTP 503")

    rp = ResilientProvider(Broken(), MockProvider())
    result = rp.analyze_chunk(CHUNK, [4, 5], {})
    assert result.topics
    assert rp.fallback_used and rp.label == "broken+fallback"
    assert rp.warnings


def test_mock_provider_extracts_structure():
    analysis = MockProvider().analyze_chunk(CHUNK, [4, 5], {})
    topic = analysis.topics[0]
    assert topic.title == "Enzymes"
    assert any(d.term == "Enzyme" for d in topic.definitions)
    assert topic.examples and "amylase" in topic.examples[0].text
    assert set(topic.pages) == {4, 5}


def test_mock_regenerate_keeps_identity():
    slide = Slide(type=SlideType.content, title="Enzymes", bullets=["old"], source_pages=[4])
    new = MockProvider().regenerate_slide(slide, CHUNK, {"kind": "summary", "variant": 2})
    assert new.id == slide.id and new.bullets and new.bullets != ["old"]
