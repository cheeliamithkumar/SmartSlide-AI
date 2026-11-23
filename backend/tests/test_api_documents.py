"""Health, upload, validation and extraction endpoints."""
import io

import pymupdf
import pytest

from app.services.pdf_extractor import tesseract_available
from tests.conftest import upload, wait_for_job


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["ai_provider"] == "mock"
    assert body["limits"]["max_upload_mb"] == 5


def test_templates_listed(client):
    r = client.get("/api/templates")
    ids = {t["id"] for t in r.json()}
    assert ids == {"modern_education", "minimal_white", "professional_blue", "dark_academic"}


def test_upload_valid_pdf(client, samples):
    r = upload(client, samples["text"])
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["page_count"] == 3
    assert doc["original_filename"] == "photosynthesis.pdf"
    assert doc["word_count"] > 500
    assert doc["is_scanned"] is False
    assert "stored_path" not in doc  # server paths are never exposed
    assert client.get(f"/api/documents/{doc['id']}").status_code == 200


def test_upload_rejects_non_pdf_extension(client):
    r = client.post("/api/documents", files={"file": ("notes.txt", b"hello world", "text/plain")})
    assert r.status_code == 415


def test_upload_rejects_fake_pdf(client):
    r = client.post("/api/documents", files={"file": ("fake.pdf", b"this is not a pdf" * 20, "application/pdf")})
    assert r.status_code == 415
    assert "not a valid PDF" in r.json()["detail"]


def test_upload_rejects_corrupted_pdf(client):
    r = client.post("/api/documents", files={"file": ("broken.pdf", b"%PDF-1.7\n garbage", "application/pdf")})
    assert r.status_code == 400


def test_upload_rejects_empty_file(client):
    r = client.post("/api/documents", files={"file": ("empty.pdf", b"", "application/pdf")})
    assert r.status_code == 400


def test_upload_rejects_too_large(client):
    big = b"%PDF-1.4\n" + b"0" * (6 * 1024 * 1024)
    r = client.post("/api/documents", files={"file": ("big.pdf", big, "application/pdf")})
    assert r.status_code == 413


def test_upload_rejects_too_many_pages(client):
    doc = pymupdf.open()
    for _ in range(41):
        doc.new_page()
    data = doc.tobytes()
    r = client.post("/api/documents", files={"file": ("long.pdf", data, "application/pdf")})
    assert r.status_code == 413
    assert "maximum" in r.json()["detail"].lower()


def test_upload_rejects_encrypted_pdf(client):
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "secret")
    buf = io.BytesIO()
    doc.save(buf, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="pw", owner_pw="pw")
    r = client.post("/api/documents", files={"file": ("locked.pdf", buf.getvalue(), "application/pdf")})
    assert r.status_code == 400
    assert "password" in r.json()["detail"].lower()


def test_upload_sanitizes_filename(client, samples):
    r = upload(client, samples["text"], name="../../etc/<evil>name.pdf")
    assert r.status_code == 201
    name = r.json()["original_filename"]
    assert "/" not in name and "<" not in name and ".." not in name


def test_content_extraction(client, samples):
    doc = upload(client, samples["text"]).json()
    r = client.get(f"/api/documents/{doc['id']}/content")
    assert r.status_code == 200
    data = r.json()
    assert data["page_count"] == 3
    assert [p["page"] for p in data["pages"]] == [1, 2, 3]
    all_headings = [h for p in data["pages"] for h in p["headings"]]
    assert "The Calvin Cycle" in all_headings
    assert "Photosynthesis: How Plants Make Food" in all_headings  # multi-line heading merged
    assert "light-dependent" in data["pages"][0]["text"].lower()
    # page range filter
    r2 = client.get(f"/api/documents/{doc['id']}/content", params={"page_from": 2, "page_to": 2})
    assert [p["page"] for p in r2.json()["pages"]] == [2]


def test_empty_pdf_is_reported_and_job_fails_gracefully(client, samples):
    doc = upload(client, samples["empty"]).json()
    assert doc["empty_pages"] == 2
    content = client.get(f"/api/documents/{doc['id']}/content").json()
    assert content["empty_pages"] == [1, 2]
    assert any("no readable text" in w for w in content["warnings"])
    job = client.post("/api/jobs", json={"document_id": doc["id"]}).json()
    final = wait_for_job(client, job["id"])
    assert final["status"] == "failed"
    assert "readable text" in final["error"]


@pytest.mark.skipif(not tesseract_available(), reason="Tesseract not installed")
def test_scanned_pdf_uses_ocr(client, samples):
    doc = upload(client, samples["scanned"]).json()
    assert doc["is_scanned"] is True
    content = client.get(f"/api/documents/{doc['id']}/content").json()
    assert content["ocr_pages"] == [1, 2]
    assert "photosynthesis" in content["pages"][0]["text"].lower()
    assert all(p["method"] == "ocr" for p in content["pages"])


def test_unknown_document_404(client):
    assert client.get("/api/documents/doesnotexist").status_code == 404
    r = client.post("/api/jobs", json={"document_id": "doesnotexist"})
    assert r.status_code == 404


def test_job_validation(client, samples):
    doc = upload(client, samples["text"]).json()
    r = client.post("/api/jobs", json={"document_id": doc["id"], "template": "nope"})
    assert r.status_code == 422
    r = client.post("/api/jobs", json={"document_id": doc["id"], "kinds": []})
    assert r.status_code == 422
    r = client.post("/api/jobs", json={"document_id": doc["id"], "summary_slides": 99})
    assert r.status_code == 422


def test_delete_document(client, samples):
    doc = upload(client, samples["text"]).json()
    assert client.delete(f"/api/documents/{doc['id']}").status_code == 204
    assert client.get(f"/api/documents/{doc['id']}").status_code == 404
