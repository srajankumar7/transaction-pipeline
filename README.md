# AI-Powered Transaction Processing Pipeline

A FastAPI + Celery + PostgreSQL + Redis backend that accepts dirty financial CSVs, cleans them, detects anomalies, classifies transactions via Gemini LLM, and produces structured summary reports — all retrieved via a polling API.

---

## Architecture Overview

```
Client
  │
  ▼
FastAPI (api service, port 8000)
  │  POST /jobs/upload → saves file, creates Job row, enqueues Celery task
  │  GET  /jobs/{id}/status → poll job state
  │  GET  /jobs/{id}/results → full cleaned data + anomalies + LLM summary
  │  GET  /jobs → list all jobs (filterable by ?status=)
  │
  ▼
Redis (broker + Celery result backend)
  │
  ▼
Celery Worker (worker service)
  │  1. Clean CSV (dates, amounts, duplicates, missing fields)
  │  2. Detect anomalies (statistical outlier + currency mismatch)
  │  3. LLM classify uncategorised transactions (batched, Gemini 1.5 Flash)
  │  4. LLM narrative summary (single call → JSON with risk_level)
  │  5. Persist to PostgreSQL (Transaction + JobSummary tables)
  │
  ▼
PostgreSQL
  Tables: jobs | transactions | job_summaries
```

---

## Quick Start

### Prerequisites
- Docker & Docker Compose installed
- A free [Google AI Studio](https://aistudio.google.com/) API key for Gemini

### 1. Clone and configure

```bash
git clone https://github.com/YOUR_USERNAME/transaction-pipeline.git
cd transaction-pipeline
cp .env.example .env          # or edit .env directly
# Edit .env and set GEMINI_API_KEY=your_actual_key
```

### 2. Start everything

```bash
docker compose up --build
```

That's it. The API will be live at `http://localhost:8000` once PostgreSQL and Redis are healthy (~15 seconds).

---

## API Endpoints

### POST /jobs/upload
Upload a CSV file. Returns `job_id` immediately; processing runs asynchronously.

```bash
curl -X POST http://localhost:8000/jobs/upload \
  -F "file=@transactions.csv"
```

Response:
```json
{"job_id": 1, "filename": "abc_transactions.csv", "status": "pending"}
```

### GET /jobs/{job_id}/status
Poll job state. When `completed`, also returns a high-level `summary` block.

```bash
curl http://localhost:8000/jobs/1/status
```

Response (completed):
```json
{
  "job_id": 1,
  "status": "completed",
  "row_count_raw": 92,
  "row_count_clean": 89,
  "summary": {
    "total_spend_inr": 412830.50,
    "total_spend_usd": 8920.10,
    "anomaly_count": 5,
    "risk_level": "medium",
    "narrative": "Spending is concentrated in shopping and food categories..."
  }
}
```

### GET /jobs/{job_id}/results
Full results: cleaned transactions, flagged anomalies, per-category breakdown, LLM narrative.

```bash
curl http://localhost:8000/jobs/1/results
```

Response:
```json
{
  "job_id": 1,
  "status": "completed",
  "transactions": [...],
  "flagged_anomalies": [
    {
      "txn_id": "TXN1009",
      "merchant": "MakeMyTrip",
      "amount": 7428.06,
      "currency": "USD",
      "reason": "USD currency used at domestic merchant 'MakeMyTrip'"
    }
  ],
  "category_spend_breakdown": {
    "Food": 45230.10,
    "Shopping": 120400.00,
    "Travel": 32900.55
  },
  "llm_summary": {
    "total_spend_inr": 412830.50,
    "total_spend_usd": 8920.10,
    "top_merchants": [{"merchant": "Amazon", "total_amount": 95000}],
    "anomaly_count": 5,
    "narrative": "...",
    "risk_level": "medium"
  }
}
```

### GET /jobs
List all jobs. Filter by status with `?status=pending|processing|completed|failed`.

```bash
curl "http://localhost:8000/jobs?status=completed"
```

---

## Processing Pipeline (Worker)

| Step | What happens |
|------|--------------|
| **1. Data Cleaning** | Normalise dates → ISO 8601. Strip `$` from amounts. Uppercase status & currency. Fill blank categories → `Uncategorised`. Auto-generate txn_id for blank rows. Remove exact duplicates. |
| **2. Anomaly Detection** | Flag amount > 3× account median. Flag USD transactions at domestic merchants (Swiggy, Ola, IRCTC, Zomato, etc.). |
| **3. LLM Classification** | Batch-call Gemini for uncategorised transactions only. Categories: Food / Shopping / Travel / Transport / Utilities / Cash Withdrawal / Entertainment / Other. |
| **4. LLM Narrative** | Single Gemini call → JSON with `narrative` (2-3 sentences) and `risk_level` (low/medium/high). |
| **5. Retry Logic** | Up to 3 retries with exponential backoff (2s, 4s, 8s). Failed batches marked `llm_failed=true`; job continues. |

---

## Data Models

**`jobs`** — tracks upload and processing lifecycle  
**`transactions`** — one row per cleaned transaction, includes anomaly flags and LLM results  
**`job_summaries`** — aggregated stats + narrative per job

---

## Interactive Docs

Swagger UI: `http://localhost:8000/docs`  
ReDoc: `http://localhost:8000/redoc`

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GEMINI_API_KEY` | *(required)* | Google Gemini 1.5 Flash API key |
| `DATABASE_URL` | set in compose | PostgreSQL connection string |
| `REDIS_URL` | set in compose | Redis connection string |
