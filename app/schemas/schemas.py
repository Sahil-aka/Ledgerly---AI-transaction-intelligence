import uuid
from datetime import datetime
from typing import Optional, List, Any

from pydantic import BaseModel


# ─── Job Schemas ──────────────────────────────────────────────────────────────

class JobCreateResponse(BaseModel):
    job_id: uuid.UUID
    status: str
    message: str


class JobSummaryOut(BaseModel):
    total_spend_inr: Optional[float] = None
    total_spend_usd: Optional[float] = None
    top_merchants: Optional[Any] = None
    anomaly_count: Optional[int] = None
    category_breakdown: Optional[Any] = None
    narrative: Optional[str] = None
    risk_level: Optional[str] = None

    class Config:
        from_attributes = True


class JobStatusResponse(BaseModel):
    job_id: uuid.UUID
    status: str
    filename: str
    row_count_raw: Optional[int] = None
    row_count_clean: Optional[int] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    summary: Optional[JobSummaryOut] = None

    class Config:
        from_attributes = True


class JobListItem(BaseModel):
    job_id: uuid.UUID
    status: str
    filename: str
    row_count_raw: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Transaction Schemas ──────────────────────────────────────────────────────

class TransactionOut(BaseModel):
    id: uuid.UUID
    txn_id: Optional[str] = None
    date: Optional[str] = None
    merchant: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    status: Optional[str] = None
    category: Optional[str] = None
    account_id: Optional[str] = None
    notes: Optional[str] = None
    is_anomaly: bool
    anomaly_reason: Optional[str] = None
    llm_category: Optional[str] = None
    llm_failed: bool

    class Config:
        from_attributes = True


class JobResultsResponse(BaseModel):
    job_id: uuid.UUID
    status: str
    transactions: List[TransactionOut]
    anomalies: List[TransactionOut]
    category_breakdown: Optional[Any] = None
    summary: Optional[JobSummaryOut] = None
