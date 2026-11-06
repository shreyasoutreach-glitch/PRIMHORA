import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.authz import ROLES
from app.core.database import Base, get_db
from app.core.tenancy import TenantScopedSession, tenant_scope
from app.main import app
from app.models import entities as m

TEST_TENANT = "TEN_API_TEST"


@pytest.fixture()
def client(tmp_path):
    db_path = tmp_path / "api_test.db"
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
    db.add(m.Tenant(id=TEST_TENANT, name="API Test Tenant"))
    db.add(m.Tenant(id="TEN_NORTHBRIDGE", name="Northbridge Demo"))
    db.commit()

    tokens = {}
    with tenant_scope(db, TEST_TENANT):
        for role in ROLES:
            token = f"test_token_{role.lower()}"
            db.add(m.User(id=f"USR_{role}", email=f"{role.lower()}@test.demo",
                          display_name=role, role=role, api_token=token))
            tokens[role] = token
        db.commit()

        merchant = m.Merchant(id="MER_API", name="API Test Co", category="retail")
        db.add(merchant)
        contact = m.Contact(id="CON_API", merchant_id="MER_API", name="New Vendor", type="vendor",
                            created_at=dt.datetime(2026, 6, 1, 10, 40))
        db.add(contact)
        fa = m.FundAccount(id="FA_API", contact_id="CON_API", vpa="newvendor@upi")
        db.add(fa)
        for i in range(30):
            db.add(m.Payout(id=f"PYO_HIST_{i}", merchant_id="MER_API", contact_id="CON_API",
                            fund_account_id="FA_API", amount=15000 + i * 100, status="processed",
                            created_at=dt.datetime(2026, 1, 1) + dt.timedelta(days=i)))
        db.commit()

        from app.services.incident.detector import create_incident_from_payouts
        payout = m.Payout(id="PYO_API_1", merchant_id="MER_API", contact_id="CON_API", fund_account_id="FA_API",
                          amount=5_000_000, status="processed", created_at=dt.datetime(2026, 6, 1, 11, 0),
                          is_injected=True)
        db.add(payout)
        db.commit()
        create_incident_from_payouts(db, incident_id="INC_API_TEST", merchant_id="MER_API",
                                      payout_ids=["PYO_API_1"], scenario="test_scenario")
    db.close()

    with TestClient(app) as c:
        yield {"client": c, "tokens": tokens, "session_factory": TestingSessionLocal}
    app.dependency_overrides.clear()


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_demo_session_bootstraps_without_authentication(client):
    """The synthetic demo must be able to bootstrap its own demo credential."""
    db = client["session_factory"]()
    try:
        with tenant_scope(db, "TEN_NORTHBRIDGE"):
            db.add(m.User(
                id="USR_DEMO_ADMIN",
                email="administrator@northbridge.demo",
                display_name="Administrator (Demo)",
                role="ADMINISTRATOR",
                api_token="demo-admin-token",
            ))
            db.commit()
    finally:
        db.close()

    resp = client["client"].post("/api/demo/session?role=ADMINISTRATOR")
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "DEMO"
    assert body["role"] == "ADMINISTRATOR"
    assert body["token"] == "demo-admin-token"


def test_requires_authentication(client):
    """No Authorization header at all -> 401, not a silent unscoped fetch."""
    resp = client["client"].get("/api/incident/INC_API_TEST")
    assert resp.status_code == 401


def test_rejects_invalid_token(client):
    resp = client["client"].get("/api/incident/INC_API_TEST", headers=auth("not-a-real-token"))
    assert resp.status_code == 401


def test_get_incident_returns_headline(client):
    resp = client["client"].get("/api/incident/INC_API_TEST", headers=auth(client["tokens"]["ANALYST"]))
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "INC_API_TEST"
    assert body["headline"]["payout_count"] == 1
    assert body["incident_evidence_score"] > 0


def test_incident_queue_exposes_operational_metadata(client):
    resp = client["client"].get("/api/incidents", headers=auth(client["tokens"]["ANALYST"]))
    assert resp.status_code == 200
    item = next(x for x in resp.json() if x["id"] == "INC_API_TEST")
    assert item["merchant_name"] == "API Test Co"
    assert "severity" in item
    assert "financial_exposure" in item
    assert "confidence" in item
    assert "affected_entities" in item


def test_get_incident_404_for_unknown(client):
    resp = client["client"].get("/api/incident/NOPE", headers=auth(client["tokens"]["ANALYST"]))
    assert resp.status_code == 404


def test_timeline_endpoint_sorted_chronologically(client):
    resp = client["client"].get("/api/incident/INC_API_TEST/timeline", headers=auth(client["tokens"]["ANALYST"]))
    assert resp.status_code == 200
    events = resp.json()
    timestamps = [e["timestamp"] for e in events]
    assert timestamps == sorted(timestamps)


def test_exposure_endpoint(client):
    resp = client["client"].get("/api/incident/INC_API_TEST/exposure", headers=auth(client["tokens"]["ANALYST"]))
    assert resp.status_code == 200
    body = resp.json()
    assert float(body["confirmed_moved"]["total"]) == 5_000_000


def test_graph_endpoint(client):
    resp = client["client"].get("/api/incident/INC_API_TEST/graph", headers=auth(client["tokens"]["ANALYST"]))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["nodes"]) > 0


def test_next_question_then_attestation_changes_state(client):
    resp = client["client"].get("/api/incident/INC_API_TEST/questions/next", headers=auth(client["tokens"]["ANALYST"]))
    assert resp.status_code == 200
    question = resp.json()
    assert question["question_id"] == "q_authorized_payouts"

    resp2 = client["client"].post(
        "/api/incident/INC_API_TEST/attestation",
        json={"question_id": "q_authorized_payouts", "answer": "NO", "note": "not me"},
        headers=auth(client["tokens"]["INVESTIGATOR"]),
    )
    assert resp2.status_code == 200
    body = resp2.json()
    assert body["new_state"] == "INCIDENT_CONFIRMED"
    assert "does not rewrite" in body["message"]


def test_attestation_requires_investigate_permission(client):
    """An ANALYST (VIEW only) must not be able to record an attestation --
    this is the exact "viewer shouldn't be able to act" property RBAC is
    for."""
    resp = client["client"].post(
        "/api/incident/INC_API_TEST/attestation",
        json={"question_id": "q_authorized_payouts", "answer": "NO"},
        headers=auth(client["tokens"]["ANALYST"]),
    )
    assert resp.status_code == 403


def test_attestation_rejects_unknown_question(client):
    resp = client["client"].post(
        "/api/incident/INC_API_TEST/attestation",
        json={"question_id": "q_not_real", "answer": "YES"},
        headers=auth(client["tokens"]["INVESTIGATOR"]),
    )
    assert resp.status_code == 400


def test_attestation_rejects_high_amount_question_when_signal_is_absent(client):
    """Question eligibility must come from the incident score, not hard-coded defaults."""
    db = client["session_factory"]()
    try:
        with tenant_scope(db, TEST_TENANT):
            incident = db.get(m.Incident, "INC_API_TEST")
            incident.score_components = {}
            db.commit()
    finally:
        db.close()

    resp = client["client"].post(
        "/api/incident/INC_API_TEST/attestation",
        json={"question_id": "q_authorized_payouts", "answer": "NO"},
        headers=auth(client["tokens"]["INVESTIGATOR"]),
    )
    assert resp.status_code == 400


def test_recovery_packet_has_source_references(client):
    resp = client["client"].get("/api/incident/INC_API_TEST/recovery-packet", headers=auth(client["tokens"]["ANALYST"]))
    assert resp.status_code == 200
    packet = resp.json()
    assert packet["case_id"] == "INC_API_TEST"
    assert packet["transaction_table"][0]["source_reference"]


def test_generic_csv_import_creates_read_only_case(client):
    csv = b"transaction_id,timestamp,amount,currency,status,beneficiary_name,account_number,ifsc\nCSV-001,2026-09-30T10:00:00+00:00,5000000,INR,processed,New Vendor,XXXX7788,ABCD0001234\n"
    resp = client["client"].post(
        "/api/import/payouts-csv",
        files={"file": ("payouts.csv", csv, "text/csv")},
        data={"merchant_name": "Customer CSV Co", "source_system": "bank_csv"},
        headers=auth(client["tokens"]["INVESTIGATOR"]),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["imported_rows"] == 1
    assert body["read_only"] is True
    assert body["incident_count"] >= 0
    assert len(body["imported_payout_ids"]) == 1


def test_recovery_execute_route_is_read_only(client):
    resp = client["client"].post(
        "/api/recovery-commands/RC_DOES_NOT_MATTER/execute",
        headers=auth(client["tokens"]["ADMINISTRATOR"]),
    )
    assert resp.status_code == 409
    assert "read-only" in resp.json()["detail"].lower()


def test_recovery_packet_pdf_exports(client):
    pdf = client["client"].get(
        "/api/incident/INC_API_TEST/recovery-packet.pdf",
        headers=auth(client["tokens"]["ANALYST"]),
    )
    assert pdf.status_code == 200
    assert pdf.headers["content-type"].startswith("application/pdf")
    assert pdf.content.startswith(b"%PDF")


def test_recovery_packet_get_is_read_only(client):
    db = client["session_factory"]()
    try:
        with tenant_scope(db, TEST_TENANT):
            before = db.get(m.Incident, "INC_API_TEST").state
            audit_before = db.query(m.AuditEvent).filter(m.AuditEvent.incident_id == "INC_API_TEST").count()
    finally:
        db.close()

    resp = client["client"].get("/api/incident/INC_API_TEST/recovery-packet", headers=auth(client["tokens"]["ANALYST"]))
    assert resp.status_code == 200

    db = client["session_factory"]()
    try:
        with tenant_scope(db, TEST_TENANT):
            after = db.get(m.Incident, "INC_API_TEST").state
            audit_after = db.query(m.AuditEvent).filter(m.AuditEvent.incident_id == "INC_API_TEST").count()
    finally:
        db.close()

    assert after == before
    assert audit_after == audit_before


def test_demo_reset_requires_administrator(client):
    resp = client["client"].post("/api/demo/reset", headers=auth(client["tokens"]["INVESTIGATOR"]))
    assert resp.status_code == 403


def test_demo_reset_reseeds_flagship_incident(client, monkeypatch):
    from app.api import routes_demo
    monkeypatch.setattr(routes_demo.settings, "demo_allow_global_reset", True)
    resp = client["client"].post("/api/demo/reset", headers=auth(client["tokens"]["ADMINISTRATOR"]))
    assert resp.status_code == 200
    body = resp.json()
    assert body["flagship_incident_id"] == "INC-001"
    assert "TEN_NORTHBRIDGE" in body["tenants"]

    # /demo/reset wipes the ENTIRE database, including this fixture's own
    # tenant/tokens -- grab a freshly-seeded token from the response to
    # keep going, rather than reusing the (now-deleted) fixture token.
    new_admin_token = body["tokens_by_tenant"]["TEN_NORTHBRIDGE"]["ADMINISTRATOR"]
    new_viewer_token = body["tokens_by_tenant"]["TEN_NORTHBRIDGE"]["ANALYST"]

    resp2 = client["client"].get("/api/incident/INC-001", headers=auth(new_viewer_token))
    assert resp2.status_code == 200
    assert resp2.json()["headline"]["payout_count"] == 3


def test_demo_inject_incident_scenario(client, monkeypatch):
    from app.api import routes_demo
    monkeypatch.setattr(routes_demo.settings, "demo_allow_global_reset", True)
    # MER_HARBOR (the dedicated Chaos Lab merchant) only exists after a seed/reset.
    reset_resp = client["client"].post("/api/demo/reset", headers=auth(client["tokens"]["ADMINISTRATOR"]))
    admin_token = reset_resp.json()["tokens_by_tenant"]["TEN_NORTHBRIDGE"]["ADMINISTRATOR"]

    resp = client["client"].post(
        "/api/demo/inject-incident",
        json={"scenario": "new_beneficiary_burst", "merchant_id": "MER_HARBOR"},
        headers=auth(admin_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["incident_evidence_score"] > 0
    assert len(body["payout_ids"]) == 3



def test_demo_reset_is_disabled_by_default_even_for_demo_admin(client, monkeypatch):
    from app.api import routes_demo
    monkeypatch.setattr(routes_demo.settings, "demo_allow_global_reset", False)
    response = client["client"].post(
        "/api/demo/reset",
        headers=auth(client["tokens"]["ADMINISTRATOR"]),
    )
    assert response.status_code == 403
    assert "Global demo reset is disabled" in response.json()["detail"]


def test_csv_import_namespaces_same_source_id_by_merchant(client):
    csv = (
        b"transaction_id,timestamp,amount,currency,status,beneficiary_name,account_number,ifsc\n"
        b"SHARED-001,2026-09-30T10:00:00+00:00,15000,INR,processed,Vendor A,XXXX1111,ABCD0001234\n"
    )
    ids = []
    for merchant_name in ("Merchant One", "Merchant Two"):
        response = client["client"].post(
            "/api/import/payouts-csv",
            files={"file": ("payouts.csv", csv, "text/csv")},
            data={"merchant_name": merchant_name, "source_system": "test", "import_mode": "baseline"},
            headers=auth(client["tokens"]["INVESTIGATOR"]),
        )
        assert response.status_code == 200, response.text
        ids.extend(response.json()["imported_payout_ids"])
    assert len(ids) == 2
    assert ids[0] != ids[1]


def test_csv_import_replay_rejects_changed_destination_or_status(client):
    csv = (
        b"transaction_id,timestamp,amount,currency,status,beneficiary_name,account_number,ifsc\n"
        b"PAYLOAD-001,2026-09-30T10:00:00+00:00,15000,INR,processed,Vendor A,XXXX1111,ABCD0001234\n"
    )
    first = client["client"].post(
        "/api/import/payouts-csv",
        files={"file": ("payouts.csv", csv, "text/csv")},
        data={"merchant_name": "Replay Integrity Co", "import_mode": "baseline"},
        headers=auth(client["tokens"]["INVESTIGATOR"]),
    )
    assert first.status_code == 200, first.text

    changed = csv.replace(b",processed,Vendor A,", b",reversed,Vendor B,")
    replay = client["client"].post(
        "/api/import/payouts-csv",
        files={"file": ("payouts.csv", changed, "text/csv")},
        data={"merchant_name": "Replay Integrity Co", "import_mode": "baseline"},
        headers=auth(client["tokens"]["INVESTIGATOR"]),
    )
    assert replay.status_code == 422
    assert "conflicts" in replay.json()["detail"]["errors"][0]


def test_baseline_import_then_monitor_creates_currency_aware_case(client):
    baseline_rows = [
        f"HIST-{i:03d},2026-01-{i + 1:02d}T10:00:00+00:00,{10000 + i * 100},INR,processed,Regular Vendor,XXXX1234,ABCD0001234"
        for i in range(12)
    ]
    header = "transaction_id,timestamp,amount,currency,status,beneficiary_name,account_number,ifsc\n"
    baseline_csv = (header + "\n".join(baseline_rows) + "\n").encode()
    baseline = client["client"].post(
        "/api/import/payouts-csv",
        files={"file": ("history.csv", baseline_csv, "text/csv")},
        data={"merchant_name": "Baseline Workflow Co", "import_mode": "baseline"},
        headers=auth(client["tokens"]["INVESTIGATOR"]),
    )
    assert baseline.status_code == 200, baseline.text
    baseline_body = baseline.json()
    assert baseline_body["imported_rows"] == 12
    assert baseline_body["incident_count"] == 0
    assert baseline_body["baseline_observations_by_currency"]["INR"] == 12
    assert baseline_body["baseline_ready_by_currency"]["INR"] is True

    monitored_csv = (
        header + "NEW-001,2026-01-13T10:00:00+00:00,5000000,INR,processed,New Recipient,XXXX9876,ABCD0009876\n"
    ).encode()
    monitored = client["client"].post(
        "/api/import/payouts-csv",
        files={"file": ("current.csv", monitored_csv, "text/csv")},
        data={"merchant_name": "Baseline Workflow Co", "import_mode": "monitor"},
        headers=auth(client["tokens"]["INVESTIGATOR"]),
    )
    assert monitored.status_code == 200, monitored.text
    assert monitored.json()["incident_count"] >= 1
    assert monitored.json()["skipped_for_insufficient_baseline"] == 0
