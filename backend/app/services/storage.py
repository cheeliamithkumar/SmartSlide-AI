"""Persistence helpers for extracted text and rendered presentations."""
from __future__ import annotations

import json
from pathlib import Path

from app.config import get_settings
from app.models import Document, Presentation
from app.schemas import ExtractionResult, Slide
from app.services.pptx_builder import render_presentation
from app.utils.files import slugify


def extraction_path(document_id: str) -> Path:
    return get_settings().extracted_dir / f"{document_id}.json"


def save_extraction(document_id: str, result: ExtractionResult) -> None:
    path = extraction_path(document_id)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(result.model_dump_json(), encoding="utf-8")
    tmp.replace(path)


def load_extraction(document_id: str) -> ExtractionResult | None:
    path = extraction_path(document_id)
    if not path.exists():
        return None
    try:
        return ExtractionResult.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (ValueError, OSError):
        return None


def extraction_from_doc(doc: Document) -> ExtractionResult | None:
    if doc.extraction:
        try:
            return ExtractionResult.model_validate(doc.extraction)
        except ValueError:
            return None
    return None


def get_or_extract(doc: Document) -> ExtractionResult:
    """Return the cached extraction (file or database), extracting the PDF if needed.

    The result is stored on the Document row as well, so that stateless/serverless
    instances that do not have the uploaded file can still process the document.
    """
    from app.services.pdf_extractor import extract_pdf

    cached = load_extraction(doc.id) or extraction_from_doc(doc)
    if cached is None:
        path = Path(doc.stored_path)
        if not path.exists():
            raise FileNotFoundError("The uploaded PDF has expired. Please upload it again.")
        cached = extract_pdf(path)
        save_extraction(doc.id, cached)
    if not doc.extraction:
        doc.extraction = cached.model_dump(mode="json")
    return cached


def source_text_for_pages(document_id: str, pages: list[int], doc: Document | None = None) -> str:
    extraction = load_extraction(document_id)
    if extraction is None and doc is not None:
        try:
            extraction = get_or_extract(doc)
        except FileNotFoundError:
            return ""
    if extraction is None:
        return ""
    wanted = set(pages)
    parts = [f"[Page {p.page}]\n{p.text}" for p in extraction.pages if (not wanted or p.page in wanted) and p.text]
    return "\n\n".join(parts)


def output_path(pres: Presentation) -> Path:
    return get_settings().outputs_dir / f"{pres.id}.pptx"


def download_name(pres: Presentation, doc: Document) -> str:
    stem = doc.original_filename.rsplit(".", 1)[0]
    return f"{slugify(stem)}-{pres.kind}.pptx"


def render(pres: Presentation, doc: Document) -> Path:
    slides = [Slide.model_validate(s) for s in pres.slides]
    path = render_presentation(slides, pres.template, doc.original_filename, pres.kind, output_path(pres))
    pres.file_path = str(path)
    pres.dirty = False
    return path
