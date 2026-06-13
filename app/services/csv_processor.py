import pandas as pd
import re
from datetime import datetime


DOMESTIC_MERCHANTS = {"swiggy", "ola", "irctc", "zomato", "bigbasket", "namma yatri", "rapido"}


def parse_date(date_str: str) -> str:
    """Normalise any date string to ISO 8601 (YYYY-MM-DD)."""
    if not date_str or str(date_str).strip() in ("", "nan", "NaT"):
        return None
    date_str = str(date_str).strip()
    for fmt in ("%d-%m-%Y", "%Y/%m/%d", "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return date_str   # Return as-is if unparseable


def clean_amount(val) -> float:
    """Strip currency symbols and convert to float."""
    if val is None or str(val).strip() in ("", "nan"):
        return None
    cleaned = re.sub(r"[^\d.]", "", str(val))
    try:
        return float(cleaned)
    except ValueError:
        return None


def clean_csv(file_path: str) -> dict:
    df = pd.read_csv(file_path)
    raw_count = len(df)

    # 1. Remove exact duplicates
    df = df.drop_duplicates()

    # 2. Normalise date
    df["date"] = df["date"].apply(lambda x: parse_date(x))

    # 3. Clean amount
    df["amount"] = df["amount"].apply(clean_amount)

    # 4. Uppercase status & currency
    df["status"] = df["status"].astype(str).str.upper().str.strip()
    df["currency"] = df["currency"].astype(str).str.upper().str.strip()

    # 5. Fill missing category
    df["category"] = df["category"].fillna("Uncategorised").replace("", "Uncategorised")

    # 6. Generate txn_id for blanks
    df["txn_id"] = df["txn_id"].fillna("").astype(str)
    mask = df["txn_id"].str.strip() == ""
    df.loc[mask, "txn_id"] = [f"AUTO-{i}" for i in range(mask.sum())]

    clean_count = len(df)
    df = df.where(pd.notnull(df), None)

    return {
        "raw_count": raw_count,
        "clean_count": clean_count,
        "dataframe": df,
        "transactions": df.to_dict(orient="records"),
    }
