from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.orm import sessionmaker

from app.api import catalog_routes, dependencies
from app.authentication.demo import (
    DEMO_MEMBERSHIP_ID,
    DEMO_TENANT_ID,
    DEMO_TENANT_SLUG,
    DEMO_USER_ID,
)
from app.config import Settings
from app.domain.identity.models import Permission
from app.main import app
from app.persistence.models import TenantMembershipRecord, TenantRecord, UserIdentityRecord

SECRET = "0123456789abcdef" * 4


def demo_settings() -> Settings:
    return Settings(_env_file=None, auth_mode="demo", demo_auth_secret=SECRET)


def test_modes_and_secret_are_explicit() -> None:
    assert Settings(_env_file=None).auth_mode == "keycloak"
    with pytest.raises(ValidationError):
        Settings(_env_file=None, auth_mode="unknown")
    for secret in (None, "short", "Z" * 64):
        with pytest.raises(ValidationError):
            Settings(_env_file=None, auth_mode="demo", demo_auth_secret=secret)


def test_demo_credential_and_oidc_fail_closed(monkeypatch) -> None:
    monkeypatch.setattr(dependencies, "get_settings", demo_settings)
    with pytest.raises(HTTPException) as missing:
        dependencies.get_current_principal(None)
    assert missing.value.status_code == 401
    with pytest.raises(HTTPException):
        dependencies.get_current_principal(
            HTTPAuthorizationCredentials(scheme="Bearer", credentials="wrong")
        )
    principal = dependencies.get_current_principal(
        HTTPAuthorizationCredentials(scheme="Bearer", credentials=SECRET)
    )
    assert principal.display_name == "Demo User"

    class InvalidValidator:
        def validate(self, token: str):
            from app.authentication.tokens import InvalidAccessToken

            raise InvalidAccessToken("invalid")

    monkeypatch.setattr(dependencies, "get_settings", lambda: Settings(_env_file=None))
    monkeypatch.setattr(dependencies, "get_access_token_validator", lambda: InvalidValidator())
    with pytest.raises(HTTPException) as rejected:
        dependencies.get_current_principal(
            HTTPAuthorizationCredentials(scheme="Bearer", credentials=SECRET)
        )
    assert rejected.value.status_code == 401


def test_demo_bootstrap_and_authorization(db_engine, monkeypatch) -> None:
    from app import cli

    with db_engine.connect() as connection:
        transaction = connection.begin()
        factory = sessionmaker(
            bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        monkeypatch.setattr(cli, "get_settings", demo_settings)
        monkeypatch.setattr(cli, "create_session_factory", lambda: factory)
        monkeypatch.setattr(dependencies, "get_settings", demo_settings)
        monkeypatch.setattr(dependencies, "create_session_factory", lambda: factory)
        monkeypatch.setattr(catalog_routes, "get_settings", demo_settings)
        monkeypatch.setattr(catalog_routes, "create_session_factory", lambda: factory)
        try:
            client = TestClient(app)
            headers = {"Authorization": f"Bearer {SECRET}"}
            assert client.get("/api/v1/me", headers=headers).status_code == 503
            cli._bootstrap_demo()
            with factory.begin() as session:
                membership = session.get(TenantMembershipRecord, DEMO_MEMBERSHIP_ID)
                assert membership is not None
                updated_at = membership.updated_at
            cli._bootstrap_demo()
            with factory.begin() as session:
                membership = session.get(TenantMembershipRecord, DEMO_MEMBERSHIP_ID)
                assert membership is not None
                assert membership.updated_at == updated_at
                extra_id = uuid4()
                tenant = session.get(TenantRecord, DEMO_TENANT_ID)
                assert tenant is not None
                session.add(
                    TenantRecord(
                        id=extra_id,
                        name="Other",
                        slug=f"other-{extra_id}",
                        created_at=tenant.created_at,
                        updated_at=tenant.updated_at,
                    )
                )
                session.flush()
                session.add(
                    TenantMembershipRecord(
                        id=uuid4(),
                        tenant_id=extra_id,
                        user_id=DEMO_USER_ID,
                        role="tenant_admin",
                        status="active",
                        created_at=tenant.created_at,
                        updated_at=tenant.updated_at,
                    )
                )
            assert client.get("/api/v1/me", headers=headers).json()["display_name"] == "Demo User"
            tenants = client.get("/api/v1/tenants", headers=headers)
            assert tenants.status_code == 200
            assert [item["id"] for item in tenants.json()["items"]] == [str(DEMO_TENANT_ID)]
            assert "tenant:manage" not in tenants.json()["items"][0]["permissions"]
            denied_response = client.get(f"/api/v1/tenants/{extra_id}/catalogs", headers=headers)
            assert denied_response.status_code == 403
            allowed = client.get(f"/api/v1/tenants/{DEMO_TENANT_ID}/catalogs", headers=headers)
            assert allowed.status_code == 200
            principal = dependencies.get_current_principal(
                HTTPAuthorizationCredentials(scheme="Bearer", credentials=SECRET)
            )
            identity = dependencies.get_current_identity(principal)
            with pytest.raises(HTTPException) as denied:
                dependencies.require_tenant_permission(Permission.TENANT_MANAGE)(
                    DEMO_TENANT_ID, identity
                )
            assert denied.value.status_code == 403
            with factory.begin() as session:
                membership = session.get(TenantMembershipRecord, DEMO_MEMBERSHIP_ID)
                assert membership is not None
                membership.role = "tenant_admin"
            with pytest.raises(ValueError, match="conflicts"):
                cli._bootstrap_demo()
            assert client.get("/api/v1/me", headers=headers).status_code == 503
            with factory.begin() as session:
                membership = session.get(TenantMembershipRecord, DEMO_MEMBERSHIP_ID)
                assert membership is not None
                assert membership.role == "tenant_admin"
        finally:
            transaction.rollback()


def test_bootstrap_disabled_in_keycloak_mode(monkeypatch) -> None:
    from app import cli

    monkeypatch.setattr(cli, "get_settings", lambda: Settings(_env_file=None))
    with pytest.raises(ValueError, match="requires AUTH_MODE=demo"):
        cli._bootstrap_demo()


def test_demo_bootstrap_rolls_back_on_tenant_conflict(db_engine, monkeypatch) -> None:
    from app import cli

    with db_engine.connect() as connection:
        transaction = connection.begin()
        factory = sessionmaker(
            bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        monkeypatch.setattr(cli, "get_settings", demo_settings)
        monkeypatch.setattr(cli, "create_session_factory", lambda: factory)
        try:
            now = datetime.now(UTC)
            existing_id = uuid4()
            with factory.begin() as session:
                session.add(
                    TenantRecord(
                        id=existing_id,
                        name="Existing",
                        slug=DEMO_TENANT_SLUG,
                        created_at=now,
                        updated_at=now,
                    )
                )
            with pytest.raises(ValueError, match="conflicts"):
                cli._bootstrap_demo()
            with factory.begin() as session:
                assert session.get(TenantRecord, existing_id).name == "Existing"
                assert session.get(TenantRecord, DEMO_TENANT_ID) is None
                assert session.get(UserIdentityRecord, DEMO_USER_ID) is None
        finally:
            transaction.rollback()
