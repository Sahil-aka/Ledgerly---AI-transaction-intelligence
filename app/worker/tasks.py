"""
Celery task: process_job

Executes the full pipeline for a given job_id:
  1. Data cleaning
  2. Anomaly detection
  3. LLM classification (batched)
  4. LLM narrative summary
  5. Persist results to PostgreSQL
"""

import csv
import io
import logging
import uuid
from datetime import datetime, timezone

from app.worker.celery_app import celery_app
from app.database import SessionLocal
from app.models import Job, Transaction, JobSummary
from app.services.cleaner import clean_transactions
from app.services.anomaly import detect_anomalies
from app.services.llm import classify_transactions, generate_narrative_summary

logger = logging.getLogger(__name__)


def process_job_sync(job_id: str, csv_content: str):
    """
    Main processing task. Accepts the raw CSV content as a string
    (stored in Redis via the enqueue call).
    """
    db = SessionLocal()
    try:
        # ── Load job ──────────────────────────────────────────────────────────
        job = db.query(Job).filter(Job.id == uuid.UUID(job_id)).first()
        if not job:
            logger.error("Job %s not found", job_id)
            return

        job.status = "processing"
        db.commit()

        # ── Parse CSV ─────────────────────────────────────────────────────────
        reader = csv.DictReader(io.StringIO(csv_content))
        raw_rows = [dict(row) for row in reader]
        job.row_count_raw = len(raw_rows)
        db.commit()

        # ── Step 1: Clean ─────────────────────────────────────────────────────
        cleaned = clean_transactions(raw_rows)
        job.row_count_clean = len(cleaned)
        db.commit()

        # ── Step 2: Anomaly Detection ─────────────────────────────────────────
        annotated = detect_anomalies(cleaned)

        # ── Step 3: LLM Classification ────────────────────────────────────────
        classified = classify_transactions(annotated)

        # ── Step 4: LLM Narrative Summary ─────────────────────────────────────
        summary_data = generate_narrative_summary(classified)

        # ── Step 5: Persist Transactions ─────────────────────────────────────
        db.query(Transaction).filter(Transaction.job_id == job.id).delete()

        for txn_dict in classified:
            txn = Transaction(
                id=uuid.uuid4(),
                job_id=job.id,
                txn_id=txn_dict.get("txn_id"),
                date=txn_dict.get("date"),
                merchant=txn_dict.get("merchant"),
                amount=txn_dict.get("amount"),
                currency=txn_dict.get("currency"),
                status=txn_dict.get("status"),
                category=txn_dict.get("llm_category") or txn_dict.get("category"),
                account_id=txn_dict.get("account_id"),
                notes=txn_dict.get("notes"),
                is_anomaly=txn_dict.get("is_anomaly", False),
                anomaly_reason=txn_dict.get("anomaly_reason"),
                llm_category=txn_dict.get("llm_category"),
                llm_raw_response=txn_dict.get("llm_raw_response"),
                llm_failed=txn_dict.get("llm_failed", False),
            )
            db.add(txn)

        # ── Step 6: Persist Summary ───────────────────────────────────────────
        existing_summary = (
            db.query(JobSummary).filter(JobSummary.job_id == job.id).first()
        )
        if existing_summary:
            db.delete(existing_summary)
            db.flush()

        job_summary = JobSummary(
            id=uuid.uuid4(),
            job_id=job.id,
            total_spend_inr=summary_data["total_spend_inr"],
            total_spend_usd=summary_data["total_spend_usd"],
            top_merchants=summary_data["top_merchants"],
            anomaly_count=summary_data["anomaly_count"],
            category_breakdown=summary_data["category_breakdown"],
            narrative=summary_data["narrative"],
            risk_level=summary_data["risk_level"],
        )
        db.add(job_summary)

        # ── Finalise ──────────────────────────────────────────────────────────
        job.status = "completed"
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
        logger.info("Job %s completed successfully", job_id)

    except Exception as exc:
        logger.exception("Job %s failed: %s", job_id, exc)
        try:
            job = db.query(Job).filter(Job.id == uuid.UUID(job_id)).first()
            if job:
                job.status = "failed"
                job.error_message = str(exc)
                db.commit()
        except Exception:
            pass
        raise
    finally:
        db.close()


@celery_app.task(bind=True, max_retries=0, name="app.worker.tasks.process_job")
def process_job(self, job_id: str, csv_content: str):
    """Celery entry point; the same processing function is used by inline mode."""
    return process_job_sync(job_id, csv_content)
