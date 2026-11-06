from __future__ import annotations

import datetime as dt
import re
from decimal import Decimal, InvalidOperation

ALIASES = {
    "transaction_id": ("transaction_id", "payout_id", "txn_id", "id", "reference_id"),
    "timestamp": ("timestamp", "created_at", "event_time", "date", "transaction_date"),
    "amount": ("amount", "value", "payout_amount"),
    "currency": ("currency", "ccy"),
    "status": ("status", "state"),
    "beneficiary": ("beneficiary", "beneficiary_name", "vendor", "vendor_name", "payee"),
    "beneficiary_id": ("beneficiary_id", "vendor_id", "contact_id", "destination_id", "account_id"),
    "bank_account": ("bank_account", "account_number", "masked_bank_account"),
    "ifsc": ("ifsc", "bank_ifsc", "masked_ifsc"),
    "reference": ("reference", "reference_id", "narration", "description"),
}

def _pick(row: dict[str, str], key: str) -> str:
    lowered = {str(k).strip().lower(): (v or "") for k, v in row.items()}
    for alias in ALIASES[key]:
        if lowered.get(alias, "").strip():
            return lowered[alias].strip()
    return ""

def _parse_timestamp(raw: str) -> dt.datetime:
    value = raw.strip().replace("Z", "+00:00")
    parsed = dt.datetime.fromisoformat(value)
    if parsed.tzinfo:
        parsed = parsed.astimezone(dt.timezone.utc).replace(tzinfo=None)
    return parsed

def normalize_payout_rows(rows: list[dict[str, str]]) -> list[dict]:
    if not rows:
        raise ValueError("CSV has no data rows")
    fields = {str(k).strip().lower() for k in rows[0].keys()}
    for required in ("transaction_id", "timestamp", "amount"):
        if not any(alias in fields for alias in ALIASES[required]):
            raise ValueError(f"CSV is missing required field: {required}")

    parsed = []
    for index, row in enumerate(rows, start=2):
        source_id = _pick(row, "transaction_id")
        timestamp_raw = _pick(row, "timestamp")
        amount_raw = _pick(row, "amount").replace(",", "").replace("₹", "").strip()
        if not source_id or not timestamp_raw or not amount_raw:
            raise ValueError(f"row {index}: transaction_id, timestamp and amount are required")
        try:
            amount = Decimal(amount_raw)
        except InvalidOperation as exc:
            raise ValueError(f"row {index}: invalid amount") from exc
        if not amount.is_finite():
            raise ValueError(f"row {index}: amount must be a finite number")
        if amount < 0:
            raise ValueError(f"row {index}: amount must not be negative")
        currency = (_pick(row, "currency") or "INR").strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", currency):
            raise ValueError(f"row {index}: currency must be a 3-letter ISO-style code")
        parsed.append({
            "source_id": source_id,
            "timestamp": _parse_timestamp(timestamp_raw),
            "amount": amount,
            "currency": currency,
            "status": _pick(row, "status") or "processed",
            "beneficiary": _pick(row, "beneficiary") or "Unknown beneficiary",
            "beneficiary_id": _pick(row, "beneficiary_id"),
            "bank_account": _pick(row, "bank_account"),
            "ifsc": _pick(row, "ifsc"),
            "reference": _pick(row, "reference") or source_id,
        })
    return parsed
