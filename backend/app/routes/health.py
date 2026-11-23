from fastapi import APIRouter

from app import __version__
from app.config import get_settings
from app.services.ai.factory import provider_status
from app.services.pdf_extractor import tesseract_available
from app.services.templates import list_themes

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/health")
def health():
    s = get_settings()
    return {
        "status": "ok",
        "app": s.app_name,
        "version": __version__,
        "ai_provider": s.ai_provider,
        "ocr_available": s.ocr_enabled and tesseract_available(),
        "limits": {"max_upload_mb": s.max_upload_mb, "max_pages": s.max_pages},
    }


@router.get("/templates")
def templates():
    return list_themes()


@router.get("/providers")
def providers():
    return provider_status()
