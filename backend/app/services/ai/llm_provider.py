"""Shared logic for HTTP-based LLM providers (Claude, Gemini)."""
from __future__ import annotations

import logging
import time
from abc import abstractmethod

import httpx

from app.schemas import ChunkAnalysis, DocumentOverview, Slide, Topic
from app.services.ai import prompts
from app.services.ai.base import AIProvider, AIProviderError, T, ground_analysis, parse_model

logger = logging.getLogger(__name__)


class LLMProvider(AIProvider):
    """Template: subclasses implement ``_complete(system, user, max_tokens) -> str``."""

    def __init__(self, api_key: str, model: str, timeout: float = 90.0, max_retries: int = 2,
                 client: httpx.Client | None = None):
        if not api_key:
            raise AIProviderError(f"{self.name} API key is not configured")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self._client = client or httpx.Client(timeout=timeout)

    @abstractmethod
    def _complete(self, system: str, user: str, max_tokens: int) -> str: ...

    # ------------------------------------------------------------------
    def _post(self, url: str, headers: dict, payload: dict) -> dict:
        """POST with retries on transient errors (429/5xx/network)."""
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = self._client.post(url, headers=headers, json=payload, timeout=self.timeout)
            except httpx.HTTPError as exc:
                last_exc = exc
                logger.warning("%s request failed (attempt %s): %s", self.name, attempt + 1, exc)
            else:
                if resp.status_code == 200:
                    return resp.json()
                if resp.status_code in (401, 403):
                    raise AIProviderError(f"{self.name} rejected the API key (HTTP {resp.status_code})")
                # provider error messages go to server logs only (never to users)
                logger.warning("%s HTTP %s: %s", self.name, resp.status_code, resp.text[:300].replace("\n", " "))
                if resp.status_code in (429, 500, 502, 503, 504, 529):
                    last_exc = AIProviderError(f"{self.name} temporarily unavailable (HTTP {resp.status_code})",
                                               status_code=resp.status_code)
                else:
                    # do not leak response bodies that might echo request content
                    raise AIProviderError(f"{self.name} request failed (HTTP {resp.status_code})",
                                          status_code=resp.status_code)
            if attempt < self.max_retries:
                time.sleep(min(2 ** (attempt + 1), 10))
        if isinstance(last_exc, AIProviderError):
            raise last_exc  # keeps status_code so callers can fail over
        raise AIProviderError(str(last_exc) if last_exc else f"{self.name} request failed")

    def _structured(self, system: str, user: str, model: type[T], max_tokens: int = 8000) -> T:
        """Call the model and validate JSON; retry once with a corrective instruction."""
        text = self._complete(system, user, max_tokens)
        try:
            return parse_model(text, model)
        except AIProviderError as first:
            logger.info("%s returned invalid structured output, retrying: %s", self.name, first)
            fix = (
                user
                + "\n\nIMPORTANT: Your previous answer was not valid JSON for the requested schema "
                f"({first}). Respond again with ONLY the JSON object."
            )
            return parse_model(self._complete(system, fix, max_tokens), model)

    # ------------------------------------------------------------------
    def _system(self, context: dict) -> str:
        return prompts.SYSTEM_PROMPT.format(audience=context.get("audience", "students"))

    def analyze_chunk(self, chunk_text: str, pages: list[int], context: dict) -> ChunkAnalysis:
        page_range = f"{min(pages)}–{max(pages)}" if pages else "?"
        user = prompts.CHUNK_PROMPT.format(
            doc_name=context.get("doc_name", "document"),
            page_range=page_range,
            part=context.get("part", 1),
            total=context.get("total", 1),
            schema=prompts.dumps(prompts.CHUNK_SCHEMA),
            text=chunk_text,
        )
        result = self._structured(self._system(context), user, ChunkAnalysis)
        return ground_analysis(result, chunk_text, pages)

    def document_overview(self, topics: list[Topic], context: dict) -> DocumentOverview:
        brief = [
            {"title": t.title, "summary": t.summary, "importance": t.importance,
             "points": t.simplified_points[:4] or [k.text for k in t.key_points[:3]]}
            for t in topics[:60]
        ]
        user = prompts.OVERVIEW_PROMPT.format(
            doc_name=context.get("doc_name", "document"),
            schema=prompts.dumps(prompts.OVERVIEW_SCHEMA),
            topics=prompts.dumps(brief),
        )
        return self._structured(self._system(context), user, DocumentOverview, max_tokens=3000)

    def regenerate_slide(self, slide: Slide, source_text: str, context: dict) -> Slide:
        current = slide.model_dump(include={"type", "title", "subtitle", "bullets", "definitions", "steps", "comparison", "diagram"})
        user = prompts.SLIDE_PROMPT.format(
            kind=context.get("kind", "summary"),
            slide_type=slide.type.value,
            slide=prompts.dumps(current),
            schema=prompts.dumps(prompts.SLIDE_SCHEMA),
            text=source_text[:16000],
        )
        new = self._structured(self._system(context), user, Slide, max_tokens=3000)
        new.id = slide.id
        new.type = slide.type
        new.source_pages = slide.source_pages
        return new
