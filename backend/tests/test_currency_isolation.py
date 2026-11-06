import datetime as dt
from decimal import Decimal

from app.models import entities as m
from app.services.incident.detector import build_baseline, score_payout


def test_foreign_currency_history_does_not_distort_baseline_or_velocity(db_session):
    merchant = m.Merchant(id="MER_CURRENCY", name="Currency Test Co", category="industrial")
    inr_contact = m.Contact(
        id="CON_INR", merchant_id=merchant.id, name="INR Vendor",
        type="vendor", created_at=dt.datetime(2026, 1, 1),
    )
    usd_contact = m.Contact(
        id="CON_USD", merchant_id=merchant.id, name="USD Vendor",
        type="vendor", created_at=dt.datetime(2026, 1, 1),
    )
    inr_fund = m.FundAccount(id="FA_INR", contact_id=inr_contact.id)
    usd_fund = m.FundAccount(id="FA_USD", contact_id=usd_contact.id)
    db_session.add_all([merchant, inr_contact, usd_contact, inr_fund, usd_fund])

    history_start = dt.datetime(2026, 1, 1, 10, 0)
    for index in range(12):
        db_session.add(m.Payout(
            id=f"PYO_INR_{index}", merchant_id=merchant.id,
            contact_id=inr_contact.id, fund_account_id=inr_fund.id,
            amount=Decimal(10000 + index * 100), currency="INR",
            status="processed", created_at=history_start + dt.timedelta(days=index),
        ))

    target_time = dt.datetime(2026, 6, 2, 10, 5)
    for index in range(3):
        db_session.add(m.Payout(
            id=f"PYO_USD_{index}", merchant_id=merchant.id,
            contact_id=usd_contact.id, fund_account_id=usd_fund.id,
            amount=Decimal("50000000"), currency="USD",
            status="processed", created_at=target_time - dt.timedelta(minutes=9 - index * 2),
        ))
    db_session.add(m.Payout(
        id="PYO_INR_FUTURE", merchant_id=merchant.id,
        contact_id=inr_contact.id, fund_account_id=inr_fund.id,
        amount=Decimal("9000000"), currency="INR",
        status="processed", created_at=target_time + dt.timedelta(minutes=1),
    ))
    db_session.commit()

    baseline = build_baseline(
        db_session, merchant.id, currency="INR", before=target_time,
    )
    assert len(baseline.payout_amounts) == 12
    assert baseline.median_payout == 10550

    target = m.Payout(
        id="PYO_INR_TARGET", merchant_id=merchant.id,
        contact_id=inr_contact.id, fund_account_id=inr_fund.id,
        amount=Decimal("15000"), currency="INR",
        status="processed", created_at=target_time,
    )
    components = score_payout(db_session, target, baseline)
    assert components.velocity_anomaly == 0.0
