import json
import logging
from datetime import datetime
from celery import Celery
from app.config import REDIS_URL, DATABASE_URL
from app.services.csv_processor import clean_csv
from app.services.anomaly_detector import detect_anomalies
from app.services.gemini_service import classify_transactions_batch, generate_narrative_summary

logger = logging.getLogger(__name__)

celery_app = Celery("tasks", broker=REDIS_URL, backend=REDIS_URL)
celery_app.conf.task_track_started = True


def _get_db():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    return Session()


@celery_app.task(bind=True, name="tasks.process_job")
def process_job(self, job_id: int, filepath: str):
    db = _get_db()
    from app.models.job import Job
    from app.models.transaction import Transaction
    from app.models.summary import JobSummary

    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        db.close()
        return

    try:
        # --- Mark processing ---
        job.status = "processing"
        db.commit()

        # --- Step 1: Clean CSV ---
        result = clean_csv(filepath)
        df = result["dataframe"]
        job.row_count_raw = result["raw_count"]
        job.row_count_clean = result["clean_count"]
        db.commit()

        # --- Step 2: Anomaly Detection ---
        df = detect_anomalies(df)

        # --- Step 3: LLM Classification (batch for uncategorised only) ---
        uncategorised_mask = df["category"].str.lower().str.strip() == "uncategorised"
        uncategorised = df[uncategorised_mask].to_dict(orient="records")

        llm_categories = {}
        llm_batch_failed = False
        if uncategorised:
            llm_categories = classify_transactions_batch(uncategorised)
            if not llm_categories:
                llm_batch_failed = True

        # --- Step 4: Save transactions ---
        db.query(Transaction).filter(Transaction.job_id == job_id).delete()
        for _, row in df.iterrows():
            txn_id = str(row.get("txn_id", ""))
            llm_cat = llm_categories.get(txn_id)
            t = Transaction(
                job_id=job_id,
                txn_id=txn_id,
                date=row.get("date"),
                merchant=row.get("merchant"),
                amount=row.get("amount"),
                currency=row.get("currency"),
                status=row.get("status"),
                category=row.get("category"),
                account_id=row.get("account_id"),
                notes=str(row.get("notes") or ""),
                is_anomaly=bool(row.get("is_anomaly", False)),
                anomaly_reason=row.get("anomaly_reason"),
                llm_category=llm_cat,
                llm_failed=llm_batch_failed and row.get("category", "").lower() == "uncategorised",
            )
            db.add(t)
        db.commit()

        # --- Step 5: LLM Narrative Summary ---
        anomaly_count = int(df["is_anomaly"].sum())
        inr_spend = float(df[df["currency"] == "INR"]["amount"].dropna().sum())
        usd_spend = float(df[df["currency"] == "USD"]["amount"].dropna().sum())

        top_merchants = (
            df.groupby("merchant")["amount"]
            .sum()
            .nlargest(3)
            .reset_index()
            .rename(columns={"amount": "total_amount"})
            .to_dict(orient="records")
        )
        category_spend = (
            df.groupby("category")["amount"]
            .sum()
            .reset_index()
            .rename(columns={"amount": "total"})
            .to_dict(orient="records")
        )

        stats = {
            "total_spend_inr": round(inr_spend, 2),
            "total_spend_usd": round(usd_spend, 2),
            "anomaly_count": anomaly_count,
            "top_merchants": top_merchants,
            "category_breakdown": category_spend,
            "total_transactions": len(df),
        }
        llm_summary = generate_narrative_summary(stats)

        # Save / update summary
        summary = db.query(JobSummary).filter(JobSummary.job_id == job_id).first()
        if not summary:
            summary = JobSummary(job_id=job_id)
            db.add(summary)
        summary.total_spend_inr = inr_spend
        summary.total_spend_usd = usd_spend
        summary.top_merchants = json.dumps(top_merchants)
        summary.anomaly_count = anomaly_count
        summary.narrative = llm_summary.get("narrative", "")
        summary.risk_level = llm_summary.get("risk_level", "unknown")
        db.commit()

        # --- Mark completed ---
        job.status = "completed"
        job.completed_at = datetime.utcnow()
        db.commit()

    except Exception as e:
        logger.exception(f"Job {job_id} failed: {e}")
        job.status = "failed"
        job.error_message = str(e)
        db.commit()
    finally:
        db.close()
