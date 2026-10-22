"""Authenticated transaction-processing job endpoints."""

import csv
import io
import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.auth.security import get_current_user
from app.config import settings
from app.database import get_db
from app.models import Job, JobSummary, Transaction, User
from app.schemas import (
    JobCreateResponse,
    JobListItem,
    JobResultsResponse,
    JobStatusResponse,
    JobSummaryOut,
    TransactionOut,
)
from app.worker.tasks import process_job, process_job_sync

router = APIRouter(prefix="/jobs", tags=["Jobs"])


def get_owned_job(job_id: uuid.UUID, user: User, db: Session) -> Job:
    job = db.query(Job).filter(Job.id == job_id, Job.owner_id == user.id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


@router.post("/upload", response_model=JobCreateResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_csv(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Validate a CSV, create an owned job, and schedule processing."""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted.")

    content_bytes = await file.read()
    try:
        csv_content = content_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded.")

    reader = csv.DictReader(io.StringIO(csv_content))
    required_columns = {"txn_id", "date", "merchant", "amount", "currency", "status"}
    missing = required_columns.difference(reader.fieldnames or [])
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"CSV is missing required columns: {', '.join(sorted(missing))}",
        )

    job = Job(
        id=uuid.uuid4(),
        owner_id=user.id,
        filename=file.filename,
        status="pending",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    if settings.PROCESSING_MODE.strip().lower() == "inline":
        # Runs inside the API process after returning the response; suitable for
        # small demo uploads when a separate Celery worker is not deployed.
        background_tasks.add_task(process_job_sync, str(job.id), csv_content)
        message = "Job created and processing started."
    else:
        try:
            process_job.delay(str(job.id), csv_content)
        except Exception as exc:
            job.status = "failed"
            job.error_message = "The processing queue is unavailable. Please try again."
            db.commit()
            raise HTTPException(status_code=503, detail=job.error_message) from exc
        message = "Job created and enqueued for processing."

    return JobCreateResponse(
        job_id=job.id,
        status=job.status,
        message=message,
    )


@router.get("/{job_id}/status", response_model=JobStatusResponse)
def get_job_status(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = get_owned_job(job_id, user, db)
    summary_out = JobSummaryOut.model_validate(job.summary) if job.status == "completed" and job.summary else None
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


@router.get("/{job_id}/results", response_model=JobResultsResponse)
def get_job_results(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = get_owned_job(job_id, user, db)
    if job.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job is not completed yet. Current status: {job.status}",
        )

    transactions = db.query(Transaction).filter(Transaction.job_id == job_id).all()
    anomalies = [transaction for transaction in transactions if transaction.is_anomaly]
    summary_out = JobSummaryOut.model_validate(job.summary) if job.summary else None
    return JobResultsResponse(
        job_id=job.id,
        status=job.status,
        transactions=[TransactionOut.model_validate(transaction) for transaction in transactions],
        anomalies=[TransactionOut.model_validate(transaction) for transaction in anomalies],
        category_breakdown=job.summary.category_breakdown if job.summary else None,
        summary=summary_out,
    )


@router.get("", response_model=list[JobListItem])
def list_jobs(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by job status"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = db.query(Job).filter(Job.owner_id == user.id).order_by(Job.created_at.desc())
    if status_filter:
        query = query.filter(Job.status == status_filter.lower())
    return [
        JobListItem(
            job_id=job.id,
            status=job.status,
            filename=job.filename,
            row_count_raw=job.row_count_raw,
            created_at=job.created_at,
            summary=JobSummaryOut.model_validate(job.summary) if job.status == "completed" and job.summary else None,
        )
        for job in query.all()
    ]
