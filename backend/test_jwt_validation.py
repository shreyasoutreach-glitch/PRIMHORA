from __future__ import annotations

import pytest
import jwt
from fastapi import HTTPException
from unittest.mock import patch

from app.core.authz import get_current_user
from app.models.entities import User
from app.core.config import get_settings

settings = get_settings()


class MockDB:
    def set_tenant(self, tenant):
        pass

    def set_oidc_subject(self, subject):
        self.oidc_subject = subject

    def set_demo_token(self, token):
        self.demo_token = token

    def query(self, model):
        return self

    def filter(self, condition):
        self.cond = condition
        return self

    def first(self):
        field = getattr(self.cond.left, "name", "")
        value = self.cond.right.value
        if field == "idp_subject" and value == "id123":
            return User(
                id="u1",
                email="admin@firsthour.local",
                role="ADMINISTRATOR",
                tenant_id="t1",
                idp_subject="id123",
            )
        return None


def test_jwt_validation():
    db = MockDB()

    with pytest.raises(HTTPException) as exc:
        get_current_user("", db)
    assert exc.value.status_code == 401

    with pytest.raises(HTTPException) as exc:
        get_current_user("Bearer ", db)
    assert exc.value.status_code == 401

    original_demo_mode = settings.demo_mode
    original_issuer = settings.auth_provider_issuer
    original_audience = settings.auth_provider_audience
    original_jwks = settings.auth_provider_jwks_url
    settings.demo_mode = False
    settings.auth_provider_issuer = "https://issuer.example"
    settings.auth_provider_audience = "primhora"
    settings.auth_provider_jwks_url = "https://issuer.example/.well-known/jwks.json"
    try:
        with patch("app.core.authz.jwks_client") as mock_jwks, patch("jwt.decode") as mock_decode:
            mock_jwks.get_signing_key_from_jwt.return_value.key = "fake-key"

            mock_decode.side_effect = jwt.InvalidSignatureError()
            with pytest.raises(HTTPException) as exc:
                get_current_user("Bearer fake", db)
            assert exc.value.status_code == 401

            mock_decode.side_effect = jwt.ExpiredSignatureError()
            with pytest.raises(HTTPException) as exc:
                get_current_user("Bearer fake", db)
            assert exc.value.status_code == 401

            mock_decode.side_effect = jwt.InvalidIssuerError()
            with pytest.raises(HTTPException) as exc:
                get_current_user("Bearer fake", db)
            assert exc.value.status_code == 401

            mock_decode.side_effect = None
            mock_decode.return_value = {"sub": "id123"}
            user = get_current_user("Bearer valid", db)
            assert user.role == "ADMINISTRATOR"
            assert user.tenant_id == "t1"

            mock_decode.return_value = {"sub": "id456", "email": "unknown@firsthour.local"}
            with pytest.raises(HTTPException) as exc:
                get_current_user("Bearer valid", db)
            assert exc.value.status_code == 403

            mock_decode.return_value = {"sub": "id123", "email": "admin@firsthour.local"}
            user = get_current_user("Bearer valid", db)
            assert user.role == "ADMINISTRATOR"
            assert user.tenant_id == "t1"
    finally:
        settings.demo_mode = original_demo_mode
        settings.auth_provider_issuer = original_issuer
        settings.auth_provider_audience = original_audience
        settings.auth_provider_jwks_url = original_jwks
