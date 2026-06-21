# AI-Powered Transaction Processing Pipeline

A backend API that accepts dirty financial CSVs, processes them asynchronously through a Celery + Redis job queue, uses **Gemini 2.5 Flash** to classify transactions and generate narrative summaries, and persists results in **PostgreSQL 18** — all containerised with Docker Compose.

---

## Architecture

```
┌─────────────┐     POST /jobs/upload      ┌──────────────────┐
│   Client    │ ────────────────────────► │  FastAPI (8000)   │
│             │ ◄──────────────────────── │                  │
│             │     job_id (202)           └────────┬─────────┘
│             │                                     │ enqueue task
│             │                                     ▼
│             │                           ┌──────────────────┐
│             │     GET /jobs/{id}/status │  Celery Worker   │
│             │ ────────────────────────► │                  │
│             │ ◄──────────────────────── │  1. Clean CSV    │
│             │     status + summary      │  2. Detect Anomalies│
└─────────────┘                           │  3. LLM Classify │
                                          │  4. LLM Narrative│
        ┌─────────────┐                   └────────┬─────────┘
        │   Redis     │ ◄── broker/result ─────────┘
        │  (Queue)    │
        └─────────────┘

        ┌─────────────┐
        │ PostgreSQL  │ ◄── persist jobs, transactions, summaries
        │    18       │
        └─────────────┘
```

---

## Quick Start

### 1. Clone & Configure

```bash
git clone <your-repo-url>
cd Backend_DevOps_Assignment

# Copy and fill in your Gemini API key
cp .env.example .env
# Edit .env and set GEMINI_API_KEY=your_actual_key
```

### 2. Start Everything

```bash
docker compose up --build
```

The system starts in order: PostgreSQL → Redis → API + Worker.

- **API**: http://localhost:8000
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

---

## API Endpoints

### POST /jobs/upload — Upload CSV

```bash
curl -X POST http://localhost:8000/jobs/upload \
  -F "file=@transactions.csv"
```

**Response (202):**
```json
{
  "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "status": "pending",
  "message": "Job created and enqueued for processing."
}
```

---

### GET /jobs/{job_id}/status — Poll Status

```bash
curl http://localhost:8000/jobs/3fa85f64-5717-4562-b3fc-2c963f66afa6/status
```

**Response (while processing):**
```json
{
  "job_id": "3fa85f64-...",
  "status": "processing",
  "filename": "transactions.csv",
  "row_count_raw": 96,
  "row_count_clean": 78,
  "created_at": "2024-07-15T10:00:00Z"
}
```

**Response (completed):**
```json
{
  "job_id": "3fa85f64-...",
  "status": "completed",
  "summary": {
    "total_spend_inr": 485234.56,
    "total_spend_usd": 45123.10,
    "anomaly_count": 8,
    "risk_level": "high",
    "narrative": "The account shows elevated spending..."
  }
}
```

---

### GET /jobs/{job_id}/results — Full Results

```bash
curl http://localhost:8000/jobs/3fa85f64-5717-4562-b3fc-2c963f66afa6/results
```

**Response:**
```json
{
  "job_id": "3fa85f64-...",
  "status": "completed",
  "transactions": [...],
  "anomalies": [
    {
      "txn_id": "TXN2003",
      "merchant": "IRCTC",
      "amount": 193647.29,
      "is_anomaly": true,
      "anomaly_reason": "Amount 193647.29 exceeds 3x account median (5277.39)"
    }
  ],
  "category_breakdown": {
    "Food": 52340.12,
    "Travel": 34120.88,
    ...
  },
  "summary": { ... }
}
```

---

### GET /jobs — List All Jobs

```bash
# All jobs
curl http://localhost:8000/jobs

# Filter by status
curl "http://localhost:8000/jobs?status=completed"
curl "http://localhost:8000/jobs?status=pending"
```

---

## Processing Pipeline

When a job is dequeued, the Celery worker executes these steps:

| Step | What happens |
|---|---|
| **1. Data Cleaning** | Normalise dates (DD-MM-YYYY & YYYY/MM/DD → ISO 8601), strip $ from amounts, uppercase status/currency, fill missing categories with 'Uncategorised', remove exact duplicate rows |
| **2. Anomaly Detection** | Flag amounts > 3× account median; flag USD transactions on domestic-only merchants (Swiggy, Ola, IRCTC, Zomato, etc.) |
| **3. LLM Classification** | Batch call to Gemini 2.5 Flash for all uncategorised transactions → Food, Shopping, Travel, Transport, Utilities, Cash Withdrawal, Entertainment, Other |
| **4. LLM Narrative** | Single Gemini call producing total spend, top merchants, anomaly count, 2-3 sentence narrative, risk_level (low/medium/high) |
| **5. Retry Logic** | Up to 3 retries with exponential backoff (2s, 4s, 8s). LLM failures mark batch as `llm_failed` but don't abort the job |

---

## Database Schema

### jobs
| Column | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| filename | VARCHAR | Uploaded CSV filename |
| status | VARCHAR | pending / processing / completed / failed |
| row_count_raw | INT | Rows before cleaning |
| row_count_clean | INT | Rows after dedup |
| created_at | TIMESTAMPTZ | Creation time |
| completed_at | TIMESTAMPTZ | Completion time |
| error_message | TEXT | Set on failure |

### transactions
| Column | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| job_id | UUID FK | Parent job |
| txn_id | VARCHAR | Original transaction ID |
| date | VARCHAR | ISO 8601 date |
| merchant | VARCHAR | Merchant name |
| amount | NUMERIC | Cleaned amount |
| currency | VARCHAR | Uppercased (INR/USD) |
| status | VARCHAR | Uppercased (SUCCESS/FAILED/PENDING) |
| category | VARCHAR | Final category (original or LLM-assigned) |
| is_anomaly | BOOLEAN | Anomaly flag |
| anomaly_reason | TEXT | Reason for anomaly |
| llm_category | VARCHAR | LLM-assigned category |
| llm_failed | BOOLEAN | True if LLM classification failed |

### job_summaries
| Column | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| job_id | UUID FK | Parent job |
| total_spend_inr | NUMERIC | Total INR spend |
| total_spend_usd | NUMERIC | Total USD spend |
| top_merchants | JSONB | Top 3 merchants by spend |
| anomaly_count | INT | Total anomalies |
| category_breakdown | JSONB | Spend per category |
| narrative | TEXT | LLM narrative |
| risk_level | VARCHAR | low / medium / high |

---

## Tech Stack

| Component | Technology |
|---|---|
| API Framework | FastAPI 0.115 |
| Database | PostgreSQL 18 |
| ORM | SQLAlchemy 2.0 |
| Job Queue | Celery 5.4 + Redis 7 |
| LLM | Gemini 2.5 Flash |
| Containerisation | Docker + Docker Compose |

---

## Health Check

```bash
curl http://localhost:8000/health
# {"status": "ok", "service": "transaction-pipeline"}
```
