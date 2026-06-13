import pandas as pd

DOMESTIC_MERCHANTS = {"swiggy", "ola", "irctc", "zomato", "bigbasket", "namma yatri", "rapido"}


def detect_anomalies(df: pd.DataFrame) -> pd.DataFrame:
    """
    Flag:
      1. Statistical outlier: amount > 3x the account's median
      2. Currency mismatch: USD transaction at a domestic-only merchant
    Returns dataframe with is_anomaly (bool) and anomaly_reason (str) columns.
    """
    df = df.copy()
    df["is_anomaly"] = False
    df["anomaly_reason"] = None

    # --- Rule 1: Statistical outlier per account ---
    if "account_id" in df.columns and "amount" in df.columns:
        median_by_account = (
            df.dropna(subset=["amount", "account_id"])
            .groupby("account_id")["amount"]
            .median()
        )
        for idx, row in df.iterrows():
            acct = row.get("account_id")
            amt = row.get("amount")
            if acct and amt is not None and acct in median_by_account:
                median = median_by_account[acct]
                if median and amt > 3 * median:
                    df.at[idx, "is_anomaly"] = True
                    reason = df.at[idx, "anomaly_reason"] or ""
                    df.at[idx, "anomaly_reason"] = (
                        (reason + "; " if reason else "")
                        + f"Amount {amt:.2f} exceeds 3x account median ({median:.2f})"
                    )

    # --- Rule 2: USD + domestic merchant ---
    if "currency" in df.columns and "merchant" in df.columns:
        for idx, row in df.iterrows():
            merchant_lower = str(row.get("merchant", "")).lower().strip()
            currency = str(row.get("currency", "")).upper().strip()
            if currency == "USD" and any(d in merchant_lower for d in DOMESTIC_MERCHANTS):
                df.at[idx, "is_anomaly"] = True
                reason = df.at[idx, "anomaly_reason"] or ""
                df.at[idx, "anomaly_reason"] = (
                    (reason + "; " if reason else "")
                    + f"USD currency used at domestic merchant '{row.get('merchant')}'"
                )

    return df
