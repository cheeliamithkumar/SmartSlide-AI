"""Prompt templates for LLM providers. All prompts request strict JSON output."""
from __future__ import annotations

import json

SYSTEM_PROMPT = """You are SmartSlide AI, an expert instructional designer who turns educational \
documents into clear, accurate presentation material for {audience}.

Rules you must always follow:
- Use ONLY information present in the provided source text. Never invent facts, numbers, names or examples.
- Preserve important technical terminology exactly as written in the source.
- Simplify difficult explanations into plain language without changing their meaning.
- Every item must cite the page number(s) it came from, using the [Page N] markers in the source.
- Keep bullet points concise (ideally under 20 words) and self-contained.
- Respond with a single valid JSON object and nothing else: no markdown, no commentary."""

CHUNK_SCHEMA = {
    "topics": [
        {
            "title": "short topic title (max 8 words)",
            "summary": "2-3 sentence plain-language summary of the topic",
            "importance": "integer 1-5 (5 = central concept of the document)",
            "pages": [1],
            "key_points": [{"text": "faithful, detailed point from the source", "pages": [1]}],
            "simplified_points": ["concise simplified bullet (max 18 words)"],
            "definitions": [{"term": "exact term from source", "definition": "definition from source", "pages": [1]}],
            "examples": [{"text": "example given in the source", "pages": [1]}],
            "process_steps": ["ordered step, only if the source describes a process/sequence"],
            "comparisons": [
                {
                    "title": "X vs Y",
                    "left_title": "X",
                    "right_title": "Y",
                    "left": ["property of X"],
                    "right": ["matching property of Y"],
                    "pages": [1],
                }
            ],
            "visual_suggestion": "optional idea for a diagram/visual, e.g. 'flowchart of the cycle'",
            "key_takeaway": "the single most important sentence a learner should remember about this topic",
        }
    ]
}

CHUNK_PROMPT = """Analyze this section of the document "{doc_name}" (pages {page_range}, part {part} of {total}).

Identify every distinct topic in logical order. For each topic extract key points (faithful and \
detailed, for a detailed presentation), simplified points (short, for a summary presentation), \
definitions, examples, process steps and comparisons — only when they are actually present in the text. \
Use empty arrays when something is absent. Lines starting with '## ' are headings from the PDF.

Return JSON exactly in this shape:
{schema}

SOURCE TEXT:
<<<
{text}
>>>"""

OVERVIEW_SCHEMA = {
    "title": "presentation title derived from the document",
    "subtitle": "one-line description",
    "overview": ["3-5 bullets describing what the document covers"],
    "key_takeaways": ["4-6 most important takeaways a learner must remember"],
    "conclusion": ["2-4 concluding bullets"],
}

OVERVIEW_PROMPT = """Below are the topics extracted from the document "{doc_name}". \
Write the presentation framing: title, subtitle, overview, key takeaways and conclusion. \
Base everything strictly on these topics.

Return JSON exactly in this shape:
{schema}

TOPICS:
{topics}"""

SLIDE_SCHEMA = {
    "type": "same slide type as given",
    "title": "improved slide title",
    "bullets": ["3-6 concise bullets"],
    "definitions": [{"term": "...", "definition": "..."}],
    "steps": ["..."],
    "comparison": None,
    "diagram": "only for slides that have one: same kind, with improved 'center' and 'nodes' [{label, detail}]",
    "notes": "speaker notes explaining the slide in 2-4 sentences",
    "visual_suggestion": "optional",
}

SLIDE_PROMPT = """Rewrite this {kind} presentation slide so it is clearer and better structured, \
using only facts from the source pages below. Keep the same slide type ("{slide_type}"). \
Use the field(s) appropriate to the type: bullets for content/example/takeaways/conclusion, \
definitions for definition slides, steps for process slides, comparison for comparison slides, \
diagram nodes for diagram slides. The result must differ from the current slide.

CURRENT SLIDE:
{slide}

Return JSON exactly in this shape:
{schema}

SOURCE PAGES:
<<<
{text}
>>>"""


def dumps(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False)
