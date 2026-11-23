"""Conversion jobs as a resumable, step-based pipeline.

extract -> analyze chunk 1..N (AI) -> overview (AI) -> compose + render

Progress is persisted in ``Job.state`` after every unit of work, so a job can be
advanced by many short requests (serverless: the browser calls
``POST /api/jobs/{id}/advance`` repeatedly) or by one background thread
(self-hosted). A database lease guarantees that only one worker advances a job at
a time, and every request stays well below proxy / serverless time limits.
"""
from __future__ import annotations

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, update

from app.config import get_settings
from app.database import session_scope
from app.models import Document, Job, Presentation
from app.schemas import DocumentOverview, Topic
from app.services import storage
from app.services.ai.factory import ResilientProvider, get_provider
from app.services.ai.mock_provider import MockProvider
from app.services.chunker import chunk_document
from app.services.content_processor import build_decks, merge_topics

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="smartslide-job")
LEASE_SECONDS = 90


class JobError(RuntimeError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _update(job_id: str, **fields) -> None:
    with session_scope() as db:
        job = db.get(Job, job_id)
        if job is None:
            return
        for k, v in fields.items():
            setattr(job, k, v)


def _doc_title(doc: Document, extraction) -> str:
    if doc.title and len(doc.title) > 3 and not re.search(r"\.(docx?|pdf|tex)$|^untitled|^microsoft", doc.title, re.I):
        return doc.title
    for p in extraction.pages[:3]:
        if p.headings:
            return p.headings[0][:200]
    stem = doc.original_filename.rsplit(".", 1)[0]
    return re.sub(r"[_\-]+", " ", stem).strip().title() or "Presentation"


# ---------------------------------------------------------------------------
# Lease (one worker per job)
# ---------------------------------------------------------------------------
def _acquire(job_id: str) -> bool:
    now = _now()
    with session_scope() as db:
        res = db.execute(
            update(Job)
            .where(Job.id == job_id, Job.status.in_(("queued", "running")),
                   or_(Job.lease_until.is_(None), Job.lease_until < now))
            .values(lease_until=now + timedelta(seconds=LEASE_SECONDS))
        )
        return res.rowcount == 1


def _release(job_id: str) -> None:
    _update(job_id, lease_until=None)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------
def advance(job_id: str, time_limit: float | None = None) -> bool:
    """Do as much work as fits in ``time_limit`` seconds. Returns True if work was done."""
    settings = get_settings()
    time_limit = time_limit if time_limit is not None else settings.job_step_seconds
    if not _acquire(job_id):
        return False
    started = time.monotonic()
    try:
        _run_units(job_id, started + time_limit)
    except JobError as exc:
        logger.info("Job %s failed: %s", job_id, exc)
        _update(job_id, status="failed", stage="failed", error=str(exc), message="Conversion failed")
    except Exception:  # pragma: no cover - unexpected
        logger.exception("Job %s crashed", job_id)
        _update(job_id, status="failed", stage="failed", message="Conversion failed",
                error="An unexpected error occurred while generating the presentation. Please try again.")
    finally:
        _release(job_id)
    return True


def _run_units(job_id: str, deadline: float) -> None:
    settings = get_settings()
    with session_scope() as db:
        job = db.get(Job, job_id)
        if job is None or job.status not in ("queued", "running"):
            return
        doc = db.get(Document, job.document_id)
        if doc is None:
            raise JobError("The source document no longer exists.")
        try:
            extraction = storage.get_or_extract(doc)
        except FileNotFoundError as exc:
            raise JobError(str(exc)) from exc
        options = dict(job.options or {})
        state = dict(job.state or {})
        doc_id, doc_name, doc_title = doc.id, doc.original_filename, _doc_title(doc, extraction)
        if job.status == "queued":
            job.status, job.stage, job.progress, job.message = "running", "extracting", 5, "Reading your PDF"

    if extraction.total_words < 30:
        raise JobError(
            "Not enough readable text was found in this PDF to build a presentation. "
            + ("It looks like a scanned document and OCR could not read it." if extraction.is_scanned else "")
        )

    chunks = chunk_document(extraction, settings.chunk_max_chars)
    state.setdefault("phase", "analyze")
    state.setdefault("next_chunk", 0)
    state.setdefault("topics", [])
    state.setdefault("warnings", list(extraction.warnings))
    state.setdefault("ai_seconds", 0.0)
    state.setdefault("labels", [])
    context = {"doc_name": doc_name, "doc_title": doc_title, "audience": options.get("audience", "students"),
               "total": len(chunks)}

    def provider_for_unit() -> ResilientProvider:
        """AI provider limited to the time left in this step and in the job's overall AI budget."""
        step_left = deadline - time.monotonic()
        ai_left = settings.ai_time_budget_seconds - state["ai_seconds"]
        budget = min(step_left - 3, ai_left)
        if budget < 8:
            if ai_left < 8 and "ai_budget_note" not in state:
                state["ai_budget_note"] = True
                state["warnings"].append("The AI provider was slow, so offline extraction was used for the "
                                         "remaining content.")
            return ResilientProvider(None, MockProvider())
        return get_provider(options.get("provider"), time_budget=budget)

    def run_ai(fn):
        provider = provider_for_unit()
        t0 = time.monotonic()
        result = fn(provider)
        if provider.primary is not None:
            state["ai_seconds"] += time.monotonic() - t0
        state["labels"].append(provider.label)
        for w in provider.warnings:
            if w not in state["warnings"]:
                state["warnings"].append(w)
        return result

    def save(**fields) -> None:
        with session_scope() as db:
            j = db.get(Job, job_id)
            j.state = dict(state)
            for k, v in fields.items():
                setattr(j, k, v)

    # A unit always runs at least once per step, then more while time remains.
    first = True
    while first or time.monotonic() < deadline - 10:
        first = False
        if state["phase"] == "analyze" and state["next_chunk"] >= len(chunks):
            state["phase"] = "overview"  # phase change is not a unit of work: fall through to the next phase
        phase = state["phase"]
        if phase == "analyze":
            i = state["next_chunk"]
            chunk = chunks[i]
            analysis = run_ai(lambda p: p.analyze_chunk(chunk.text, chunk.pages, {**context, "part": i + 1}))
            state["topics"] += [t.model_dump(mode="json") for t in analysis.topics]
            state["next_chunk"] = i + 1
            save(stage="analyzing", progress=15 + 55 * (i + 1) / max(len(chunks), 1),
                 message=f"Analyzed section {i + 1} of {len(chunks)} (pages {chunk.page_range})")
        elif phase == "overview":
            topics = merge_topics([Topic.model_validate(t) for t in state["topics"]])
            if not topics:
                raise JobError("No meaningful content could be identified in this document.")
            overview = run_ai(lambda p: p.document_overview(topics, context))
            if not overview.title or overview.title.lower() in {"presentation", "document"}:
                overview.title = doc_title
            state["overview"] = overview.model_dump(mode="json")
            state["phase"] = "compose"
            save(stage="composing", progress=80, message="Designing slides")
        elif phase == "compose":
            _compose(job_id, doc_id, doc_name, options, state)
            return
        else:
            return


def _compose(job_id: str, doc_id: str, doc_name: str, options: dict, state: dict) -> None:
    settings = get_settings()
    topics = [Topic.model_validate(t) for t in state["topics"]]
    overview = DocumentOverview.model_validate(state["overview"])
    kinds = options.get("kinds", ["summary", "detailed"])
    decks = build_decks(
        topics, overview, doc_name, kinds,
        summary_target=int(options.get("summary_slides", settings.summary_slides_default)),
        detailed_target=int(options.get("detailed_slides", settings.detailed_slides_default)),
        include_notes=bool(options.get("include_notes", True)),
    )
    labels = state.get("labels") or ["mock"]
    ai_names = sorted({lbl.split("+")[0] for lbl in labels if lbl != "mock"})
    if not ai_names:
        provider_used = "mock"
    else:
        provider_used = ai_names[0] + ("+fallback" if any(lbl == "mock" or "+fallback" in lbl for lbl in labels) else "")
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
        state["phase"] = "done"
        job.state = dict(state)
        job.status, job.stage, job.progress = "completed", "completed", 100
        job.message = "Your presentations are ready"
        job.provider_used = provider_used
        job.warnings = state.get("warnings", [])


# ---------------------------------------------------------------------------
# Self-hosted mode: one background thread drives the job to completion
# ---------------------------------------------------------------------------
def run_job(job_id: str) -> None:
    while True:
        with session_scope() as db:
            job = db.get(Job, job_id)
            if job is None or job.status not in ("queued", "running"):
                return
        if not advance(job_id, time_limit=600):
            time.sleep(1)  # another worker holds the lease


def submit(job_id: str) -> None:
    _executor.submit(run_job, job_id)
