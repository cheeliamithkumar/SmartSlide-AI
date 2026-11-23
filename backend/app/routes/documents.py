"""PDF upload, information and content extraction endpoints."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import Document
from app.schemas import DocumentOut, ExtractionResult
from app.services import blob, storage
from app.services.cleanup import delete_document_files
from app.services.pdf_extractor import PDFValidationError, inspect_pdf, validate_pdf_bytes
from app.utils.files import safe_filename

router = APIRouter(prefix="/api/documents", tags=["documents"])

ALLOWED_TYPES = {"application/pdf", "application/x-pdf", "application/octet-stream", ""}


def get_document_or_404(document_id: str, db: Session) -> Document:
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return doc


async def _read_limited(file: UploadFile, limit: int) -> bytes:
    buf = bytearray()
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        buf.extend(chunk)
        if len(buf) > limit:
            raise HTTPException(413,
                                f"File is too large. Maximum size is {get_settings().max_upload_mb} MB.")
    return bytes(buf)


async def _ingest(data: bytes, name: str, db: Session) -> Document:
    """Validate, store and inspect PDF bytes; create the Document row."""
    settings = get_settings()
    try:
        await run_in_threadpool(validate_pdf_bytes, data)
    except PDFValidationError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc

    doc_id = uuid.uuid4().hex
    path = settings.uploads_dir / f"{doc_id}.pdf"  # never use the user-provided name on disk
    path.write_bytes(data)
    try:
        info = await run_in_threadpool(inspect_pdf, path)
    except Exception as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The PDF could not be processed.") from exc

    doc = Document(
        id=doc_id, original_filename=name, stored_path=str(path), size_bytes=len(data),
        page_count=info.page_count, title=info.title, author=info.author, is_scanned=info.is_scanned,
        text_pages=info.text_pages, empty_pages=info.empty_pages, word_count=info.word_count,
    )
    if settings.serverless:
        # the uploaded file only exists on this instance: extract now and keep the text in the DB
        try:
            await run_in_threadpool(storage.get_or_extract, doc)
        except Exception as exc:
            path.unlink(missing_ok=True)
            raise HTTPException(400, "The PDF could not be processed.") from exc
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def _check_name(filename: str | None) -> str:
    name = safe_filename(filename)
    if not name.lower().endswith(".pdf"):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Only PDF files are supported.")
    return name


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(file: UploadFile = File(...), db: Session = Depends(get_db)):
    settings = get_settings()
    name = _check_name(file.filename)
    if (file.content_type or "") not in ALLOWED_TYPES:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Only PDF files are supported.")
    data = await _read_limited(file, settings.max_upload_bytes)
    return await _ingest(data, name, db)


class BlobUploadRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    size: int = Field(gt=0)


class BlobDocumentRequest(BaseModel):
    url: str = Field(min_length=10, max_length=1000)
    filename: str = Field(min_length=1, max_length=255)


@router.post("/upload-token")
def create_upload_token(payload: BlobUploadRequest):
    """Issue a short-lived token so the browser can upload a large PDF directly to private storage."""
    settings = get_settings()
    if not blob.enabled():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Direct uploads are not enabled on this server.")
    _check_name(payload.filename)
    if payload.size > settings.max_upload_bytes:
        raise HTTPException(413, f"File is too large. Maximum size is {settings.max_upload_mb} MB.")
    pathname = f"uploads/{uuid.uuid4().hex}.pdf"
    return {"token": blob.client_token(pathname, settings.max_upload_bytes), "pathname": pathname,
            "access": "private"}


@router.post("/from-blob", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def create_from_blob(payload: BlobDocumentRequest, db: Session = Depends(get_db)):
    """Import a PDF the browser uploaded to Vercel Blob; the temporary blob is deleted afterwards."""
    settings = get_settings()
    if not blob.enabled():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Direct uploads are not enabled on this server.")
    name = _check_name(payload.filename)
    if not blob.is_allowed_url(payload.url):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid upload reference.")
    try:
        data = await run_in_threadpool(blob.download, payload.url, settings.max_upload_bytes)
    except blob.BlobError as exc:
        code = 413 if "too large" in str(exc) else 400
        raise HTTPException(code, str(exc)) from exc
    finally:
        await run_in_threadpool(blob.delete, payload.url)
    return await _ingest(data, name, db)


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(document_id: str, db: Session = Depends(get_db)):
    return get_document_or_404(document_id, db)


@router.get("/{document_id}/content", response_model=ExtractionResult)
async def get_content(
    document_id: str,
    page_from: int | None = Query(default=None, ge=1),
    page_to: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
):
    """Extract (and cache) page-wise text, including OCR for scanned pages."""
    doc = get_document_or_404(document_id, db)
    try:
        result = await run_in_threadpool(storage.get_or_extract, doc)
    except FileNotFoundError as exc:
        raise HTTPException(410, str(exc)) from exc
    db.commit()
    if page_from or page_to:
        lo, hi = page_from or 1, page_to or result.page_count
        if lo > hi:
            raise HTTPException(422, "page_from must be <= page_to")
        result = result.model_copy(update={"pages": [p for p in result.pages if lo <= p.page <= hi]})
    return result


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: str, db: Session = Depends(get_db)):
    doc = get_document_or_404(document_id, db)
    delete_document_files(doc)
    db.delete(doc)
    db.commit()
