from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.config import get_settings
from app.models import entities as m
from app.services.integrations.razorpayx import normalize_payout, verify_webhook_signature

router = APIRouter(tags=["webhooks"])
settings = get_settings()


def _upsert_payout(db: Session, merchant_id: str, payload: dict) -> str:
    normalized = normalize_payout(payload)
    payout_id = normalized["external_id"]
    if not payout_id:
        raise HTTPException(400, "Webhook payout id missing")

    existing = db.get(m.Payout, payout_id)
    if existing:
        existing.status = normalized["status"]
        existing.amount = normalized["amount"]
        existing.reference_id = normalized["reference_id"]
        existing.narration = normalized["narration"]
        existing.created_at = normalized["created_at"]
        return payout_id

    contact_id = normalized["contact_id"] or f"RZP_CONTACT_{uuid.uuid4().hex[:10]}"
    contact = db.get(m.Contact, contact_id)
    if contact is None:
        contact = m.Contact(
            id=contact_id,
            merchant_id=merchant_id,
            name=normalized["contact_name"],
            type=normalized["contact_type"],
            phone=normalized["phone"],
            email=normalized["email"],
            upi_id=normalized["vpa"],
            created_at=normalized["created_at"],
        )
        db.add(contact)
        db.flush()

    fund_id = normalized["fund_account_id"] or f"RZP_FA_{uuid.uuid4().hex[:10]}"
    fund = db.get(m.FundAccount, fund_id)
    if fund is None:
        fund = m.FundAccount(
            id=fund_id,
            contact_id=contact.id,
            account_type=normalized["account_type"],
            masked_bank_account=normalized["masked_bank_account"],
            masked_ifsc=normalized["masked_ifsc"],
            vpa=normalized["vpa"],
            created_at=normalized["created_at"],
        )
        db.add(fund)
        db.flush()

    db.add(
        m.Payout(
            id=payout_id,
            merchant_id=merchant_id,
            contact_id=contact.id,
            fund_account_id=fund.id,
            amount=normalized["amount"],
            currency=normalized["currency"],
            purpose=normalized["purpose"],
            mode=normalized["mode"],
            narration=normalized["narration"],
            reference_id=normalized["reference_id"],
            status=normalized["status"],
            created_at=normalized["created_at"],
            is_injected=False,
        )
    )
    return payout_id


@router.post("/webhooks/razorpay")
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: str = Header(default=""),
    x_razorpay_event_id: str = Header(default=""),
):
    if settings.demo_mode:
        raise HTTPException(404, "Provider webhooks are disabled in demo mode")
    secret = settings.razorpay_webhook_secret
    merchant_id = settings.razorpay_merchant_id
    tenant_id = settings.razorpay_tenant_id
    if not secret or not merchant_id or not tenant_id:
        raise HTTPException(503, "Razorpay webhook integration is not configured")

    raw = await request.body()
    if not verify_webhook_signature(raw, x_razorpay_signature, secret):
        raise HTTPException(401, "Invalid Razorpay webhook signature")

    payload = json.loads(raw.decode("utf-8"))
    event_id = x_razorpay_event_id or f"evt_{uuid.uuid5(uuid.NAMESPACE_URL, raw.decode('utf-8'))}"

    db = SessionLocal()
    try:
        # The integration configuration binds this webhook to exactly one
        # tenant. No global merchant lookup is performed with the runtime role.
        db.set_tenant(tenant_id)
        merchant = db.get(m.Merchant, merchant_id)
        if merchant is None or merchant.tenant_id != tenant_id:
            raise HTTPException(404, "Configured Razorpay merchant does not exist in the configured tenant")

        if db.get(m.WebhookEvent, event_id):
            return {"status": "duplicate_ignored", "event_id": event_id}

        event = m.WebhookEvent(
            id=event_id,
            event_type=payload.get("event", "unknown"),
            source_object_type="payout",
            source_object_id=(
                payload.get("payload", {}).get("payout", {}).get("entity", {}).get("id", "")
            ),
            merchant_id=merchant_id,
            tenant_id=tenant_id,
            payload=payload,
        )
        db.add(event)
        db.flush()

        payout_entity = payload.get("payload", {}).get("payout", {}).get("entity")
        if payout_entity:
            _upsert_payout(db, merchant_id, payout_entity)

        db.commit()
        return {"status": "accepted", "event_id": event_id}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
