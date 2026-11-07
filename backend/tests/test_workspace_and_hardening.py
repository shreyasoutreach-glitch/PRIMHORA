import os
os.environ["DEMO_MODE"] = "true"

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app
from app.models import entities as m
from app.core.tenancy import TenantScopedSession


def test_workspace_creation_persists_and_returns_scoped_token(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'workspace.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, class_=TenantScopedSession)
    db = SessionLocal()
    db.set_tenant(None)

    seed_tenant = m.Tenant(id="TEN_OWNER", name="Owner Seed")
    owner = m.User(
        id="USR_OWNER",
        tenant_id=seed_tenant.id,
        email="owner@demo.test",
        display_name="Owner",
        role="ADMINISTRATOR",
        api_token="owner-token",
    )
    db.add_all([seed_tenant, owner])
    db.commit()
    db.close()

    def override_db():
        session = SessionLocal()
        session.set_tenant(None)
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)
        response = client.post(
            "/api/workspace",
            headers={"Authorization": "Bearer owner-token"},
            json={"name": "Acme Finance", "industry": "Fintech"},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["name"] == "Acme Finance"
        assert payload["industry"] == "Fintech"
        assert payload["provisioning_mode"] == "demo"
        assert payload["token"]

        follow_up = client.get(
            "/api/workspace",
            headers={"Authorization": f"Bearer {payload['token']}"},
        )
        assert follow_up.status_code == 200
        assert follow_up.json()["tenant_id"] == payload["tenant_id"]
        assert follow_up.json()["name"] == "Acme Finance"
    finally:
        app.dependency_overrides.clear()


def test_api_security_headers_are_present():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_http_requests_receive_server_generated_correlation_id(caplog):
    import uuid

    caplog.set_level("INFO", logger="primhora.http")
    client = TestClient(app)
    response = client.get(
        "/",
        headers={"X-Request-ID": "caller-controlled-value"},
    )

    assert response.status_code == 200
    request_id = response.headers["x-request-id"]
    assert str(uuid.UUID(request_id)) == request_id
    assert request_id != "caller-controlled-value"
    matching = [
        record for record in caplog.records
        if getattr(record, "request_id", None) == request_id
    ]
    assert matching
    assert matching[-1].path == "/"
    assert matching[-1].method == "GET"
    assert matching[-1].status_code == 200
    assert not hasattr(matching[-1], "query_string")
