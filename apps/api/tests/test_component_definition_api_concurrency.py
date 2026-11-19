# SPDX-License-Identifier: Apache-2.0
# Copyright The Collaborative OSCAL Authors.

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api import dependencies
from app.config import get_settings
from app.domain.catalogs.models import CatalogOriginType
from app.persistence.database import create_session_factory
from app.persistence.identity import SQLIdentityRepository, SQLMembershipRepository

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
    tenant = grc_service.create_tenant("Component API tenant", f"component-api-{suffix}")
    subject = f"component-api-user-{suffix}"
    with session_factory.begin() as session:
        identity = SQLIdentityRepository(session).get_or_create(
            issuer=ISSUER,
            subject=subject,
            display_name="Component API Tester",
            email=None,
        )
        SQLMembershipRepository(session).assign(
            tenant_id=tenant.id,
            user_id=identity.id,
            role="catalog_editor",
            status="active",
        )

    catalog = grc_service.create_catalog(tenant.id, "API baseline", CatalogOriginType.CUSTOM)
    revision = grc_service.create_draft_catalog_revision(
        tenant.id,
        catalog.id,
        json.loads(FIXTURE_PATH.read_text()),
    )

    yield {
        "tenant_id": tenant.id,
        "subject": subject,
        "catalog_id": catalog.id,
        "revision_id": revision.id,
    }

    get_settings.cache_clear()
    create_session_factory.cache_clear()


@pytest.fixture
def client(api_world):
    from app.main import app

    return TestClient(app)


def _headers(subject: str) -> dict[str, str]:
    return {"Authorization": f"Bearer token-{subject}"}


def _create_document(client: TestClient, api_world: dict[str, object]) -> dict:
    tenant_id = api_world["tenant_id"]
    created = client.post(
        f"/api/v1/tenants/{tenant_id}/component-definitions",
        headers=_headers(api_world["subject"]),
        json={
            "title": "Security document",
            "type": "policy",
            "description": "Reusable guidance",
            "requirements": [
                {
                    "catalog_id": str(api_world["catalog_id"]),
                    "revision_id": str(api_world["revision_id"]),
                    "control_id": "ac-1",
                    "description": "Require MFA.",
                }
            ],
        },
    )
    assert created.status_code == 201
    return created.json()


def _update_payload(document: dict, *, expected_version: int, title: str) -> dict:
    return {
        "expected_version": expected_version,
        "title": title,
        "components": [
            {
                "id": component["id"],
                "type": component["type"],
                "title": component["title"],
                "description": component["description"],
                "requirements": component["requirements"],
            }
            for component in document["components"]
        ],
    }


def test_component_definition_update_and_delete_require_expected_version(client, api_world) -> None:
    tenant_id = api_world["tenant_id"]
    headers = _headers(api_world["subject"])
    created = _create_document(client, api_world)

    update = client.put(
        f"/api/v1/tenants/{tenant_id}/component-definitions/{created['id']}",
        headers=headers,
        json={
            "title": "missing token",
            "components": [
                {
                    "id": created["components"][0]["id"],
                    "type": created["components"][0]["type"],
                    "title": created["components"][0]["title"],
                    "description": created["components"][0]["description"],
                    "requirements": created["components"][0]["requirements"],
                }
            ],
        },
    )
    assert update.status_code == 422

    delete_document = client.delete(
        f"/api/v1/tenants/{tenant_id}/component-definitions/{created['id']}",
        headers=headers,
    )
    assert delete_document.status_code == 422

    delete_component = client.delete(
        (
            f"/api/v1/tenants/{tenant_id}/component-definitions/{created['id']}"
            f"/components/{created['components'][0]['id']}"
        ),
        headers=headers,
    )
    assert delete_component.status_code == 422


def test_component_definition_delete_component_response_contract(client, api_world) -> None:
    tenant_id = api_world["tenant_id"]
    headers = _headers(api_world["subject"])
    created = _create_document(client, api_world)

    expanded = client.put(
        f"/api/v1/tenants/{tenant_id}/component-definitions/{created['id']}",
        headers=headers,
        json={
            "expected_version": created["concurrency_version"],
            "title": created["title"],
            "components": [
                {
                    "id": created["components"][0]["id"],
                    "type": created["components"][0]["type"],
                    "title": created["components"][0]["title"],
                    "description": created["components"][0]["description"],
                    "requirements": created["components"][0]["requirements"],
                },
                {
                    "type": "software",
                    "title": "Audit logging",
                    "description": "Capture events.",
                    "requirements": [],
                },
            ],
        },
    )
    assert expanded.status_code == 200
    expanded_body = expanded.json()
    assert len(expanded_body["components"]) == 2

    removed_component = client.delete(
        (
            f"/api/v1/tenants/{tenant_id}/component-definitions/{created['id']}"
            f"/components/{created['components'][0]['id']}"
            f"?expected_version={expanded_body['concurrency_version']}"
        ),
        headers=headers,
    )
    assert removed_component.status_code == 200
    remaining = removed_component.json()
    assert len(remaining["components"]) == 1
    assert remaining["concurrency_version"] == expanded_body["concurrency_version"] + 1

    removed_document = client.delete(
        (
            f"/api/v1/tenants/{tenant_id}/component-definitions/{created['id']}"
            f"/components/{remaining['components'][0]['id']}"
            f"?expected_version={remaining['concurrency_version']}"
        ),
        headers=headers,
    )
    assert removed_document.status_code == 204


def test_component_definition_nested_only_requirement_mutation_advances_concurrency_version(
    client, api_world
) -> None:
    tenant_id = api_world["tenant_id"]
    headers = _headers(api_world["subject"])
    created = _create_document(client, api_world)
    token = int(created["concurrency_version"])

    component = created["components"][0]
    nested_update = client.put(
        f"/api/v1/tenants/{tenant_id}/component-definitions/{created['id']}",
        headers=headers,
        json={
            "expected_version": token,
            "title": created["title"],
            "components": [
                {
                    "id": component["id"],
                    "type": component["type"],
                    "title": component["title"],
                    "description": component["description"],
                    "requirements": [
                        {
                            **component["requirements"][0],
                            "description": "Require MFA and document exception handling.",
                        }
                    ],
                }
            ],
        },
    )
    assert nested_update.status_code == 200
    body = nested_update.json()
    assert int(body["concurrency_version"]) == token + 1
    assert body["title"] == created["title"]
    assert (
        body["components"][0]["requirements"][0]["description"]
        == "Require MFA and document exception handling."
    )


def test_component_definition_stale_update_and_delete_return_409_and_preserve_state(
    client, api_world
) -> None:
    tenant_id = api_world["tenant_id"]
    headers = _headers(api_world["subject"])
    created = _create_document(client, api_world)
    token = int(created["concurrency_version"])

    updated = client.put(
        f"/api/v1/tenants/{tenant_id}/component-definitions/{created['id']}",
        headers=headers,
        json=_update_payload(created, expected_version=token, title="Updated title"),
    )
    assert updated.status_code == 200
    next_version = int(updated.json()["concurrency_version"])

    before_stale = client.get(
        f"/api/v1/tenants/{tenant_id}/component-definitions/{created['id']}",
        headers=headers,
    )
    assert before_stale.status_code == 200

    stale_update = client.put(
        f"/api/v1/tenants/{tenant_id}/component-definitions/{created['id']}",
        headers=headers,
        json=_update_payload(created, expected_version=token, title="stale"),
    )
    assert stale_update.status_code == 409
    assert stale_update.json()["detail"] == {
        "code": "stale_update",
        "document_id": created["id"],
        "expected_version": token,
        "current_version": next_version,
    }

    stale_delete_document = client.delete(
        (
            f"/api/v1/tenants/{tenant_id}/component-definitions/{created['id']}"
            f"?expected_version={token}"
        ),
        headers=headers,
    )
    assert stale_delete_document.status_code == 409
    assert stale_delete_document.json()["detail"] == {
        "code": "stale_update",
        "document_id": created["id"],
        "expected_version": token,
        "current_version": next_version,
    }

    stale_delete_component = client.delete(
        (
            f"/api/v1/tenants/{tenant_id}/component-definitions/{created['id']}"
            f"/components/{created['components'][0]['id']}?expected_version={token}"
        ),
        headers=headers,
    )
    assert stale_delete_component.status_code == 409
    assert stale_delete_component.json()["detail"] == {
        "code": "stale_update",
        "document_id": created["id"],
        "expected_version": token,
        "current_version": next_version,
    }

    after_stale = client.get(
        f"/api/v1/tenants/{tenant_id}/component-definitions/{created['id']}",
        headers=headers,
    )
    assert after_stale.status_code == 200
    assert after_stale.json() == before_stale.json()



