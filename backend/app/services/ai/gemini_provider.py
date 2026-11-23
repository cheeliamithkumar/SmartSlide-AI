"""Google Gemini provider (Generative Language REST API)."""
from __future__ import annotations

import logging
import re

from app.services.ai.base import AIProviderError
from app.services.ai.llm_provider import LLMProvider

logger = logging.getLogger(__name__)

BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
API_URL = BASE_URL + "/models/{model}:generateContent"

# Gemini models may "think" before answering; thinking tokens count against the output
# budget, so give generous headroom (Flash models support far larger outputs).
MIN_OUTPUT_TOKENS = 16384


def _version_key(name: str) -> tuple:
    nums = [int(x) for x in re.findall(r"\d+", name.split("/")[-1])[:2]]
    return tuple(nums) + ((0,) * (2 - len(nums)))


def usable_models(models: list[dict]) -> list[str]:
    """Stable 'flash' models supporting generateContent, newest first."""
    usable = [
        m["name"].split("/")[-1] for m in models
        if "generateContent" in (m.get("supportedGenerationMethods") or [])
        and "flash" in m.get("name", "")
        and not re.search(r"(lite|image|tts|live|audio|exp|preview|thinking|embedding)", m.get("name", ""))
    ]
    return sorted(set(usable), key=_version_key, reverse=True)


def pick_model(models: list[dict]) -> str | None:
    """Choose the newest stable 'flash' model that supports generateContent."""
    found = usable_models(models)
    return found[0] if found else None


class GeminiProvider(LLMProvider):
    name = "gemini"
    _resolved_model: str | None = None  # shared across instances once discovered

    def _discover_models(self) -> list[str]:
        try:
            resp = self._client.get(f"{BASE_URL}/models", headers={"x-goog-api-key": self.api_key},
                                    params={"pageSize": 200}, timeout=self.timeout)
            if resp.status_code != 200:
                logger.warning("Gemini model listing failed: HTTP %s", resp.status_code)
                return []
            return usable_models(resp.json().get("models", []))
        except Exception as exc:  # pragma: no cover - network
            logger.warning("Gemini model discovery failed: %s", exc)
            return []

    def _request(self, model: str, system: str, user: str, max_tokens: int) -> dict:
        return self._post(
            API_URL.format(model=model),
            headers={"x-goog-api-key": self.api_key, "content-type": "application/json"},
            payload={
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {
                    "temperature": 0.3,
                    "maxOutputTokens": max(max_tokens, MIN_OUTPUT_TOKENS),
                    "responseMimeType": "application/json",
                },
            },
        )

    def _complete(self, system: str, user: str, max_tokens: int) -> str:
        model = GeminiProvider._resolved_model or self.model
        try:
            data = self._request(model, system, user, max_tokens)
        except AIProviderError as exc:
            # Model retired/unknown (400/404) or persistently overloaded/rate limited (429/503):
            # try the other currently available Flash models before giving up.
            if exc.status_code not in (400, 404, 429, 500, 503):
                raise
            data = None
            for alt in [m for m in self._discover_models() if m != model][:3]:
                try:
                    data = self._request(alt, system, user, max_tokens)
                except AIProviderError as alt_exc:
                    logger.warning("Gemini fallback model %s failed: %s", alt, alt_exc)
                    continue
                logger.info("Gemini model %s unavailable (%s); using %s", model, exc, alt)
                GeminiProvider._resolved_model = alt
                break
            if data is None:
                raise
        candidates = data.get("candidates") or []
        if not candidates:
            raise AIProviderError("Gemini returned no candidates (content may have been blocked)")
        parts = (candidates[0].get("content") or {}).get("parts") or []
        # skip "thought" parts some models return alongside the answer
        text = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
        if not text:
            reason = candidates[0].get("finishReason", "unknown")
            raise AIProviderError(f"Gemini returned an empty response (finish reason: {reason})")
        return text
