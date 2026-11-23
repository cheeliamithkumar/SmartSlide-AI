"""Periodic cleanup of expired uploads, extracted text and generated files."""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select

from app.config import get_settings
from app.database import session_scope
from app.models import Document
from app.services.storage import extraction_path
from app.utils.files import safe_unlink

logger = logging.getLogger(__name__)


def delete_document_files(doc: Document) -> None:
    settings = get_settings()
    safe_unlink(doc.stored_path, settings.uploads_dir)
    safe_unlink(extraction_path(doc.id), settings.extracted_dir)
    for pres in doc.presentations:
        safe_unlink(pres.file_path, settings.outputs_dir)


def cleanup_expired(now: datetime | None = None) -> int:
    """Delete documents (and their jobs/presentations/files) older than the retention period."""
    settings = get_settings()
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=settings.file_retention_hours)
    removed = 0
    with session_scope() as db:
        for doc in db.scalars(select(Document)).all():
            created = doc.created_at if doc.created_at.tzinfo else doc.created_at.replace(tzinfo=timezone.utc)
            if created < cutoff:
                delete_document_files(doc)
                db.delete(doc)
                removed += 1
    # orphaned temp files (e.g. interrupted writes)
    for folder in (settings.uploads_dir, settings.outputs_dir, settings.extracted_dir):
        for f in folder.glob("*.tmp*"):
            try:
                if datetime.fromtimestamp(f.stat().st_mtime, timezone.utc) < cutoff:
                    safe_unlink(f, folder)
            except OSError:
                pass
    if removed:
        logger.info("Cleanup removed %s expired document(s)", removed)
    return removed


class CleanupThread(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True, name="smartslide-cleanup")
        self._stop_event = threading.Event()

    def run(self):  # pragma: no cover - timing based
        interval = max(60.0, get_settings().cleanup_interval_minutes * 60)
        while not self._stop_event.wait(interval):
            try:
                cleanup_expired()
            except Exception:
                logger.exception("Cleanup failed")

    def stop(self):
        self._stop_event.set()
