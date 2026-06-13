import os
import uuid
import json
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.job import Job
from app.models.transaction import Transaction
from app.models.summary import JobSummary
from app.config import UPLOAD_DIR

router = APIRouter(prefix="/jobs", tags=["Jobs"])


# ─── POST /jobs/upload ────────────────────────────────────────────────────────

@router.post("/upload")
async def upload_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are accepted.")

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    filename = f"{uuid.uuid4()}_{file.filename}"
    filepath = os.path.join(UPLOAD_DIR, filename)

    content = await file.read()
    with open(filepath, "wb") as f:
        f.write(content)

    job = Job(filename=filename, status="pending")
    db.add(job)
    db.commit()
    db.refresh(job)

    # Enqueue Celery task
    from app.workers.tasks import process_job
    process_job.delay(job.id, filepath)

    return {"job_id": job.id, "filename": filename, "status": "pending"}


# ─── GET /jobs ────────────────────────────────────────────────────────────────

@router.get("/")
def list_jobs(
    status: str = Query(None, description="Filter by status"),
    db: Session = Depends(get_db),
):
    query = db.query(Job)
    if status:
        query = query.filter(Job.status == status)
    jobs = query.order_by(Job.created_at.desc()).all()
    return [
        {
            "id": j.id,
            "filename": j.filename,
            "status": j.status,
            "row_count_raw": j.row_count_raw,
            "row_count_clean": j.row_count_clean,
            "created_at": str(j.created_at),
            "completed_at": str(j.completed_at) if j.completed_at else None,
        }
        for j in jobs
    ]


# ─── GET /jobs/{job_id}/status ────────────────────────────────────────────────

@router.get("/{job_id}/status")
def get_job_status(job_id: int, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    resp = {
        "job_id": job.id,
        "status": job.status,
        "filename": job.filename,
        "row_count_raw": job.row_count_raw,
        "row_count_clean": job.row_count_clean,
        "created_at": str(job.created_at),
        "completed_at": str(job.completed_at) if job.completed_at else None,
    }
    if job.status == "completed":
        summary = db.query(JobSummary).filter(JobSummary.job_id == job_id).first()
        if summary:
            resp["summary"] = {
                "total_spend_inr": summary.total_spend_inr,
                "total_spend_usd": summary.total_spend_usd,
                "anomaly_count": summary.anomaly_count,
                "risk_level": summary.risk_level,
                "narrative": summary.narrative,
            }
    if job.status == "failed":
        resp["error_message"] = job.error_message

    return resp


# ─── GET /jobs/{job_id}/results ──────────────────────────────────────────────

@router.get("/{job_id}/results")
def get_results(job_id: int, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status not in ("completed", "failed"):
        return {"message": f"Job is still {job.status}. Poll /status for updates."}

    transactions = db.query(Transaction).filter(Transaction.job_id == job_id).all()
    summary = db.query(JobSummary).filter(JobSummary.job_id == job_id).first()

    # Build category spend breakdown
    category_spend: dict = {}
    anomalies = []
    txn_list = []
    for t in transactions:
        txn_list.append({
            "txn_id": t.txn_id,
            "date": t.date,
            "merchant": t.merchant,
            "amount": t.amount,
            "currency": t.currency,
            "status": t.status,
            "category": t.llm_category or t.category,
            "account_id": t.account_id,
            "notes": t.notes,
            "is_anomaly": t.is_anomaly,
            "anomaly_reason": t.anomaly_reason,
            "llm_failed": t.llm_failed,
        })
        cat = t.llm_category or t.category or "Uncategorised"
        category_spend[cat] = round(category_spend.get(cat, 0) + (t.amount or 0), 2)
        if t.is_anomaly:
            anomalies.append({
                "txn_id": t.txn_id,
                "merchant": t.merchant,
                "amount": t.amount,
                "currency": t.currency,
                "reason": t.anomaly_reason,
            })

    result = {
        "job_id": job_id,
        "status": job.status,
        "transactions": txn_list,
        "flagged_anomalies": anomalies,
        "category_spend_breakdown": category_spend,
    }
    if summary:
        result["llm_summary"] = {
            "total_spend_inr": summary.total_spend_inr,
            "total_spend_usd": summary.total_spend_usd,
            "top_merchants": json.loads(summary.top_merchants or "[]"),
            "anomaly_count": summary.anomaly_count,
            "narrative": summary.narrative,
            "risk_level": summary.risk_level,
        }
    return result
