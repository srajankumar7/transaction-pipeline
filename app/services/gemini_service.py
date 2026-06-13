import time
import json
import logging
from groq import Groq
from app.config import GEMINI_API_KEY

logger = logging.getLogger(__name__)

VALID_CATEGORIES = [
    "Food", "Shopping", "Travel", "Transport",
    "Utilities", "Cash Withdrawal", "Entertainment", "Other"
]


def _client():
    return Groq(api_key=GEMINI_API_KEY)


def classify_transactions_batch(transactions: list[dict], retries: int = 3) -> dict:
    if not transactions:
        return {}

    client = _client()
    batch_text = "\n".join(
        f"{i+1}. txn_id={t.get('txn_id','?')}, merchant={t.get('merchant','?')}, "
        f"amount={t.get('amount','?')}, notes={t.get('notes','')}"
        for i, t in enumerate(transactions)
    )
    prompt = f"""Classify each transaction into exactly one of these categories:
{', '.join(VALID_CATEGORIES)}

Transactions:
{batch_text}

Respond ONLY with a JSON object mapping txn_id to category, e.g.:
{{"TXN001": "Food", "TXN002": "Shopping"}}
No explanation, no markdown fences."""

    for attempt in range(retries):
        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1000,
            )
            text = response.choices[0].message.content.strip()
            text = text.replace("```json", "").replace("```", "").strip()
            return json.loads(text)
        except Exception as e:
            wait = 10 * (attempt + 1)
            logger.warning(f"LLM classify attempt {attempt+1} failed: {e}. Retrying in {wait}s")
            time.sleep(wait)

    logger.error("LLM classify failed after all retries")
    return {}


def generate_narrative_summary(stats: dict, retries: int = 3) -> dict:
    client = _client()
    prompt = f"""You are a financial analyst. Given these transaction stats:
{json.dumps(stats, indent=2)}

Produce a JSON object with exactly these fields:
- "narrative": a 2-3 sentence spending narrative
- "risk_level": one of "low", "medium", or "high"

Respond ONLY with the JSON object, no markdown, no explanation."""

    for attempt in range(retries):
        try:
            response = client.chat.completions.create(
model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
            )
            text = response.choices[0].message.content.strip()
            text = text.replace("```json", "").replace("```", "").strip()
            return json.loads(text)
        except Exception as e:
            wait = 10 * (attempt + 1)
            logger.warning(f"LLM narrative attempt {attempt+1} failed: {e}. Retrying in {wait}s")
            time.sleep(wait)

    logger.error("LLM narrative failed after all retries")
    return {"narrative": "LLM generation failed.", "risk_level": "unknown"}