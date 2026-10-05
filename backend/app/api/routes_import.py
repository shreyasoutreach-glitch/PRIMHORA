from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.audit.logger import log as audit_log
from app.core.authz import get_tenant_db, require_permission
from app.models import entities as m
from app.services.incident.detector import create_incident_from_payouts, sync_financial_events_for_payouts
from app.services.imports.csv_payouts import normalize_payout_rows

router = APIRouter(tags=["imports"])

def _stable_id(prefix: str, value: str, length: int = 18) -> str:
    return f"{prefix}_{hashlib.sha256(value.encode('utf-8')).hexdigest()[:length]}"


@router.post("/import/payouts-csv")
async def import_payouts_csv(
    file: UploadFile = File(...),
    merchant_id: str = Form(""),
    merchant_name: str = Form(""),
    source_system: str = Form("csv"),
    db: Session = Depends(get_tenant_db),
    user: m.User = Depends(require_permission("INVESTIGATE")),
):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Only CSV imports are supported by this endpoint")

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


    merchant = db.get(m.Merchant, merchant_id) if merchant_id else None
    if merchant is None:
        name = merchant_name.strip() or file.filename.rsplit(".", 1)[0]
        merchant = m.Merchant(id=f"MER_{hashlib.sha256((user.tenant_id + name).encode()).hexdigest()[:10]}", name=name)
        db.add(merchant)
        db.flush()

    imported_ids: list[str] = []
    skipped = 0
    errors: list[str] = []
    rows = list(reader)
    try:
        parsed_rows = normalize_payout_rows(rows)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

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

            payout_id = f"CSV_{source_id}"[:32]
            existing = db.get(m.Payout, payout_id)
            if existing is not None:
                if existing.amount != amount or existing.created_at != timestamp:
                    raise ValueError(f"duplicate source id {source_id} conflicts with existing payout")
                skipped += 1
                continue

            beneficiary_key = beneficiary_id or f"{beneficiary}|{bank_account}|{ifsc}"
            contact_id = _stable_id("CON", f"{merchant.id}|{beneficiary_key}")
            contact = db.get(m.Contact, contact_id)
            if contact is None:
                contact = m.Contact(
                    id=contact_id, merchant_id=merchant.id, name=beneficiary,
                    type="vendor", created_at=timestamp,
                )
                db.add(contact)
                db.flush()

            fund_key = bank_account or ifsc or beneficiary_key
            fund_id = _stable_id("FA", f"{contact.id}|{fund_key}")
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

    incidents = []
    for payout in imported_payouts:
        baseline = __import__("app.services.incident.detector", fromlist=["build_baseline"]).build_baseline(
            db, merchant.id, exclude_payout_ids=set(imported_ids)
        )
        components = __import__("app.services.incident.detector", fromlist=["score_payout"]).score_payout(db, payout, baseline)
        from app.services.incident.scoring import incident_evidence_score
        if incident_evidence_score(components) >= 60:
            incident_id = f"INC_{hashlib.sha256((merchant.id + payout.id).encode()).hexdigest()[:10]}"
            incidents.append(create_incident_from_payouts(
                db, incident_id=incident_id, merchant_id=merchant.id,
                payout_ids=[payout.id], scenario="CSV_IMPORT_ANOMALY",
                dataset_version="csv-import-v1", config_version="v1",
            ))

    audit_log(
        db, incident_id="", actor="HUMAN", actor_user_id=user.id,
        event_type="CSV_PAYOUT_IMPORT",
        summary=f"Imported {len(imported_ids)} payout row(s) from {file.filename}",
        sources=imported_ids,
        detail={"merchant_id": merchant.id, "source_system": source_system, "skipped": skipped, "errors": len(errors)},
    )
    db.commit()

    return {
        "merchant_id": merchant.id,
        "merchant_name": merchant.name,
        "source_system": source_system,
        "received_rows": len(rows),
        "imported_rows": len(imported_ids),
        "skipped_rows": skipped,
        "error_rows": len(errors),
        "errors": errors[:20],
        "incident_count": len(incidents),
        "incident_ids": [i.id for i in incidents],
        "imported_payout_ids": imported_ids,
        "read_only": True,
    }
