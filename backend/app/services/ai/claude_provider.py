"""Anthropic Claude provider (Messages API over HTTPS)."""
from __future__ import annotations

from app.services.ai.base import AIProviderError
from app.services.ai.llm_provider import LLMProvider

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"


class ClaudeProvider(LLMProvider):
    name = "claude"

    def _complete(self, system: str, user: str, max_tokens: int) -> str:
        data = self._post(
            API_URL,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": API_VERSION,
                "content-type": "application/json",
            },
            payload={
                "model": self.model,
                "max_tokens": max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
        )
        if data.get("stop_reason") == "refusal":
            raise AIProviderError("Claude declined to process this content")
        parts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
        text = "".join(parts).strip()
        if not text:
            raise AIProviderError("Claude returned an empty response")
        return text
