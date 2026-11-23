"""Test configuration: isolated storage, offline AI provider, sample PDFs."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

import pytest

# Configure the environment BEFORE the app is imported.
_TMP = Path(tempfile.mkdtemp(prefix="smartslide-test-"))
os.environ.update({
    "ENVIRONMENT": "test",
    "STORAGE_DIR": str(_TMP / "storage"),
    "AI_PROVIDER": "mock",
    "MAX_UPLOAD_MB": "5",
    "MAX_PAGES": "40",
    "ANTHROPIC_API_KEY": "",
    "GEMINI_API_KEY": "",
})

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "scripts"))

import make_sample_pdf  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def samples() -> dict[str, Path]:
    out = _TMP / "samples"
    make_sample_pdf.main(out)
    return {
        "text": out / "photosynthesis.pdf",
        "scanned": out / "photosynthesis_scanned.pdf",
        "empty": out / "empty.pdf",
    }


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


def upload(client, path: Path, name: str | None = None, content_type: str = "application/pdf"):
    with open(path, "rb") as fh:
        return client.post("/api/documents", files={"file": (name or path.name, fh, content_type)})


def wait_for_job(client, job_id: str, timeout: float = 90.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = client.get(f"/api/jobs/{job_id}").json()
        if data["status"] in ("completed", "failed"):
            return data
        time.sleep(0.2)
    raise AssertionError(f"Job {job_id} did not finish in {timeout}s")


@pytest.fixture(scope="session")
def completed_job(client, samples) -> dict:
    """Upload the sample PDF and run a full conversion once for the session."""
    doc = upload(client, samples["text"]).json()
    resp = client.post("/api/jobs", json={"document_id": doc["id"], "kinds": ["summary", "detailed"],
                                          "template": "professional_blue", "summary_slides": 12,
                                          "detailed_slides": 24})
    assert resp.status_code == 202, resp.text
    job = wait_for_job(client, resp.json()["id"])
    assert job["status"] == "completed", job
    return job


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_TMP, ignore_errors=True)
