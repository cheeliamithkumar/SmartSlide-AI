"""AI provider abstraction and structured-output validation helpers."""
from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.schemas import ChunkAnalysis, DocumentOverview, Slide, Topic

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class AIProviderError(RuntimeError):
    """Raised when a provider call fails (network, auth, quota, invalid output)."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class AIProvider(ABC):
    """Interface every AI backend implements."""

    name: str = "base"

    @abstractmethod
    def analyze_chunk(self, chunk_text: str, pages: list[int], context: dict) -> ChunkAnalysis:
        """Identify topics, key points, definitions, examples, steps and comparisons."""

    @abstractmethod
    def document_overview(self, topics: list[Topic], context: dict) -> DocumentOverview:
        """Produce title, overview, key takeaways and conclusion from topic summaries."""

    @abstractmethod
    def regenerate_slide(self, slide: Slide, source_text: str, context: dict) -> Slide:
        """Rewrite one slide from its source pages."""


# ---------------------------------------------------------------------------
# JSON parsing / validation for LLM output
# ---------------------------------------------------------------------------
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S | re.I)


def extract_json(text: str) -> object:
    """Parse JSON from model output, tolerating code fences and surrounding prose."""
    if text is None:
        raise AIProviderError("Empty response from model")
    candidates = [text.strip()]
    candidates += [m.strip() for m in _FENCE.findall(text)]
    # outermost {...} block
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])
    for cand in candidates:
        try:
            return json.loads(cand)
        except (json.JSONDecodeError, TypeError):
            continue
        # try removing trailing commas
    for cand in candidates:
        fixed = re.sub(r",\s*([}\]])", r"\1", cand)
        try:
            return json.loads(fixed)
        except (json.JSONDecodeError, TypeError):
            continue
    raise AIProviderError("Model response was not valid JSON")


def parse_model(text: str, model: type[T]) -> T:
    data = extract_json(text)
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise AIProviderError(f"Model response failed schema validation: {exc.error_count()} error(s)") from exc


def _in_range(pages: list[int], allowed: set[int]) -> list[int]:
    return sorted({p for p in pages if p in allowed})


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def ground_analysis(analysis: ChunkAnalysis, source_text: str, pages: list[int]) -> ChunkAnalysis:
    """Anti-hallucination pass on AI output.

    * page references outside the chunk are dropped (fallback: the chunk's pages)
    * definitions whose term does not appear in the source text are removed
    * empty topics are removed
    """
    allowed = set(pages)
    norm_src = _norm(source_text)
    topics: list[Topic] = []
    from app.schemas import strip_citations

    for t in analysis.topics:
        t.summary = strip_citations(t.summary)
        t.simplified_points = [strip_citations(p) for p in t.simplified_points]
        for kp in t.key_points:
            kp.text = strip_citations(kp.text)
        for d in t.definitions:
            d.definition = strip_citations(d.definition)
        for ex in t.examples:
            ex.text = strip_citations(ex.text)
        if t.key_takeaway:
            t.key_takeaway = strip_citations(t.key_takeaway)
        t.pages = _in_range(t.pages, allowed) or list(pages)
        for kp in t.key_points:
            kp.pages = _in_range(kp.pages, allowed) or t.pages
        defs = []
        for d in t.definitions:
            term = _norm(d.term)
            if term and term in norm_src:
                d.pages = _in_range(d.pages, allowed) or t.pages
                defs.append(d)
            else:
                logger.info("Dropping ungrounded definition: %r", d.term)
        t.definitions = defs
        for ex in t.examples:
            ex.pages = _in_range(ex.pages, allowed) or t.pages
        for c in t.comparisons:
            c.pages = _in_range(c.pages, allowed) or t.pages
        if t.key_points or t.simplified_points or t.definitions or t.summary:
            topics.append(t)
    return ChunkAnalysis(topics=topics)
