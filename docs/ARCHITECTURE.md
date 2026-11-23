# Architecture

```
┌──────────────────────┐   REST/JSON    ┌──────────────────────────────────────────────┐
│ React + Vite + Tailwind│ ────────────▶ │ FastAPI                                        │
│  pages / components   │ ◀──────────── │  routes/ ─▶ services/ ─▶ models (SQLite)       │
└──────────────────────┘   PPTX blob    │                 │                              │
                                         │                 ▼                              │
                                         │  background job (thread pool)                 │
                                         │  extract ▶ chunk ▶ AI analyze ▶ compose ▶ render│
                                         └──────────────────────────────────────────────┘
```

## Conversion pipeline (`services/jobs.py`)

1. **Extraction** (`pdf_extractor.py`)
   - `validate_pdf_bytes`: checks magic bytes, size, corruption, encryption and page limit.
   - `extract_pdf`: reads `page.get_text("dict")` for every page. It detects the body font size,
     marks larger or bold short lines as headings (`## Heading`), merges multi-line headings, and
     removes running headers/footers and page numbers. It also repairs hyphenation and ligatures.
   - Pages with almost no text but with images are OCR'd with Tesseract (up to `OCR_MAX_PAGES`).
     Empty pages are recorded and surfaced as warnings. Content is never silently discarded.
   - The result is cached as JSON (`storage/extracted/<doc>.json`) with page numbers preserved.
2. **Chunking** (`chunker.py`): pages are grouped into chunks of at most `CHUNK_MAX_CHARS`.
   New chunks preferably start at a heading so topics stay intact. Very long pages are split on paragraph
   boundaries. Each chunk embeds `[Page N]` markers so the model can cite sources.
3. **AI analysis** (`services/ai/`): every chunk produces a validated `ChunkAnalysis`: topics, key points,
   simplified points, definitions, examples, process steps, comparisons, visual suggestions and page refs.
   A final call produces the `DocumentOverview` (title, overview, takeaways, conclusion) from topic summaries only.
4. **Composition** (`content_processor.py`): topics split across chunks are merged. Candidate slides are created
   with priorities, and the highest-priority set that fits the slide budget is kept in document order.
   Empty section dividers are dropped. Limits: at most 5 bullets per slide, 3 definitions per slide, and 6 process steps.
5. **Rendering** (`pptx_builder.py`): python-pptx draws each slide type with native shapes on a 16:9 canvas,
   with fitted font sizes, footers (document name, source pages, slide number) and speaker notes.

## AI provider abstraction

```
AIProvider (base.py)                   analyze_chunk / document_overview / regenerate_slide
├── LLMProvider (llm_provider.py)      prompts, JSON parse + 1 corrective retry, HTTP retries/backoff
│   ├── ClaudeProvider                 POST https://api.anthropic.com/v1/messages
│   └── GeminiProvider                 POST generativelanguage.googleapis.com …:generateContent
└── MockProvider (mock_provider.py)    offline extractive engine (demo mode / fallback)

ResilientProvider (factory.py)         primary + fallback, records user-visible warnings
```

**Reliability and anti-hallucination measures**

- Prompts require using only the source text, preserving terminology and citing `[Page N]`.
- Output is parsed tolerantly (code fences, trailing commas) and validated against Pydantic schemas. One
  corrective retry is made with the validation error.
- `ground_analysis` drops definitions whose term is not in the source and replaces page references outside the chunk.
- Transient errors (429/5xx/timeouts) are retried with backoff. Auth errors fail fast.
- On any provider failure, the offline engine processes that chunk and the user sees a notice.

The **MockProvider** is extractive: it splits sections by detected headings, scores sentences
(term frequency, cue words, position, title overlap), and detects definitions with patterns such as
"X is defined as" or "X is called Y", along with examples, numbered or sequential steps, and "A vs B" comparisons.
It simplifies wording with rule-based rewrites.

## Data model (SQLite via SQLAlchemy)

| Table | Key fields |
|-------|-----------|
| `documents` | id (uuid hex), original_filename (sanitised, display only), stored_path, page_count, is_scanned, word stats |
| `jobs` | id, document_id, status, stage, progress, message, error, options (JSON), provider_used, warnings |
| `presentations` | id, document_id, job_id, kind (summary/detailed), template, title, slides (JSON), dirty, version |

Slides are stored as JSON (`schemas.Slide`). Edits mark the presentation `dirty`, and the PPTX is re-rendered
on the next download, so exports always match the editor.

## Frontend

- `pages/`: one component per route: `/`, `/upload`, `/configure/:documentId`, `/processing/:jobId`,
  `/preview/:jobId?kind=summary|detailed`, `/download/:jobId`.
- `components/SlideCanvas.jsx`: HTML preview that mirrors the PPTX layouts and theme colours, scaled with container query units.
- `components/SlideEditor.jsx`: type-aware editor (bullets, definitions, steps, comparison, notes).
- `services/api.js`: Axios client with friendly error messages. No secrets live in the frontend.
- The preview page autosaves edits (debounced PATCH) and flushes pending saves before any download,
  reorder, delete, regenerate or template change.

## Security

- Uploads are size-checked while streaming, magic-byte checked, opened safely and rejected if encrypted.
- Files are stored as `<uuid>.pdf`. User filenames are sanitised and used only for display and download names.
- No static route exposes `storage/`. All access goes through IDs (128-bit random) and API handlers.
- Deletion is constrained to the storage root (`safe_unlink`). A background thread removes expired documents,
  extracted text and outputs.
- CORS uses an explicit allow-list. Error responses never include stack traces or upstream API bodies.
- API keys are read from the environment only and never logged or returned.
