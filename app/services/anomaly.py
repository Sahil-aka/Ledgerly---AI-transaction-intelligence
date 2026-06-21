"""
Anomaly detection service.

Rules:
  1. Statistical outlier: amount > 3× the account's median amount.
  2. Currency mismatch: currency is USD but merchant is a domestic-only brand.
"""

import statistics
from collections import defaultdict


# Known domestic-only Indian merchants that should never appear with USD
DOMESTIC_ONLY_MERCHANTS = {
    "swiggy",
    "ola",
    "irctc",
    "zomato",
    "jio recharge",
    "bookmyshow",
    "hdfc atm",
    "flipkart",
}


def detect_anomalies(transactions: list[dict]) -> list[dict]:
    """
    Annotate each transaction dict with `is_anomaly` and `anomaly_reason`.
    Returns the same list with those fields populated.
    """
    # Build per-account amount lists for median calculation
    account_amounts: dict[str, list[float]] = defaultdict(list)
    for txn in transactions:
        acct = txn.get("account_id")
        amt = txn.get("amount")
        if acct and amt is not None:
            account_amounts[acct].append(float(amt))

    # Compute medians
    account_medians: dict[str, float] = {}
    for acct, amounts in account_amounts.items():
        account_medians[acct] = statistics.median(amounts)

    annotated: list[dict] = []
    for txn in transactions:
        reasons: list[str] = []

        # Rule 1: Statistical outlier
        acct = txn.get("account_id")
        amt = txn.get("amount")
        if acct and amt is not None and acct in account_medians:
            median = account_medians[acct]
            if median > 0 and float(amt) > 3 * median:
                reasons.append(
                    f"Amount {amt} exceeds 3x account median ({median:.2f})"
                )

        # Rule 2: Domestic merchant billed in USD
        currency = (txn.get("currency") or "").upper()
        merchant = (txn.get("merchant") or "").lower().strip()
        if currency == "USD" and any(dm in merchant for dm in DOMESTIC_ONLY_MERCHANTS):
            reasons.append(
                f"Domestic-only merchant '{txn.get('merchant')}' billed in USD"
            )

        txn["is_anomaly"] = bool(reasons)
        txn["anomaly_reason"] = "; ".join(reasons) if reasons else None
        annotated.append(txn)

    return annotated
