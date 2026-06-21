"""
LLM service using Gemini 2.5 Flash.

Responsibilities:
  - Batch classify transactions without categories.
  - Generate a structured narrative summary.
  - Retry failed calls up to 3 times with exponential backoff.
"""

import json
import logging
import time
from collections import defaultdict
from typing import Any

import google.generativeai as genai

from app.config import settings

logger = logging.getLogger(__name__)

# Categories the LLM is allowed to assign
VALID_CATEGORIES = {
    "Food",
    "Shopping",
    "Travel",
    "Transport",
    "Utilities",
    "Cash Withdrawal",
    "Entertainment",
    "Other",
}

_MODEL_NAME = "gemini-2.5-flash"


def _get_model() -> genai.GenerativeModel:
    genai.configure(api_key=settings.GEMINI_API_KEY)
    return genai.GenerativeModel(_MODEL_NAME)


def _call_with_retry(model: genai.GenerativeModel, prompt: str, max_retries: int = 3) -> str | None:
    """Call Gemini with exponential backoff retry. Returns raw text or None."""
    delay = 2
    for attempt in range(1, max_retries + 1):
        try:
            response = model.generate_content(prompt)
            return response.text
        except Exception as exc:
            logger.warning("LLM call failed (attempt %d/%d): %s", attempt, max_retries, exc)
            if attempt < max_retries:
                time.sleep(delay)
                delay *= 2
    return None


def classify_transactions(transactions: list[dict]) -> list[dict]:
    """
    For transactions with category == 'Uncategorised', use a single batched
    LLM call to assign a category. Returns the updated list.

    Marks `llm_failed=True` on any transaction whose category could not be
    classified if the LLM call fails.
    """
    # Identify indices needing classification
    to_classify = [
        (i, txn)
        for i, txn in enumerate(transactions)
        if (txn.get("category") or "").strip().lower() == "uncategorised"
    ]

    if not to_classify:
        return transactions

    model = _get_model()

    # Build a single prompt with all uncategorised transactions
    items_text = "\n".join(
        f'{idx}. merchant="{txn.get("merchant")}", amount={txn.get("amount")}, '
        f'currency={txn.get("currency")}, notes="{txn.get("notes")}"'
        for idx, (_, txn) in enumerate(to_classify)
    )

    prompt = f"""You are a financial transaction classifier.
Classify each transaction below into EXACTLY ONE of these categories:
Food, Shopping, Travel, Transport, Utilities, Cash Withdrawal, Entertainment, Other.

Return a JSON array with one object per transaction in the same order:
[{{"index": 0, "category": "..."}}, ...]

Transactions:
{items_text}

Respond ONLY with valid JSON. No explanation."""

    raw = _call_with_retry(model, prompt)

    if raw is None:
        # Mark all as llm_failed
        for _, (orig_idx, _) in enumerate(to_classify):
            transactions[orig_idx]["llm_failed"] = True
        return transactions

    # Parse response
    try:
        # Strip markdown code fences if present
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        classifications: list[dict] = json.loads(clean.strip())

        for item in classifications:
            list_idx = item.get("index")
            category = item.get("category", "Other")
            if category not in VALID_CATEGORIES:
                category = "Other"
            if list_idx is not None and list_idx < len(to_classify):
                orig_idx = to_classify[list_idx][0]
                transactions[orig_idx]["llm_category"] = category
                transactions[orig_idx]["llm_raw_response"] = raw
                transactions[orig_idx]["llm_failed"] = False
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        logger.error("Failed to parse LLM classification response: %s | raw: %s", exc, raw)
        for _, (orig_idx, _) in enumerate(to_classify):
            transactions[orig_idx]["llm_failed"] = True

    return transactions


def generate_narrative_summary(transactions: list[dict]) -> dict[str, Any]:
    """
    Make a single LLM call to produce a structured JSON summary.
    Returns a dict with keys: total_spend_inr, total_spend_usd, top_merchants,
    anomaly_count, narrative, risk_level, category_breakdown.
    Falls back to computed values if LLM call fails.
    """
    model = _get_model()

    # Pre-compute stats to feed the LLM
    inr_total = sum(
        float(t["amount"])
        for t in transactions
        if t.get("currency", "").upper() == "INR" and t.get("amount") is not None
    )
    usd_total = sum(
        float(t["amount"])
        for t in transactions
        if t.get("currency", "").upper() == "USD" and t.get("amount") is not None
    )
    anomaly_count = sum(1 for t in transactions if t.get("is_anomaly"))

    merchant_totals: dict[str, float] = defaultdict(float)
    for t in transactions:
        if t.get("merchant") and t.get("amount") is not None:
            merchant_totals[t["merchant"]] += float(t["amount"])
    top_merchants = sorted(merchant_totals.items(), key=lambda x: x[1], reverse=True)[:3]
    top_merchants_list = [{"merchant": m, "total": round(v, 2)} for m, v in top_merchants]

    category_totals: dict[str, float] = defaultdict(float)
    for t in transactions:
        effective_cat = t.get("llm_category") or t.get("category") or "Uncategorised"
        if t.get("amount") is not None:
            category_totals[effective_cat] += float(t["amount"])
    category_breakdown = {k: round(v, 2) for k, v in category_totals.items()}

    prompt = f"""You are a financial analysis AI. Based on the transaction data below, produce a JSON summary.

Stats:
- Total INR spend: {inr_total:.2f}
- Total USD spend: {usd_total:.2f}
- Anomaly count: {anomaly_count}
- Top merchants by spend: {top_merchants_list}
- Category breakdown: {category_breakdown}
- Total transactions: {len(transactions)}

Produce a JSON object with these exact keys:
{{
  "narrative": "<2-3 sentence spending summary>",
  "risk_level": "<low|medium|high>"
}}

Rules for risk_level:
- high: anomaly_count >= 5 or any transaction > 100000
- medium: anomaly_count >= 2 or any transaction > 50000
- low: otherwise

Respond ONLY with valid JSON."""

    raw = _call_with_retry(model, prompt)

    narrative = "Unable to generate narrative (LLM unavailable)."
    risk_level = "low"

    if raw:
        try:
            clean = raw.strip()
            if clean.startswith("```"):
                clean = clean.split("```")[1]
                if clean.startswith("json"):
                    clean = clean[4:]
            parsed = json.loads(clean.strip())
            narrative = parsed.get("narrative", narrative)
            risk_level = parsed.get("risk_level", "low")
            if risk_level not in {"low", "medium", "high"}:
                risk_level = "low"
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.error("Failed to parse LLM narrative response: %s", exc)

    return {
        "total_spend_inr": round(inr_total, 2),
        "total_spend_usd": round(usd_total, 2),
        "top_merchants": top_merchants_list,
        "anomaly_count": anomaly_count,
        "category_breakdown": category_breakdown,
        "narrative": narrative,
        "risk_level": risk_level,
    }
