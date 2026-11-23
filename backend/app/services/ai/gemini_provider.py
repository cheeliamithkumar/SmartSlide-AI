"""Google Gemini provider (Generative Language REST API)."""
from __future__ import annotations

from app.services.ai.base import AIProviderError
from app.services.ai.llm_provider import LLMProvider

API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GeminiProvider(LLMProvider):
    name = "gemini"

    def _complete(self, system: str, user: str, max_tokens: int) -> str:
        data = self._post(
            API_URL.format(model=self.model),
            headers={"x-goog-api-key": self.api_key, "content-type": "application/json"},
            payload={
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {
                    "temperature": 0.3,
                    "maxOutputTokens": max_tokens,
                    "responseMimeType": "application/json",
                },
            },
        )
        candidates = data.get("candidates") or []
        if not candidates:
            raise AIProviderError("Gemini returned no candidates (content may have been blocked)")
        parts = (candidates[0].get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts).strip()
        if not text:
            raise AIProviderError("Gemini returned an empty response")
        return text
