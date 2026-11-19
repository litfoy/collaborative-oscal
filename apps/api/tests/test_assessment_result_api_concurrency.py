from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api import dependencies
from app.application.assessment_plans import AssessmentPlanService
from app.application.assessment_results import AssessmentResultService
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
    tenant = grc_service.create_tenant("AR API tenant", f"ar-api-{suffix}")
    subject = f"ar-api-user-{suffix}"
    with session_factory.begin() as session:
        identity = SQLIdentityRepository(session).get_or_create(
            issuer=ISSUER,
            subject=subject,
            display_name="Assessment Result API Tester",
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
    assessment_plan_service = AssessmentPlanService(lambda: session_factory.begin())
    assessment_result_service = AssessmentResultService(lambda: session_factory.begin())

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
    ssp = ssp_service.create_plan(
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
    included = ssp_service.associate_implementation(
        tenant.id,
        actor_id,
        ssp["id"],
        implementation.id,
        component["id"],
        expected_version=ssp["concurrency_version"],
    )
    ssp["concurrency_version"] = included["concurrency_version"]
    ssp_version = ssp_service.create_version(
        tenant.id,
        actor_id,
        ssp["id"],
        expected_version=ssp["concurrency_version"],
    )

    plan = assessment_plan_service.create_plan(
        tenant.id,
        actor_id,
        system["id"],
        ssp_version_id=ssp_version["id"],
        title="API Assessment Plan",
        description="Concurrency API coverage",
    )
    plan = assessment_plan_service.update_plan(
        tenant.id,
        actor_id,
        plan["id"],
        expected_version=plan["concurrency_version"],
        title=plan["title"],
        description=plan["description"],
        working_data={
            "control_ids": [control_id],
            "source_objectives": [],
            "local_objectives": [
                {
                    "objective_id": "local-mfa-objective",
                    "control_id": control_id,
                    "description": "Validate MFA challenge behavior.",
                    "methods": ["EXAMINE"],
                }
            ],
            "subject_uuids": [str(component["oscal_component_uuid"])],
            "activities": [],
            "tasks": [],
            "roles": [],
            "parties": [],
            "terms": None,
        },
    )
    plan_version = assessment_plan_service.create_version(
        tenant.id,
        actor_id,
        plan["id"],
        expected_version=plan["concurrency_version"],
    )
    other_tenant = grc_service.create_tenant("Other tenant", f"other-{suffix}")

    result = assessment_result_service.create_result(
        tenant.id,
        actor_id,
        system["id"],
        assessment_plan_id=plan["id"],
        assessment_plan_version_id=plan_version["id"],
        title="API Assessment Result",
        description="Concurrency API coverage",
    )
    observation_id = str(uuid4())
    result = assessment_result_service.update_result(
        tenant.id,
        actor_id,
        result["id"],
        expected_version=result["concurrency_version"],
        title=result["title"],
        description=result["description"],
        working_data={
            "reviewed_control_ids": [control_id],
            "start": "2026-11-20T00:00:00+00:00",
            "end": "2026-11-20T01:00:00+00:00",
            "observations": [
                {
                    "id": observation_id,
                    "title": "Observation",
                    "description": "desc",
                    "methods": ["EXAMINE"],
                    "collected_at": "2026-11-20T00:30:00+00:00",
                    "subject_uuids": [str(component["oscal_component_uuid"])],
                    "evidence": [],
                }
            ],
            "findings": [
                {
                    "title": "Supported finding",
                    "description": "desc",
                    "target_type": "objective-id",
                    "target_id": "local-mfa-objective",
                    "status": "satisfied",
                    "related_observation_ids": [observation_id],
                }
            ],
        },
    )

    yield {
        "tenant_id": tenant.id,
        "other_tenant_id": other_tenant.id,
        "subject": subject,
        "result_id": result["id"],
        "plan_id": plan["id"],
        "plan_version_id": plan_version["id"],
        "control_id": control_id,
        "subject_uuid": str(component["oscal_component_uuid"]),
        "title": result["title"],
        "description": result["description"],
        "reviewed_control_ids": result["reviewed_control_ids"],
    }

    get_settings.cache_clear()
    create_session_factory.cache_clear()


@pytest.fixture
def client(api_world):
    from app.main import app

    return TestClient(app)


def _headers(subject: str) -> dict[str, str]:
    return {"Authorization": f"Bearer token-{subject}"}


def _base(tenant_id: UUID, result_id: UUID) -> str:
    return f"/api/v1/tenants/{tenant_id}/assessment-results/{result_id}"


def _working_payload(
    api_world: dict[str, object], *, expected_version: int, title: str
) -> dict[str, object]:
    return {
        "expected_version": expected_version,
        "title": title,
        "description": api_world["description"],
        "reviewed_control_ids": api_world["reviewed_control_ids"],
        "observations": [],
        "findings": [],
        "start": None,
        "end": None,
    }


def _import_base(tenant_id: UUID, plan_id: UUID, plan_version_id: UUID) -> str:
    return (
        f"/api/v1/tenants/{tenant_id}/assessment-plans/{plan_id}/versions/"
        f"{plan_version_id}/assessment-results/import"
    )


def _import_payload(
    api_world: dict[str, object], *, metadata_version: str = "automation-1"
) -> dict:
    evidence_uuid = str(uuid4())
    observation_uuid = str(uuid4())
    return {
        "assessment-results": {
            "uuid": str(uuid4()),
            "metadata": {
                "title": "AI Governance Demo automated submission",
                "last-modified": "2026-11-19T10:00:00+00:00",
                "version": metadata_version,
                "oscal-version": "1.2.1",
            },
            "import-ap": {
                "href": (
                    f"/api/v1/tenants/{api_world['tenant_id']}/assessment-plans/"
                    f"{api_world['plan_id']}/versions/{api_world['plan_version_id']}/export"
                )
            },
            "results": [
                {
                    "uuid": str(uuid4()),
                    "title": "Automated result",
                    "description": "Automated scanner output for MFA objectives.",
                    "reviewed-controls": {
                        "control-selections": [
                            {"include-controls": [{"control-id": api_world["control_id"]}]}
                        ]
                    },
                    "start": "2026-11-19T09:00:00+00:00",
                    "end": "2026-11-19T09:30:00+00:00",
                    "observations": [
                        {
                            "uuid": observation_uuid,
                            "title": "Automated observation",
                            "description": "Tool telemetry observation.",
                            "methods": ["TEST"],
                            "collected": "2026-11-19T09:25:00+00:00",
                            "subjects": [
                                {
                                    "type": "component",
                                    "subject-uuid": api_world["subject_uuid"],
                                }
                            ],
                            "relevant-evidence": [
                                {
                                    "href": f"#{evidence_uuid}",
                                    "description": "Automated scan evidence.",
                                }
                            ],
                        }
                    ],
                    "findings": [
                        {
                            "uuid": str(uuid4()),
                            "title": "Automated finding",
                            "description": "Objective satisfied.",
                            "target": {
                                "type": "objective-id",
                                "target-id": "local-mfa-objective",
                                "status": {"state": "satisfied"},
                            },
                            "related-observations": [
                                {"observation-uuid": observation_uuid}
                            ],
                        }
                    ],
                }
            ],
            "back-matter": {
                "resources": [
                    {
                        "uuid": evidence_uuid,
                        "title": "Automation evidence",
                        "description": "Automated scan evidence.",
                        "rlinks": [{"href": "https://example.test/evidence/automation.json"}],
                    }
                ]
            },
        }
    }


def test_assessment_result_update_requires_expected_version(client, api_world) -> None:
    payload = {
        "title": api_world["title"],
        "description": api_world["description"],
        "reviewed_control_ids": api_world["reviewed_control_ids"],
        "observations": [],
        "findings": [],
        "start": None,
        "end": None,
    }
    response = client.put(
        _base(api_world["tenant_id"], api_world["result_id"]),
        headers=_headers(api_world["subject"]),
        json=payload,
    )

    assert response.status_code == 422


def test_assessment_result_publish_requires_expected_version(client, api_world) -> None:
    response = client.post(
        f"{_base(api_world['tenant_id'], api_world['result_id'])}/versions",
        headers=_headers(api_world["subject"]),
        json={},
    )

    assert response.status_code == 422


def test_assessment_result_endpoints_return_stale_409_with_stable_detail(client, api_world) -> None:
    headers = _headers(api_world["subject"])
    base = _base(api_world["tenant_id"], api_world["result_id"])

    current = client.get(base, headers=headers)
    assert current.status_code == 200
    token = current.json()["concurrency_version"]

    updated = client.put(
        base,
        headers=headers,
        json=_working_payload(api_world, expected_version=token, title="API Assessment Result v2"),
    )
    assert updated.status_code == 200

    stale = client.put(
        base,
        headers=headers,
        json=_working_payload(api_world, expected_version=token, title="stale"),
    )
    assert stale.status_code == 409
    assert stale.json()["detail"] == {
        "code": "stale_update",
        "result_id": str(api_world["result_id"]),
        "expected_version": token,
        "current_version": token + 1,
    }


def test_publish_then_save_uses_returned_token_without_false_conflict(client, api_world) -> None:
    headers = _headers(api_world["subject"])
    base = _base(api_world["tenant_id"], api_world["result_id"])

    current = client.get(base, headers=headers)
    assert current.status_code == 200
    token = current.json()["concurrency_version"]

    published = client.post(
        f"{base}/versions",
        headers=headers,
        json={"expected_version": token},
    )
    assert published.status_code == 201
    published_body = published.json()
    assert published_body["concurrency_version"] == token + 1

    saved = client.put(
        base,
        headers=headers,
        json=_working_payload(
            api_world,
            expected_version=published_body["concurrency_version"],
            title="post-publish save",
        ),
    )
    assert saved.status_code == 200


def test_stale_publish_creates_no_additional_snapshot(client, api_world) -> None:
    headers = _headers(api_world["subject"])
    base = _base(api_world["tenant_id"], api_world["result_id"])

    current = client.get(base, headers=headers)
    token = current.json()["concurrency_version"]

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


def test_assessment_result_import_endpoint_supports_create_and_replay(client, api_world) -> None:
    headers = _headers(api_world["subject"])
    path = _import_base(api_world["tenant_id"], api_world["plan_id"], api_world["plan_version_id"])
    payload = _import_payload(api_world)

    created = client.post(path, headers=headers, json=payload)
    assert created.status_code == 201, created.json()
    created_id = created.json()["id"]

    replay = client.post(path, headers=headers, json=payload)
    assert replay.status_code == 200
    assert replay.json()["id"] == created_id


def test_assessment_result_import_endpoint_returns_409_for_conflicting_replay(
    client, api_world
) -> None:
    headers = _headers(api_world["subject"])
    path = _import_base(api_world["tenant_id"], api_world["plan_id"], api_world["plan_version_id"])
    payload = _import_payload(api_world, metadata_version="automation-2")
    payload["assessment-results"]["uuid"] = str(uuid4())

    created = client.post(path, headers=headers, json=payload)
    assert created.status_code == 201, created.json()

    conflicting = json.loads(json.dumps(payload))
    conflicting["assessment-results"]["metadata"]["version"] = "automation-3"
    replay = client.post(path, headers=headers, json=conflicting)
    assert replay.status_code == 409
    assert replay.json()["detail"]["code"] == "import_conflict"
    assert replay.json()["detail"]["reason"] == "content_mismatch"


def test_assessment_result_import_endpoint_requires_authentication(client, api_world) -> None:
    path = _import_base(api_world["tenant_id"], api_world["plan_id"], api_world["plan_version_id"])
    response = client.post(path, json=_import_payload(api_world))
    assert response.status_code == 401


def test_assessment_result_import_endpoint_enforces_tenant_isolation(client, api_world) -> None:
    headers = _headers(api_world["subject"])
    path = _import_base(
        api_world["other_tenant_id"],
        api_world["plan_id"],
        api_world["plan_version_id"],
    )
    response = client.post(path, headers=headers, json=_import_payload(api_world))
    assert response.status_code == 403



