"""AI-powered transaction processing API."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.database import Base, engine
from app.models import Job, JobSummary, Transaction, User  # noqa: F401
from app.routers.auth import router as auth_router
from app.routers.jobs import router as jobs_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create missing tables and upgrade existing jobs tables without removing their data.
Base.metadata.create_all(bind=engine)
with engine.begin() as connection:
    connection.execute(
        text(
            "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS owner_id UUID "
            "REFERENCES users(id) ON DELETE SET NULL"
        )
    )
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_jobs_owner_id ON jobs(owner_id)"))

app = FastAPI(
    title="AI-Powered Transaction Processing Pipeline",
    description="Upload and analyze financial transaction CSV files.",
    version="1.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth_router)
app.include_router(jobs_router)


@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "ok", "service": "transaction-pipeline"}