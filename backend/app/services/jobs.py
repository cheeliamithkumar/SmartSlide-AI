"""Background conversion jobs: extract -> chunk -> analyze -> compose -> render."""
from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor

from app.config import get_settings
from app.database import session_scope
from app.models import Document, Job, Presentation
from app.schemas import Topic
from app.services import storage
from app.services.ai.factory import get_provider
from app.services.chunker import chunk_document
from app.services.content_processor import build_decks, merge_topics

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="smartslide-job")


class JobError(RuntimeError):
    pass


def _update(job_id: str, **fields) -> None:
    with session_scope() as db:
        job = db.get(Job, job_id)
        if job is None:
            return
        for k, v in fields.items():
            setattr(job, k, v)


def submit(job_id: str) -> None:
    _executor.submit(run_job, job_id)


def _doc_title(doc: Document, extraction) -> str:
    if doc.title and len(doc.title) > 3 and not re.search(r"\.(docx?|pdf|tex)$|^untitled|^microsoft", doc.title, re.I):
        return doc.title
    for p in extraction.pages[:3]:
        if p.headings:
            return p.headings[0][:200]
    stem = doc.original_filename.rsplit(".", 1)[0]
    return re.sub(r"[_\-]+", " ", stem).strip().title() or "Presentation"


def run_job(job_id: str) -> None:
    settings = get_settings()
    try:
        with session_scope() as db:
            job = db.get(Job, job_id)
            if job is None:
                return
            doc = db.get(Document, job.document_id)
            if doc is None:
                raise JobError("The source document no longer exists.")
            options = dict(job.options or {})
            doc_id, doc_name = doc.id, doc.original_filename
            job.status, job.stage, job.progress, job.message = "running", "extracting", 5, "Extracting text from PDF"

        # 1. Extraction (cached on disk and in the database) ---------------
        with session_scope() as db:
            try:
                extraction = storage.get_or_extract(db.get(Document, doc_id))
            except FileNotFoundError as exc:
                raise JobError(str(exc)) from exc
        warnings = list(extraction.warnings)
        if extraction.total_words < 30:
            raise JobError(
                "Not enough readable text was found in this PDF to build a presentation. "
                + ("It looks like a scanned document and OCR could not read it." if extraction.is_scanned else "")
            )

        # 2. Chunking -----------------------------------------------------
        chunks = chunk_document(extraction, settings.chunk_max_chars)
        _update(job_id, stage="analyzing", progress=15,
                message=f"Analyzing content ({len(chunks)} section{'s' if len(chunks) != 1 else ''})")

        provider = get_provider(options.get("provider"))
        with session_scope() as db:
            doc = db.get(Document, doc_id)
            doc_title = _doc_title(doc, extraction)
        context = {"doc_name": doc_name, "doc_title": doc_title, "audience": options.get("audience", "students"),
                   "total": len(chunks)}

        # 3. AI analysis per chunk ---------------------------------------
        topics: list[Topic] = []
        for i, chunk in enumerate(chunks, start=1):
            analysis = provider.analyze_chunk(chunk.text, chunk.pages, {**context, "part": i})
            topics.extend(analysis.topics)
            _update(job_id, progress=15 + 55 * i / max(len(chunks), 1),
                    message=f"Analyzed section {i} of {len(chunks)} (pages {chunk.page_range})")
        topics = merge_topics(topics)
        if not topics:
            raise JobError("No meaningful content could be identified in this document.")

        _update(job_id, stage="structuring", progress=72, message="Identifying key takeaways")
        overview = provider.document_overview(topics, context)
        if not overview.title or overview.title.lower() in {"presentation", "document"}:
            overview.title = doc_title

        # 4. Compose decks -----------------------------------------------
        _update(job_id, stage="composing", progress=80, message="Designing slides")
        kinds = options.get("kinds", ["summary", "detailed"])
        decks = build_decks(
            topics, overview, doc_name, kinds,
            summary_target=int(options.get("summary_slides", settings.summary_slides_default)),
            detailed_target=int(options.get("detailed_slides", settings.detailed_slides_default)),
            include_notes=bool(options.get("include_notes", True)),
        )

        # 5. Render PPTX ---------------------------------------------------
        _update(job_id, stage="rendering", progress=88, message="Building PowerPoint files")
        warnings += provider.warnings
        with session_scope() as db:
            doc = db.get(Document, doc_id)
            job = db.get(Job, job_id)
            for kind, slides in decks.items():
                pres = Presentation(
                    document_id=doc_id, job_id=job_id, kind=kind, template=options.get("template", "modern_education"),
                    title=overview.title[:500], slides=[s.model_dump(mode="json") for s in slides],
                )
                db.add(pres)
                db.flush()
                storage.render(pres, doc)
            job.status, job.stage, job.progress = "completed", "completed", 100
            job.message = "Your presentations are ready"
            job.provider_used = provider.label
            job.warnings = warnings
    except JobError as exc:
        logger.info("Job %s failed: %s", job_id, exc)
        _update(job_id, status="failed", stage="failed", error=str(exc), message="Conversion failed")
    except Exception as exc:  # pragma: no cover - unexpected
        logger.exception("Job %s crashed", job_id)
        _update(job_id, status="failed", stage="failed", message="Conversion failed",
                error="An unexpected error occurred while generating the presentation. Please try again.")
