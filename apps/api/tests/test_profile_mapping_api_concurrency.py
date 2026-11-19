# SPDX-License-Identifier: Apache-2.0
# Copyright The Collaborative OSCAL Authors.

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api import dependencies
from app.application.catalog_import import CatalogImportService
from app.config import get_settings
from app.persistence.database import create_session_factory
from app.persistence.identity import SQLIdentityRepository, SQLMembershipRepository
from app.persistence.models import CatalogControlIndexRecord
from app.persistence.repositories import SQLAlchemyUnitOfWork

pytestmark = pytest.mark.integration

ISSUER = "https://identity.example.test/realms/test"
EXAMPLES = Path(__file__).parents[3] / "examples" / "catalogs"


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
    tenant = grc_service.create_tenant("PM API tenant", f"pm-api-{suffix}")
    subject = f"pm-api-user-{suffix}"
    with session_factory.begin() as session:
        identity = SQLIdentityRepository(session).get_or_create(
            issuer=ISSUER,
            subject=subject,
            display_name="Profile Mapping API Tester",
            email=None,
        )
        SQLMembershipRepository(session).assign(
            tenant_id=tenant.id,
            user_id=identity.id,
            role="catalog_editor",
            status="active",
        )

    importer = CatalogImportService(lambda: SQLAlchemyUnitOfWork(session_factory))
    source = importer.import_catalog(
        tenant.id,
        (EXAMPLES / "sample-security-practices.json").read_bytes(),
    )
    target = importer.import_catalog(
        tenant.id,
        (EXAMPLES / "sample-data-handling.json").read_bytes(),
    )

    with session_factory.begin() as session:
        source_control = session.scalars(
            select(CatalogControlIndexRecord.oscal_control_id)
            .where(
                CatalogControlIndexRecord.tenant_id == tenant.id,
                CatalogControlIndexRecord.catalog_revision_id == source.revision.id,
            )
            .order_by(CatalogControlIndexRecord.oscal_control_id)
        ).first()
        target_control = session.scalars(
            select(CatalogControlIndexRecord.oscal_control_id)
            .where(
                CatalogControlIndexRecord.tenant_id == tenant.id,
                CatalogControlIndexRecord.catalog_revision_id == target.revision.id,
            )
            .order_by(CatalogControlIndexRecord.oscal_control_id)
        ).first()
    assert source_control is not None
    assert target_control is not None

    yield {
        "tenant_id": tenant.id,
        "subject": subject,
        "source_catalog_id": source.catalog.id,
        "source_revision_id": source.revision.id,
        "source_control": source_control,
        "target_catalog_id": target.catalog.id,
        "target_revision_id": target.revision.id,
        "target_control": target_control,
    }

    get_settings.cache_clear()
    create_session_factory.cache_clear()


@pytest.fixture
def client(api_world):
    from app.main import app

    return TestClient(app)


def _headers(subject: str) -> dict[str, str]:
    return {"Authorization": f"Bearer token-{subject}"}


def test_profile_update_requires_expected_version(client, api_world) -> None:
    tenant_id = api_world["tenant_id"]
    headers = _headers(api_world["subject"])
    created = client.post(
        f"/api/v1/tenants/{tenant_id}/profiles",
        headers=headers,
        json={
            "catalog_id": str(api_world["source_catalog_id"]),
            "revision_id": str(api_world["source_revision_id"]),
            "title": "API profile",
            "control_ids": [api_world["source_control"]],
        },
    )
    assert created.status_code == 201
    profile = created.json()

    update = client.put(
        f"/api/v1/tenants/{tenant_id}/profiles/{profile['id']}",
        headers=headers,
        json={
            "title": "API profile updated",
            "control_ids": [api_world["source_control"]],
        },
    )
    assert update.status_code == 422


def test_profile_update_returns_stale_409_and_preserves_state(client, api_world) -> None:
    tenant_id = api_world["tenant_id"]
    headers = _headers(api_world["subject"])
    created = client.post(
        f"/api/v1/tenants/{tenant_id}/profiles",
        headers=headers,
        json={
            "catalog_id": str(api_world["source_catalog_id"]),
            "revision_id": str(api_world["source_revision_id"]),
            "title": "Stale profile",
            "control_ids": [api_world["source_control"]],
        },
    )
    assert created.status_code == 201
    profile = created.json()

    updated = client.put(
        f"/api/v1/tenants/{tenant_id}/profiles/{profile['id']}",
        headers=headers,
        json={
            "expected_version": profile["concurrency_version"],
            "title": "Updated profile",
            "control_ids": [api_world["source_control"]],
        },
    )
    assert updated.status_code == 200
    token = updated.json()["concurrency_version"]

    before_stale = client.get(
        f"/api/v1/tenants/{tenant_id}/profiles/{profile['id']}/export",
        headers=headers,
    ).json()

    stale = client.put(
        f"/api/v1/tenants/{tenant_id}/profiles/{profile['id']}",
        headers=headers,
        json={
            "expected_version": profile["concurrency_version"],
            "title": "stale",
            "control_ids": [api_world["source_control"]],
        },
    )
    assert stale.status_code == 409
    assert stale.json()["detail"] == {
        "code": "stale_update",
        "profile_id": profile["id"],
        "expected_version": profile["concurrency_version"],
        "current_version": token,
    }

    after_stale = client.get(
        f"/api/v1/tenants/{tenant_id}/profiles/{profile['id']}/export",
        headers=headers,
    ).json()
    assert after_stale == before_stale


def _create_mapping_collection(
    client: TestClient,
    api_world: dict[str, object],
) -> dict[str, object]:
    tenant_id = api_world["tenant_id"]
    headers = _headers(api_world["subject"])
    response = client.post(
        f"/api/v1/tenants/{tenant_id}/mapping-collections",
        headers=headers,
        json={
            "title": "API mapping",
            "description": "Test",
            "mappings": [
                {
                    "source_catalog_id": str(api_world["source_catalog_id"]),
                    "source_revision_id": str(api_world["source_revision_id"]),
                    "target_catalog_id": str(api_world["target_catalog_id"]),
                    "target_revision_id": str(api_world["target_revision_id"]),
                    "entries": [
                        {
                            "sources": [api_world["source_control"]],
                            "targets": [api_world["target_control"]],
                            "relationship": "equivalent-to",
                            "matching_rationale": "semantic",
                            "justification": "test",
                        }
                    ],
                }
            ],
        },
    )
    assert response.status_code == 201
    return response.json()


def _mapping_update_payload(
    api_world: dict[str, object],
    *,
    expected_version: int,
) -> dict[str, object]:
    return {
        "expected_version": expected_version,
        "title": "API mapping updated",
        "description": "Test update",
        "mappings": [
            {
                "source_catalog_id": str(api_world["source_catalog_id"]),
                "source_revision_id": str(api_world["source_revision_id"]),
                "target_catalog_id": str(api_world["target_catalog_id"]),
                "target_revision_id": str(api_world["target_revision_id"]),
                "entries": [
                    {
                        "sources": [api_world["source_control"]],
                        "targets": [api_world["target_control"]],
                        "relationship": "subset-of",
                        "matching_rationale": "functional",
                        "justification": "updated",
                    }
                ],
            }
        ],
    }


def test_mapping_update_and_delete_require_expected_version(client, api_world) -> None:
    tenant_id = api_world["tenant_id"]
    headers = _headers(api_world["subject"])
    collection = _create_mapping_collection(client, api_world)

    update = client.put(
        f"/api/v1/tenants/{tenant_id}/mapping-collections/{collection['id']}",
        headers=headers,
        json={
            "title": "missing token",
            "description": "desc",
            "mappings": [
                {
                    "source_catalog_id": str(api_world["source_catalog_id"]),
                    "source_revision_id": str(api_world["source_revision_id"]),
                    "target_catalog_id": str(api_world["target_catalog_id"]),
                    "target_revision_id": str(api_world["target_revision_id"]),
                    "entries": [
                        {
                            "sources": [api_world["source_control"]],
                            "targets": [api_world["target_control"]],
                            "relationship": "equivalent-to",
                            "matching_rationale": "semantic",
                            "justification": "test",
                        }
                    ],
                }
            ],
        },
    )
    assert update.status_code == 422

    delete = client.delete(
        f"/api/v1/tenants/{tenant_id}/mapping-collections/{collection['id']}",
        headers=headers,
    )
    assert delete.status_code == 422


def test_mapping_stale_update_and_delete_preserve_collection(client, api_world) -> None:
    tenant_id = api_world["tenant_id"]
    headers = _headers(api_world["subject"])
    collection = _create_mapping_collection(client, api_world)
    token = int(collection["concurrency_version"])

    updated = client.put(
        f"/api/v1/tenants/{tenant_id}/mapping-collections/{collection['id']}",
        headers=headers,
        json=_mapping_update_payload(api_world, expected_version=token),
    )
    assert updated.status_code == 200
    next_token = int(updated.json()["concurrency_version"])

    before_stale = client.get(
        f"/api/v1/tenants/{tenant_id}/mapping-collections/{collection['id']}",
        headers=headers,
    ).json()

    stale_update = client.put(
        f"/api/v1/tenants/{tenant_id}/mapping-collections/{collection['id']}",
        headers=headers,
        json=_mapping_update_payload(api_world, expected_version=token),
    )
    assert stale_update.status_code == 409
    assert stale_update.json()["detail"] == {
        "code": "stale_update",
        "collection_id": collection["id"],
        "expected_version": token,
        "current_version": next_token,
    }

    stale_delete = client.delete(
        f"/api/v1/tenants/{tenant_id}/mapping-collections/{collection['id']}?expected_version={token}",
        headers=headers,
    )
    assert stale_delete.status_code == 409
    assert stale_delete.json()["detail"] == {
        "code": "stale_update",
        "collection_id": collection["id"],
        "expected_version": token,
        "current_version": next_token,
    }

    after_stale = client.get(
        f"/api/v1/tenants/{tenant_id}/mapping-collections/{collection['id']}",
        headers=headers,
    )
    assert after_stale.status_code == 200
    assert after_stale.json() == before_stale

    deleted = client.delete(
        f"/api/v1/tenants/{tenant_id}/mapping-collections/{collection['id']}?expected_version={next_token}",
        headers=headers,
    )
    assert deleted.status_code == 204

    missing = client.get(
        f"/api/v1/tenants/{tenant_id}/mapping-collections/{collection['id']}",
        headers=headers,
    )
    assert missing.status_code == 404

