"""Pydantic schemas: slide structure, AI structured output and API payloads."""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Slides
# ---------------------------------------------------------------------------
class SlideType(str, Enum):
    title = "title"
    section = "section"
    content = "content"
    definition = "definition"
    comparison = "comparison"
    process = "process"
    example = "example"
    takeaways = "takeaways"
    conclusion = "conclusion"


class Definition(BaseModel):
    term: str = Field(min_length=1, max_length=200)
    definition: str = Field(min_length=1, max_length=900)


class Comparison(BaseModel):
    left_title: str = Field(default="A", max_length=120)
    right_title: str = Field(default="B", max_length=120)
    left: list[str] = Field(default_factory=list)
    right: list[str] = Field(default_factory=list)


def _clean_list(items: list[str]) -> list[str]:
    out = []
    for it in items:
        s = " ".join(str(it).split())
        if s:
            out.append(s[:600])
    return out


class Slide(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    type: SlideType = SlideType.content
    title: str = Field(default="Untitled", max_length=300)
    subtitle: str | None = Field(default=None, max_length=400)
    bullets: list[str] = Field(default_factory=list)
    definitions: list[Definition] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    comparison: Comparison | None = None
    notes: str | None = Field(default=None, max_length=6000)
    source_pages: list[int] = Field(default_factory=list)
    visual_suggestion: str | None = Field(default=None, max_length=300)

    @field_validator("bullets", "steps")
    @classmethod
    def _clean(cls, v: list[str]) -> list[str]:
        return _clean_list(v)

    @field_validator("title")
    @classmethod
    def _title(cls, v: str) -> str:
        v = " ".join(v.split())
        return v or "Untitled"

    @field_validator("source_pages")
    @classmethod
    def _pages(cls, v: list[int]) -> list[int]:
        return sorted({int(p) for p in v if int(p) > 0})


class SlideUpdate(BaseModel):
    """Partial update of a single slide."""

    type: SlideType | None = None
    title: str | None = Field(default=None, max_length=300)
    subtitle: str | None = Field(default=None, max_length=400)
    bullets: list[str] | None = None
    definitions: list[Definition] | None = None
    steps: list[str] | None = None
    comparison: Comparison | None = None
    notes: str | None = Field(default=None, max_length=6000)


# ---------------------------------------------------------------------------
# AI structured output (per chunk)
# ---------------------------------------------------------------------------
class KeyPoint(BaseModel):
    text: str = Field(min_length=1, max_length=600)
    pages: list[int] = Field(default_factory=list)


class SourcedDefinition(Definition):
    pages: list[int] = Field(default_factory=list)


class SourcedText(BaseModel):
    text: str = Field(min_length=1, max_length=900)
    pages: list[int] = Field(default_factory=list)


class TopicComparison(Comparison):
    title: str = Field(default="Comparison", max_length=200)
    pages: list[int] = Field(default_factory=list)


class Topic(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(default="", max_length=1500)
    importance: int = Field(default=3, ge=1, le=5)
    key_points: list[KeyPoint] = Field(default_factory=list)
    simplified_points: list[str] = Field(default_factory=list)
    definitions: list[SourcedDefinition] = Field(default_factory=list)
    examples: list[SourcedText] = Field(default_factory=list)
    process_steps: list[str] = Field(default_factory=list)
    comparisons: list[TopicComparison] = Field(default_factory=list)
    visual_suggestion: str | None = Field(default=None, max_length=300)
    key_takeaway: str | None = Field(default=None, max_length=400)
    pages: list[int] = Field(default_factory=list)

    @field_validator("importance", mode="before")
    @classmethod
    def _clamp_importance(cls, v):
        try:
            return max(1, min(5, int(v)))
        except (TypeError, ValueError):
            return 3


class ChunkAnalysis(BaseModel):
    topics: list[Topic] = Field(default_factory=list)


class DocumentOverview(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    subtitle: str | None = Field(default=None, max_length=400)
    overview: list[str] = Field(default_factory=list)
    key_takeaways: list[str] = Field(default_factory=list)
    conclusion: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------
class PageText(BaseModel):
    page: int
    text: str
    headings: list[str] = Field(default_factory=list)
    method: Literal["text", "ocr", "empty"] = "text"
    word_count: int = 0


class ExtractionResult(BaseModel):
    page_count: int
    pages: list[PageText]
    is_scanned: bool = False
    ocr_pages: list[int] = Field(default_factory=list)
    empty_pages: list[int] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def total_words(self) -> int:
        return sum(p.word_count for p in self.pages)


# ---------------------------------------------------------------------------
# API payloads
# ---------------------------------------------------------------------------
class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    original_filename: str
    size_bytes: int
    page_count: int
    title: str | None
    author: str | None
    is_scanned: bool
    text_pages: int
    empty_pages: int
    word_count: int
    created_at: datetime


class PresentationKind(str, Enum):
    summary = "summary"
    detailed = "detailed"


class JobCreate(BaseModel):
    document_id: str = Field(min_length=1, max_length=64)
    kinds: list[PresentationKind] = Field(
        default_factory=lambda: [PresentationKind.summary, PresentationKind.detailed]
    )
    template: str = Field(default="modern_education", max_length=40)
    summary_slides: int = Field(default=12, ge=6, le=20)
    detailed_slides: int = Field(default=24, ge=12, le=40)
    include_notes: bool = True
    audience: Literal["students", "educators", "general"] = "students"

    @model_validator(mode="after")
    def _kinds(self):
        if not self.kinds:
            raise ValueError("Select at least one presentation type")
        self.kinds = list(dict.fromkeys(self.kinds))
        return self


class PresentationBrief(BaseModel):
    id: str
    kind: str
    title: str
    template: str
    slide_count: int


class JobOut(BaseModel):
    id: str
    document_id: str
    status: str
    stage: str
    progress: float
    message: str | None
    error: str | None
    provider_used: str | None
    warnings: list[str]
    options: dict
    presentations: list[PresentationBrief]
    created_at: datetime
    updated_at: datetime


class PresentationOut(BaseModel):
    id: str
    document_id: str
    job_id: str | None
    kind: str
    template: str
    title: str
    slides: list[Slide]
    version: int
    document_name: str
    updated_at: datetime


class PresentationUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    template: str | None = Field(default=None, max_length=40)
    slides: list[Slide] | None = None


class SlideOrder(BaseModel):
    order: list[str] = Field(min_length=1)


class TemplateOut(BaseModel):
    id: str
    name: str
    description: str
    colors: dict[str, str]
    font: str
