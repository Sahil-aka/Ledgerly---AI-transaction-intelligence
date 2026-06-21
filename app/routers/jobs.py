"""
Jobs router — all /jobs/* endpoints.

POST /jobs/upload
GET  /jobs/{job_id}/status
GET  /jobs/{job_id}/results
GET  /jobs
"""

import csv
import io
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Job, Transaction, JobSummary
from app.schemas import (
    JobCreateResponse,
    JobStatusResponse,
    JobListItem,
    JobResultsResponse,
    JobSummaryOut,
    TransactionOut,
)
from app.worker.tasks import process_job

router = APIRouter(prefix="/jobs", tags=["Jobs"])


# ─── POST /jobs/upload ────────────────────────────────────────────────────────

@router.post("/upload", response_model=JobCreateResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Accept a CSV file upload. Validate it, create a Job record (status=pending),
    enqueue the processing task, and return the job_id immediately.
    """
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .csv files are accepted.",
        )

    content_bytes = await file.read()
    try:
        csv_content = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be UTF-8 encoded.",
        )

    # Validate CSV has expected columns
    reader = csv.DictReader(io.StringIO(csv_content))
    required_columns = {"txn_id", "date", "merchant", "amount", "currency", "status"}
    if not required_columns.issubset(set(reader.fieldnames or [])):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"CSV must contain columns: {required_columns}",
        )

    # Create job record
    job = Job(
        id=uuid.uuid4(),
        filename=file.filename,
        status="pending",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # Enqueue Celery task
    process_job.delay(str(job.id), csv_content)

    return JobCreateResponse(
        job_id=job.id,
        status=job.status,
        message="Job created and enqueued for processing.",
    )


# ─── GET /jobs/{job_id}/status ────────────────────────────────────────────────

@router.get("/{job_id}/status", response_model=JobStatusResponse)
def get_job_status(job_id: uuid.UUID, db: Session = Depends(get_db)):
    """
    Return the current status of the job. If completed, include a summary.
    """
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    summary_out = None
    if job.status == "completed" and job.summary:
        summary_out = JobSummaryOut.model_validate(job.summary)

    return JobStatusResponse(
        job_id=job.id,
        status=job.status,
        filename=job.filename,
        row_count_raw=job.row_count_raw,
        row_count_clean=job.row_count_clean,
        created_at=job.created_at,
        completed_at=job.completed_at,
        error_message=job.error_message,
        summary=summary_out,
    )


# ─── GET /jobs/{job_id}/results ───────────────────────────────────────────────

@router.get("/{job_id}/results", response_model=JobResultsResponse)
def get_job_results(job_id: uuid.UUID, db: Session = Depends(get_db)):
    """
    Return the full structured output: cleaned transactions list,
    flagged anomalies, per-category spend breakdown, and LLM narrative summary.
    """
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    if job.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job is not completed yet. Current status: {job.status}",
        )

    transactions = db.query(Transaction).filter(Transaction.job_id == job_id).all()
    anomalies = [t for t in transactions if t.is_anomaly]

    transactions_out = [TransactionOut.model_validate(t) for t in transactions]
    anomalies_out = [TransactionOut.model_validate(t) for t in anomalies]

    summary_out = None
    category_breakdown = None
    if job.summary:
        summary_out = JobSummaryOut.model_validate(job.summary)
        category_breakdown = job.summary.category_breakdown

    return JobResultsResponse(
        job_id=job.id,
        status=job.status,
        transactions=transactions_out,
        anomalies=anomalies_out,
        category_breakdown=category_breakdown,
        summary=summary_out,
    )


# ─── GET /jobs ────────────────────────────────────────────────────────────────

@router.get("", response_model=list[JobListItem])
def list_jobs(
    status: Optional[str] = Query(None, description="Filter by job status"),
    db: Session = Depends(get_db),
):
    """
    List all jobs with their status, filename, row count, and created_at.
    Supports filtering via ?status= query parameter.
    """
    query = db.query(Job).order_by(Job.created_at.desc())
    if status:
        query = query.filter(Job.status == status.lower())
    jobs = query.all()

    return [
        JobListItem(
            job_id=j.id,
            status=j.status,
            filename=j.filename,
            row_count_raw=j.row_count_raw,
            created_at=j.created_at,
        )
        for j in jobs
    ]
