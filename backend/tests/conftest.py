import os
os.environ["DEMO_MODE"] = "true"
# Test fixtures use an isolated SQLite database and explicit synthetic records.
os.environ["DEMO_ALLOW_EXTERNAL_INGESTION"] = "true"
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.core.tenancy import TenantScopedSession
from app.models import entities as m

DEFAULT_TEST_TENANT = "TEN_TEST_DEFAULT"


@pytest.fixture()
def db_session(tmp_path):
    """A tenant-scoped session pre-set to one default test tenant, so
    existing test bodies that construct rows directly (without caring about
    multi-tenancy specifically) get a working tenant_id auto-stamped for
    free, via TenantScopedSession.add() -- see app/core/tenancy.py."""
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, class_=TenantScopedSession)
    session = SessionLocal()
    session.add(m.Tenant(id=DEFAULT_TEST_TENANT, name="Default Test Tenant"))
    session.commit()
    session.set_tenant(DEFAULT_TEST_TENANT)
    yield session
    session.close()
