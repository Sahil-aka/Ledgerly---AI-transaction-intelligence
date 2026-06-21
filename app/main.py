"""
AI-Powered Transaction Processing Pipeline
FastAPI main entrypoint
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import engine
from app.models import Job, Transaction, JobSummary  # noqa: F401 — ensure models are imported
from app.database import Base
from app.routers.jobs import router as jobs_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create all tables on startup (idempotent)
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="AI-Powered Transaction Processing Pipeline",
    description=(
        "Upload dirty financial CSVs, process them asynchronously through a Celery job queue, "
        "classify transactions with Gemini 2.5 Flash, detect anomalies, and retrieve structured reports."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jobs_router)


@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "ok", "service": "transaction-pipeline"}
