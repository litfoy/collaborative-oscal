# SPDX-License-Identifier: Apache-2.0
# Copyright The Collaborative OSCAL Authors.

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api import dependencies
from app.application.implementations import ImplementationService
from app.application.system_security_plans import SystemSecurityPlanService
from app.config import get_settings
from app.domain.catalogs.models import CatalogOriginType
from app.domain.implementations import (
    ImplementationInformation,
    ImplementationStatus,
    OscalImplementationStatus,
)
from app.persistence.database import create_session_factory
from app.persistence.identity import SQLIdentityRepository, SQLMembershipRepository
from app.persistence.models import CatalogControlIndexRecord

pytestmark = pytest.mark.integration

ISSUER = "https://identity.example.test/realms/test"
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "oscal_catalog.json"


class _StubValidator:
    def validate(self, token: str) -> dict:
        from app.authentication.tokens import InvalidAccessToken

        if not token.startswith("token-"):
            raise InvalidAccessToken("unknown")
        return {"iss": ISSUER, "sub": token.removeprefix("token-")}


@pytest.fixture
def api_world(monkeypatch, postgres_url, session_factory, grc_service):
    monkeypatch.setenv("DATABASE_URL", postgres_url)
    monkeypatch.setenv("AUTH_MODE", "keycloak")
    get_settings.cache_clear()
    create_session_factory.cache_clear()
    monkeypatch.setattr(dependencies, "get_access_token_validator", lambda: _StubValidator())

    suffix = uuid4().hex[:8]
    tenant = grc_service.create_tenant("SSP API tenant", f"ssp-api-{suffix}")
    subject = f"ssp-api-user-{suffix}"
    with session_factory.begin() as session:
        identity = SQLIdentityRepository(session).get_or_create(
            issuer=ISSUER,
            subject=subject,
            display_name="SSP API Tester",
            email=None,
        )
        SQLMembershipRepository(session).assign(
            tenant_id=tenant.id,
            user_id=identity.id,
            role="catalog_editor",
            status="active",
        )
        actor_id = identity.id

    catalog = grc_service.create_catalog(tenant.id, "API baseline", CatalogOriginType.CUSTOM)
    revision = grc_service.create_draft_catalog_revision(
        tenant.id,
        catalog.id,
        json.loads(FIXTURE_PATH.read_text()),
    )

    with session_factory.begin() as session:
        control_id = session.scalars(
            select(CatalogControlIndexRecord.oscal_control_id)
            .where(
                CatalogControlIndexRecord.tenant_id == tenant.id,
                CatalogControlIndexRecord.catalog_revision_id == revision.id,
            )
            .order_by(CatalogControlIndexRecord.oscal_control_id)
        ).first()
    assert control_id is not None

    ssp_service = SystemSecurityPlanService(lambda: session_factory.begin())
    implementation_service = ImplementationService(lambda: session_factory.begin())

    system = ssp_service.create_system(
        tenant.id,
        actor_id,
        name="Corporate Identity Management",
        organization_id=None,
        description="Identity services for employees.",
        system_boundary="Identity service and managed infrastructure.",
        system_ids=[{"id": "identity.example", "identifier_type": "https://example.test/id-types"}],
        information_types=[
            {
                "title": "Employee identity data",
                "description": "Information used to authenticate employees.",
            }
        ],
        operational_status="operational",
        status_remarks=None,
        security_sensitivity_level=None,
    )
    component = ssp_service.create_component(
        tenant.id,
        actor_id,
        system["id"],
        component_type="service",
        title="Identity provider",
        description="Production identity service deployment.",
        purpose="Authenticate employees",
        status="operational",
        status_remarks=None,
    )
    plan = ssp_service.create_plan(
        tenant.id,
        actor_id,
        system["id"],
        catalog_id=catalog.id,
        revision_id=revision.id,
        title="Security SSP",
        control_implementation_description="Document requirement contributions.",
    )
    implementation = implementation_service.create(
        tenant.id,
        actor_id,
        catalog.id,
        revision.id,
        control_id,
        None,
        None,
        ImplementationInformation(
            "The identity provider enforces approved policy.",
            ImplementationStatus.IMPLEMENTED,
            [],
            [],
            OscalImplementationStatus.IMPLEMENTED,
            None,
        ),
    )

    yield {
        "tenant_id": tenant.id,
        "subject": subject,
        "plan_id": plan["id"],
        "system_id": system["id"],
        "title": plan["title"],
        "description": plan["control_implementation_description"],
        "component_id": component["id"],
        "implementation_id": implementation.id,
    }

    get_settings.cache_clear()
    create_session_factory.cache_clear()


@pytest.fixture
def client(api_world):
    from app.main import app

    return TestClient(app)


def _headers(subject: str) -> dict[str, str]:
    return {"Authorization": f"Bearer token-{subject}"}


def _base(tenant_id: UUID, plan_id: UUID) -> str:
    return f"/api/v1/tenants/{tenant_id}/system-security-plans/{plan_id}"


def _include(api_world, client: TestClient, headers: dict[str, str], token: int) -> int:
    base = _base(api_world["tenant_id"], api_world["plan_id"])
    included = client.post(
        f"{base}/implementations/{api_world['implementation_id']}",
        headers=headers,
        json={
            "expected_version": token,
            "system_component_id": str(api_world["component_id"]),
        },
    )
    assert included.status_code == 201
    return int(included.json()["concurrency_version"])


def test_ssp_update_requires_expected_version(client, api_world) -> None:
    response = client.put(
        _base(api_world["tenant_id"], api_world["plan_id"]),
        headers=_headers(api_world["subject"]),
        json={
            "title": api_world["title"],
            "control_implementation_description": api_world["description"],
        },
    )

    assert response.status_code == 422


def test_ssp_include_requires_expected_version(client, api_world) -> None:
    response = client.post(
        (
            f"{_base(api_world['tenant_id'], api_world['plan_id'])}"
            f"/implementations/{api_world['implementation_id']}"
        ),
        headers=_headers(api_world["subject"]),
        json={"system_component_id": str(api_world["component_id"])},
    )

    assert response.status_code == 422


def test_ssp_publish_requires_expected_version(client, api_world) -> None:
    response = client.post(
        f"{_base(api_world['tenant_id'], api_world['plan_id'])}/versions",
        headers=_headers(api_world["subject"]),
        json={},
    )

    assert response.status_code == 422


def test_ssp_membership_endpoints_return_token_and_stale_409(client, api_world) -> None:
    headers = _headers(api_world["subject"])
    base = _base(api_world["tenant_id"], api_world["plan_id"])

    current = client.get(base, headers=headers)
    assert current.status_code == 200
    token = current.json()["concurrency_version"]

    included = client.post(
        f"{base}/implementations/{api_world['implementation_id']}",
        headers=headers,
        json={
            "expected_version": token,
            "system_component_id": str(api_world["component_id"]),
        },
    )
    assert included.status_code == 201
    included_body = included.json()
    assert included_body["concurrency_version"] == token + 1

    stale_remove = client.delete(
        f"{base}/implementations/{api_world['implementation_id']}?expected_version={token}",
        headers=headers,
    )
    assert stale_remove.status_code == 409
    assert stale_remove.json()["detail"] == {
        "code": "stale_update",
        "plan_id": str(api_world["plan_id"]),
        "expected_version": token,
        "current_version": token + 1,
    }

    removed = client.delete(
        f"{base}/implementations/{api_world['implementation_id']}?expected_version={token + 1}",
        headers=headers,
    )
    assert removed.status_code == 200
    assert removed.json() == {"concurrency_version": token + 2}


def test_ssp_publish_then_save_uses_returned_token_without_false_conflict(
    client, api_world
) -> None:
    headers = _headers(api_world["subject"])
    base = _base(api_world["tenant_id"], api_world["plan_id"])

    current = client.get(base, headers=headers)
    assert current.status_code == 200
    token = current.json()["concurrency_version"]
    token = _include(api_world, client, headers, token)

    published = client.post(
        f"{base}/versions",
        headers=headers,
        json={"expected_version": token},
    )
    assert published.status_code == 201
    publish_body = published.json()
    assert publish_body["concurrency_version"] == token + 1

    saved = client.put(
        base,
        headers=headers,
        json={
            "expected_version": publish_body["concurrency_version"],
            "title": "post-publish save",
            "control_implementation_description": api_world["description"],
        },
    )
    assert saved.status_code == 200


def test_ssp_stale_publish_creates_no_additional_snapshot(client, api_world) -> None:
    headers = _headers(api_world["subject"])
    base = _base(api_world["tenant_id"], api_world["plan_id"])

    current = client.get(base, headers=headers)
    token = current.json()["concurrency_version"]
    token = _include(api_world, client, headers, token)

    first = client.post(
        f"{base}/versions",
        headers=headers,
        json={"expected_version": token},
    )
    assert first.status_code == 201
    first_id = first.json()["id"]

    stale = client.post(
        f"{base}/versions",
        headers=headers,
        json={"expected_version": token},
    )
    assert stale.status_code == 409

    listed = client.get(f"{base}/versions", headers=headers)
    assert listed.status_code == 200
    versions = listed.json()
    assert len(versions) == 1
    assert versions[0]["id"] == first_id


