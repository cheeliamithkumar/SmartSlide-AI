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


def test_gemini_skips_thought_parts():
    body = {"candidates": [{"content": {"parts": [{"text": "thinking...", "thought": True},
                                                  {"text": json.dumps(VALID)}]}}]}
    transport, calls = _transport([httpx.Response(200, json=body)])
    p = GeminiProvider("k", "gemini-x", client=httpx.Client(transport=transport), max_retries=0)
    assert p.analyze_chunk(CHUNK, [4, 5], {}).topics
    sent = json.loads(calls["requests"][0].content)
    assert sent["generationConfig"]["maxOutputTokens"] >= 16384


def test_gemini_discovers_model_when_configured_one_is_retired():
    from app.services.ai import gemini_provider as gp

    gp.GeminiProvider._resolved_model = None
    models = {"models": [
        {"name": "models/gemini-2.0-flash", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-3.1-flash", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-3.1-flash-lite", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-9-flash-preview", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/text-embedding-004", "supportedGenerationMethods": ["embedContent"]},
    ]}
    ok = {"candidates": [{"content": {"parts": [{"text": json.dumps(VALID)}]}}]}

    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json=models)
        if "old-model" in str(request.url):
            return httpx.Response(404, json={"error": "not found"})
        return httpx.Response(200, json=ok)

    p = gp.GeminiProvider("k", "old-model", client=httpx.Client(transport=httpx.MockTransport(handler)), max_retries=0)
    assert p.analyze_chunk(CHUNK, [4, 5], {}).topics
    assert gp.GeminiProvider._resolved_model == "gemini-3.1-flash"
    gp.GeminiProvider._resolved_model = None


def test_gemini_fails_over_when_model_overloaded():
    from app.services.ai import gemini_provider as gp

    gp.GeminiProvider._resolved_model = None
    models = {"models": [
        {"name": "models/busy-flash", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-2.0-flash", "supportedGenerationMethods": ["generateContent"]},
    ]}
    ok = {"candidates": [{"content": {"parts": [{"text": json.dumps(VALID)}]}}]}

    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json=models)
        if "busy-flash" in str(request.url):
            return httpx.Response(503, json={"error": {"message": "The model is overloaded."}})
        return httpx.Response(200, json=ok)

    p = gp.GeminiProvider("k", "busy-flash", client=httpx.Client(transport=httpx.MockTransport(handler)), max_retries=0)
    assert p.analyze_chunk(CHUNK, [4, 5], {}).topics
    assert gp.GeminiProvider._resolved_model == "gemini-2.0-flash"
    gp.GeminiProvider._resolved_model = None


def test_time_budget_switches_to_offline_engine():
    import time as _t

    class Slow(MockProvider):
        name = "slow"

        def analyze_chunk(self, *a):
            raise AssertionError("primary must not be called after the deadline")

    rp = ResilientProvider(Slow(), MockProvider(), time_budget=0.01)
    _t.sleep(0.02)
    assert rp.analyze_chunk(CHUNK, [4, 5], {}).topics
    assert rp.fallback_used and any("too slow" in w for w in rp.warnings)


def test_quota_exhausted_is_not_retried():
    transport, calls = _transport([httpx.Response(429, json={"error": {"message": "You exceeded your current quota"}})])
    p = GeminiProvider("k", "m", client=httpx.Client(transport=transport), max_retries=3)
    with pytest.raises(AIProviderError, match="quota"):
        p.analyze_chunk(CHUNK, [4, 5], {})
    assert calls["n"] == 1


def test_citation_markers_are_removed_from_slide_text():
    from app.schemas import Slide

    s = Slide(title="Light [Page 2]", bullets=["Glucose is made [Page 1].", "Oxygen is released (pp. 2-3)"])
    assert s.title == "Light"
    assert s.bullets == ["Glucose is made.", "Oxygen is released"]
