from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.authz import get_system_db, require_permission
from app.core.database import get_db
from app.core.config import get_settings
from app.demo.chaos_lab import inject_scenario
from app.models.entities import User
from app.schemas.schemas import DemoResetResponse, InjectIncidentRequest, InjectIncidentResponse

router = APIRouter(tags=["demo"])

settings = get_settings()


@router.post("/demo/session")
def demo_session(role: str = "ADMINISTRATOR", db: Session = Depends(get_db)):
    """Issue a demo credential dynamically instead of shipping it in the JS bundle."""
    if not settings.demo_mode:
        raise HTTPException(404, "Demo sessions are disabled")
    allowed = {"ANALYST", "FINANCE_OPERATOR", "INVESTIGATOR", "APPROVER", "ADMINISTRATOR"}
    role = role.upper()
    if role not in allowed:
        raise HTTPException(400, "Unsupported demo role")
    user = db.query(User).filter(User.tenant_id == "TEN_NORTHBRIDGE", User.role == role).first()
    token = user.api_token if user is not None else (settings.demo_master_token if role == "ADMINISTRATOR" else "")
    if not token:
        raise HTTPException(503, "Demo identity is unavailable. Reset the demo dataset.")
    return {"mode": "DEMO", "role": role, "tenant_id": "TEN_NORTHBRIDGE", "token": token, "simulated": True}


# These endpoints are destructive (reset wipes and reseeds the ENTIRE
# database, across every tenant) and are gated two ways: DEMO_MODE must be
# on, AND the caller must authenticate as an ADMINISTRATOR.


@router.post("/demo/inject-incident", response_model=InjectIncidentResponse)
def demo_inject_incident(
    body: InjectIncidentRequest,
    db: Session = Depends(get_system_db),
    _user: User = Depends(require_permission("EXECUTE")),
):
    if not settings.demo_mode:
        raise HTTPException(403, "DEMO_MODE is disabled")
    result = inject_scenario(db, body.scenario, body.merchant_id)
    return InjectIncidentResponse(**result)


@router.post("/demo/reset", response_model=DemoResetResponse)
def demo_reset(
    db: Session = Depends(get_system_db),
    _user: User = Depends(require_permission("EXECUTE")),
):
    if not settings.demo_mode:
        raise HTTPException(403, "DEMO_MODE is disabled")
    if not settings.demo_allow_global_reset:
        raise HTTPException(403, "Global demo reset is disabled for this deployment.")
    from seed.seed import run_seed

    result = run_seed(db, seed_value=settings.seed)
    return DemoResetResponse(
        status="reset_complete",
        dataset_version="v1",
        flagship_incident_id=result["flagship_incident_id"],
        tenants=result["tenants"],
        tokens_by_tenant=result["tokens_by_tenant"],
    )
