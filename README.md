# AI-Powered Transaction Processing Pipeline

A FastAPI + Celery + PostgreSQL + Redis backend that accepts dirty financial CSVs, cleans them, detects anomalies, classifies transactions via Groq LLaMA AI, and produces structured summary reports — all retrieved via a polling API.

---

## Architecture

```
Client
  │
  ▼
FastAPI (port 8000)
  │  POST /jobs/upload  → saves CSV, creates Job row, enqueues Celery task, returns job_id
  │  GET  /jobs/{id}/status  → poll job state (pending → processing → completed/failed)
  │  GET  /jobs/{id}/results → full cleaned data + anomalies + LLM summary
  │  GET  /jobs           → list all jobs (?status= filter)
  │
  ▼
Redis (broker + result backend)
  │
  ▼
Celery Worker
  │  Step 1: Clean CSV (dates, amounts, duplicates, missing fields)
  │  Step 2: Detect anomalies (3× median + USD-at-domestic-merchant)
  │  Step 3: LLM classify uncategorised transactions (batched)
  │  Step 4: LLM narrative summary (single call → JSON)
  │  Step 5: Persist to PostgreSQL
  │
  ▼
PostgreSQL
  Tables: jobs | transactions | job_summaries
```

---

## Quick Start

### Prerequisites
- Docker and Docker Compose installed
- A free [Groq](https://console.groq.com) API key

### 1. Clone the repo

```bash
git clone https://github.com/srajankumar7/transaction-pipeline.git
cd transaction-pipeline
```

### 2. Set your API key

Edit the `.env` file:

```
GEMINI_API_KEY=your_groq_api_key_here
```

> Note: The variable is named `GEMINI_API_KEY` in the config but holds the Groq key.

### 3. Start everything

```bash
docker compose up --build
```

All 4 services (API, worker, Redis, PostgreSQL) start with this single command. Wait for:

```
api-1  | Application startup complete.
```

---

## API Endpoints

### POST /jobs/upload
Upload a CSV file. Returns `job_id` immediately.

```bash
curl -X POST http://localhost:8000/jobs/upload \
  -F "file=@transactions.csv"
```

Response:
```json
{"job_id": 1, "filename": "abc_transactions.csv", "status": "pending"}
```

---

### GET /jobs/{job_id}/status
Poll job state. Returns summary when completed.

```bash
curl http://localhost:8000/jobs/1/status
```

Response:
```json
{
  "job_id": 1,
  "status": "completed",
  "row_count_raw": 95,
  "row_count_clean": 85,
  "summary": {
    "total_spend_inr": 1339923.0,
    "total_spend_usd": 74185.14,
    "anomaly_count": 10,
    "risk_level": "medium",
    "narrative": "Spending is concentrated in travel and utilities..."
  }
}
```

---

### GET /jobs/{job_id}/results
Full results: cleaned transactions, flagged anomalies, category breakdown, LLM summary.

```bash
curl http://localhost:8000/jobs/1/results
```

Response includes:
```json
{
  "transactions": [...],
  "flagged_anomalies": [...],
  "category_spend_breakdown": {
    "Food": 110107.31,
    "Shopping": 280715.73,
    "Travel": 481820.60
  },
  "llm_summary": {
    "top_merchants": [...],
    "narrative": "...",
    "risk_level": "medium"
  }
}
```

---

### GET /jobs
List all jobs. Filter by status.

```bash
curl "http://localhost:8000/jobs?status=completed"
```

---

## Processing Pipeline

| Step | Description |
|------|-------------|
| **1. Data Cleaning** | Normalise dates → ISO 8601. Strip `$` from amounts. Uppercase status and currency. Fill blank categories → `Uncategorised`. Auto-generate txn_id for blank rows. Remove exact duplicates. |
| **2. Anomaly Detection** | Flag amount > 3× account median. Flag USD transactions at domestic-only merchants (Swiggy, Ola, IRCTC, Zomato). |
| **3. LLM Classification** | Single batched Groq call for uncategorised rows. Categories: Food / Shopping / Travel / Transport / Utilities / Cash Withdrawal / Entertainment / Other. |
| **4. LLM Narrative** | Single Groq call → JSON with `narrative` (2-3 sentences) and `risk_level` (low/medium/high). |
| **5. Retry Logic** | Up to 3 retries with exponential backoff. Failed batches marked `llm_failed=true`. Job continues regardless. |

---

## Database Schema

**`jobs`** — tracks upload and processing lifecycle

**`transactions`** — one row per cleaned transaction with anomaly flags and LLM results

**`job_summaries`** — aggregated stats and AI narrative per job

---

## Interactive API Docs

Swagger UI: `http://localhost:8000/docs`

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` | Groq API key (free at console.groq.com) |
| `DATABASE_URL` | Set automatically by Docker Compose |
| `REDIS_URL` | Set automatically by Docker Compose |