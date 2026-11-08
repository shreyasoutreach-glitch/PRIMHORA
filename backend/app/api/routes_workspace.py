from __future__ import annotations

import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.authz import get_system_db, get_tenant_db, require_permission
from app.core.config import get_settings
from app.models import entities as m
from app.schemas.schemas import WorkspaceCreateRequest, WorkspaceResponse

router = APIRouter(tags=["workspace"])
settings = get_settings()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@router.get("/workspace", response_model=WorkspaceResponse)
def get_workspace(
    db: Session = Depends(get_tenant_db),
    user: m.User = Depends(require_permission("VIEW")),
):
    tenant = db.get(m.Tenant, user.tenant_id)
    if tenant is None:
        raise HTTPException(404, "workspace not found")
    return WorkspaceResponse(
        tenant_id=tenant.id,
        name=tenant.name,
        industry="",
        user_id=user.id,
        role=user.role,
        provisioning_mode="demo" if settings.demo_mode else "oidc",
    )


@router.post("/workspace", response_model=WorkspaceResponse)
def create_workspace(
    body: WorkspaceCreateRequest,
    db: Session = Depends(get_system_db),
    _user: m.User = Depends(require_permission("EXECUTE")),
):
    if not settings.demo_mode:
        raise HTTPException(
            503,
            "Self-service workspace provisioning requires the production identity-provider "
            "and membership-provisioning flow to be activated.",
        )

    tenant_id = _new_id("TEN")
    # Tenant creation is intentionally scoped to the new tenant ID. The
    # database policy permits inserting only the tenant whose ID is present
    # in the transaction-local context, then the same scope stamps its owner.
    db.set_tenant(tenant_id)
    tenant = m.Tenant(id=tenant_id, name=body.name)
    db.add(tenant)
    db.flush()

    workspace_token = secrets.token_urlsafe(32)[:64]
    workspace_user = m.User(
        id=_new_id("USR"),
        tenant_id=tenant_id,
        email=f"owner+{tenant_id.lower()}@primhora.demo",
        display_name="Workspace Owner",
        role="ADMINISTRATOR",
        api_token=workspace_token,
    )
    db.add(workspace_user)
    db.commit()

    return WorkspaceResponse(
        tenant_id=tenant.id,
        name=tenant.name,
        industry=body.industry,
        user_id=workspace_user.id,
        role=workspace_user.role,
        token=workspace_token,
        provisioning_mode="demo",
    )
