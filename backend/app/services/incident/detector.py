"""
The orchestrator: turns a merchant's payout history + a candidate set of
suspicious payouts into an Incident record, with every component of the
Incident Evidence Score traceable back to a real query over financial
primitives. Used both by the seed script (to build the deterministic
flagship incident) and by the Chaos Lab endpoint (to detect a freshly
injected scenario against the *existing* baseline, live).
"""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy.orm import Session

from app.audit.logger import log as audit_log
from app.models import entities as m
from app.services.financial.baseline import (
    MerchantBaseline,
    compute_merchant_baseline,
    dormancy_seconds,
    rolling_window_stats,
)
from app.services.incident.scoring import (
    ScoreComponents,
    communication_component,
    incident_evidence_score,
    aggregate_incident_components,
    normalize_dormancy,
    normalize_historical_novelty,
    normalize_robust_z,
    normalize_velocity,
)


def sync_financial_events_for_payouts(db: Session, payouts: list[m.Payout], source_system: str = "razorpay") -> list[m.FinancialEvent]:
    """Explicitly propagates tenant_id from each source payout rather than
    relying on the session's current tenant context -- this function is
    sometimes called with a batch of payouts spanning multiple tenants (the
    seed script's final canonicalization pass), so it cannot assume a single
    session-wide tenant applies to every row it creates."""
    created = []
    for p in payouts:
        existing = db.get(m.FinancialEvent, f"FEV_PYO_{p.id}")
        if existing:
            continue
        fe = m.FinancialEvent(
            id=f"FEV_PYO_{p.id}",
            tenant_id=p.tenant_id,
            event_type="payout",
            source_system=source_system,
            source_record_id=p.id,
            merchant_id=p.merchant_id,
            counterparty_id=p.contact_id,
            timestamp=p.created_at,
            amount=p.amount,
            currency=p.currency,
            attributes={},
            evidence_refs=[],
            confidence=1.0,
            extraction_method="system_of_record",
        )
        db.add(fe)
        created.append(fe)
    db.flush()
    return created


def build_baseline(
    db: Session,
    merchant_id: str,
    exclude_payout_ids: set[str] | None = None,
    *,
    currency: str | None = None,
    before: dt.datetime | None = None,
) -> MerchantBaseline:
    """The behavioral baseline is always computed from non-injected history.
    A payout marked is_injected (seeded flagship incident or a live Chaos Lab
    scenario) is, by definition, the thing being measured against the
    baseline -- it must never leak into the baseline itself, or every
    incident would quietly shrink its own anomaly score."""
    exclude_payout_ids = exclude_payout_ids or set()
    payouts = db.query(m.Payout).filter(m.Payout.merchant_id == merchant_id).all()
    currency_code = currency.upper() if currency else None
    historical = [
        p.amount for p in payouts
        if p.id not in exclude_payout_ids
        and not p.is_injected
        and (currency_code is None or p.currency.upper() == currency_code)
        and (before is None or p.created_at < before)
    ]
    injected_contact_ids = {p.contact_id for p in payouts if p.is_injected}
    contact_query = db.query(m.Contact).filter(m.Contact.merchant_id == merchant_id)
    if injected_contact_ids:
        contact_query = contact_query.filter(m.Contact.id.notin_(injected_contact_ids))
    beneficiary_count = contact_query.count()
    return compute_merchant_baseline(merchant_id, historical, beneficiary_count)


def _prior_payout_count_for_contact(db: Session, contact_id: str, before: dt.datetime) -> int:
    return (
        db.query(m.Payout)
        .filter(m.Payout.contact_id == contact_id, m.Payout.created_at < before)
        .count()
    )


def _last_payout_before(db: Session, contact_id: str, before: dt.datetime) -> m.Payout | None:
    return (
        db.query(m.Payout)
        .filter(m.Payout.contact_id == contact_id, m.Payout.created_at < before)
        .order_by(m.Payout.created_at.desc())
        .first()
    )


def score_payout(db: Session, payout: m.Payout, baseline: MerchantBaseline,
                  communication_status: str = "UNCORRELATED") -> ScoreComponents:
    contact = db.get(m.Contact, payout.contact_id)
    prior_count = _prior_payout_count_for_contact(db, payout.contact_id, payout.created_at)
    is_new = prior_count == 0

    last_payout = _last_payout_before(db, payout.contact_id, payout.created_at)
    dormant_seconds = dormancy_seconds(last_payout.created_at if last_payout else None, payout.created_at)
    dormant_component = 0.0 if is_new else normalize_dormancy(dormant_seconds)

    all_recent = (
        db.query(m.Payout)
        .filter(
            m.Payout.merchant_id == payout.merchant_id,
            m.Payout.currency == payout.currency,
            m.Payout.created_at < payout.created_at,
        )
        .all()
    )
    rolling_count, rolling_amount = rolling_window_stats(
        [(p.created_at, p.amount) for p in all_recent], payout.created_at, window_minutes=10
    )

    return ScoreComponents(
        new_beneficiary=1.0 if is_new else 0.0,
        amount_anomaly=normalize_robust_z(baseline.robust_z(payout.amount)),
        velocity_anomaly=normalize_velocity(rolling_count, rolling_amount, baseline.median_payout),
        historical_novelty=normalize_historical_novelty(prior_count),
        dormant_entity=dormant_component,
        communication_correlation=communication_component(communication_status),
    )


def create_incident_from_payouts(
    db: Session,
    *,
    incident_id: str,
    merchant_id: str,
    payout_ids: list[str],
    scenario: str,
    dataset_version: str = "v1",
    config_version: str = "v1",
) -> m.Incident:
    payouts = (
        db.query(m.Payout).filter(m.Payout.id.in_(payout_ids)).order_by(m.Payout.created_at).all()
    )
    if not payouts:
        raise ValueError("No payouts supplied for incident")

    sync_financial_events_for_payouts(db, payouts)
    incident_payout_ids = {p.id for p in payouts}

    comm_events = db.query(m.CommunicationEvent).filter(m.CommunicationEvent.incident_id == incident_id).all()

    per_payout_components: list[ScoreComponents] = []
    for idx, payout in enumerate(payouts):
        matching_comm = next(
            (c for c in comm_events
             if c.correlated_financial_event_id == f"FEV_PYO_{payout.id}"),
            None,
        )
        comm_status = matching_comm.correlation_status if matching_comm else "UNCORRELATED"
        # Compare only with earlier history in the same currency. A USD payout
        # must never inflate or suppress an INR anomaly (or vice versa).
        baseline = build_baseline(
            db, merchant_id, exclude_payout_ids=incident_payout_ids,
            currency=payout.currency, before=payout.created_at,
        )
        components = score_payout(db, payout, baseline, comm_status)
        per_payout_components.append(components)

        fe = db.get(m.FinancialEvent, f"FEV_PYO_{payout.id}")
        fe.attributes = {
            **(fe.attributes or {}),
            "score_components": components.as_dict(),
            "robust_z": round(baseline.robust_z(payout.amount), 2),
            "multiple_of_median": round(baseline.multiple_of_median(payout.amount), 2),
        }
        db.add(m.IncidentEvent(
            id=f"IEV_{uuid.uuid4().hex[:10]}",
            incident_id=incident_id,
            financial_event_id=fe.id,
            role="suspicious_payout",
            sequence=idx,
        ))

    # Incident-level components preserve the strongest event while also
    # accounting for how broadly the pattern appears across the case.
    incident_components = aggregate_incident_components(per_payout_components)
    score = incident_evidence_score(incident_components)

    incident = db.get(m.Incident, incident_id)
    if incident is None:
        incident = m.Incident(id=incident_id, merchant_id=merchant_id)
        db.add(incident)

    incident.scenario = scenario
    incident.incident_evidence_score = score
    incident.score_components = incident_components.as_dict()
    incident.window_start = payouts[0].created_at
    incident.window_end = payouts[-1].created_at
    incident.dataset_version = dataset_version
    incident.config_version = config_version
    incident.state = "RECONSTRUCTING"
    db.flush()

    audit_log(
        db,
        incident_id=incident_id,
        actor="SYSTEM",
        event_type="INCIDENT_CREATED",
        summary=f"Incident evidence score {score}/100 across {len(payouts)} payouts",
        sources=[p.id for p in payouts],
        detail={"score_components": incident_components.as_dict()},
    )
    db.commit()
    return incident
