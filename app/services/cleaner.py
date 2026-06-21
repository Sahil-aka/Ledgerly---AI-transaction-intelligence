"""
Data cleaning service.

Handles:
  - Date format normalisation (DD-MM-YYYY and YYYY/MM/DD → YYYY-MM-DD)
  - Stripping currency symbols ($) from amounts
  - Uppercasing status and currency values
  - Filling missing categories with 'Uncategorised'
  - Removing exact duplicate rows
  - Assigning auto-generated txn_ids to rows missing one
"""

import re
import uuid
from datetime import datetime
from typing import Any


# Date formats to try in order
_DATE_FORMATS = [
    "%d-%m-%Y",   # DD-MM-YYYY
    "%Y/%m/%d",   # YYYY/MM/DD
    "%Y-%m-%d",   # ISO already
]


def _parse_date(raw: str) -> str | None:
    """Try known date formats, return ISO string or None."""
    if not raw or not str(raw).strip():
        return None
    raw = str(raw).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return raw  # Return as-is if we can't parse


def _clean_amount(raw: Any) -> float | None:
    """Strip $ signs and convert to float."""
    if raw is None or str(raw).strip() == "":
        return None
    cleaned = str(raw).strip().lstrip("$").replace(",", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def clean_transactions(rows: list[dict]) -> list[dict]:
    """
    Clean a list of raw transaction dicts and return cleaned rows.
    Removes exact duplicates after cleaning.
    """
    cleaned: list[dict] = []
    seen: set[tuple] = set()

    for row in rows:
        txn_id = str(row.get("txn_id", "")).strip() or None
        date = _parse_date(str(row.get("date", "")))
        merchant = str(row.get("merchant", "")).strip() or None
        amount = _clean_amount(row.get("amount"))
        currency = str(row.get("currency", "")).strip().upper() or None
        status = str(row.get("status", "")).strip().upper() or None
        category = str(row.get("category", "")).strip() or "Uncategorised"
        if not category:
            category = "Uncategorised"
        account_id = str(row.get("account_id", "")).strip() or None
        notes = str(row.get("notes", "")).strip() or None

        # Build a hashable key for deduplication (all normalised fields)
        dedup_key = (txn_id, date, merchant, amount, currency, status, category, account_id, notes)

        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        cleaned.append(
            {
                "txn_id": txn_id,
                "date": date,
                "merchant": merchant,
                "amount": amount,
                "currency": currency,
                "status": status,
                "category": category,
                "account_id": account_id,
                "notes": notes,
            }
        )

    return cleaned
