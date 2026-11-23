"""Conversion job endpoints (AI processing + presentation generation)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Document, Job
from app.schemas import JobCreate, JobOut, PresentationBrief
from app.services import jobs as job_service
from app.services.templates import THEMES

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def job_out(job: Job) -> JobOut:
    return JobOut(
        id=job.id, document_id=job.document_id, status=job.status, stage=job.stage,
        progress=round(job.progress, 1), message=job.message, error=job.error, provider_used=job.provider_used,
        warnings=job.warnings or [], options=job.options or {},
        presentations=[
            PresentationBrief(id=p.id, kind=p.kind, title=p.title, template=p.template, slide_count=len(p.slides or []))
            for p in sorted(job.presentations, key=lambda p: p.kind != "summary")
        ],
        created_at=job.created_at, updated_at=job.updated_at,
    )


@router.post("", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
def create_job(payload: JobCreate, db: Session = Depends(get_db)):
    doc = db.get(Document, payload.document_id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    if payload.template not in THEMES:
        raise HTTPException(422, f"Unknown template '{payload.template}'")
    options = payload.model_dump(mode="json", exclude={"document_id"})
    job = Job(document_id=doc.id, options=options, status="queued", stage="queued", progress=0,
              message="Waiting to start")
    db.add(job)
    db.commit()
    db.refresh(job)
    job_service.submit(job.id)
    return job_out(job)


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    return job_out(job)
