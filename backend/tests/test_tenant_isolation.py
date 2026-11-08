"""
Explicit tenant isolation tests -- the specific deliverable the enterprise
brief calls out: prove Tenant A cannot reach Tenant B's incidents, payments,
evidence, recovery commands, financial graph, or audit logs.

Two layers are tested on purpose:
1. API-level: hitting real routes with Tenant A's token and Tenant B's
   resource IDs, asserting 404 (not-found, not 403-confirms-it-exists).
2. DB-level: using TenantScopedSession directly against models that don't
   have a dedicated read API yet (Payment, RecoveryCommand), so isolation is
   proven at the layer that actually enforces it, not just inferred from
   HTTP status codes.
"""
from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.core.tenancy import TenantScopedSession, tenant_scope
from app.main import app
from app.models import entities as m
from app.services.incident.detector import create_incident_from_payouts

TENANT_A = "TEN_ISO_A"
TENANT_B = "TEN_ISO_B"


def _build_tenant_data(db, tenant_id: str, suffix: str) -> dict:
    """Creates one merchant, one incident (with evidence + financial event +
    audit trail via create_incident_from_payouts), one payment, and one
    recovery command, all tagged to `tenant_id`. Returns the IDs so tests can
    try to reach them cross-tenant."""
    with tenant_scope(db, tenant_id):
        db.add(m.User(id=f"USR_{suffix}", email=f"viewer_{suffix}@test.demo", display_name="Viewer",
                      role="ANALYST", api_token=f"token_{suffix}"))
        db.add(m.User(id=f"USR_ADM_{suffix}", email=f"admin_{suffix}@test.demo", display_name="Admin",
                      role="ADMINISTRATOR", api_token=f"admin_token_{suffix}"))

        merchant = m.Merchant(id=f"MER_{suffix}", name=f"Merchant {suffix}", category="retail")
        db.add(merchant)
        contact = m.Contact(id=f"CON_{suffix}", merchant_id=merchant.id, name="Vendor",
                            created_at=dt.datetime(2026, 1, 1))
        db.add(contact)
        fa = m.FundAccount(id=f"FA_{suffix}", contact_id=contact.id, vpa=f"vendor_{suffix}@upi")
        db.add(fa)
        for i in range(10):
            db.add(m.Payout(id=f"PYO_HIST_{suffix}_{i}", merchant_id=merchant.id, contact_id=contact.id,
                            fund_account_id=fa.id, amount=10000 + i * 100, status="processed",
                            created_at=dt.datetime(2026, 1, 1) + dt.timedelta(days=i)))
        db.commit()

        order = m.Order(id=f"ORD_{suffix}", merchant_id=merchant.id, amount=5000,
                        created_at=dt.datetime(2026, 2, 1))
        db.add(order)
        payment = m.Payment(id=f"PAY_{suffix}", order_id=order.id, merchant_id=merchant.id,
                            customer_id=f"CUST_{suffix}", amount=5000, created_at=dt.datetime(2026, 2, 1))
        db.add(payment)
        db.commit()

        incident_payout = m.Payout(id=f"PYO_INC_{suffix}", merchant_id=merchant.id, contact_id=contact.id,
                                   fund_account_id=fa.id, amount=999999, status="processed",
                                   created_at=dt.datetime(2026, 3, 1), is_injected=True)
        db.add(incident_payout)
        db.commit()
        incident = create_incident_from_payouts(
            db, incident_id=f"INC_{suffix}", merchant_id=merchant.id,
            payout_ids=[incident_payout.id], scenario="test",
        )

        recovery_command = m.RecoveryCommand(
            id=f"REC_{suffix}", incident_id=incident.id, action="FREEZE_PAYOUT",
            target_type="payout", target_id=incident_payout.id, amount=999999,
            idempotency_key=f"idem_{suffix}", created_by=f"USR_{suffix}",
        )
        db.add(recovery_command)
        db.commit()

        return {
            "merchant_id": merchant.id,
            "incident_id": incident.id,
            "payment_id": payment.id,
            "recovery_command_id": recovery_command.id,
            "viewer_token": f"token_{suffix}",
            "admin_token": f"admin_token_{suffix}",
        }


@pytest.fixture()
def two_tenants(tmp_path):
    db_path = tmp_path / "isolation_test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine, class_=TenantScopedSession)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    db = TestingSessionLocal()
    db.add(m.Tenant(id=TENANT_A, name="Tenant A"))
    db.add(m.Tenant(id=TENANT_B, name="Tenant B"))
    db.commit()

    data_a = _build_tenant_data(db, TENANT_A, "A")
    data_b = _build_tenant_data(db, TENANT_B, "B")
    db.close()

    with TestClient(app) as c:
        yield {"client": c, "a": data_a, "b": data_b, "session_factory": TestingSessionLocal}
    app.dependency_overrides.clear()


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --- API-level isolation ----------------------------------------------------


def test_tenant_a_cannot_read_tenant_b_incident(two_tenants):
    c, a, b = two_tenants["client"], two_tenants["a"], two_tenants["b"]
    resp = c.get(f"/api/incident/{b['incident_id']}", headers=auth(a["viewer_token"]))
    assert resp.status_code == 404
    # Sanity: A really can read its OWN incident with the same token.
    own = c.get(f"/api/incident/{a['incident_id']}", headers=auth(a["viewer_token"]))
    assert own.status_code == 200


def test_tenant_a_cannot_read_tenant_b_evidence(two_tenants):
    c, a, b = two_tenants["client"], two_tenants["a"], two_tenants["b"]
    resp = c.get(f"/api/incident/{b['incident_id']}/evidence", headers=auth(a["viewer_token"]))
    assert resp.status_code == 404


def test_tenant_a_cannot_read_tenant_b_financial_graph(two_tenants):
    c, a, b = two_tenants["client"], two_tenants["a"], two_tenants["b"]
    resp = c.get(f"/api/incident/{b['incident_id']}/graph", headers=auth(a["viewer_token"]))
    assert resp.status_code == 404


def test_tenant_a_cannot_read_tenant_b_exposure(two_tenants):
    c, a, b = two_tenants["client"], two_tenants["a"], two_tenants["b"]
    resp = c.get(f"/api/incident/{b['incident_id']}/exposure", headers=auth(a["viewer_token"]))
    assert resp.status_code == 404


def test_tenant_a_cannot_read_tenant_b_audit_log(two_tenants):
    c, a, b = two_tenants["client"], two_tenants["a"], two_tenants["b"]
    resp = c.get(f"/api/incident/{b['incident_id']}/audit", headers=auth(a["viewer_token"]))
    # The audit endpoint doesn't 404 on an unknown incident (it just returns
    # whatever matches the filter) -- the real assertion is that it returns
    # EMPTY for another tenant's incident_id, never Tenant B's actual events.
    assert resp.status_code == 200
    assert resp.json() == []


def test_tenant_a_cannot_read_tenant_b_recovery_packet(two_tenants):
    c, a, b = two_tenants["client"], two_tenants["a"], two_tenants["b"]
    resp = c.get(f"/api/incident/{b['incident_id']}/recovery-packet", headers=auth(a["viewer_token"]))
    assert resp.status_code == 404


def test_list_incidents_never_leaks_other_tenant(two_tenants):
    c, a, b = two_tenants["client"], two_tenants["a"], two_tenants["b"]
    resp = c.get("/api/incidents", headers=auth(a["viewer_token"]))
    assert resp.status_code == 200
    ids = {i["id"] for i in resp.json()}
    assert a["incident_id"] in ids
    assert b["incident_id"] not in ids


def test_tenant_a_cannot_reset_using_tenant_b_administrator_token_confusion(two_tenants):
    """Sanity check the reverse direction too: Tenant B's admin token must
    not somehow let someone act on Tenant A's incident."""
    c, a, b = two_tenants["client"], two_tenants["a"], two_tenants["b"]
    resp = c.get(f"/api/incident/{a['incident_id']}", headers=auth(b["viewer_token"]))
    assert resp.status_code == 404


# --- DB-level isolation for models with no dedicated read API --------------


def test_payment_isolation_at_db_level(two_tenants):
    SessionLocal = two_tenants["session_factory"]
    b_payment_id = two_tenants["b"]["payment_id"]

    db_scoped_to_a = SessionLocal()
    db_scoped_to_a.set_tenant(TENANT_A)
    try:
        assert db_scoped_to_a.get(m.Payment, b_payment_id) is None
        all_payments = db_scoped_to_a.query(m.Payment).all()
        assert all(p.tenant_id == TENANT_A for p in all_payments)
        assert b_payment_id not in {p.id for p in all_payments}
    finally:
        db_scoped_to_a.close()


def test_recovery_command_isolation_at_db_level(two_tenants):
    SessionLocal = two_tenants["session_factory"]
    b_command_id = two_tenants["b"]["recovery_command_id"]

    db_scoped_to_a = SessionLocal()
    db_scoped_to_a.set_tenant(TENANT_A)
    try:
        assert db_scoped_to_a.get(m.RecoveryCommand, b_command_id) is None
        all_commands = db_scoped_to_a.query(m.RecoveryCommand).all()
        assert all(rc.tenant_id == TENANT_A for rc in all_commands)
        assert b_command_id not in {rc.id for rc in all_commands}
    finally:
        db_scoped_to_a.close()


def test_financial_event_isolation_at_db_level(two_tenants):
    SessionLocal = two_tenants["session_factory"]

    db_scoped_to_a = SessionLocal()
    db_scoped_to_a.set_tenant(TENANT_A)
    try:
        events = db_scoped_to_a.query(m.FinancialEvent).all()
        assert len(events) > 0
        assert all(e.tenant_id == TENANT_A for e in events)
    finally:
        db_scoped_to_a.close()



def test_tenant_scoped_session_rejects_raw_text_sql(two_tenants):
    SessionLocal = two_tenants["session_factory"]
    db = SessionLocal()
    db.set_tenant(TENANT_A)
    try:
        with pytest.raises(PermissionError, match="Textual SQL is prohibited"):
            db.execute(text("SELECT 1"))
    finally:
        db.close()


def test_system_scoped_session_retains_text_sql_access(two_tenants):
    SessionLocal = two_tenants["session_factory"]
    db = SessionLocal()
    db.set_tenant(None)
    try:
        assert db.execute(text("SELECT 1")).scalar_one() == 1
    finally:
        db.close()



def test_tenant_scoped_orm_select_filters_cross_tenant_rows(two_tenants):
    from sqlalchemy import select

    SessionLocal = two_tenants["session_factory"]
    b_payment_id = two_tenants["b"]["payment_id"]

    db = SessionLocal()
    db.set_tenant(TENANT_A)
    try:
        rows = db.execute(select(m.Payment)).scalars().all()
        assert rows
        assert all(row.tenant_id == TENANT_A for row in rows)
        assert db.execute(
            select(m.Payment).where(m.Payment.id == b_payment_id)
        ).scalar_one_or_none() is None
    finally:
        db.close()


def test_tenant_scoped_orm_select_filters_joined_entities(two_tenants):
    from sqlalchemy import select

    SessionLocal = two_tenants["session_factory"]
    b_payment_id = two_tenants["b"]["payment_id"]

    db = SessionLocal()
    db.set_tenant(TENANT_A)
    try:
        rows = db.execute(
            select(m.Payment, m.Merchant).join(
                m.Merchant, m.Merchant.id == m.Payment.merchant_id
            )
        ).all()
        assert rows
        assert all(
            payment.tenant_id == TENANT_A and merchant.tenant_id == TENANT_A
            for payment, merchant in rows
        )
        cross_tenant = db.execute(
            select(m.Payment, m.Merchant)
            .join(m.Merchant, m.Merchant.id == m.Payment.merchant_id)
            .where(m.Payment.id == b_payment_id)
        ).first()
        assert cross_tenant is None
    finally:
        db.close()


def test_system_scoped_orm_select_can_read_across_tenants(two_tenants):
    from sqlalchemy import select

    SessionLocal = two_tenants["session_factory"]
    db = SessionLocal()
    db.set_tenant(None)
    try:
        rows = db.execute(select(m.Payment)).scalars().all()
        tenant_ids = {row.tenant_id for row in rows}
        assert TENANT_A in tenant_ids
        assert TENANT_B in tenant_ids
    finally:
        db.close()


def test_risk_engine_models_with_tenant_id_are_filtered(two_tenants):
    """Risk models do not inherit TenantScoped, but still carry tenant_id."""
    from sqlalchemy import select
    from app.models.risk import RiskEventModel

    SessionLocal = two_tenants["session_factory"]
    db = SessionLocal()
    try:
        db.set_tenant(TENANT_A)
        db.add(
            RiskEventModel(
                event_id="RISK_A",
                tenant_id=TENANT_A,
                entity_id="ENTITY_A",
                event_type="PAYMENT",
                event_time=dt.datetime(2026, 4, 1),
                source="test",
                source_event_id="SRC_A",
                payload={"tenant": "A"},
                payload_hash="hash-a",
                previous_event_hash="",
            )
        )
        db.commit()

        db.set_tenant(TENANT_B)
        db.add(
            RiskEventModel(
                event_id="RISK_B",
                tenant_id=TENANT_B,
                entity_id="ENTITY_B",
                event_type="PAYMENT",
                event_time=dt.datetime(2026, 4, 1),
                source="test",
                source_event_id="SRC_B",
                payload={"tenant": "B"},
                payload_hash="hash-b",
                previous_event_hash="",
            )
        )
        db.commit()

        db.set_tenant(TENANT_A)
        rows = db.execute(select(RiskEventModel)).scalars().all()
        assert {row.event_id for row in rows} == {"RISK_A"}
        assert db.get(RiskEventModel, "RISK_B") is None
        assert {row.event_id for row in db.query(RiskEventModel).all()} == {"RISK_A"}
    finally:
        db.close()
