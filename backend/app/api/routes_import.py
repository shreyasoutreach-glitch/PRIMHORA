from __future__ import annotations

import csv
import hashlib
import io

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.audit.logger import log as audit_log
from app.core.authz import get_tenant_db, require_permission
from app.models import entities as m
from app.services.incident.detector import (
    build_baseline,
    create_incident_from_payouts,
    score_payout,
    sync_financial_events_for_payouts,
)
from app.services.incident.scoring import incident_evidence_score
from app.services.imports.csv_payouts import normalize_payout_rows

router = APIRouter(tags=["imports"])

MIN_BASELINE_OBSERVATIONS = 10
MAX_IMPORT_ROWS = 50_000


def _stable_id(prefix: str, value: str, length: int = 18) -> str:
    return f"{prefix}_{hashlib.sha256(value.encode('utf-8')).hexdigest()[:length]}"


@router.post("/import/payouts-csv")
async def import_payouts_csv(
    file: UploadFile = File(...),
    merchant_id: str = Form(""),
    merchant_name: str = Form(""),
    source_system: str = Form("csv"),
    import_mode: str = Form("monitor"),
    db: Session = Depends(get_tenant_db),
    user: m.User = Depends(require_permission("INVESTIGATE")),
):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Only CSV imports are supported by this endpoint")
    import_mode = import_mode.strip().lower()
    if import_mode not in {"baseline", "monitor"}:
        raise HTTPException(400, "import_mode must be 'baseline' or 'monitor'")

    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(413, "CSV exceeds the 10 MB import limit")

    try:
        text = data.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
    except UnicodeDecodeError as exc:
        raise HTTPException(400, "CSV must be UTF-8 encoded") from exc

    if not reader.fieldnames:
        raise HTTPException(400, "CSV has no header row")
    rows = list(reader)
    if len(rows) > MAX_IMPORT_ROWS:
        raise HTTPException(413, f"CSV exceeds the {MAX_IMPORT_ROWS:,} row import limit")
    try:
        parsed_rows = normalize_payout_rows(rows)
    except (ValueError, OverflowError) as exc:
        raise HTTPException(422, str(exc)) from exc

    # Resolve/create the merchant only after the entire file passes structural
    # validation, so malformed uploads cannot leave empty merchant records.
    merchant = db.get(m.Merchant, merchant_id) if merchant_id else None
    if merchant is None:
        name = merchant_name.strip() or file.filename.rsplit(".", 1)[0]
        merchant = m.Merchant(
            id=f"MER_{hashlib.sha256((user.tenant_id + name).encode()).hexdigest()[:10]}",
            name=name,
        )
        db.add(merchant)
        db.flush()

    imported_ids: list[str] = []
    skipped = 0
    errors: list[str] = []

    for row_number, row in enumerate(parsed_rows, start=2):
        try:
            source_id = row["source_id"]
            timestamp = row["timestamp"]
            amount = row["amount"]
            currency = row["currency"]
            status = row["status"]
            beneficiary = row["beneficiary"]
            beneficiary_id = row["beneficiary_id"]
            bank_account = row["bank_account"]
            ifsc = row["ifsc"]
            reference = row["reference"]

            # Payout IDs are globally unique primary keys. Namespace by tenant,
            # merchant and provider source ID; do not truncate raw IDs into collisions.
            payout_id = _stable_id(
                "CSV", f"{user.tenant_id}|{merchant.id}|{source_id}", length=28
            )
            beneficiary_key = beneficiary_id or f"{beneficiary}|{bank_account}|{ifsc}"
            contact_id = _stable_id("CON", f"{merchant.id}|{beneficiary_key}")
            fund_key = bank_account or ifsc or beneficiary_key
            fund_id = _stable_id("FA", f"{contact_id}|{fund_key}")

            existing = db.get(m.Payout, payout_id)
            if existing is not None:
                same_payload = (
                    existing.amount == amount
                    and existing.created_at == timestamp
                    and existing.currency.upper() == currency
                    and existing.status.strip().lower() == status.strip().lower()
                    and existing.contact_id == contact_id
                    and existing.fund_account_id == fund_id
                )
                if not same_payload:
                    raise ValueError(
                        f"duplicate source id {source_id} conflicts with previously imported "
                        "amount, timestamp, currency, status or beneficiary details"
                    )
                skipped += 1
                continue

            contact = db.get(m.Contact, contact_id)
            if contact is None:
                contact = m.Contact(
                    id=contact_id, merchant_id=merchant.id, name=beneficiary,
                    type="vendor", created_at=timestamp,
                )
                db.add(contact)
                db.flush()

            fund = db.get(m.FundAccount, fund_id)
            if fund is None:
                fund = m.FundAccount(
                    id=fund_id, contact_id=contact.id,
                    masked_bank_account=bank_account, masked_ifsc=ifsc,
                    account_type="bank_account", created_at=timestamp,
                )
                db.add(fund)
                db.flush()

            payout = m.Payout(
                id=payout_id, merchant_id=merchant.id, contact_id=contact.id,
                fund_account_id=fund.id, amount=amount, currency=currency,
                status=status, reference_id=reference or source_id,
                created_at=timestamp, is_injected=False,
            )
            db.add(payout)
            db.flush()
            imported_ids.append(payout.id)
        except (ValueError, TypeError) as exc:
            errors.append(f"row {row_number}: {exc}")

    if errors and not imported_ids:
        db.rollback()
        raise HTTPException(422, {"message": "No valid rows imported", "errors": errors[:20]})

    imported_payouts = [db.get(m.Payout, pid) for pid in imported_ids]
    imported_payouts = [p for p in imported_payouts if p is not None]
    sync_financial_events_for_payouts(db, imported_payouts, source_system=source_system)

    currencies = sorted({row["currency"] for row in parsed_rows})
    excluded_ids = set(imported_ids)
    baseline_observations: dict[str, int] = {}
    for currency in currencies:
        currency_times = [
            payout.created_at for payout in imported_payouts
            if payout.currency.upper() == currency
        ]
        if import_mode == "baseline":
            baseline = build_baseline(db, merchant.id, currency=currency)
        else:
            baseline = build_baseline(
                db, merchant.id, exclude_payout_ids=excluded_ids,
                currency=currency, before=min(currency_times) if currency_times else None,
            )
        baseline_observations[currency] = len(baseline.payout_amounts)

    incidents = []
    skipped_for_insufficient_baseline = 0
    if import_mode == "monitor":
        for payout in imported_payouts:
            baseline = build_baseline(
                db,
                merchant.id,
                exclude_payout_ids=excluded_ids,
                currency=payout.currency,
                before=payout.created_at,
            )
            if len(baseline.payout_amounts) < MIN_BASELINE_OBSERVATIONS:
                skipped_for_insufficient_baseline += 1
                continue

            components = score_payout(db, payout, baseline)
            if incident_evidence_score(components) >= 60:
                incident_id = f"INC_{hashlib.sha256((merchant.id + payout.id).encode()).hexdigest()[:10]}"
                incidents.append(create_incident_from_payouts(
                    db, incident_id=incident_id, merchant_id=merchant.id,
                    payout_ids=[payout.id], scenario="CSV_IMPORT_ANOMALY",
                    dataset_version="csv-import-v2", config_version="currency-aware-v2",
                ))

    audit_log(
        db, incident_id="", actor="HUMAN", actor_user_id=user.id,
        event_type="CSV_PAYOUT_IMPORT",
        summary=f"Imported {len(imported_ids)} payout row(s) from {file.filename}",
        sources=imported_ids,
        detail={
            "merchant_id": merchant.id,
            "source_system": source_system,
            "import_mode": import_mode,
            "skipped": skipped,
            "errors": len(errors),
            "baseline_observations": baseline_observations,
            "insufficient_baseline_rows": skipped_for_insufficient_baseline,
        },
    )
    db.commit()

    baseline_ready = {
        currency: count >= MIN_BASELINE_OBSERVATIONS
        for currency, count in baseline_observations.items()
    }
    if import_mode == "baseline":
        monitoring_note = (
            "Historical records stored as the baseline. Upload a later payout period "
            "in Monitor mode to evaluate new activity."
        )
    elif skipped_for_insufficient_baseline:
        monitoring_note = (
            f"{skipped_for_insufficient_baseline} payout(s) were not scored because their "
            f"currency has fewer than {MIN_BASELINE_OBSERVATIONS} earlier historical observations."
        )
    else:
        monitoring_note = (
            "Each monitored payout was compared with earlier history in the same currency. "
            "The evidence score is a review signal, not a fraud probability."
        )

    return {
        "merchant_id": merchant.id,
        "merchant_name": merchant.name,
        "source_system": source_system,
        "import_mode": import_mode,
        "received_rows": len(rows),
        "imported_rows": len(imported_ids),
        "skipped_rows": skipped,
        "error_rows": len(errors),
        "errors": errors[:20],
        "incident_count": len(incidents),
        "incident_ids": [i.id for i in incidents],
        "imported_payout_ids": imported_ids,
        "baseline_observations_by_currency": baseline_observations,
        "baseline_ready_by_currency": baseline_ready,
        "minimum_baseline_observations": MIN_BASELINE_OBSERVATIONS,
        "skipped_for_insufficient_baseline": skipped_for_insufficient_baseline,
        "monitoring_note": monitoring_note,
        "read_only": True,
    }
