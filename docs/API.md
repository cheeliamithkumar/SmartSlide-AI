# API Reference

Base URL: `http://localhost:8000/api`. Interactive docs: `/docs` (Swagger) and `/redoc`.
Errors are JSON: `{"detail": "Human readable message"}`. Validation errors also include `errors: [{field, message}]`.

## Meta

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Status, version, AI provider, OCR availability, limits |
| GET | `/templates` | Available presentation templates (id, name, description, colors, font) |
| GET | `/providers` | Configured AI provider and whether keys are present (never the keys) |

## Documents

### `POST /documents`
Multipart upload with field `file` (PDF).

| Status | Meaning |
|--------|---------|
| 201 | Created: returns document info |
| 400 | Empty, corrupted or password-protected PDF |
| 413 | File larger than `MAX_UPLOAD_MB` or more than `MAX_PAGES` pages |
| 415 | Not a PDF |

```json
{
  "id": "93e29777...", "original_filename": "photosynthesis.pdf", "size_bytes": 124360,
  "page_count": 3, "title": "Photosynthesis: How Plants Make Food", "author": "…",
  "is_scanned": false, "text_pages": 3, "empty_pages": 0, "word_count": 1038, "created_at": "…"
}
```

### `GET /documents/{id}`
Document information. Returns 404 if unknown or expired.

### `GET /documents/{id}/content?page_from=&page_to=`
Runs (and caches) extraction, including OCR, and returns page-wise text:

```json
{
  "page_count": 3, "is_scanned": false, "ocr_pages": [], "empty_pages": [], "warnings": [],
  "pages": [{"page": 1, "text": "## What Is Photosynthesis?\n…", "headings": ["What Is Photosynthesis?"],
             "method": "text", "word_count": 412}]
}
```

### `DELETE /documents/{id}`
Deletes the document, its jobs, presentations and files. Returns 204.

## Jobs (AI processing + generation)

### `POST /jobs` → 202
Starts background conversion.

```json
{
  "document_id": "93e29777...",
  "kinds": ["summary", "detailed"],
  "template": "modern_education",
  "summary_slides": 12,
  "detailed_slides": 24,
  "include_notes": true,
  "audience": "students"
}
```

Constraints: `summary_slides` must be 6–20 and `detailed_slides` 12–40. `template` must be one of the `/templates`
IDs. `kinds` must not be empty. Returns 404 for an unknown document and 422 for invalid options.

### `POST /jobs/{id}/advance`
Runs the next step(s) of a conversion and returns the job (each call takes under a minute). Safe to call
repeatedly or concurrently. Serverless deployments rely on the client calling this until the job completes;
self-hosted servers also run jobs in a background thread.

### `GET /jobs/{id}`
Poll for status.

```json
{
  "id": "ef91…", "status": "running", "stage": "analyzing", "progress": 42.5,
  "message": "Analyzed section 1 of 2 (pages 1–12)", "error": null,
  "provider_used": null, "warnings": [],
  "presentations": [{"id": "564f…", "kind": "summary", "title": "…", "template": "modern_education", "slide_count": 12}]
}
```

`status` is one of `queued`, `running`, `completed` or `failed`. `stage` is one of `extracting`, `analyzing`,
`structuring`, `composing`, `rendering`, `completed` or `failed`.

## Presentations

### Slide object

```json
{
  "id": "a1b2c3d4e5f6",
  "type": "content",
  "title": "The Calvin Cycle",
  "subtitle": null,
  "bullets": ["…"],
  "definitions": [{"term": "RuBisCO", "definition": "…"}],
  "steps": ["…"],
  "comparison": {"left_title": "C3 Plants", "right_title": "C4 Plants", "left": ["…"], "right": ["…"]},
  "notes": "Speaker notes…",
  "source_pages": [2],
  "visual_suggestion": "Flowchart of the steps"
}
```

`type` is one of `title`, `section`, `content`, `definition`, `comparison`, `process`, `example`, `takeaways`
or `conclusion`.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/presentations/{id}` | Preview data: metadata and slides |
| PATCH | `/presentations/{id}` | Body `{title?, template?, slides?}`: rename, change template or replace the whole slide list |
| PATCH | `/presentations/{id}/slides/{slide_id}` | Partial slide update (`title`, `bullets`, `definitions`, `steps`, `comparison`, `notes`, …) |
| DELETE | `/presentations/{id}/slides/{slide_id}` | Remove a slide (422 if it is the last one) |
| PUT | `/presentations/{id}/slides/order` | Body `{"order": [slide ids…]}`: must contain every ID exactly once |
| POST | `/presentations/{id}/slides?after={slide_id}` | Insert a new slide (body: slide object) → 201 |
| POST | `/presentations/{id}/slides/{slide_id}/regenerate` | Rewrite a slide from its source pages using the AI provider |
| GET | `/presentations/{id}/download` | Download the `.pptx`, re-rendered if edited since the last render |

Regeneration returns 422 for title slides or slides without source pages, and 503 if the AI provider fails
with no fallback available.

## Example session (curl)

```bash
DOC=$(curl -s -F "file=@backend/samples/photosynthesis.pdf;type=application/pdf" localhost:8000/api/documents | jq -r .id)
```

```bash
JOB=$(curl -s -H 'Content-Type: application/json' -d "{\"document_id\":\"$DOC\"}" localhost:8000/api/jobs | jq -r .id)
```

```bash
curl -s localhost:8000/api/jobs/$JOB | jq '.status, .presentations'
```

```bash
curl -OJ localhost:8000/api/presentations/<presentation-id>/download
```
