"""Direct (Vercel Blob) uploads for large PDFs."""
import pytest

from app.config import get_settings
from app.services import blob
from tests.conftest import wait_for_job

RW = "vercel_blob_rw_TestStore123_secretpart"
# Produced by the official SDK: generateClientTokenFromReadWriteToken({token: RW, pathname: 'uploads/abc.pdf',
#   maximumSizeInBytes: 26214400, allowedContentTypes: ['application/pdf'], addRandomSuffix: true,
#   validUntil: 1900000000000})  (@vercel/blob 2.9.0)
SDK_TOKEN = "vercel_blob_client_TestStore123_ZWU5OTA3ZDczNDRjOWVjZjJjMDFhNTdiZDgzYTUxNzU0ZDAxZDRiZDlmMDY2MGZhZTMxZGQ0M2U2NGRjYTllYS5leUp3WVhSb2JtRnRaU0k2SW5Wd2JHOWhaSE12WVdKakxuQmtaaUlzSW0xaGVHbHRkVzFUYVhwbFNXNUNlWFJsY3lJNk1qWXlNVFEwTURBc0ltRnNiRzkzWldSRGIyNTBaVzUwVkhsd1pYTWlPbHNpWVhCd2JHbGpZWFJwYjI0dmNHUm1JbDBzSW1Ga1pGSmhibVJ2YlZOMVptWnBlQ0k2ZEhKMVpTd2lkbUZzYVdSVmJuUnBiQ0k2TVRrd01EQXdNREF3TURBd01IMD0="


@pytest.fixture
def blob_enabled(monkeypatch):
    monkeypatch.setattr(get_settings(), "blob_read_write_token", RW)
    yield


def test_client_token_matches_official_sdk():
    assert blob.client_token("uploads/abc.pdf", 26214400, token=RW, valid_until_ms=1900000000000) == SDK_TOKEN


def test_direct_upload_disabled_without_token(client):
    assert client.get("/api/health").json()["direct_upload"] is False
    r = client.post("/api/documents/upload-token", json={"filename": "a.pdf", "size": 10})
    assert r.status_code == 404


def test_upload_token_validation(client, blob_enabled):
    assert client.get("/api/health").json()["direct_upload"] is True
    r = client.post("/api/documents/upload-token", json={"filename": "notes.pdf", "size": 1024})
    assert r.status_code == 200
    body = r.json()
    assert body["pathname"].startswith("uploads/") and body["access"] == "private"
    assert body["token"].startswith("vercel_blob_client_TestStore123_")
    assert client.post("/api/documents/upload-token", json={"filename": "x.exe", "size": 10}).status_code == 415
    too_big = get_settings().max_upload_bytes + 1
    assert client.post("/api/documents/upload-token", json={"filename": "a.pdf", "size": too_big}).status_code == 413


@pytest.mark.parametrize("url", [
    "https://evil.example.com/uploads/a.pdf",
    "https://otherstore.private.blob.vercel-storage.com/uploads/a.pdf",
    "http://teststore123.private.blob.vercel-storage.com/uploads/a.pdf",
    "https://teststore123.private.blob.vercel-storage.com/secret/a.pdf",
])
def test_rejects_foreign_or_unsafe_urls(client, blob_enabled, url):
    r = client.post("/api/documents/from-blob", json={"url": url, "filename": "a.pdf"})
    assert r.status_code == 400


def test_import_from_blob_end_to_end(client, samples, blob_enabled, monkeypatch):
    data = samples["text"].read_bytes()
    deleted = []
    monkeypatch.setattr(blob, "download", lambda url, max_bytes: data)
    monkeypatch.setattr(blob, "delete", lambda url: deleted.append(url))
    url = "https://teststore123.private.blob.vercel-storage.com/uploads/abc-XyZ.pdf"
    r = client.post("/api/documents/from-blob", json={"url": url, "filename": "big-notes.pdf"})
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["page_count"] == 3 and doc["original_filename"] == "big-notes.pdf"
    assert deleted == [url]  # temporary blob removed
    job = wait_for_job(client, client.post("/api/jobs", json={"document_id": doc["id"]}).json()["id"])
    assert job["status"] == "completed"


def test_blob_is_deleted_even_when_invalid(client, blob_enabled, monkeypatch):
    deleted = []
    monkeypatch.setattr(blob, "download", lambda url, max_bytes: b"not a pdf at all" * 10)
    monkeypatch.setattr(blob, "delete", lambda url: deleted.append(url))
    url = "https://teststore123.private.blob.vercel-storage.com/uploads/bad.pdf"
    r = client.post("/api/documents/from-blob", json={"url": url, "filename": "bad.pdf"})
    assert r.status_code == 415
    assert deleted == [url]


def test_download_sends_auth_and_enforces_size(blob_enabled):
    import httpx

    seen = {}

    def handler(request):
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, content=b"x" * 5000)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    url = "https://teststore123.private.blob.vercel-storage.com/uploads/a.pdf"
    assert len(blob.download(url, 10000, client=client)) == 5000
    assert seen["auth"] == f"Bearer {RW}"
    with pytest.raises(blob.BlobError, match="too large"):
        blob.download(url, 1000, client=client)
