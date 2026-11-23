"""Serverless mode (e.g. Vercel): inline jobs and no reliance on local files between requests."""
from pathlib import Path

import pytest

from app.config import get_settings
from app.database import session_scope
from app.models import Document
from tests.conftest import upload


@pytest.fixture
def serverless(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "serverless", True)
    yield s


def test_postgres_url_normalised(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "database_url", "")
    monkeypatch.setattr(s, "postgres_url", "postgres://u:p@host/db?sslmode=require")
    assert s.resolved_database_url == "postgresql+psycopg://u:p@host/db?sslmode=require"


def test_serverless_flow_without_local_files(client, samples, serverless):
    doc = upload(client, samples["text"]).json()

    # simulate a different server instance: uploaded PDF and file cache are gone
    with session_scope() as db:
        d = db.get(Document, doc["id"])
        assert d.extraction and d.extraction["page_count"] == 3  # text persisted in the DB
        Path(d.stored_path).unlink()
    (serverless.extracted_dir / f"{doc['id']}.json").unlink(missing_ok=True)

    # creating the job returns immediately; the client then drives it with short /advance calls
    r = client.post("/api/jobs", json={"document_id": doc["id"]})
    assert r.status_code == 202
    job = r.json()
    assert job["status"] == "queued"
    for _ in range(20):
        job = client.post(f"/api/jobs/{job['id']}/advance").json()
        if job["status"] in ("completed", "failed"):
            break
    assert job["status"] == "completed", job
    pres_id = job["presentations"][0]["id"]

    # regeneration works from the DB-stored text
    pres = client.get(f"/api/presentations/{pres_id}").json()
    target = next(s for s in pres["slides"] if s["type"] == "content" and s["source_pages"])
    assert client.post(f"/api/presentations/{pres_id}/slides/{target['id']}/regenerate").status_code == 200

    # download re-renders when the generated file is missing on this instance
    for f in serverless.outputs_dir.glob(f"{pres_id}*.pptx"):
        f.unlink()
    r = client.get(f"/api/presentations/{pres_id}/download")
    assert r.status_code == 200 and len(r.content) > 10000
    assert client.get("/api/health").json()["serverless"] is True


def test_advance_is_resumable_and_single_worker(client, samples, serverless, monkeypatch):
    from app.services import jobs

    doc = upload(client, samples["text"]).json()
    job = client.post("/api/jobs", json={"document_id": doc["id"]}).json()
    # a held lease makes advance a no-op (another worker is busy)
    assert jobs._acquire(job["id"]) is True
    assert jobs._acquire(job["id"]) is False
    assert client.post(f"/api/jobs/{job['id']}/advance").json()["status"] == "queued"
    jobs._release(job["id"])
    # tiny steps: each advance does one unit and saves progress, so it resumes across calls
    monkeypatch.setattr(serverless, "job_step_seconds", 0.01)
    stages = []
    for _ in range(20):
        j = client.post(f"/api/jobs/{job['id']}/advance").json()
        stages.append(j["stage"])
        if j["status"] == "completed":
            break
    assert j["status"] == "completed", (stages, j)
    assert "analyzing" in stages and "composing" in stages
    assert len(stages) >= 3  # analyze -> overview -> compose took separate requests
