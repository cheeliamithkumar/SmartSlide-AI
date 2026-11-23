"""Presentation preview, editing and download endpoints."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Document, Presentation
from app.schemas import PresentationOut, PresentationUpdate, Slide, SlideOrder, SlideType, SlideUpdate
from app.services import storage
from app.services.ai.base import AIProviderError
from app.services.ai.factory import get_provider
from app.services.templates import THEMES

router = APIRouter(prefix="/api/presentations", tags=["presentations"])

PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


def _get(pres_id: str, db: Session) -> Presentation:
    pres = db.get(Presentation, pres_id)
    if pres is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Presentation not found")
    return pres


def _out(pres: Presentation) -> PresentationOut:
    return PresentationOut(
        id=pres.id, document_id=pres.document_id, job_id=pres.job_id, kind=pres.kind, template=pres.template,
        title=pres.title, slides=[Slide.model_validate(s) for s in pres.slides], version=pres.version,
        document_name=pres.document.original_filename, updated_at=pres.updated_at,
    )


def _slides(pres: Presentation) -> list[Slide]:
    return [Slide.model_validate(s) for s in pres.slides]


def _save(pres: Presentation, slides: list[Slide], db: Session) -> None:
    if not slides:
        raise HTTPException(422, "A presentation must contain at least one slide.")
    ids = [s.id for s in slides]
    if len(ids) != len(set(ids)):
        raise HTTPException(422, "Slide ids must be unique.")
    pres.slides = [s.model_dump(mode="json") for s in slides]
    pres.dirty = True
    pres.version += 1
    db.commit()
    db.refresh(pres)


def _index(slides: list[Slide], slide_id: str) -> int:
    for i, s in enumerate(slides):
        if s.id == slide_id:
            return i
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Slide not found")


def _visible(s: Slide) -> str:
    """The parts of a slide that are actually shown, used to detect a no-op regeneration."""
    return s.model_dump_json(include={"title", "subtitle", "bullets", "definitions", "steps", "comparison", "diagram"})


@router.get("/{pres_id}", response_model=PresentationOut)
def get_presentation(pres_id: str, db: Session = Depends(get_db)):
    return _out(_get(pres_id, db))


@router.patch("/{pres_id}", response_model=PresentationOut)
def update_presentation(pres_id: str, payload: PresentationUpdate, db: Session = Depends(get_db)):
    """Update title / template and/or replace the full slide list (edits, deletions, reordering)."""
    pres = _get(pres_id, db)
    if payload.template is not None:
        if payload.template not in THEMES:
            raise HTTPException(422, f"Unknown template '{payload.template}'")
        pres.template = payload.template
        pres.dirty = True
    if payload.title is not None:
        pres.title = payload.title.strip()
    slides = payload.slides if payload.slides is not None else _slides(pres)
    if payload.title is not None and slides and slides[0].type == SlideType.title and payload.slides is None:
        slides[0].title = pres.title
    _save(pres, slides, db)
    return _out(pres)


@router.patch("/{pres_id}/slides/{slide_id}", response_model=Slide)
def update_slide(pres_id: str, slide_id: str, payload: SlideUpdate, db: Session = Depends(get_db)):
    pres = _get(pres_id, db)
    slides = _slides(pres)
    i = _index(slides, slide_id)
    merged = slides[i].model_dump()
    merged.update(payload.model_dump(exclude_unset=True))
    slides[i] = Slide.model_validate(merged)
    _save(pres, slides, db)
    return slides[i]


@router.delete("/{pres_id}/slides/{slide_id}", response_model=PresentationOut)
def delete_slide(pres_id: str, slide_id: str, db: Session = Depends(get_db)):
    pres = _get(pres_id, db)
    slides = _slides(pres)
    i = _index(slides, slide_id)
    if len(slides) == 1:
        raise HTTPException(422, "Cannot delete the last remaining slide.")
    slides.pop(i)
    _save(pres, slides, db)
    return _out(pres)


@router.put("/{pres_id}/slides/order", response_model=PresentationOut)
def reorder_slides(pres_id: str, payload: SlideOrder, db: Session = Depends(get_db)):
    pres = _get(pres_id, db)
    slides = _slides(pres)
    by_id = {s.id: s for s in slides}
    if sorted(payload.order) != sorted(by_id):
        raise HTTPException(422, "Order must contain every slide id exactly once.")
    _save(pres, [by_id[i] for i in payload.order], db)
    return _out(pres)


@router.post("/{pres_id}/slides", response_model=PresentationOut, status_code=status.HTTP_201_CREATED)
def add_slide(pres_id: str, slide: Slide, after: str | None = None, db: Session = Depends(get_db)):
    pres = _get(pres_id, db)
    slides = _slides(pres)
    new = Slide.model_validate(slide.model_dump(exclude={"id"}))
    pos = _index(slides, after) + 1 if after else len(slides)
    slides.insert(pos, new)
    _save(pres, slides, db)
    return _out(pres)


@router.post("/{pres_id}/slides/{slide_id}/regenerate", response_model=Slide)
async def regenerate_slide(pres_id: str, slide_id: str, db: Session = Depends(get_db)):
    pres = _get(pres_id, db)
    slides = _slides(pres)
    i = _index(slides, slide_id)
    slide = slides[i]
    if slide.type == SlideType.title:
        raise HTTPException(422, "Title slides cannot be regenerated.")
    doc: Document = pres.document
    pages = slide.source_pages
    if not pages:
        raise HTTPException(422,
                            "This slide has no source pages, so it cannot be regenerated. Edit it manually instead.")
    source = await run_in_threadpool(storage.source_text_for_pages, doc.id, pages, doc)
    if not source.strip():
        raise HTTPException(status.HTTP_409_CONFLICT, "The source text for this slide is no longer available.")
    # keep regeneration well under proxy/serverless request limits
    provider = get_provider((pres.job.options or {}).get("provider") if pres.job else None, time_budget=40)
    base_ctx = {"kind": pres.kind, "doc_name": doc.original_filename,
                "audience": (pres.job.options or {}).get("audience", "students") if pres.job else "students"}
    new = None
    # try a few variations until the visible content actually changes
    for attempt in range(3):
        try:
            cand = await run_in_threadpool(provider.regenerate_slide, slide, source,
                                           {**base_ctx, "variant": pres.version + attempt})
        except AIProviderError as exc:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"AI provider unavailable: {exc}") from exc
        cand.id, cand.type, cand.source_pages = slide.id, slide.type, slide.source_pages
        if cand.diagram is None:
            cand.diagram = slide.diagram  # keep the slide's visual when the AI rewrites the text
        if _visible(cand) != _visible(slide):
            new = cand
            break
    if new is None:
        raise HTTPException(409, "No alternative content was found in this slide's source pages. "
                                 "Try editing it manually instead.")
    slides[i] = new
    _save(pres, slides, db)
    return new


@router.get("/{pres_id}/download")
async def download(pres_id: str, db: Session = Depends(get_db)):
    """Download the PPTX. Re-rendered on demand if the slides were edited."""
    pres = _get(pres_id, db)
    doc = pres.document
    path = Path(pres.file_path) if pres.file_path else None
    if pres.dirty or path is None or not path.exists():
        path = await run_in_threadpool(storage.render, pres, doc)
        db.commit()
    return FileResponse(path, media_type=PPTX_MIME, filename=storage.download_name(pres, doc),
                        headers={"Cache-Control": "no-store"})
