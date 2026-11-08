from __future__ import annotations

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session
import jwt
from jwt import PyJWKClient

from app.core.database import get_db
from app.models.entities import User
from app.core.config import get_settings

ROLES = ("ANALYST", "INVESTIGATOR", "FINANCE_OPERATOR", "APPROVER", "ADMINISTRATOR")
PERMISSIONS = ("VIEW", "INVESTIGATE", "RECOMMEND", "APPROVE", "EXECUTE")

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "ANALYST": {"VIEW"},
    "FINANCE_OPERATOR": {"VIEW", "INVESTIGATE"},
    "INVESTIGATOR": {"VIEW", "INVESTIGATE", "RECOMMEND"},
    "APPROVER": {"VIEW", "INVESTIGATE", "APPROVE"},
    "ADMINISTRATOR": {"VIEW", "INVESTIGATE", "RECOMMEND", "APPROVE", "EXECUTE"},
}

settings = get_settings()

jwks_client = PyJWKClient(settings.oidc_jwks_url) if (not settings.demo_mode and settings.oidc_jwks_url) else None


def get_current_user(authorization: str = Header(default=""), db: Session = Depends(get_db)) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing or malformed Authorization header (expected 'Bearer <token>')")
    token = authorization[len("Bearer "):].strip()
    if not token:
        raise HTTPException(401, "Empty bearer token")

    # Identity bootstrap is deliberately narrow: PostgreSQL RLS permits this
    # one lookup by the already-verified OIDC subject or demo token. As soon
    # as the user row is found, clear the bootstrap GUC and scope the session
    # to that user's tenant for the rest of the request.
    db.set_tenant(None)

    if settings.demo_mode:
        db.set_demo_token(token)
        user = db.query(User).filter(User.api_token == token).first()
        db.set_demo_token(None)
        if user is not None:
            db.set_tenant(user.tenant_id)
            return user
        if token == settings.demo_master_token and settings.demo_master_token:
            db.set_tenant("TEN_NORTHBRIDGE")
            return User(
                id="USR_DEMO_MASTER",
                tenant_id="TEN_NORTHBRIDGE",
                email="administrator@northbridge.demo",
                display_name="Administrator (Demo Master)",
                role="ADMINISTRATOR",
                api_token=settings.demo_master_token,
            )
        raise HTTPException(401, "Invalid token")

    if jwks_client is None or not settings.oidc_issuer or not settings.auth_provider_audience:
        raise HTTPException(503, "Production identity provider is not configured")

    try:
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.auth_provider_audience,
            issuer=settings.oidc_issuer,
            options={"require": ["exp", "iat", "sub", "iss", "aud"]},
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token has expired")
    except jwt.InvalidIssuerError:
        raise HTTPException(401, "Invalid token issuer")
    except jwt.InvalidAudienceError:
        raise HTTPException(401, "Invalid token audience")
    except jwt.InvalidSignatureError:
        raise HTTPException(401, "Invalid token signature")
    except jwt.exceptions.PyJWKClientError:
        raise HTTPException(503, "Unable to obtain signing keys from Identity Provider")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid authentication token")
    except Exception:
        raise HTTPException(401, "Token validation failed")

    subject = payload.get("sub")
    if not subject or not isinstance(subject, str):
        raise HTTPException(401, "JWT payload must contain an immutable 'sub' claim")

    db.set_oidc_subject(subject)
    user = db.query(User).filter(User.idp_subject == subject).first()
    db.set_oidc_subject(None)
    if user is None:
        raise HTTPException(403, "Identity is authenticated but not provisioned for this application")

    db.set_tenant(user.tenant_id)
    return user


def require_permission(permission: str):
    if permission not in PERMISSIONS:
        raise ValueError(f"Unknown permission: {permission}")

    def dependency(user: User = Depends(get_current_user)) -> User:
        user_perms = ROLE_PERMISSIONS.get(user.role, set())
        if permission not in user_perms:
            raise HTTPException(403, f"Role {user.role} lacks permission {permission}")
        return user

    return dependency


def get_tenant_db(user: User = Depends(require_permission("VIEW")), db: Session = Depends(get_db)) -> Session:
    db.set_tenant(user.tenant_id)
    return db


def get_system_db(
    user: User = Depends(require_permission("EXECUTE")),
    db: Session = Depends(get_db),
) -> Session:
    """Administrator operations remain tenant-scoped, never global by default."""
    if user.role != "ADMINISTRATOR":
        raise HTTPException(403, "Administrator role required for system operations")
    db.set_tenant(user.tenant_id)
    return db
