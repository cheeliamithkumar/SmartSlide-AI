"""Vercel Blob direct uploads (lets the browser upload large PDFs straight to storage).

Serverless functions on Vercel accept request bodies of at most ~4.5 MB. For larger
files the browser uploads the PDF directly to a *private* Vercel Blob store using a
short-lived client token issued here; the backend then downloads it once, deletes it,
and processes it like a normal upload.

The client-token format mirrors ``generateClientTokenFromReadWriteToken`` from the
official ``@vercel/blob`` SDK (verified by a parity test).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
from urllib.parse import urlparse

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

API_URL = "https://vercel.com/api/blob"
API_VERSION = "13"


class BlobError(RuntimeError):
    pass


def _token() -> str:
    return get_settings().blob_read_write_token or ""


def enabled() -> bool:
    return bool(_token())


def store_id(token: str | None = None) -> str:
    parts = (token if token is not None else _token()).split("_")
    return parts[3] if len(parts) > 3 else ""


def client_token(pathname: str, max_bytes: int, valid_seconds: int = 300, *, token: str | None = None,
                 valid_until_ms: int | None = None) -> str:
    """Create a client upload token restricted to one pathname, PDF content and a max size."""
    rw = token if token is not None else _token()
    sid = store_id(rw)
    if not sid:
        raise BlobError("Vercel Blob is not configured")
    args = {
        "pathname": pathname,
        "maximumSizeInBytes": max_bytes,
        "allowedContentTypes": ["application/pdf"],
        "addRandomSuffix": True,
        "validUntil": valid_until_ms if valid_until_ms is not None else int((time.time() + valid_seconds) * 1000),
    }
    payload = base64.b64encode(json.dumps(args, separators=(",", ":")).encode()).decode()
    signature = hmac.new(rw.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"vercel_blob_client_{sid}_{base64.b64encode(f'{signature}.{payload}'.encode()).decode()}"


def is_allowed_url(url: str) -> bool:
    """Only accept blobs from *our* store, inside the uploads/ folder (prevents SSRF)."""
    try:
        u = urlparse(url)
    except ValueError:
        return False
    sid = store_id().lower()
    host = (u.hostname or "").lower()
    return (u.scheme == "https" and bool(sid) and host.startswith(f"{sid}.")
            and host.endswith(".blob.vercel-storage.com") and u.path.startswith("/uploads/"))


def download(url: str, max_bytes: int, client: httpx.Client | None = None) -> bytes:
    if not is_allowed_url(url):
        raise BlobError("Invalid upload reference")
    c = client or httpx.Client(timeout=60)
    buf = bytearray()
    with c.stream("GET", url, headers={"authorization": f"Bearer {_token()}"}) as r:
        if r.status_code != 200:
            raise BlobError(f"Could not read the uploaded file (HTTP {r.status_code})")
        for chunk in r.iter_bytes():
            buf.extend(chunk)
            if len(buf) > max_bytes:
                raise BlobError("File is too large")
    return bytes(buf)


def delete(url: str, client: httpx.Client | None = None) -> None:
    """Best-effort removal of the temporary upload."""
    try:
        c = client or httpx.Client(timeout=20)
        c.post(f"{API_URL}/delete", json={"urls": [url]},
               headers={"authorization": f"Bearer {_token()}", "x-api-version": API_VERSION})
    except Exception as exc:  # pragma: no cover - network
        logger.warning("Could not delete temporary blob: %s", exc)
