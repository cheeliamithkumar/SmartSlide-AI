"""Provider factory + resilient wrapper that falls back to the offline engine."""
from __future__ import annotations

import logging

from app.config import Settings, get_settings
from app.schemas import ChunkAnalysis, DocumentOverview, Slide, Topic
from app.services.ai.base import AIProvider, AIProviderError
from app.services.ai.mock_provider import MockProvider

logger = logging.getLogger(__name__)


def build_provider(name: str, settings: Settings | None = None) -> AIProvider:
    settings = settings or get_settings()
    if name == "mock":
        return MockProvider()
    if name == "claude":
        from app.services.ai.claude_provider import ClaudeProvider

        return ClaudeProvider(settings.anthropic_api_key or "", settings.claude_model,
                              settings.ai_timeout_seconds, settings.ai_max_retries)
    if name == "gemini":
        from app.services.ai.gemini_provider import GeminiProvider

        return GeminiProvider(settings.gemini_api_key or "", settings.gemini_model,
                              settings.ai_timeout_seconds, settings.ai_max_retries)
    raise AIProviderError(f"Unknown AI provider: {name}")


class ResilientProvider(AIProvider):
    """Delegates to the primary provider; on failure uses the offline engine.

    Records warnings so the user is told when fallback content was used.
    """

    def __init__(self, primary: AIProvider | None, fallback: AIProvider | None, init_error: str | None = None):
        self.primary = primary
        self.fallback = fallback
        self.warnings: list[str] = []
        self.fallback_used = False
        if init_error:
            self._warn(init_error)
        self.name = primary.name if primary else (fallback.name if fallback else "none")

    def _warn(self, msg: str):
        if msg not in self.warnings:
            self.warnings.append(msg)

    def _call(self, method: str, *args):
        if self.primary is not None:
            try:
                return getattr(self.primary, method)(*args)
            except AIProviderError as exc:
                logger.warning("Primary provider %s failed in %s: %s", self.primary.name, method, exc)
                if self.fallback is None:
                    raise
                self._warn(f"AI provider '{self.primary.name}' was unavailable ({exc}); "
                           "offline extraction was used for part of the content.")
        if self.fallback is None:
            raise AIProviderError("No AI provider available")
        self.fallback_used = True
        return getattr(self.fallback, method)(*args)

    def analyze_chunk(self, chunk_text: str, pages: list[int], context: dict) -> ChunkAnalysis:
        return self._call("analyze_chunk", chunk_text, pages, context)

    def document_overview(self, topics: list[Topic], context: dict) -> DocumentOverview:
        return self._call("document_overview", topics, context)

    def regenerate_slide(self, slide: Slide, source_text: str, context: dict) -> Slide:
        return self._call("regenerate_slide", slide, source_text, context)

    @property
    def label(self) -> str:
        if self.primary is None:
            return "mock"
        return f"{self.primary.name}+fallback" if self.fallback_used else self.primary.name


def get_provider(name: str | None = None) -> ResilientProvider:
    settings = get_settings()
    name = name or settings.ai_provider
    fallback = MockProvider() if settings.ai_fallback_to_mock else None
    if name == "mock":
        return ResilientProvider(None, MockProvider())
    try:
        primary = build_provider(name, settings)
    except AIProviderError as exc:
        if fallback is None:
            raise
        return ResilientProvider(None, fallback, init_error=f"{exc}. Using offline demo mode instead.")
    return ResilientProvider(primary, fallback)


def provider_status() -> dict:
    s = get_settings()
    return {
        "configured": s.ai_provider,
        "claude_key_present": bool(s.anthropic_api_key),
        "gemini_key_present": bool(s.gemini_api_key),
        "fallback_enabled": s.ai_fallback_to_mock,
    }
