import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class JobCreateResponse(BaseModel):
    job_id: uuid.UUID
    status: str
    message: str


class JobSummaryOut(BaseModel):
    total_spend_inr: float | None = None
    total_spend_usd: float | None = None
    top_merchants: Any | None = None
    anomaly_count: int | None = None
    category_breakdown: Any | None = None
    narrative: str | None = None
    risk_level: str | None = None

    model_config = ConfigDict(from_attributes=True)


class JobStatusResponse(BaseModel):
    job_id: uuid.UUID
    status: str
    filename: str
    row_count_raw: int | None = None
    row_count_clean: int | None = None
    created_at: datetime
    completed_at: datetime | None = None
    error_message: str | None = None
    summary: JobSummaryOut | None = None

    model_config = ConfigDict(from_attributes=True)


class JobListItem(BaseModel):
    job_id: uuid.UUID
    status: str
    filename: str
    row_count_raw: int | None = None
    created_at: datetime
    summary: JobSummaryOut | None = None

    model_config = ConfigDict(from_attributes=True)


class TransactionOut(BaseModel):
    id: uuid.UUID
    txn_id: str | None = None
    date: str | None = None
    merchant: str | None = None
    amount: float | None = None
    currency: str | None = None
    status: str | None = None
    category: str | None = None
    account_id: str | None = None
    notes: str | None = None
    is_anomaly: bool
    anomaly_reason: str | None = None
    llm_category: str | None = None
    llm_failed: bool

    model_config = ConfigDict(from_attributes=True)


class JobResultsResponse(BaseModel):
    job_id: uuid.UUID
    status: str
    transactions: list[TransactionOut]
    anomalies: list[TransactionOut]
    category_breakdown: Any | None = None
    summary: JobSummaryOut | None = None