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
    monkeypatch.setattr(s, "jobs_sync", None)
    yield s


def test_postgres_url_normalised(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "database_url", "")
    monkeypatch.setattr(s, "postgres_url", "postgres://u:p@host/db?sslmode=require")
    assert s.resolved_database_url == "postgresql+psycopg://u:p@host/db?sslmode=require"


def test_serverless_flow_without_local_files(client, samples, serverless):
    assert serverless.run_jobs_inline
    doc = upload(client, samples["text"]).json()

    # simulate a different server instance: uploaded PDF and file cache are gone
    with session_scope() as db:
        d = db.get(Document, doc["id"])
        assert d.extraction and d.extraction["page_count"] == 3  # text persisted in the DB
        Path(d.stored_path).unlink()
    (serverless.extracted_dir / f"{doc['id']}.json").unlink(missing_ok=True)

    # job runs inside the request and is already complete in the response
    r = client.post("/api/jobs", json={"document_id": doc["id"]})
    assert r.status_code == 202
    job = r.json()
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
